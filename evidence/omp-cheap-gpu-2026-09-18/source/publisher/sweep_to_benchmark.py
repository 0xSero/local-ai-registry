#!/usr/bin/env python3
"""Convert completed sglang_sweep raw records into candidate benchmark rows.

The index convention (schema/benchmark.schema.json, prior accepted rows, and
the historical frontier data) is phase-separated rates. This converter is
deliberately conservative about what it claims:

- decode_tok_s_per_stream is an ESTIMATOR: 1000 / mean_tpot_ms averaged over
  samples. It reflects each stream's steady decode pace, never the client's
  blended output_throughput.
- decode_tok_s_aggregate is always null here: mean-TPOT multiplied by the
  configured concurrency is not an observed aggregate because the client
  semaphore and long staggered prefills desynchronize the decode phases. An
  aggregate may only be recorded when it is directly measured over a common
  decode window.
- TTFT p50/p95 are true percentiles over the pooled raw per-request ttfts of
  all samples, not averages of per-sample summary statistics.
- prefill_tok_s is prompt length divided by TTFT, reported only at
  concurrency 1; at higher concurrency TTFT includes admission waiting.
- Rows are emitted with status "candidate". Promotion to "accepted" is a
  reviewed decision, never automatic.

Eligibility is enforced, not assumed: every converted run must carry the
current exact token-ID command shape (--tokenize-prompt with range ratio 1.0)
and every (context, concurrency, scenario) point must have at least two
samples with distinct raw-artifact hashes.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from statistics import mean, median
from typing import Any, Mapping


class ConversionError(RuntimeError):
    pass


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ConversionError("cannot take a percentile of no values")
    rank = fraction * (len(ordered) - 1)
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return ordered[low]
    weight = rank - low
    return ordered[low] * (1 - weight) + ordered[high] * weight


def _range_ratio(command: list) -> str | None:
    try:
        return command[command.index("--random-range-ratio") + 1]
    except (ValueError, IndexError):
        return None


def _require_exact_length(run: Mapping[str, Any], protocol: Mapping[str, Any] | None) -> None:
    """Enforce exact-length prompts per engine.

    SGLang's exact ratio is 1.0; vLLM's is 0.0 (its range is symmetric). Engines
    with no range-ratio argv at all (e.g. the llama.cpp native driver, which
    passes a verbatim token-id array) are gated on the manifest's declared
    length_sampling instead of a driver-specific flag shape.
    """
    command = run.get("command") or []
    joined = " ".join(str(part) for part in command)
    if "sglang.benchmark.serving" in joined or "--tokenize-prompt" in command:
        if "--tokenize-prompt" not in command:
            raise ConversionError(f"run {run.get('id')} was not produced with token-ID prompts")
        if _range_ratio(command) != "1.0":
            raise ConversionError(f"run {run.get('id')} used a non-exact SGLang range ratio")
    elif "bench" in command and "serve" in command:
        if _range_ratio(command) != "0.0":
            raise ConversionError(f"run {run.get('id')} used a non-exact vLLM range ratio")
    else:
        sampling = (protocol or {}).get("length_sampling")
        if sampling not in ("exact", "exact-token-id-array"):
            raise ConversionError(
                f"run {run.get('id')} is not from an exact-length protocol "
                f"(length_sampling={sampling!r})"
            )


def _per_request_rates(records: list[Mapping[str, Any]]) -> tuple[list[float], list[float]]:
    """Pooled per-request (end_to_end_tok_s, client_decode_tok_s).

    end_to_end = output_tokens / (ttft + sum(itl)) = output/(t_last - t_dispatch);
    the headline rate, measured from dispatch to last token (ttft includes queue).
    client_decode = (output_tokens - 1) / (t_last - t_first). It is derived from
    the OUTPUT TOKEN COUNT, not the number of stream chunks: an SSE chunk may
    carry several tokens, so sum(itl) is the decode SPAN while (output-1) is the
    true number of decode steps. A single-token output (output <= 1) has no decode
    interval, so TPOT/client_decode is undefined and omitted. A request whose
    output_len is None (usage missing) is skipped entirely — never counted from
    chunk arithmetic.
    """
    e2e: list[float] = []
    client_decode: list[float] = []
    for record in records:
        ttfts = record.get("ttfts") or []
        itls = record.get("itls") or []
        output_lens = record.get("output_lens") or []
        for index, out_len in enumerate(output_lens):
            if out_len is None or index >= len(ttfts) or index >= len(itls):
                continue
            intervals = itls[index] or []
            decode_time = sum(intervals)
            total_time = ttfts[index] + decode_time
            if out_len > 0 and total_time > 0:
                e2e.append(out_len / total_time)
            # decode span is t_last - t_first regardless of chunk granularity;
            # (out_len - 1) is the true decode-step count.
            if out_len > 1 and decode_time > 0:
                client_decode.append((out_len - 1) / decode_time)
    return e2e, client_decode


def _iqr(values: list[float]) -> dict | None:
    if not values:
        return None
    p25 = _percentile(values, 0.25)
    p50 = _percentile(values, 0.50)
    p75 = _percentile(values, 0.75)
    return {
        "p25": round(p25, 3),
        "p50": round(p50, 3),
        "p75": round(p75, 3),
        "iqr": round(p75 - p25, 3),
        "unstable": p50 > 0 and (p75 - p25) > 0.25 * p50,
    }


def _wave_endpoints(record: Mapping[str, Any]) -> list[tuple[float, float, float]] | None:
    """Per-request (dispatch, first_token, last_token) monotonic times for one
    wave, built only from requests that carry an absolute start_time AND a first
    token. Returns None when the driver emitted no absolute start_times at all."""
    starts = record.get("start_times")
    ttfts = record.get("ttfts") or []
    itls = record.get("itls") or []
    if not starts:
        return None
    endpoints = []
    for index, start in enumerate(starts):
        if start is None or index >= len(ttfts) or index >= len(itls):
            continue
        ttft = ttfts[index]
        if ttft is None:
            continue
        first = start + ttft
        last = first + sum(itls[index] or [])
        endpoints.append((start, first, last))
    return endpoints or None


def _overlap_metrics(records: list[Mapping[str, Any]]) -> dict | None:
    """Observed STREAM overlap from absolute per-request start_times (engine- or driver-reported).

    This is client-observed stream overlap, NEVER engine batch size: buffering,
    chunked prefill and time-slicing decouple the two, so no max_concurrency is
    derived from it. Returns None when no wave exposes absolute start_times (e.g.
    the sglang bench output), so the caller emits null-with-reason rather than
    inferring overlap from relative intervals.
    """
    max_overlap = 0
    means: list[float] = []
    skews: list[float] = []
    seen = False
    for record in records:
        endpoints = _wave_endpoints(record)
        if endpoints is None:
            continue
        seen = True
        starts = [point[0] for point in endpoints]
        skews.append((max(starts) - min(starts)) * 1000.0)
        events: list[tuple[float, int]] = []
        for _, first, last in endpoints:
            if last > first:
                events.append((first, 1))
                events.append((last, -1))
        if not events:
            continue
        events.sort()
        current = 0
        area = 0.0
        prev = events[0][0]
        local_max = 0
        for time_point, delta in events:
            area += current * (time_point - prev)
            current += delta
            prev = time_point
            local_max = max(local_max, current)
        span = max(point[2] for point in endpoints) - min(point[1] for point in endpoints)
        max_overlap = max(max_overlap, local_max)
        if span > 0:
            means.append(area / span)
    if not seen:
        return None
    return {
        "observed_max_stream_overlap": max_overlap,
        "mean_stream_overlap": round(mean(means), 2) if means else None,
        "dispatch_skew_ms": round(max(skews), 1) if skews else None,
        "basis": (
            "client-observed stream overlap from absolute per-request start_times "
            "(engine- or driver-reported); NOT engine batch size"
        ),
    }


def _client_queue_wait_s(records: list[Mapping[str, Any]]) -> float | None:
    """CLIENT-side queue wait (time in the driver's concurrency gate before
    dispatch) when the driver reports queue_times. This is NOT the engine's queue
    time and never populates queue_wait_s."""
    values = [
        value
        for record in records
        for value in (record.get("queue_times") or [])
        if isinstance(value, (int, float))
    ]
    return round(_percentile(values, 0.50), 4) if values else None


def _admission_pattern(records: list[Mapping[str, Any]]) -> dict:
    """Descriptive within-wave admission signal from the TTFT spread.

    Requests in a wave dispatch together, so a staircase of TTFTs against one
    request's own service time is queue evidence needing no absolute clock (the
    Flash-Next 262144/C4 diagnosis). Descriptive only: never a batch or
    concurrency number.
    """
    labels: list[str] = []
    sorted_ttfts: list[list[float]] = []
    for record in records:
        ttfts = sorted(value for value in (record.get("ttfts") or []) if value is not None)
        itls = record.get("itls") or []
        if len(ttfts) < 3:
            continue
        sorted_ttfts.append([round(value, 3) for value in ttfts])
        completions = [sum(intervals or []) for intervals in itls]
        service = min(ttfts) + (median(completions) if completions else 0.0)
        diffs = [later - earlier for earlier, later in zip(ttfts, ttfts[1:])]
        med_diff = median(diffs) if diffs else 0.0
        if service > 0 and med_diff >= 0.5 * service:
            labels.append("staircase")
        elif service > 0 and med_diff <= 0.1 * service:
            labels.append("concurrent-admission")
        else:
            labels.append("mixed")
    if not labels:
        return {"label": None, "reason": "fewer than 3 requests per wave; admission pattern undefined"}
    return {
        "label": max(set(labels), key=labels.count),
        "per_wave": labels,
        "sorted_ttfts_s": sorted_ttfts,
    }


def _scenario_evidence(records: list[Mapping[str, Any]]) -> tuple[str, str]:
    """Cold/warm from evidence, never from a label (§3.2).

    Prefer per-request cached_tokens (needs the engine's cache-report flag). If
    absent, a recorded cache flush proves the wave started cold
    (backend-verified-reset); warm cannot be verified from a flush, so without
    counts it stays unverified.
    """
    cached_lists = [record.get("cached_tokens") for record in records]
    if all(isinstance(entry, list) and entry for entry in cached_lists):
        flat = [value for entry in cached_lists for value in entry]
        if all(isinstance(value, int) for value in flat):
            if all(value == 0 for value in flat):
                return "cold", "cached_tokens"
            if all(value > 0 for value in flat):
                return "warm", "cached_tokens"
            return "mixed", "cached_tokens"
    if any(record.get("cache_reset") == "flush_cache" for record in records):
        return "cold", "backend-verified-reset"
    return "unverified", "label-only"


def _valid_view(record: Mapping[str, Any]) -> tuple[dict, int | None, int | None, bool]:
    """Aggregation view of one wave with per-request-INVALID samples removed.

    A wave carries per-request validity only when the client wrote the raw
    `requests` array (omp-bench-client protocol-v2): request i is valid iff
    requests[i] exists and its error is None/empty. For such a wave this returns
    a COPY whose per-request arrays keep only valid indices and whose summary
    fields (means, totals) are recomputed over the survivors, so every downstream
    rate, percentile and overlap excludes invalid requests. The raw record is
    NEVER mutated and no observation is nulled to hide it - the raw detail file
    retains every value; this is only the aggregation lens.

    A legacy wave without a `requests` array cannot be validated per-request: it
    is returned unchanged and flagged has_validity=False so the caller keeps it
    legacy-provisional instead of auto-upgrading it to a per-request-verified cell.
    """
    requests = record.get("requests")
    if not isinstance(requests, list):
        return dict(record), None, None, False
    valid_idx = [
        index
        for index, req in enumerate(requests)
        if isinstance(req, Mapping) and req.get("error") in (None, "")
    ]
    n_total = len(requests)
    n_valid = len(valid_idx)

    def pick(name: str) -> list:
        seq = record.get(name) or []
        return [seq[index] for index in valid_idx if index < len(seq)]

    ttfts = pick("ttfts")
    itls = pick("itls")
    output_lens = pick("output_lens")
    valid_ttfts = [value for value in ttfts if value is not None]
    tpots = [
        sum(itls[index]) / (out_len - 1)
        for index, out_len in enumerate(output_lens)
        if out_len and out_len > 1 and index < len(itls) and sum(itls[index]) > 0
    ]
    view = dict(record)
    view["ttfts"] = ttfts
    view["itls"] = itls
    view["output_lens"] = output_lens
    view["input_lens"] = pick("input_lens")
    view["start_times"] = pick("start_times")
    view["queue_times"] = pick("queue_times")
    view["cached_tokens"] = pick("cached_tokens")
    view["errors"] = pick("errors")
    view["requests"] = [requests[index] for index in valid_idx]
    view["total_output_tokens"] = sum(value for value in output_lens if value)
    view["mean_ttft_ms"] = round(mean(valid_ttfts) * 1000.0, 3) if valid_ttfts else None
    view["mean_tpot_ms"] = round(mean(tpots) * 1000.0, 3) if tpots else None
    return view, n_valid, n_total, True

def row_from_records(run: Mapping[str, Any], records: list[Mapping[str, Any]]) -> dict:
    views = [_valid_view(record) for record in records]
    all_validated = bool(views) and all(has for _, _, _, has in views)
    survivor_request_count = sum(n for _, n, _, has in views if has and n is not None)
    expected_request_count = sum(t for _, _, t, has in views if has and t is not None)
    # A cell is COMPLETE only when every wave carries per-request validity and
    # every measured request survived validation; the survivor subset is reported,
    # never promoted to a full-count claim. Legacy waves without per-request codes
    # stay provisional (None), not auto-upgraded to a per-request-verified cell.
    cell_complete = (
        (survivor_request_count == expected_request_count) if all_validated else None
    )
    # Aggregate ONLY over surviving requests: invalid samples are excluded from
    # every rate, percentile and overlap computed below.
    records = [view for view, _, _, _ in views]
    concurrency = run["concurrency"]
    # Harness-observed steady decode pace; undefined when the wave produced a
    # single token (no inter-token interval, so no TPOT).
    tpot_rates = [1000.0 / record["mean_tpot_ms"] for record in records if record.get("mean_tpot_ms")]
    per_stream = round(mean(tpot_rates), 1) if tpot_rates else None
    pooled_ttft_ms = [
        value * 1000.0
        for record in records
        for value in (record.get("ttfts") or [])
        if value is not None
    ]
    request_count = run["request_count"]
    cached = [
        (record.get("cache_report") or {}).get("total_cached_tokens")
        for record in records
    ]
    cached_prompt = None
    hit_rate = None
    if all(isinstance(value, int) for value in cached):
        cached_prompt = round(sum(cached) / (len(records) * request_count))
        hit_rate = min(1.0, max(0.0, cached_prompt / run["prompt_tokens"]))
    prefill = None
    ttft_means = [record["mean_ttft_ms"] for record in records if record.get("mean_ttft_ms")]
    if concurrency == 1 and ttft_means:
        prefill = mean(run["prompt_tokens"] / (value / 1000.0) for value in ttft_means)
    e2e, client_decode = _per_request_rates(records)
    per_wave_aggregate = [
        round(record["total_output_tokens"] / record["duration"], 1)
        for record in records
        if record.get("duration") and record.get("total_output_tokens")
    ]
    overlap = _overlap_metrics(records)
    client_queue_wait = _client_queue_wait_s(records)
    scenario, scenario_evidence = _scenario_evidence(records)
    # Omission eligibility for the source-verified-zero-omission witness: True only
    # when EVERY surviving request's cached_tokens was OMITTED (None). A cell with
    # any observed count (warm/mixed/cold-observed) is NOT an omission and must
    # never be promoted to derived-cold by a witness.
    cache_flat = [value for record in records for value in (record.get("cached_tokens") or [])]
    cache_all_omitted = bool(cache_flat) and all(value is None for value in cache_flat)
    dispersion = _iqr(e2e)
    return {
        "context_tokens": run["prompt_tokens"],
        "total_context_tokens": run["total_context_tokens"],
        "concurrency": concurrency,
        "output_tokens_requested": run["measurement_output_tokens"],
        "prefill_tok_s": round(prefill, 1) if prefill is not None else None,
        "decode_tok_s_per_stream": per_stream,
        "decode_tok_s_aggregate": None,
        "end_to_end_tok_s_per_stream": round(_percentile(e2e, 0.50), 1) if e2e else None,
        "client_decode_tok_s_per_stream": (
            round(_percentile(client_decode, 0.50), 1) if client_decode else None
        ),
        "wave_aggregate_tok_s": {
            "mean": round(mean(per_wave_aggregate), 1) if per_wave_aggregate else None,
            "per_wave": per_wave_aggregate,
            "basis": (
                "driver wave wall clock; absolute per-request dispatch times "
                + ("available (engine start_times)" if overlap else "unavailable")
            ),
        },
        "observed_max_stream_overlap": overlap["observed_max_stream_overlap"] if overlap else None,
        "mean_stream_overlap": overlap["mean_stream_overlap"] if overlap else None,
        "dispatch_skew_ms": overlap["dispatch_skew_ms"] if overlap else None,
        "queue_wait_s": None,
        "client_queue_wait_s": client_queue_wait,
        "admission_pattern": _admission_pattern(records),
        "serialized": None,
        "ttft_ms_p50": round(_percentile(pooled_ttft_ms, 0.50), 1) if pooled_ttft_ms else None,
        "ttft_ms_p95": round(_percentile(pooled_ttft_ms, 0.95), 1) if pooled_ttft_ms else None,
        "cached_prompt_tokens": cached_prompt,
        "prefix_cache_hit_rate": round(hit_rate, 4) if hit_rate is not None else None,
        "scenario": scenario,
        "scenario_intent": run["scenario"],
        "scenario_evidence": scenario_evidence,
        "cache_all_omitted": cache_all_omitted,
        "status": "candidate",
        "samples": len(records),
        "request_count_pooled": len(e2e),
        "cell_complete": cell_complete,
        "survivor_request_count": survivor_request_count if all_validated else None,
        "expected_request_count": expected_request_count if all_validated else None,
        "per_request_validation": (
            "protocol-v2 per-request validity present; invalid requests excluded "
            "from all rates/percentiles/overlap"
            if all_validated else
            "legacy record without per-request validity; left provisional, not "
            "upgraded to a per-request-verified cell"
        ),
        "end_to_end_dispersion": dispersion,
        "unstable": bool(dispersion["unstable"]) if dispersion else None,
        "repetition_shortfall": (
            None if len(records) >= 3
            else "insufficient repetition under §3.5 (needs >=3 waves; this cell has %d)" % len(records)
        ),
        "null_reasons": {
            "decode_tok_s_per_stream": (
                None if per_stream is not None
                else "output length 1 or engine reported no TPOT; per-token decode rate undefined"
            ),
            "decode_tok_s_aggregate": (
                "per-stream x concurrency is not an observed aggregate; requires a "
                "directly measured common decode window"
            ),
            "observed_max_stream_overlap": (
                None if overlap
                else "the driver emitted no absolute per-request start_times; "
                     "overlap needs absolute dispatch timestamps and is "
                     "client-observed, never engine batch"
            ),
            "engine_batch": (
                "only derivable from engine-side batch instrumentation, not from "
                "client stream timing"
            ),
            "serialized": (
                "not inferable; equal Cn/C1 wave throughput does not prove "
                "serialization (consistent with both a queue and a saturated batch)"
            ),
            "queue_wait_s": (
                "engine queue time (t_first - t_dispatch - engine prompt_time) is "
                "not obtainable from either bench path; no per-request engine "
                "prompt_time is exposed. client_queue_wait_s carries the client-side "
                "gate wait when the driver reports it"
            ),
            "prefix_cache_hit_rate": (
                None if hit_rate is not None else "engine reports no per-request cached_tokens"
            ),
        },
    }


# The benchmark-candidate row is the PRIVATE benchmark.schema row contract
# (schema/benchmark.schema.json rows.items, additionalProperties:false). Mirror
# its declared properties so convert() emits acceptance-ready rows; every rich
# enrichment observation row_from_records computes is preserved in the envelope's
# per-row diagnostics (never silently dropped). recompute_from_details and the
# public recorder stay fully rich (speed-sweep.schema allows additionalProperties).
_BENCHMARK_ROW_FIELDS = frozenset((
    "context_tokens", "total_context_tokens", "concurrency", "output_tokens_requested",
    "prefill_tok_s", "decode_tok_s_aggregate", "decode_tok_s_per_stream",
    "ttft_ms_p50", "ttft_ms_p95", "cached_prompt_tokens", "prefix_cache_hit_rate",
    "kv_cache_used_tokens", "kv_cache_usage_pct", "peak_vram_gb", "peak_power_w",
    "peak_temperature_c", "scenario", "status", "samples", "note",
))


def convert(sweep_dir: Path) -> dict:
    manifest = json.loads((sweep_dir / "manifest.json").read_text())
    protocol = manifest.get("protocol") or {}
    grouped: dict[tuple, list] = {}
    hashes: dict[tuple, set] = {}
    runs_by_key: dict[tuple, Mapping[str, Any]] = {}
    for run in manifest["runs"]:
        if run.get("status") != "completed":
            continue
        _require_exact_length(run, protocol)
        artifact_hash = run.get("artifact_sha256")
        if not artifact_hash:
            raise ConversionError(f"run {run.get('id')} has no raw artifact hash")
        detail = sweep_dir / run["detail_file"]
        record = json.loads(
            [line for line in detail.read_text().splitlines() if line.strip()][-1]
        )
        key = (run["total_context_tokens"], run["concurrency"], run["scenario"])
        grouped.setdefault(key, []).append(record)
        hashes.setdefault(key, set()).add(artifact_hash)
        runs_by_key[key] = run
    rows = []
    diagnostics = []
    for key in sorted(grouped):
        records = grouped[key]
        if len(records) < 2 or len(hashes[key]) < 2:
            raise ConversionError(
                f"point {key} lacks two unique hashed samples and cannot be converted"
            )
        rich = row_from_records(runs_by_key[key], records)
        # Project to the declared benchmark.schema contract; retain the full
        # enrichment in diagnostics (same order as rows, self-identified by point).
        rows.append({k: v for k, v in rich.items() if k in _BENCHMARK_ROW_FIELDS})
        diagnostics.append({
            "context_tokens": rich["context_tokens"], "concurrency": rich["concurrency"],
            "scenario": rich["scenario"],
            **{k: v for k, v in rich.items() if k not in _BENCHMARK_ROW_FIELDS},
        })
    return {
        "schema_version": "inference-index/benchmark-candidate-v1",
        "method": {
            "end_to_end_tok_s_per_stream": (
                "headline: median over pooled requests of output_tokens / "
                "(ttft + sum(itl)); measured from dispatch to last token"
            ),
            "decode_tok_s_per_stream": (
                "harness-observed steady decode pace: mean over samples of "
                "1000/mean_tpot_ms; per-stream decode pace, NOT end-to-end; null "
                "when output length 1 (TPOT undefined)"
            ),
            "client_decode_tok_s_per_stream": (
                "median over pooled requests of (output_tokens-1)/sum(itl); "
                "n-1 inter-token intervals, client-observed"
            ),
            "wave_aggregate_tok_s": (
                "per-wave total_output_tokens/duration (driver wave wall clock), "
                "with the mean and every wave value published; a wave-level "
                "throughput for C1-vs-Cn comparison, not a per-stream rate"
            ),
            "observed_max_stream_overlap": (
                "client-observed concurrent streams from absolute per-request "
                "start_times (engine- or driver-reported); NOT engine batch size; "
                "null-with-reason when the driver emits no start_times"
            ),
            "admission_pattern": (
                "descriptive within-wave TTFT-spread label (staircase / "
                "concurrent-admission / mixed) with raw sorted TTFTs; never a "
                "concurrency or batch number"
            ),
            "serialized": (
                "always null: not inferable from client stream timing or an "
                "aggregate ratio; needs engine-side batch instrumentation"
            ),
            "decode_tok_s_aggregate": (
                "null by construction: per-stream x concurrency is not an "
                "observed aggregate because staggered prefills desynchronize "
                "decode; record only a directly measured common-window value"
            ),
            "ttft_percentiles": "true percentiles over pooled raw per-request ttfts",
            "prefill_tok_s": "prompt tokens / TTFT at concurrency 1 only",
            "dispersion": (
                "end_to_end_dispersion carries p25/p50/p75/IQR; a cell is flagged "
                "unstable when IQR > 25% of the median; repetition_shortfall marks "
                "cells below the >=3-wave floor (§3.5)"
            ),
            "status": "candidate rows require review before acceptance",
        },
        "rows": rows,
        # Enrichment observations projected out of the schema-declared rows above,
        # preserved per row (documented scope: candidate-envelope diagnostics only).
        "diagnostics": diagnostics,
    }


def recompute_from_details(
    sweep_dir: Path, manifest: Mapping[str, Any]
) -> dict[str, dict]:
    """Recompute per-run point metrics from raw detail files, tolerant of
    interruption.

    Returns {run_id: metrics}. Never raises: a completed run whose detail file is
    missing or unparseable is simply absent from the result, so an interrupted
    sweep yields the rows it can honestly support instead of a wall of nulls.
    Unlike convert(), this does NOT require two unique-hashed samples per point.

    PROTOCOL-V2 is PER-CELL: each run_id's metrics come from ITS OWN detail
    record, so two samples at the same (context, concurrency, scenario) point keep
    their own timing, per-request validity and cache observations - a partial or
    cache-invalid sample NEVER borrows a complete sibling's metrics or counters.
    LEGACY (sglang-sweep-v1) keeps the pooled-point contract unchanged: a point's
    samples are grouped and share the pooled row across their run_ids.
    """
    def _load_record(run: Mapping[str, Any]):
        detail = sweep_dir / run.get("detail_file", f"raw/{run.get('id')}.jsonl")
        try:
            lines = [line for line in detail.read_text().splitlines() if line.strip()]
            return json.loads(lines[-1])
        except (OSError, ValueError, IndexError):
            return None

    recomputed: dict[str, dict] = {}
    protocol_v2 = manifest.get("schema_version") == "inference-index/omp-bench-client-v1"
    if protocol_v2:
        for run in manifest.get("runs", []):
            if run.get("status") != "completed":
                continue
            record = _load_record(run)
            if record is None:
                continue
            try:
                recomputed[run["id"]] = row_from_records(run, [record])
            except (KeyError, ZeroDivisionError, ConversionError, TypeError):
                continue
        return recomputed
    # Legacy pooled-point contract (unchanged).
    grouped: dict[tuple, list] = {}
    ids_by_key: dict[tuple, list[str]] = {}
    runs_by_key: dict[tuple, Mapping[str, Any]] = {}
    for run in manifest.get("runs", []):
        if run.get("status") != "completed":
            continue
        record = _load_record(run)
        if record is None:
            continue
        key = (run.get("total_context_tokens"), run.get("concurrency"), run.get("scenario"))
        grouped.setdefault(key, []).append(record)
        ids_by_key.setdefault(key, []).append(run["id"])
        runs_by_key[key] = run
    for key, records in grouped.items():
        try:
            row = row_from_records(runs_by_key[key], records)
        except (KeyError, ZeroDivisionError, ConversionError, TypeError):
            continue
        for run_id in ids_by_key[key]:
            recomputed[run_id] = row
    return recomputed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sweep-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(convert(args.sweep_dir), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
