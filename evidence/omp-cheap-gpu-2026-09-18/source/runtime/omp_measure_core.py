#!/usr/bin/env python3
"""Engine-agnostic protocol-v2 measurement core.

The per-request validation, client-side monotonic timestamps, cached_tokens
index-alignment, raw per-request retention and record assembly are IDENTICAL to
the frozen SGLang client (scripts/omp_bench_client.py); they live here so a
second engine (TabbyAPI/ExLlamaV3) reuses exactly the same measurement contract
instead of a divergent copy. An engine supplies only three hooks:

  dispatch(index) -> result   one streamed request for request `index`; returns
                              the dict `stream_completion` produces.
  prime()         -> result   optional unmeasured warm-cache prime (identical
                              prompt), fired before a measured warm wave.
  reset()         -> (ok,det) optional backend cache reset for a verified-cold
                              wave; engines without a flush endpoint pass None
                              and rely on OBSERVED cached_tokens==0 per request.

This module is import-only; it is not a runnable client. The SGLang client's
migration onto it is staged separately (it stays frozen until its pod finishes);
until then the two share this contract by construction, never by duplication.
"""
from __future__ import annotations

import json
import statistics
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable

STEADY_STATE_WAVES = 5


def post_stream(url: str, payload: dict, timeout: float):
    """POST `payload` and return the streaming response object (SSE lines)."""
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"content-type": "application/json"},
        method="POST",
    )
    return urllib.request.urlopen(request, timeout=timeout)


def stream_completion(url: str, payload: dict, timeout: float) -> dict:
    """One streamed OpenAI /v1/completions request with client monotonic timing.

    Engine-agnostic: the caller builds `payload` (SGLang token-id prompt +
    ignore_eos, or TabbyAPI string prompt + min_tokens). Timestamps are captured
    on the client's monotonic clock, never trusted from the server.
    """
    t_dispatch = time.monotonic()
    t_first: float | None = None
    last = t_dispatch
    itl: list[float] = []
    text_parts: list[str] = []
    usage: dict | None = None
    finish_reason: str | None = None
    error = ""
    try:
        response = post_stream(url, payload, timeout)
        for raw in response:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            data = line[len("data:"):].strip()
            if data == "[DONE]":
                break
            chunk = json.loads(data)
            if chunk.get("usage"):
                usage = chunk["usage"]
            choices = chunk.get("choices") or []
            if not choices:
                continue
            if choices[0].get("finish_reason"):
                finish_reason = choices[0]["finish_reason"]
            text = choices[0].get("text") or ""
            if not text:
                continue
            text_parts.append(text)
            now = time.monotonic()
            if t_first is None:
                t_first = now
            else:
                itl.append(now - last)
            last = now
    except Exception as exc:  # network/HTTP/parse — recorded, never raised
        error = type(exc).__name__
    return {
        "t_dispatch": t_dispatch,
        "t_first": t_first,
        "t_last": last,
        "itl": itl,
        "usage": usage or {},
        "finish_reason": finish_reason,
        "completion_text": "".join(text_parts),
        "error": error,
    }


def sglang_flush_cache(base_url: str, timeout: float) -> tuple[bool, str]:
    """SGLang-specific /flush_cache reset for a verified-cold wave.

    Matches SGLang's ACTUAL success contract, not a general cross-engine rule:
    SGLang's http_server /flush_cache returns HTTP 200 on success, and v0.5.19's
    200 SUCCESS body includes a static 'will not be performed' warning that does
    NOT indicate refusal. The frozen SG client's substring check therefore falsely
    records a successful reset as refused; here HTTP 200 is success and any
    non-200 is a real refusal/error. Cold validity rests on the OBSERVED
    cached_tokens==0 witness, never on this marker alone; None is never made 0.
    This is the staged SGLang engine's reset() hook ONLY; TabbyAPI has NO flush
    endpoint and passes reset=None.
    """
    try:
        request = urllib.request.Request(
            base_url.rstrip("/") + "/flush_cache", data=b"", method="POST")
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = getattr(response, "status", response.getcode())
        return (True, "flush_cache") if status == 200 else (False, f"flush refused: HTTP {status}")
    except urllib.error.HTTPError as exc:
        return False, f"flush refused: HTTP {exc.code}"
    except Exception as exc:
        return False, f"flush_cache unavailable: {type(exc).__name__}"


def _usage_cached(usage: dict):
    """cached_tokens for one request: the server value, or None when omitted.

    Both engines expose OpenAI prompt_tokens_details.cached_tokens (SGLang with
    --enable-cache-report; TabbyAPI always, PromptTokensDetails default 0). None
    is never coerced to 0: a missing value means the wave's cache state cannot be
    verified for that request.
    """
    details = usage.get("prompt_tokens_details") or {}
    if "cached_tokens" in details:
        return int(details["cached_tokens"] or 0)
    return None


