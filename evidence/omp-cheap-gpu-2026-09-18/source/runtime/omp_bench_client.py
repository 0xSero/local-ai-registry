#!/usr/bin/env python3
"""Engine-agnostic streaming benchmark client with client-side monotonic timing.

Why this exists: reading TTFT/ITL out of `sglang.benchmark.serving` or
`vllm bench serve` gives per-request relative intervals but no absolute dispatch
clock, so the protocol-v2 overlap integral, dispatch skew and queue wait were
stuck at null-with-reason for sglang (§3.4). This driver launches the requests
itself over the OpenAI-compatible /v1/completions streaming endpoint and records
its OWN monotonic timestamps around each stream:

    t_dispatch  - captured immediately before the HTTP send
    t_first     - first streamed token
    t_last      - last streamed token

From those three the metrics layer derives the honest set: end_to_end (the
headline) = output/(t_last - t_dispatch); client_decode = (output-1)/(t_last -
t_first); and the CLIENT-OBSERVED stream overlap (never engine batch). It emits a
record with the same keys sweep_to_benchmark/omp_registry_record already consume
(ttfts, itls, start_times, input_lens, output_lens, duration, ...), plus
per-request cached_tokens when the server returns prompt_tokens_details, so the
cold/warm split is evidence-based (§3.2), not a label.

Exactness (§3.1): the prompt is sent as a verbatim token-id array
("prompt": [int, ...]); both vLLM and SGLang accept token-id prompts on
/v1/completions, so input length is exact without a range ratio.

Stdlib only; runs on the rented pod. This is a protocol-v2 driver: unlike the
legacy detail-file recovery in omp_registry_record.sweep_rows, records produced
here carry absolute timestamps and MAY back a protocol-v2 bench claim once
validated on hardware.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import threading
import time
import urllib.request
from pathlib import Path

MANIFEST_NAME = "manifest.json"
STEADY_STATE_WAVES = 5


def _post_json(url: str, payload: dict, timeout: float):
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"content-type": "application/json"},
        method="POST",
    )
    return urllib.request.urlopen(request, timeout=timeout)


def load_tokenizer(model_dir: str, trust_remote_code: bool):
    """The model's own tokenizer from the mounted pinned revision (no network).

    SGLang exposes no usable server tokenize contract for our purpose (its
    /tokenize ignores add_generation_prompt), so prompts are built locally from
    the mounted model dir - one deterministic model-native path across engines.
    """
    from transformers import AutoTokenizer  # in-image dependency (confirmed by ImageDelivery)
    return AutoTokenizer.from_pretrained(
        model_dir, local_files_only=True, trust_remote_code=trust_remote_code
    )


def build_token_pool(tok, minimum: int) -> list[int]:
    """A pool of at least `minimum` real token ids from the model's own tokenizer.

    The sweep sends these ids verbatim as the prompt (exact length, no range
    ratio). Speed measurement does not need the chat template; raw token-id
    filler is a valid fixed-length prompt.
    """
    filler = (
        "The quick brown fox studies distributed systems while the lazy dog "
        "audits ternary quantization kernels across a long context window. "
    )
    ids = tok.encode(filler * (minimum // 8 + 16), add_special_tokens=False)
    if len(ids) < minimum:
        raise RuntimeError("tokenizer produced too few tokens for the requested window")
    return [int(value) for value in ids[:minimum]]

def flush_cache(base_url: str, timeout: float) -> tuple[bool, str]:
    """Reset the engine's prefix/radix cache for a verified-cold wave.

    SGLang exposes POST /flush_cache (http_server.py). Returns (flushed, detail).
    A refusal ("...will not be performed" when requests are in flight) or any
    error returns False so the caller records the wave as unverified rather than
    assuming a cold cache.
    """
    try:
        request = urllib.request.Request(
            base_url.rstrip("/") + "/flush_cache", data=b"", method="POST"
        )
        response = urllib.request.urlopen(request, timeout=timeout)
        body = response.read().decode("utf-8", "replace")
    except Exception as exc:
        return False, f"flush_cache unavailable: {type(exc).__name__}"
    if "will not be performed" in body:
        return False, "flush refused: running or waiting requests"
    return True, "flush_cache"



def stream_one(
    base_url: str, model: str, prompt_ids: list[int], max_tokens: int, timeout: float
) -> dict:
    """One streamed /v1/completions request with client-side monotonic timing."""
    body = {
        "model": model,
        "prompt": prompt_ids,
        "max_tokens": max_tokens,
        "stream": True,
        "stream_options": {"include_usage": True},
        "temperature": 0.0,
        "ignore_eos": True,
    }
    t_dispatch = time.monotonic()
    t_first: float | None = None
    last = t_dispatch
    itl: list[float] = []
    usage: dict | None = None
    finish_reason: str | None = None
    error = ""
    try:
        response = _post_json(base_url.rstrip("/") + "/v1/completions", body, timeout)
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
        "error": error,
    }


def run_wave(
    base_url: str,
    model: str,
    pool: list[int],
    prompt_tokens: int,
    max_tokens: int,
    concurrency: int,
    request_count: int,
    timeout: float,
    shared_prompt: bool,
    reset_cache: bool = False,
    prime: bool = False,
) -> dict:
    """Fire `request_count` requests through a `concurrency`-wide gate, capturing
    absolute per-request timings, and fold them into one detail record.

    warm: every request sends the identical prompt (pool[:prompt_tokens]) so the
    prefix cache is exercised. cold: each request uses a different window offset
    into the pool, so prefixes differ from token 0 and the radix cache cannot
    reuse across requests; when reset_cache is set the cache is flushed first so
    the wave provably starts cold (backend-verified-reset).
    """
    results: list[dict | None] = [None] * request_count
    gate = threading.Semaphore(concurrency)
    span = max(1, len(pool) - prompt_tokens + 1)

    def worker(index: int) -> None:
        if shared_prompt:
            ids = pool[:prompt_tokens]
        else:
            offset = index % span
            ids = pool[offset:offset + prompt_tokens]
        with gate:
            results[index] = stream_one(base_url, model, ids, max_tokens, timeout)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(request_count)]
    cache_reset = None
    cache_reset_error = None
    if reset_cache:
        flushed, detail = flush_cache(base_url, timeout)
        cache_reset = "flush_cache" if flushed else None
        if not flushed:
            cache_reset_error = detail
    # §3.2 warm priming: an UNMEASURED prime of the identical shared prompt,
    # immediately before each measured warm wave and after any preceding cell, so
    # a cold cell's distinct prefixes cannot leave the first measured request cold.
    # Byte-identical to the wave's pool[:prompt_tokens]; a COMPLETED request before
    # dispatch; excluded from every wave statistic. Its own cached_tokens is
    # recorded honestly (0 or more) and read into nothing: warm validity is a
    # RESIDENT prefix - every MEASURED request shows cached>0 - not a fresh
    # cold->warm transition per cell, so how the prefix became resident is
    # irrelevant. The prime does NOT relax that per-request rule; it makes it
    # satisfiable.
    prime_evidence = None
    if prime:
        primed = stream_one(base_url, model, pool[:prompt_tokens], 1, timeout)
        p_usage = primed["usage"]
        p_details = p_usage.get("prompt_tokens_details") or {}
        p_ttft = (primed["t_first"] - primed["t_dispatch"]) if primed["t_first"] is not None else None
        prime_evidence = {
            "measured": False,
            "note": "unmeasured warm cache prime; identical prompt; excluded from all wave stats",
            "cached_tokens": p_details.get("cached_tokens"),
            "output_len": p_usage.get("completion_tokens"),
            "ttft_s": round(p_ttft, 4) if p_ttft is not None else None,
            "error": primed["error"] or None,
        }
    wave_start = time.monotonic()
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    wave_end = time.monotonic()
    duration = wave_end - wave_start

    ttfts: list[float] = []
    itls: list[list[float]] = []
    start_times: list[float] = []
    output_lens: list[int] = []
    input_lens: list[int] = []
    cached_tokens: list[int] = []
    queue_times: list[float] = []
    errors: list[str] = []
    base = min((r["t_dispatch"] for r in results if r), default=wave_start)
    raw_requests: list[dict | None] = []
    for result in results:
        if result is None:
            errors.append("no-result")
            input_lens.append(None)
            output_lens.append(None)
            start_times.append(None)
            queue_times.append(None)
            ttfts.append(None)
            itls.append([])
            cached_tokens.append(None)
            raw_requests.append(None)
            continue
        usage = result["usage"]
        completion = usage.get("completion_tokens")
        observed_prompt = usage.get("prompt_tokens")
        finish_reason = result.get("finish_reason")
        t_dispatch = result["t_dispatch"]
        t_first = result["t_first"]
        t_last = result["t_last"]
        timestamps_ok = (
            t_first is not None
            and t_last is not None
            and t_first >= t_dispatch
            and t_last >= t_first
        )
        # Every MEASURED request is validated against the requested horizon with
        # the same rigor the gate applies to its single request: a stream is not
        # counted unless the server REPORTS a prompt length equal to what we sent,
        # a completion length equal to the requested horizon, finish_reason
        # "length" (ignore_eos was requested), and usable monotonic timestamps.
        # A missing field is measurement-invalid, never fabricated or defaulted.
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
        # Honest observations only: the SERVER-reported counts, or None when the
        # server omitted them. Never substitute the client-requested value - that
        # asserts an intended length as if it were measured and defeats the
        # prompt/horizon parity checks above.
        input_lens.append(int(observed_prompt) if observed_prompt is not None else None)
        output_lens.append(int(completion) if completion is not None else None)
        start_times.append(t_dispatch - base)
        # client-side gate wait: time from wave start until this request actually
        # dispatched through the concurrency gate. Attributes harness queueing so
        # a long TTFT is not misread as engine latency (client_queue_wait_s).
        queue_times.append(t_dispatch - wave_start)
        ttfts.append((t_first - t_dispatch) if t_first is not None else None)
        itls.append(result["itl"])
        details = usage.get("prompt_tokens_details") or {}
        # index-aligned with errors/input_lens/output_lens: None when the backend
        # omits cached_tokens, so a per-request warm/cold check reads request i's
        # own value (None => not-warm) and never a neighbour's.
        cached_tokens.append(
            int(details["cached_tokens"] or 0) if "cached_tokens" in details else None
        )
        # Full raw per-request result retained in the detail file alongside the
        # derived arrays: absolute client timestamps, the untouched usage block,
        # and finish_reason, so overlap/admission analysis can recompute every
        # derived value from source instead of trusting the arrays.
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
    # TPOT from the token count and the decode SPAN, not the chunk count:
    # tpot = (t_last - t_first) / (output_tokens - 1), robust to multi-token chunks.
    tpots = [
        sum(itls[index]) / (out_len - 1)
        for index, out_len in enumerate(output_lens)
        if out_len and out_len > 1 and index < len(itls) and sum(itls[index]) > 0
    ]
    record = {
        "backend": "omp-bench-client",
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
        # raw monotonic wave bounds on the SAME clock as each request's
        # t_dispatch, so aggregate output/wave duration and the client gate wait
        # recompute from the public raw values, not only the rounded duration.
        "wave_start": wave_start,
        "wave_end": wave_end,
        "output_throughput": round(total_output / duration, 3) if duration > 0 else None,
        "mean_ttft_ms": round(statistics.mean(valid_ttfts) * 1000.0, 3) if valid_ttfts else None,
        "mean_tpot_ms": round(statistics.mean(tpots) * 1000.0, 3) if tpots else None,
    }
    # index-aligned length == request_count (None where the backend omitted the
    # field); the converter must treat None as not-warm and never coerce None->0.
    record["cached_tokens"] = cached_tokens
    record["requests"] = raw_requests
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


def _detail(record: dict) -> tuple[str, str]:
    payload = json.dumps(record)
    return payload, hashlib.sha256(payload.encode()).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--model", required=True)
    parser.add_argument("--model-dir", required=True, help="mounted pinned model dir on the pod")
    parser.add_argument("--trust-remote-code", action="store_true")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--total-contexts", required=True)
    parser.add_argument("--concurrencies", required=True)
    parser.add_argument("--output-tokens", type=int, default=512)
    parser.add_argument("--context-len", type=int, default=None,
                        help="model context ceiling; caps usable = context_len - reserved")
    parser.add_argument("--reserved-positions", type=int, default=0,
                        help="engine positions reserved at the ceiling (SGLang: 2)")
    parser.add_argument("--samples", type=int, default=3)
    parser.add_argument("--scenarios", default="cold,warm")
    parser.add_argument("--timeout", type=float, default=1800)
    args = parser.parse_args(argv)

    contexts = [int(v) for v in args.total_contexts.split(",") if v]
    concurrencies = [int(v) for v in args.concurrencies.split(",") if v]
    scenarios = [s for s in args.scenarios.split(",") if s]
    raw_dir = args.output_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    ceiling = (args.context_len - args.reserved_positions) if args.context_len else None
    # usable per cell caps input+output at the reserved ceiling so the engine
    # never clamps max_new_tokens (real window accounting: nominal vs usable).
    def usable_of(context):
        return min(context, ceiling) if ceiling else context
    max_prompt = max(usable_of(c) for c in contexts) - args.output_tokens
    # extra headroom so cold waves can offset-rotate the window into distinct,
    # non-overlapping-prefix slices (span >= request_count).
    tok = load_tokenizer(args.model_dir, args.trust_remote_code)
    pool = build_token_pool(
        tok, max_prompt + max(concurrencies) * STEADY_STATE_WAVES + 8
    )

    created_at = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())
    manifest_path = args.output_dir / MANIFEST_NAME

    def flush(runs: list) -> None:
        manifest = {
            "schema_version": "inference-index/omp-bench-client-v1",
            "created_at": created_at,
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
            "driver": "scripts/omp_bench_client.py",
            "engine": "openai-completions",
            "endpoint": "<local-base-url>",
            "model": args.model,
            "protocol": {
                "total_context_tokens": contexts,
                "concurrencies": concurrencies,
                "scenarios": scenarios,
                "samples_per_scenario": args.samples,
                "measurement_output_tokens": args.output_tokens,
                "length_sampling": "exact-token-id-array",
                "streaming": "enabled",
                "client_monotonic_timestamps": True,
            },
            "runs": runs,
        }
        tmp = manifest_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(manifest, indent=2, sort_keys=True))
        tmp.replace(manifest_path)

    def plan_run(context, usable, prompt_tokens, concurrency, scenario, sample):
        return {
            "id": f"t{context}-c{concurrency}-{scenario}-s{sample}",
            "status": "planned",
            "total_context_tokens": context,
            "usable_context_tokens": usable,
            "engine_reserved_positions": args.reserved_positions,
            "prompt_tokens": prompt_tokens,
            "measurement_output_tokens": args.output_tokens,
            "concurrency": concurrency,
            "scenario": scenario,
            "request_count": concurrency * STEADY_STATE_WAVES,
            "measurement_samples": args.samples,
        }

    # Prepopulate the FULL planned grid so the manifest enumerates every cell the
    # sweep intended to measure (the SGLang planned-grid convention); executed
    # runs update IN PLACE. An interrupted sweep therefore leaves the unrun cells
    # as status "planned", so a recorder verifies coverage against the protocol
    # dimensions and can never read 1-of-N executed cells as a complete sweep.
    runs: list[dict] = [
        plan_run(context, usable_of(context), usable_of(context) - args.output_tokens,
                 concurrency, scenario, sample)
        for context in contexts
        for concurrency in concurrencies
        for scenario in scenarios
        for sample in range(1, args.samples + 1)
    ]
    flush(runs)
    for run in runs:
        record = run_wave(
            args.base_url, args.model, pool, run["prompt_tokens"], args.output_tokens,
            run["concurrency"], run["request_count"], args.timeout,
            shared_prompt=(run["scenario"] == "warm"),
            reset_cache=(run["scenario"] == "cold"),
            prime=(run["scenario"] == "warm"),
        )
        payload, digest = _detail(record)
        (raw_dir / f"{run['id']}.jsonl").write_text(payload + "\n")
        completed = record["completed"] == run["request_count"] and not record["failed"]
        run["status"] = "completed" if completed else "measurement-invalid"
        run["detail_file"] = f"raw/{run['id']}.jsonl"
        run["artifact_sha256"] = digest
        if not completed:
            # A per-request validation failure is a MEASUREMENT invalidity (the
            # sample cannot be trusted), not a physical infrastructure failure;
            # carry the ACTUAL per-request cause(s), never a blanket "client_error".
            causes = record.get("invalid_causes") or ["unknown"]
            run["invalid_reason"] = (
                f"{record['failed']} of {run['request_count']} measured requests"
                " failed per-request validation"
            )
            run["invalid_cause"] = ",".join(causes)
            run["failure_scope"] = "measurement"
            run["survivor_count"] = record["completed"]
        print(json.dumps({"id": run["id"], "status": run["status"]}), flush=True)
        flush(runs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
