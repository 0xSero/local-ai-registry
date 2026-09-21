#!/usr/bin/env python3
"""TabbyAPI / ExLlamaV3 protocol-v2 measurement adapter (staged; live-gated).

Reuses the IDENTICAL measurement contract from omp_measure_core (per-request
validation, client timestamps, cached_tokens alignment, record shape). This
module supplies ONLY the TabbyAPI engine specifics, all grounded in the
installed source (bundle /tmp/tabby_src, cu12 @47c4c6eb; the six contract files
byte-identical to cu13 @53da7919):

  * Prompt is a STRING. TabbyAPI's CompletionRequest.prompt is Union[str,
    List[str]] and token-id prompts are explicitly out of scope
    (endpoints/OAI/types/completion.py:57-62). The server re-tokenises with the
    exllamav3 Tokenizer, so exact prompt length is achieved and VERIFIED through
    /v1/token/encode (endpoints/core/types/token.py) with add_bos_token=false,
    and the completion is sent with add_bos_token=false so no BOS is prepended
    (common/sampling.py:243; backends/exllamav3/model.py:1362,1380).
  * Fixed horizon uses min_tokens == max_tokens. ignore_eos is only an alias of
    ban_eos_token, which is in UNSUPPORTED_PARAMS and is IGNORED by the exllamav3
    backend at generation time (common/sampling.py:25-35, 247-252) - so it CANNOT
    pin the horizon. min_tokens maps to min_new_tokens (model.py:1488); with
    min==max the job emits exactly max_tokens. The exact min_new_tokens vs
    EOS/stop-condition interaction is NOT visible in this bundle (exllamav3 is a
    compiled dependency), so a LIVE preflight gate confirms it fail-closed before
    any measured sweep. NO extra EOS ban is added.
  * Reservation is validated by the server (common/errors.py:40
    validate_context_requirements) across BOTH allocation branches (streaming
    max_rq_tokens=None: input+output<=cache; requeue: ceil((input-1+max_rq)/256)
    *256<=cache). The served config decides the branch, so the client targets
    input=min(window-output, max_seq_len, cache_capacity-output) and the live
    gate fails closed on a 400 context_length_exceeded rather than guessing.
  * No cache-flush endpoint exists. COLD is verified by OBSERVED
    cached_tokens==0 on every measured request (distinct prompts make them fresh
    but the evidence is the observed count, never the offset); WARM by an
    unmeasured identical prime plus observed cached_tokens>0 on every measured
    request.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import omp_measure_core as core  # noqa: E402

# One-token filler words used to tune a prompt to an exact server token count.
_FILLER_WORDS = [" the", " and", " of", " to", " in", " a", " that", " it"]
_BASE_SENTENCE = (
    "The quick brown fox studies distributed systems while the lazy dog audits "
    "ternary quantization kernels across a long context window. "
)


def encode_ids(base_url: str, text: str, timeout: float,
               add_bos: bool = False) -> tuple[list[int], int]:
    """Server-side exllamav3 token ids + length of `text` (add_bos_token as given).

    Uses the SAME add_bos_token the completion path will use, so the measured
    length is exactly what /v1/completions will report as prompt_tokens.
    """
    body = {"text": text, "add_bos_token": add_bos, "encode_special_tokens": True}
    request = urllib.request.Request(
        base_url.rstrip("/") + "/v1/token/encode",
        data=json.dumps(body).encode(),
        headers={"content-type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8", "replace"))
    return list(payload.get("tokens") or []), int(payload["length"])


def encode_length(base_url: str, text: str, timeout: float, add_bos: bool = False) -> int:
    """Server-side token length of `text` (see encode_ids)."""
    return encode_ids(base_url, text, timeout, add_bos)[1]


def decode_ids(base_url: str, tokens: list[int], timeout: float) -> str:
    """Server-side exllamav3 detokenisation of `tokens` back to text."""
    body = {"tokens": tokens, "decode_special_tokens": True}
    request = urllib.request.Request(
        base_url.rstrip("/") + "/v1/token/decode",
        data=json.dumps(body).encode(),
        headers={"content-type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8", "replace"))
    return str(payload["text"])


def build_exact_prompt(base_url: str, target: int, unique_prefix: str, timeout: float) -> str:
    """A string whose server length (add_bos_token=false) is EXACTLY target, built
    with a BOUNDED number of HTTP calls independent of `target`.

    Naive per-token growth re-tokenises the whole text every step - O(target) HTTP
    round trips and quadratic server tokenisation at a 131072 window. Instead:
    build one text safely OVER target (exponential doubling if the estimate falls
    short), encode it ONCE to ids, TRUNCATE the ids to `target` (the unique prefix
    sits at the front and is preserved), DECODE back to text, and re-encode to
    verify. A re-tokenised boundary can drift by a few tokens; a bounded repair
    loop trims or borrows ids from the already-encoded pool to land exact. Total
    calls are a small constant (~1 encode + O(log) growth + 1 decode + a few
    repairs). Fails CLOSED if no exact fit is found.
    """
    approx_sentences = max(1, target // 12 + 8)  # conservative >= target overshoot
    text = unique_prefix + _BASE_SENTENCE * approx_sentences
    ids, length = encode_ids(base_url, text, timeout)
    grow = 0
    while length < target and grow < 24:  # exponential doubling, bounded
        text += text
        ids, length = encode_ids(base_url, text, timeout)
        grow += 1
    if length < target:
        raise RuntimeError(f"could not reach a {target}-token prompt pool (got {length})")
    candidate = ids[:target]
    text = decode_ids(base_url, candidate, timeout)
    ids2, length2 = encode_ids(base_url, text, timeout)
    repair = 0
    while length2 != target and repair < 12:
        if length2 > target:
            candidate = ids2[:target]
        else:
            candidate = ids2 + ids[target: target + (target - length2)]
        text = decode_ids(base_url, candidate, timeout)
        ids2, length2 = encode_ids(base_url, text, timeout)
        repair += 1
    if length2 != target:
        raise RuntimeError(f"could not build an exact-{target}-token prompt (got {length2})")
    return text


def reservation(window: int, output: int, max_seq_len: int, cache_capacity: int) -> int:
    """Prompt token target that fits the served window; the server validates it.

    input = min(nominal window - output, server max_seq_len, cache_capacity -
    output). This satisfies the streaming allocation branch directly; the requeue
    branch (if the served config enables it) is checked live by the preflight
    gate, which fails closed on a 400 rather than the client guessing max_rq.
    """
    return min(window - output, max_seq_len, cache_capacity - output)


def tabby_body(model: str, prompt: str, max_tokens: int) -> dict:
    """The exact /v1/completions body for a fixed-horizon measured request.

    min_tokens == max_tokens pins the horizon (ignore_eos is ignored by the
    backend); add_bos_token=false keeps prompt_tokens equal to the encoded
    length; temperature 0 is deterministic. No EOS ban is added.
    """
    return {
        "model": model,
        "prompt": prompt,
        "max_tokens": max_tokens,
        "min_tokens": max_tokens,
        "add_bos_token": False,
        "stream": True,
        "stream_options": {"include_usage": True},
        "temperature": 0.0,
    }


def classify_mtp(mtp_counters) -> dict:
    """MTP observation from accepted/rejected prediction counts. NEVER claims a
    speedup, and NEVER infers a loaded drafter from a zero-valued counter.

    proposed = accepted + rejected. proposed>0 -> observed speculation with an
    acceptance rate (still not a speedup claim). All 0/0 -> ZERO observed proposals
    / acceptance UNDEFINED: it does NOT prove the drafter is loaded or configured -
    that is separate runtime evidence, not this API counter. Absent counters ->
    the engine did not report MTP.
    """
    present = [m for m in (mtp_counters or []) if m]
    if not present:
        return {"status": "not-reported", "proposed": 0, "accepted": 0, "acceptance_rate": None}
    proposed = sum(m["accepted"] + m["rejected"] for m in present)
    accepted = sum(m["accepted"] for m in present)
    if proposed == 0:
        return {"status": "zero-proposals", "proposed": 0, "accepted": 0,
                "acceptance_rate": None,
                "note": "0/0: zero observed proposals; acceptance undefined. Does NOT "
                        "prove the drafter is loaded/configured (separate runtime "
                        "evidence); no speedup claimed."}
    return {"status": "observed", "proposed": proposed, "accepted": accepted,
            "acceptance_rate": round(accepted / proposed, 4)}

def preflight_gate(base_url: str, model: str, window: int, output: int,
                   max_seq_len: int, cache_capacity: int, timeout: float) -> dict:
    """LIVE fail-closed gate run before any measured sweep on a fresh pod.

    Confirms on the real server that (a) the reservation is accepted (no 400
    context_length_exceeded), (b) add_bos_token=false makes prompt_tokens equal
    the encoded target (BOS accounting), and (c) min_tokens==max_tokens actually
    yields completion_tokens==max_tokens with finish_reason "length" (the
    exllamav3 min_new_tokens semantic that the source bundle cannot prove). Any
    miss returns a rc1 measurement-invalidity with a specific code; the sweep
    must not run until it passes.
    """
    target = reservation(window, output, max_seq_len, cache_capacity)
    failures = []
    try:
        # The prefix must be window-specific: every window's gate prompt is built
        # from the SAME repeated base sentence, so a shared prefix let a later
        # window's "cold" gate hit the earlier window's cached prefix
        # (cached_tokens=32000 at the 131072 window) and the coldness witness
        # failed closed. Distinguishing the first tokens makes each gate fresh.
        prompt = build_exact_prompt(base_url, target, unique_prefix=f"gate{window} ", timeout=timeout)
    except Exception as exc:
        return {"passed": False, "code": "exact_prompt_build_failed",
                "detail": f"{type(exc).__name__}: {exc}", "target": target}
    result = core.stream_completion(base_url.rstrip("/") + "/v1/completions",
                                    tabby_body(model, prompt, output), timeout)
    if result["error"]:
        return {"passed": False, "code": "gate_request_error", "detail": result["error"],
                "target": target}
    usage = result["usage"]
    observed_prompt = usage.get("prompt_tokens")
    completion = usage.get("completion_tokens")
    if observed_prompt != target:
        failures.append(("prompt_token_mismatch", f"observed {observed_prompt} != target {target}"))
    if completion != output:
        failures.append(("min_tokens_horizon_unmet",
                         f"completion {completion} != requested {output} "
                         "(min_new_tokens did not pin the horizon)"))
    if result.get("finish_reason") != "length":
        failures.append(("finish_reason_not_length", str(result.get("finish_reason"))))
    # 4th witness (free): the first cold gate request MUST report cached_tokens==0.
    # This proves the cache report works on THIS backend before any warm claim
    # rests on it - the witness discipline SGLang had to reconstruct after the fact.
    cached = (usage.get("prompt_tokens_details") or {}).get("cached_tokens")
    if cached != 0:
        failures.append(("cache_report_unverified",
                         f"first cold gate cached_tokens={cached}, expected 0"))
    return {
        "passed": not failures,
        "code": None if not failures else failures[0][0],
        "failures": [{"code": c, "detail": d} for c, d in failures],
        "window": window,
        "target": target,
        "observed_prompt_tokens": observed_prompt,
        "observed_completion_tokens": completion,
        "finish_reason": result.get("finish_reason"),
        "observed_cached_tokens": cached,
        # MTP: configured/loaded is NOT observed speculation - distinguish
        # proposed>0 (observed) from 0/0 (loaded-undefined) from not-reported; a
        # merely-enabled drafter never licenses a speedup claim.
        "mtp": classify_mtp([core._mtp(usage)]),
        # LIMIT: this gate exercises min_new_tokens against EOS only. exllamav3 is
        # compiled, so min_new_tokens vs stop STRINGS is unproven; the benchmark
        # sends no stop strings, but any package that sets one needs its own proof.
        "stop_string_coverage": "not-tested (benchmark sends no stop strings)",
    }


def run_wave(base_url: str, model: str, prompt_tokens: int, max_tokens: int,
             concurrency: int, request_count: int, timeout: float,
             scenario: str, cell_id: str, stop_event=None, stop_grace_s: float = 10.0) -> dict:
    """One measured wave for a (context, concurrency, scenario) cell.

    Every prompt is PREBUILT before the measured wave starts, so the wave clock
    and the client gate wait never include the /v1/token/encode construction HTTP
    work. Every prompt is GLOBALLY unique - keyed by the cell id (t/c/scenario/
    sample) and the request index - so a persistent cache with NO flush endpoint
    cannot silently reuse a prior cold prompt across windows, cells or samples;
    cold distinctness is then witnessed by the observed cached_tokens==0. warm
    shares ONE prompt within the cell (distinct from every other cell's warm
    prompt). The raw per-request prompt identity is recorded for audit.
    """
    completions_url = base_url.rstrip("/") + "/v1/completions"
    warm = scenario == "warm"
    if warm:
        warm_prompt = build_exact_prompt(base_url, prompt_tokens, f"{cell_id} warm ", timeout)
        prompts = [warm_prompt] * request_count
        identities = [f"{cell_id}:warm"] * request_count
    else:
        prompts = [build_exact_prompt(base_url, prompt_tokens, f"{cell_id} r{index} ", timeout)
                   for index in range(request_count)]
        identities = [f"{cell_id}:r{index}" for index in range(request_count)]

    def dispatch(index: int) -> dict:
        return core.stream_completion(completions_url,
                                      tabby_body(model, prompts[index], max_tokens), timeout)

    prime = None
    if warm:
        def prime() -> dict:
            return core.stream_completion(completions_url,
                                          tabby_body(model, warm_prompt, 1), timeout)

    # No backend flush endpoint: cold rests on observed cached_tokens==0, so reset
    # is always None; global prompt uniqueness is what keeps cold requests fresh.
    record = core.run_wave(prompt_tokens, max_tokens, concurrency, request_count,
                           dispatch, prime=prime, reset=None, backend="omp-tabby-client",
                           stop_event=stop_event, stop_grace_s=stop_grace_s)
    record["prompt_identities"] = identities
    if warm:
        record["prime_prompt_identity"] = f"{cell_id}:warm"
    return record


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:5000")
    parser.add_argument("--model", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--total-contexts", required=True)
    parser.add_argument("--concurrencies", required=True)
    parser.add_argument("--output-tokens", type=int, default=512)
    parser.add_argument("--max-seq-len", type=int, required=True,
                        help="served max_seq_len (baked model config)")
    parser.add_argument("--cache-capacity", type=int, required=True,
                        help="served cache size in tokens (baked model config)")
    parser.add_argument("--samples", type=int, default=3)
    parser.add_argument("--scenarios", default="cold,warm")
    parser.add_argument("--timeout", type=float, default=1800,
                        help="PER-REQUEST HTTP timeout (one /v1/completions or /v1/token call); "
                             "NOT the sweep wall limit. The controller enforces the budget-coupled "
                             "wall deadline separately via SIGTERM + grace, never by inflating this.")
    parser.add_argument("--stop-grace-s", type=float, default=10.0,
                        help="on a graceful stop (SIGTERM/SIGINT), seconds to let in-flight "
                             "requests finish and be persisted before folding+abandoning "
                             "stragglers; keep the controller's force-kill grace > this + write.")
    parser.add_argument("--gate-only", action="store_true",
                        help="run only the live preflight gate and exit")
    args = parser.parse_args(argv)

    contexts = [int(v) for v in args.total_contexts.split(",") if v]
    concurrencies = [int(v) for v in args.concurrencies.split(",") if v]
    scenarios = [s for s in args.scenarios.split(",") if s]
    raw_dir = args.output_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    # Fail-closed live gate at EVERY distinct window before any measured request:
    # validate_context_requirements picks its allocation branch from the requested
    # completion (job_max_rq_tokens), and different windows also traverse different
    # prefill-chunk counts, so a pass at one window certifies ONLY that window.
    gates = []
    for window in sorted(set(contexts)):
        gate = preflight_gate(args.base_url, args.model, window, args.output_tokens,
                              args.max_seq_len, args.cache_capacity, args.timeout)
        gates.append(gate)
        print(json.dumps({"gate_window": window, "result": "pass" if gate["passed"] else "fail",
                          "code": gate.get("code")}), flush=True)
    (args.output_dir / "preflight-gate.json").write_text(json.dumps(gates, indent=2, sort_keys=True))
    if not all(gate["passed"] for gate in gates):
        return 1
    if args.gate_only:
        return 0

    import time
    created_at = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())
    runs = [
        {"id": f"t{ctx}-c{conc}-{scen}-s{s}", "status": "planned",
         "total_context_tokens": ctx, "usable_context_tokens": min(ctx, args.max_seq_len),
         "prompt_tokens": reservation(ctx, args.output_tokens, args.max_seq_len, args.cache_capacity),
         "measurement_output_tokens": args.output_tokens, "concurrency": conc,
         "scenario": scen, "request_count": conc * core.STEADY_STATE_WAVES,
         "measurement_samples": args.samples}
        for ctx in contexts for conc in concurrencies for scen in scenarios
        for s in range(1, args.samples + 1)
    ]

    def flush() -> None:
        manifest = {
            "schema_version": "inference-index/omp-bench-client-v1",
            "created_at": created_at,
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
            "driver": "scripts/omp_tabby_client.py",
            "engine": "tabbyapi-exllamav3",
            "endpoint": "<local-base-url>",
            "model": args.model,
            "protocol": {
                "total_context_tokens": contexts,
                "concurrencies": concurrencies,
                "scenarios": scenarios,
                "samples_per_scenario": args.samples,
                "measurement_output_tokens": args.output_tokens,
                "length_sampling": "exact-token-string-via-token-encode",
                "streaming": "enabled",
                "client_monotonic_timestamps": True,
                "horizon_control": "min_tokens==max_tokens",
            },
            "runs": runs,
        }
        tmp = (args.output_dir / "manifest.json.tmp")
        tmp.write_text(json.dumps(manifest, indent=2, sort_keys=True))
        tmp.replace(args.output_dir / "manifest.json")

    import signal
    import threading
    stop_event = threading.Event()

    def _graceful_stop(_signum, _frame):
        # Bounded graceful stop: let the in-flight wave fold and persist its
        # already-completed requests; never kill mid-write.
        stop_event.set()

    for _sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(_sig, _graceful_stop)

    flush()
    for run in runs:
        if stop_event.is_set():
            # A later cell never started stays honestly "planned" (not reached),
            # never fabricated as run, complete or failed.
            break
        # Mark the cell running BEFORE the wave so even a hard kill shows it was
        # in-flight, never silently "planned"; a graceful stop upgrades it to
        # "interrupted" with the completed records preserved below.
        run["status"] = "running"
        flush()
        record = run_wave(args.base_url, args.model, run["prompt_tokens"], args.output_tokens,
                          run["concurrency"], run["request_count"], args.timeout, run["scenario"],
                          run["id"], stop_event=stop_event, stop_grace_s=args.stop_grace_s)
        payload = json.dumps(record)
        import hashlib
        digest = hashlib.sha256(payload.encode()).hexdigest()
        (raw_dir / f"{run['id']}.jsonl").write_text(payload + "\n")
        run["detail_file"] = f"raw/{run['id']}.jsonl"
        run["artifact_sha256"] = digest
        completed = record["completed"] == run["request_count"] and not record["failed"]
        if completed:
            run["status"] = "completed"
        elif record.get("interrupted"):
            # Completed requests are on disk; the cell is incomplete, never
            # falsely complete. The neutral cause never asserts a phantom failure.
            run["status"] = "interrupted"
            run["survivor_count"] = record["completed"]
            run["invalid_cause"] = "graceful-stop"
            run["failure_scope"] = "interruption"
        else:
            causes = record.get("invalid_causes") or ["unknown"]
            run["status"] = "measurement-invalid"
            run["invalid_reason"] = (
                f"{record['failed']} of {run['request_count']} measured requests"
                " failed per-request validation")
            run["invalid_cause"] = ",".join(causes)
            run["failure_scope"] = "measurement"
            run["survivor_count"] = record["completed"]
        print(json.dumps({"id": run["id"], "status": run["status"]}), flush=True)
        flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