def _mtp(usage: dict):
    """Speculative (MTP) counters when the engine reports them, else None.

    OpenAI Predicted-Outputs shape: completion_tokens_details.accepted /
    rejected_prediction_tokens. Reported as-is; 0/0 stays 0/0 (undefined rate),
    never a fabricated acceptance percentage.
    """
    details = usage.get("completion_tokens_details") or {}
    if "accepted_prediction_tokens" in details or "rejected_prediction_tokens" in details:
        return {
            "accepted": int(details.get("accepted_prediction_tokens") or 0),
            "rejected": int(details.get("rejected_prediction_tokens") or 0),
        }
    return None


def run_wave(
    prompt_tokens: int,
    max_tokens: int,
    concurrency: int,
    request_count: int,
    dispatch: Callable[[int], dict],
    prime: Callable[[], dict] | None = None,
    reset: Callable[[], tuple[bool, str]] | None = None,
    backend: str = "omp-measure-core",
    stop_event: "threading.Event | None" = None,
    stop_grace_s: float = 10.0,
) -> dict:
    """Fire `request_count` requests through a `concurrency`-wide gate and fold
    them into one detail record with the frozen protocol-v2 contract.

    Every MEASURED request is validated against the requested horizon: the server
    must REPORT a prompt length equal to `prompt_tokens`, a completion length
    equal to `max_tokens`, finish_reason "length", and usable monotonic
    timestamps. A missing field is measurement-invalid, never fabricated. Raw
    per-request timestamps + usage + finish_reason and the wave's monotonic bounds
    are retained. cached_tokens is index-aligned (None where the backend omits it,
    never a neighbour's value).
    """
    results: list[dict | None] = [None] * request_count
    dispatched: list[bool] = [False] * request_count
    gate = threading.Semaphore(concurrency)

    def worker(index: int) -> None:
        # Graceful bounded stop (SIGTERM/timeout): a worker still waiting on the
        # concurrency gate when the stop fires never dispatches a new request, so
        # already-completed requests are preserved and no phantom request is sent
        # after the deadline. In-flight requests finish on their own.
        if stop_event is not None and stop_event.is_set():
            return
        with gate:
            if stop_event is not None and stop_event.is_set():
                return
            dispatched[index] = True
            results[index] = dispatch(index)

    # Daemon workers: a straggler still blocked in a stalled in-flight HTTP read
    # when the grace expires must NOT keep the process alive - we snapshot the
    # completed requests and let the interpreter exit; the OS reaps the socket.
    threads = [threading.Thread(target=worker, args=(i,), daemon=True)
               for i in range(request_count)]

    cache_reset = None
    cache_reset_error = None
    if reset is not None:
        flushed, detail = reset()
        cache_reset = "flush_cache" if flushed else None
        if not flushed:
            cache_reset_error = detail

    prime_evidence = None
    if prime is not None:
        primed = prime()
        p_usage = primed["usage"]
        p_ttft = (primed["t_first"] - primed["t_dispatch"]) if primed["t_first"] is not None else None
        prime_evidence = {
            "measured": False,
            "note": "unmeasured warm cache prime; identical prompt; excluded from all wave stats",
            # Deliberate normalisation: the frozen SG client recorded the prime's
            # cache as p_details.get("cached_tokens") (None on an explicit-null
            # server); _usage_cached coerces that lone case to 0, matching the
            # measured path's own "or 0". The prime is unmeasured and excluded from
            # every statistic, so this has no statistical effect - it only makes the
            # prime consistent with the requests, never diverging from them.
            "cached_tokens": _usage_cached(p_usage),
            "output_len": p_usage.get("completion_tokens"),
            "ttft_s": round(p_ttft, 4) if p_ttft is not None else None,
            "error": primed["error"] or None,
        }

    wave_start = time.monotonic()
    for thread in threads:
        thread.start()
    # Poll the workers rather than issuing an unbounded join: an unbounded
    # thread.join() on a stalled in-flight request blocks the MAIN thread in a C
    # call, so a pending SIGTERM handler never runs and the stop is never seen.
    # Polling with a short timeout lets the handler run between joins; once the
    # graceful stop fires, the remaining wait is bounded by stop_grace_s so the
    # fold+persist of completed requests happens BEFORE the controller force-kills
    # - a request still stalled past the grace is abandoned (its slot stays
    # incomplete), never a fabricated completion, never a blocked process exit.
    grace_deadline = None
    for thread in threads:
        while thread.is_alive():
            if stop_event is not None and stop_event.is_set():
                if grace_deadline is None:
                    grace_deadline = time.monotonic() + max(0.0, stop_grace_s)
                remaining = grace_deadline - time.monotonic()
                if remaining <= 0:
                    break
                thread.join(timeout=min(remaining, 0.2))
            else:
                thread.join(timeout=0.2)
        if grace_deadline is not None and time.monotonic() >= grace_deadline:
            break
    wave_end = time.monotonic()
    duration = wave_end - wave_start

    ttfts: list[float | None] = []
    itls: list[list[float]] = []
    start_times: list[float | None] = []
    output_lens: list[int | None] = []
    input_lens: list[int | None] = []
    cached_tokens: list[int | None] = []
    queue_times: list[float | None] = []
    errors: list[str] = []
    raw_requests: list[dict | None] = []
    mtp_counters: list[dict | None] = []
    base = min((r["t_dispatch"] for r in results if r), default=wave_start)
    stopped = stop_event is not None and stop_event.is_set()
    for index, result in enumerate(results):
        if result is None:
            # A request the graceful stop kept from ever dispatching is NOT a
            # measurement failure and NOT a phantom send; it marks the wave
            # incomplete. A None while NOT stopped is a genuine no-result.
            errors.append(
                "interrupted-not-dispatched" if stopped and not dispatched[index]
                else "interrupted-in-flight" if stopped and dispatched[index]
                else "no-result")
            input_lens.append(None)
            output_lens.append(None)
            start_times.append(None)
            queue_times.append(None)
            ttfts.append(None)
            itls.append([])
            cached_tokens.append(None)
            raw_requests.append(None)
            mtp_counters.append(None)
            continue
        usage = result["usage"]
        completion = usage.get("completion_tokens")
        observed_prompt = usage.get("prompt_tokens")
        finish_reason = result.get("finish_reason")
        t_dispatch = result["t_dispatch"]
        t_first = result["t_first"]
        t_last = result["t_last"]
        timestamps_ok = (
            t_first is not None and t_last is not None
            and t_first >= t_dispatch and t_last >= t_first
        )
        error = result["error"]
        if not error:
            if observed_prompt is None:
                error = "prompt_tokens_missing"
            elif int(observed_prompt) != prompt_tokens:
                error = "prompt_token_mismatch"
            elif completion is None:
                error = "completion_tokens_missing"
            elif int(completion) != max_tokens:
                error = "output_len_below_horizon"
            elif finish_reason != "length":
                error = "finish_reason_not_length"
            elif not timestamps_ok:
                error = "timestamps_unusable"
        errors.append(error)
        input_lens.append(int(observed_prompt) if observed_prompt is not None else None)
        output_lens.append(int(completion) if completion is not None else None)
        start_times.append(t_dispatch - base)
        queue_times.append(t_dispatch - wave_start)
        ttfts.append((t_first - t_dispatch) if t_first is not None else None)
        itls.append(result["itl"])
        cached_tokens.append(_usage_cached(usage))
        mtp_counters.append(_mtp(usage))
        raw_requests.append({
            "t_dispatch": t_dispatch,
            "t_first": t_first,
            "t_last": t_last,
            "usage": usage,
            "finish_reason": finish_reason,
            "error": error or None,
        })
    valid_ttfts = [value for value in ttfts if value is not None]
    total_output = sum(value for value in output_lens if value)
    tpots = [
        sum(itls[index]) / (out_len - 1)
        for index, out_len in enumerate(output_lens)
        if out_len and out_len > 1 and index < len(itls) and sum(itls[index]) > 0
    ]
    record = {
        "backend": backend,
        "completed": sum(1 for error in errors if not error),
        "failed": sum(1 for error in errors if error),
        "errors": errors,
        "input_lens": input_lens,
        "output_lens": output_lens,
        "total_input_tokens": sum(value for value in input_lens if value),
        "total_output_tokens": total_output,
        "ttfts": ttfts,
        "itls": itls,
        "start_times": start_times,
        "queue_times": queue_times,
        "duration": round(duration, 4),
        "wave_start": wave_start,
        "wave_end": wave_end,
        "output_throughput": round(total_output / duration, 3) if duration > 0 else None,
        "mean_ttft_ms": round(statistics.mean(valid_ttfts) * 1000.0, 3) if valid_ttfts else None,
        "mean_tpot_ms": round(statistics.mean(tpots) * 1000.0, 3) if tpots else None,
    }
    record["cached_tokens"] = cached_tokens
    record["requests"] = raw_requests
    record["dispatched"] = sum(dispatched)
    if stopped:
        # The wave was cut short by a graceful stop: completed requests above are
        # real and preserved; the cell is incomplete, never falsely complete.
        record["interrupted"] = True
    if any(mtp_counters):
        record["mtp"] = mtp_counters
    invalid_causes = sorted({error for error in errors if error})
    if invalid_causes:
        record["invalid_causes"] = invalid_causes
    if cache_reset:
        record["cache_reset"] = cache_reset
    elif cache_reset_error:
        record["cache_reset_error"] = cache_reset_error
    if prime_evidence is not None:
        record["prime"] = prime_evidence
    return record
