#!/usr/bin/env python3
"""Analyze dsbench receipts, bootstrap clusters, and apply REPORT.md requirements."""
from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

if __package__:
    from .common import cluster_bootstrap, geometric_mean, paired_bootstrap, percentile, read_jsonl, write_json_atomic
else:
    from common import cluster_bootstrap, geometric_mean, paired_bootstrap, percentile, read_jsonl, write_json_atomic

CATEGORY_WEIGHTS = {"agentic": 0.35, "code": 0.30, "prose": 0.20, "structured": 0.15}
TARGETS = {
    "0": {1: (68.0, 68.0), 4: (150.0, 37.5), 8: (190.0, 23.75)},
    "32k": {1: (65.0, 65.0), 4: (145.0, 36.25), 8: (185.0, 23.1)},
    "128k": {1: (62.0, 62.0), 4: (138.0, 34.5), 8: (175.0, 21.9)},
    "400k": {1: (58.0, 58.0), 4: (130.0, 32.5), 8: (165.0, 20.6)},
}
GM_TARGETS = {1: (63.0, 63.0), 4: (140.0, 35.0), 8: (180.0, 22.5)}


def discover(paths: Iterable[Path], filename: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in paths:
        if path.is_file() and path.name == filename:
            rows.extend(read_jsonl(path))
        elif path.is_dir():
            for candidate in sorted(path.rglob(filename)):
                rows.extend(read_jsonl(candidate))
    return rows


def discover_json(paths: Iterable[Path], filename: str) -> list[dict[str, Any]]:
    rows = []
    for path in paths:
        candidates = [path] if path.is_file() and path.name == filename else (sorted(path.rglob(filename)) if path.is_dir() else [])
        for candidate in candidates:
            rows.append(json.loads(candidate.read_text(encoding="utf-8")))
    return rows


def assert_manifest_compatibility(manifests: list[dict[str, Any]], labels: list[str]) -> None:
    protocol_keys = ("model_id", "model_revision", "tokenizer_hash", "chat_template_hash", "harness_commit", "prompts_sha256", "contexts_index_sha256", "profiles", "tier", "cluster_inventory")
    series_keys = protocol_keys + ("engine_commit", "image_id", "server_args", "engine_environment", "git_commits")
    for label in labels:
        rows = [row for row in manifests if row.get("label") == label]
        if not rows:
            raise ValueError(f"no manifest.json found for label {label}")
        if any(row.get("smoke_skipped") or not row.get("warmup_waves") for row in rows):
            raise ValueError(f"label {label} contains development runs with smoke or warmup skipped")
        identity = {key: rows[0].get(key) for key in series_keys}
        for row in rows[1:]:
            if {key: row.get(key) for key in series_keys} != identity:
                raise ValueError(f"label {label} contains incompatible benchmark identities")
    if len(labels) == 2:
        left = next(row for row in manifests if row.get("label") == labels[0])
        right = next(row for row in manifests if row.get("label") == labels[1])
        mismatches = [key for key in protocol_keys if left.get(key) != right.get(key)]
        if mismatches:
            raise ValueError(f"A/B protocol identity mismatch: {mismatches}")


def median_or_none(values: Iterable[float | None]) -> float | None:
    usable = [float(value) for value in values if value is not None]
    return statistics.median(usable) if usable else None


def block_scores(cells: list[dict[str, Any]], requests: list[dict[str, Any]], label: str) -> list[dict[str, Any]]:
    valid_ids = {cell["cell_id"] for cell in cells if cell.get("valid") and cell.get("block_id") != "warmup" and cell.get("label") == label}
    accepted_requests = [row for row in requests if row.get("cell_id") in valid_ids and row.get("label") == label]
    req_groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    cell_groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in accepted_requests:
        key = (row.get("boot_id"), row.get("block_id"), row["context"], int(row["concurrency"]), row["profile"])
        req_groups[key].append(row)
    for row in cells:
        if row.get("cell_id") not in valid_ids:
            continue
        key = (row.get("boot_id"), row.get("block_id"), row["context"], int(row["concurrency"]), row["profile"])
        cell_groups[key].append(row)
    per_profile: list[dict[str, Any]] = []
    for key, reqs in req_groups.items():
        boot, block, context, concurrency, profile = key
        category_values = {}
        for category in CATEGORY_WEIGHTS:
            category_values[category] = median_or_none(
                row.get("metrics", {}).get("decode_tps") for row in reqs if row.get("category") == category
            )
        present = [(category_values[name], CATEGORY_WEIGHTS[name]) for name in CATEGORY_WEIGHTS if category_values[name] is not None]
        stream_score = geometric_mean([value for value, _ in present], [weight for _, weight in present]) if present else None
        waves = cell_groups.get(key, [])
        raw_aggregate = median_or_none(row.get("metrics", {}).get("aggregate_wave_tps") for row in waves)
        unweighted_stream = median_or_none(row.get("metrics", {}).get("decode_tps") for row in reqs)
        if concurrency == 1:
            aggregate = stream_score
        else:
            aggregate = raw_aggregate * stream_score / unweighted_stream if raw_aggregate and stream_score and unweighted_stream else None
        p10 = percentile([float(row["metrics"]["decode_tps"]) for row in reqs if row.get("metrics", {}).get("decode_tps") is not None], 0.10)
        per_profile.append({
            "boot_id": boot, "block_id": block, "context": context, "concurrency": concurrency,
            "profile": profile, "stream_score": stream_score, "aggregate_score": aggregate,
            "raw_aggregate_score": raw_aggregate, "p10_stream": p10, "category_scores": category_values,
        })
    # Headline score combines S0 and S1-omp equally. G0 stays informational.
    combined: list[dict[str, Any]] = []
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in per_profile:
        groups[(row["boot_id"], row["block_id"], row["context"], row["concurrency"])].append(row)
    for key, rows in groups.items():
        panels = {row["profile"]: row for row in rows}
        if "S0" not in panels or "S1-omp" not in panels:
            continue
        s0, s1 = panels["S0"], panels["S1-omp"]
        combined.append({
            "boot_id": key[0], "block_id": key[1], "context": key[2], "concurrency": key[3],
            "stream_score": geometric_mean([s0["stream_score"], s1["stream_score"]]) if s0["stream_score"] and s1["stream_score"] else None,
            "aggregate_score": geometric_mean([s0["aggregate_score"], s1["aggregate_score"]]) if s0["aggregate_score"] and s1["aggregate_score"] else None,
            "p10_stream": min(value for value in (s0["p10_stream"], s1["p10_stream"]) if value is not None),
            "profiles": panels,
        })
    return combined


def confidence(rows: list[dict[str, Any]], key: str, samples: int, seed: int) -> dict[str, float] | None:
    usable = [row for row in rows if row.get(key) is not None]
    if not usable:
        return None
    point, low, high = cluster_bootstrap(usable, key, samples=samples, seed=seed)
    return {"median": point, "ci95_low": low, "ci95_high": high, "n_blocks": len(usable), "n_boots": len({row["boot_id"] for row in usable})}


def requirement_results(scores: list[dict[str, Any]], samples: int, seed: int, blocked: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results = []
    for context, targets in TARGETS.items():
        for concurrency, (aggregate_target, stream_target) in targets.items():
            rows = [row for row in scores if row["context"] == context and row["concurrency"] == concurrency]
            aggregate = confidence(rows, "aggregate_score", samples, seed + concurrency)
            stream = confidence(rows, "stream_score", samples, seed + concurrency + 100)
            p10 = median_or_none(row.get("p10_stream") for row in rows)
            has_blocked = any(row.get("context") == context and int(row.get("concurrency", -1)) == concurrency for row in blocked)
            sample_sufficient = bool(aggregate and stream and aggregate["n_blocks"] >= 15 and stream["n_blocks"] >= 15 and aggregate["n_boots"] >= 3 and stream["n_boots"] >= 3)
            passed = bool(
                aggregate and stream
                and aggregate["median"] >= aggregate_target
                and aggregate["ci95_low"] >= aggregate_target * 0.95
                and stream["median"] >= stream_target
                and stream["ci95_low"] >= stream_target * 0.95
                and p10 is not None and p10 >= stream_target * 0.75
                and not has_blocked
                and sample_sufficient
            )
            results.append({
                "context": context, "concurrency": concurrency,
                "aggregate_target": aggregate_target, "stream_target": stream_target,
                "aggregate": aggregate, "stream": stream, "p10_stream": p10,
                "blocked_cell": has_blocked, "pass": passed,
                "sample_sufficient": sample_sufficient,
            })
    # Equal-context geometric means are point summaries. CI is conservatively the GM of context LCBs.
    for concurrency, (aggregate_target, stream_target) in GM_TARGETS.items():
        rows = [row for row in results if row["concurrency"] == concurrency and row["context"] != "equal-context-gm"]
        aggregate_points = [row["aggregate"]["median"] for row in rows if row["aggregate"]]
        aggregate_lows = [row["aggregate"]["ci95_low"] for row in rows if row["aggregate"]]
        stream_points = [row["stream"]["median"] for row in rows if row["stream"]]
        stream_lows = [row["stream"]["ci95_low"] for row in rows if row["stream"]]
        result = {
            "context": "equal-context-gm", "concurrency": concurrency,
            "aggregate_target": aggregate_target, "stream_target": stream_target,
            "aggregate": {"median": geometric_mean(aggregate_points), "ci95_low": geometric_mean(aggregate_lows)} if len(aggregate_points) == 4 else None,
            "stream": {"median": geometric_mean(stream_points), "ci95_low": geometric_mean(stream_lows)} if len(stream_points) == 4 else None,
        }
        result["pass"] = bool(all(row["pass"] for row in rows) and result["aggregate"] and result["stream"] and result["aggregate"]["median"] >= aggregate_target and result["aggregate"]["ci95_low"] >= aggregate_target * .95 and result["stream"]["median"] >= stream_target and result["stream"]["ci95_low"] >= stream_target * .95)
        results.append(result)
    return results


def paired_deltas(cells: list[dict[str, Any]], baseline: str, candidate: str, samples: int, seed: int) -> list[dict[str, Any]]:
    usable = [row for row in cells if row.get("valid") and row.get("block_id") != "warmup" and row.get("label") in (baseline, candidate)]
    expected_counts: dict[tuple[Any, ...], int] = defaultdict(int)
    for row in usable:
        expected_counts[(row.get("boot_id"), row.get("block_id"), row["profile"], row["context"], int(row["concurrency"]), row["label"])] += 1
    groups: dict[tuple[Any, ...], dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in usable:
        key = (row.get("pair_id"), row.get("boot_id"), row.get("block_id"), row["profile"], row["context"], int(row["concurrency"]), row.get("wave"), tuple(row.get("request_ids", [])), tuple(row.get("context_request_hashes", [])))
        groups[key][row["label"]] = row
    observations: list[dict[str, Any]] = []
    for key, arms in groups.items():
        if baseline not in arms or candidate not in arms:
            continue
        drift_values = []
        for host in set(arms[baseline].get("node_telemetry_summary", {})) & set(arms[candidate].get("node_telemetry_summary", {})):
            for hardware_metric in ("sm_clock_mhz", "power_w"):
                left_hw = arms[baseline].get("node_telemetry_summary", {}).get(host, {}).get(hardware_metric, {}).get("median")
                right_hw = arms[candidate].get("node_telemetry_summary", {}).get(host, {}).get(hardware_metric, {}).get("median")
                if left_hw and right_hw:
                    drift_values.append(abs(right_hw - left_hw) / left_hw * 100)
        hardware_drift = max(drift_values, default=None)
        for metric in ("aggregate_wave_tps", "median_stream_tps"):
            left = arms[baseline].get("metrics", {}).get(metric)
            right = arms[candidate].get("metrics", {}).get(metric)
            if left and right:
                observations.append({
                    "pair_id": key[0], "boot_id": key[1], "block_id": key[2], "profile": key[3], "context": key[4], "concurrency": key[5],
                    "metric": metric, "baseline": left, "candidate": right, "delta_pct": (right - left) / left * 100,
                    "hardware_drift_pct": hardware_drift,
                })
    collapsed_groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in observations:
        collapsed_groups[(row["boot_id"], row["block_id"], row["profile"], row["context"], row["concurrency"], row["metric"])].append(row)
    collapsed = []
    for key, rows in collapsed_groups.items():
        baseline_count = expected_counts[(key[0], key[1], key[2], key[3], key[4], baseline)]
        candidate_count = expected_counts[(key[0], key[1], key[2], key[3], key[4], candidate)]
        if baseline_count != candidate_count or len(rows) != baseline_count:
            continue
        collapsed.append({
            "boot_id": key[0], "block_id": key[1], "profile": key[2], "context": key[3], "concurrency": key[4], "metric": key[5],
            "delta_pct": statistics.median(row["delta_pct"] for row in rows),
            "hardware_drift_pct": max((row["hardware_drift_pct"] for row in rows if row.get("hardware_drift_pct") is not None), default=None),
        })
    output = []
    keys = sorted({(row["profile"], row["context"], row["concurrency"], row["metric"]) for row in collapsed})
    for profile, context, concurrency, metric in keys:
        rows = [row for row in collapsed if (row["profile"], row["context"], row["concurrency"], row["metric"]) == (profile, context, concurrency, metric)]
        point, low, high = paired_bootstrap(rows, samples=samples, seed=seed)
        max_drift = max((row["hardware_drift_pct"] for row in rows if row.get("hardware_drift_pct") is not None), default=None)
        n_boots = len({row["boot_id"] for row in rows})
        required_pairs = 40 if point < 5.0 else 15
        sample_sufficient = len(rows) >= required_pairs and n_boots >= 3
        output.append({"profile": profile, "context": context, "concurrency": concurrency, "metric": metric, "median_delta_pct": point, "ci95_low": low, "ci95_high": high, "n_pairs": len(rows), "n_boots": n_boots, "required_pairs": required_pairs, "sample_sufficient": sample_sufficient, "max_clock_power_drift_pct": max_drift, "hardware_comparable": max_drift is not None and max_drift <= 2.0, "faster_over_3pct": low > 3.0 and max_drift is not None and max_drift <= 2.0 and sample_sufficient})
    return output


def guardrails(requests: list[dict[str, Any]], cells: list[dict[str, Any]], baseline: str, candidate: str) -> list[dict[str, Any]]:
    valid_by_label = {label: {cell["cell_id"] for cell in cells if cell.get("valid") and cell.get("label") == label} for label in (baseline, candidate)}
    output = []
    dimensions = sorted({(row.get("category"), row.get("profile"), row.get("context"), int(row.get("concurrency", 0))) for row in requests if row.get("label") in (baseline, candidate)})
    for category, profile, context, concurrency in dimensions:
        values = {}
        for label in (baseline, candidate):
            rows = [row for row in requests if row.get("label") == label and row.get("cell_id") in valid_by_label[label] and (row.get("category"), row.get("profile"), row.get("context"), int(row.get("concurrency", 0))) == (category, profile, context, concurrency)]
            values[label] = {
                "decode": median_or_none(row.get("metrics", {}).get("decode_tps") for row in rows),
                "ttft": median_or_none(row.get("metrics", {}).get("ttft_s") for row in rows),
                "gap_p95": median_or_none(row.get("metrics", {}).get("inter_event_gap_p95_s") for row in rows),
            }
        regressions = {}
        for metric, limit in (("decode", -3.0), ("ttft", 10.0), ("gap_p95", 10.0)):
            left, right = values[baseline][metric], values[candidate][metric]
            delta = (right - left) / left * 100 if left and right else None
            regressions[metric] = {"delta_pct": delta, "pass": delta is not None and (delta >= limit if metric == "decode" else delta <= limit)}
        output.append({"category": category, "profile": profile, "context": context, "concurrency": concurrency, "values": values, "checks": regressions, "pass": all(check["pass"] for check in regressions.values())})
    engine_dimensions = sorted({(row.get("profile"), row.get("context"), int(row.get("concurrency", 0))) for row in cells if row.get("label") in (baseline, candidate)})
    for profile, context, concurrency in engine_dimensions:
        values = {}
        for label in (baseline, candidate):
            rows = [row for row in cells if row.get("label") == label and row.get("valid") and (row.get("profile"), row.get("context"), int(row.get("concurrency", 0))) == (profile, context, concurrency)]
            values[label] = median_or_none(row.get("metrics", {}).get("engine_step_gap_p95_s") for row in rows)
        left, right = values[baseline], values[candidate]
        delta = (right - left) / left * 100 if left and right else None
        output.append({"category": "__engine_step_gap__", "profile": profile, "context": context, "concurrency": concurrency, "values": values, "checks": {"engine_step_gap_p95": {"delta_pct": delta, "pass": delta is not None and delta <= 10.0}}, "pass": delta is not None and delta <= 10.0})
    return output


def spec_summary(cells: list[dict[str, Any]], label: str) -> list[dict[str, Any]]:
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for cell in cells:
        if cell.get("valid") and cell.get("label") == label and cell.get("block_id") != "warmup":
            groups[(cell["profile"], cell["context"], int(cell["concurrency"]))].append(cell)
    output = []
    for key, rows in sorted(groups.items()):
        output.append({
            "profile": key[0], "context": key[1], "concurrency": key[2],
            "steps_per_s": median_or_none(row.get("metrics", {}).get("steps_per_s") for row in rows),
            "committed_tokens_per_step": median_or_none(row.get("metrics", {}).get("committed_tokens_per_step") for row in rows),
            "acceptance_ratio": median_or_none(row.get("metrics", {}).get("acceptance_ratio") for row in rows),
            "steady_server_tps": median_or_none(row.get("metrics", {}).get("steady_server_tps") for row in rows),
            "verify_length_mix": dict(sum((CounterLike(row.get("metrics", {}).get("verify_length_mix", {})) for row in rows), CounterLike())),
        })
    return output


def prompt_qualification(requests: list[dict[str, Any]], cells: list[dict[str, Any]], label: str) -> list[dict[str, Any]]:
    valid_ids = {cell["cell_id"] for cell in cells if cell.get("valid") and cell.get("label") == label}
    output = []
    prompt_ids = sorted({row.get("prompt_id") for row in requests if row.get("label") == label})
    for prompt_id in prompt_ids:
        for profile, minimum, cap in (("S0", 512, 1024), ("S1-omp", 768, 2048)):
            rows = [row for row in requests if row.get("cell_id") in valid_ids and row.get("prompt_id") == prompt_id and row.get("profile") == profile and row.get("context") == "0" and int(row.get("concurrency", 0)) == 1]
            tokens = [row.get("metrics", {}).get("completion_tokens") for row in rows if row.get("metrics", {}).get("completion_tokens") is not None]
            median = statistics.median(tokens) if tokens else None
            cap_fraction = sum(value >= cap for value in tokens) / len(tokens) if tokens else None
            output.append({"prompt_id": prompt_id, "profile": profile, "median_completion_tokens": median, "minimum": minimum, "cap_fraction": cap_fraction, "pass": median is not None and median >= minimum and cap_fraction < 0.20})
    return output


def absolute_category_floors(requests: list[dict[str, Any]], cells: list[dict[str, Any]], label: str) -> list[dict[str, Any]]:
    valid_ids = {cell["cell_id"] for cell in cells if cell.get("valid") and cell.get("label") == label}
    output = []
    for context, code_floor, prose_floor in (("0", 72.0, 40.0), ("400k", 62.0, 34.0)):
        for group, categories, target in (("agentic_code", {"agentic", "code"}, code_floor), ("prose", {"prose"}, prose_floor)):
            profile_values = []
            for profile in ("S0", "S1-omp"):
                values = [row.get("metrics", {}).get("decode_tps") for row in requests if row.get("cell_id") in valid_ids and row.get("profile") == profile and row.get("context") == context and int(row.get("concurrency", 0)) == 1 and row.get("category") in categories]
                median = median_or_none(values)
                if median is not None:
                    profile_values.append(median)
            score = geometric_mean(profile_values) if len(profile_values) == 2 else None
            output.append({"context": context, "group": group, "score": score, "target": target, "pass": score is not None and score >= target})
    return output


class CounterLike(dict):
    def __add__(self, other: dict[str, Any]) -> "CounterLike":
        result = CounterLike(self)
        for key, value in other.items():
            result[key] = result.get(key, 0) + value
        return result
    __radd__ = __add__


def markdown(summary: dict[str, Any]) -> str:
    lines = ["# dsbench summary", "", f"Label: `{summary['label']}`. Accepted cells: {summary['accepted_cells']}; invalid attempts: {summary['invalid_cells']}; blocked cells: {summary['blocked_cells']}.", "", "Benchmark requests use bounded `max_tokens` only for measurement; production omp remains uncapped.", "", "## Requirement table", "", "| context | C | aggregate (95% CI) / target | median stream (95% CI) / target | p10 | result |", "|---:|---:|---:|---:|---:|:---:|"]
    def fmt(metric: dict[str, Any] | None) -> str:
        if not metric or metric.get("median") is None:
            return "missing"
        if metric.get("ci95_high") is None:
            return f"{metric['median']:.2f} (LCB {metric.get('ci95_low', float('nan')):.2f})"
        return f"{metric['median']:.2f} [{metric['ci95_low']:.2f}, {metric['ci95_high']:.2f}]"
    for row in summary["requirements"]:
        lines.append(f"| {row['context']} | {row['concurrency']} | {fmt(row.get('aggregate'))} / {row['aggregate_target']:.2f} | {fmt(row.get('stream'))} / {row['stream_target']:.2f} | {row.get('p10_stream') if row.get('p10_stream') is not None else '—'} | {'PASS' if row['pass'] else 'FAIL'} |")
    lines += ["", "## Speculative decode decomposition", "", "| profile | context | C | steps/s | committed/step | accept rate | server tok/s |", "|---|---:|---:|---:|---:|---:|---:|"]
    for row in summary["spec_decomposition"]:
        values = [row.get(name) for name in ("steps_per_s", "committed_tokens_per_step", "acceptance_ratio", "steady_server_tps")]
        rendered = ["—" if value is None else f"{value:.3f}" for value in values]
        lines.append(f"| {row['profile']} | {row['context']} | {row['concurrency']} | " + " | ".join(rendered) + " |")
    lines += ["", "## Correctness and category guardrails", "", f"Prompt output qualification: {'PASS' if summary.get('prompt_qualification_pass') else 'FAIL'}.", "", "| context | category group | score | floor | result |", "|---:|---|---:|---:|:---:|"]
    for row in summary.get("absolute_category_floors", []):
        score = "—" if row["score"] is None else f"{row['score']:.2f}"
        lines.append(f"| {row['context']} | {row['group']} | {score} | {row['target']:.2f} | {'PASS' if row['pass'] else 'FAIL'} |")
    if summary.get("paired_deltas"):
        lines += ["", "## Paired A/B deltas", "", "| profile | context | C | metric | median delta | 95% CI | decision |", "|---|---:|---:|---|---:|---:|---|"]
        for row in summary["paired_deltas"]:
            lines.append(f"| {row['profile']} | {row['context']} | {row['concurrency']} | {row['metric']} | {row['median_delta_pct']:.2f}% | [{row['ci95_low']:.2f}%, {row['ci95_high']:.2f}%] | {'accepted faster' if row.get('optimization_accepted') else 'not established'} |")
        failed_guardrails = sum(not row.get("pass", False) for row in summary.get("guardrails", []))
        lines += ["", f"Relative category/TTFT/inter-event-gap guardrails failing: {failed_guardrails}."]
    if summary.get("sparkdash_compatibility"):
        lines += ["", "## sparkDash compatibility appendix", "", "Compatibility-only; excluded from every real-use score.", "", "| type | C | per-stream mean | aggregate | TTFT ms |", "|---|---:|---:|---:|---:|"]
        for row in summary["sparkdash_compatibility"]:
            lines.append(f"| {row['prompt_type']} | {row['concurrency']} | {row['per_stream_mean_tps']:.2f} | {row['aggregate_wave_tps']:.2f} | {row.get('ttft_median_ms') if row.get('ttft_median_ms') is not None else '—'} |")
    lines += ["", "Invalid attempts remain in the raw receipts and never enter accepted-score calculations. A failed/blocked requirement is not converted into a best-of-retries result.", ""]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--label", required=True)
    parser.add_argument("--baseline-label")
    parser.add_argument("--candidate-label")
    parser.add_argument("--bootstrap-samples", type=int, default=10_000)
    parser.add_argument("--seed", type=int, default=41)
    parser.add_argument("--json-output", type=Path, default=Path("summary.json"))
    parser.add_argument("--markdown-output", type=Path, default=Path("summary.md"))
    parser.add_argument("--sparkdash", type=Path, action="append", default=[], help="sparkdash_bridge JSONL receipt")
    args = parser.parse_args()
    cells = discover(args.paths, "cells.jsonl")
    requests = discover(args.paths, "requests.jsonl")
    blocked = discover(args.paths, "blocked.jsonl")
    manifests = discover_json(args.paths, "manifest.json")
    comparison_labels = [args.label]
    if args.baseline_label and args.candidate_label:
        comparison_labels = [args.baseline_label, args.candidate_label]
    assert_manifest_compatibility(manifests, comparison_labels)
    scores = block_scores(cells, requests, args.label)
    selected_cells = [row for row in cells if row.get("label") == args.label and row.get("block_id") != "warmup"]
    summary: dict[str, Any] = {
        "schema": "dsbench.analysis.v1", "label": args.label,
        "accepted_cells": sum(bool(row.get("valid")) for row in selected_cells),
        "invalid_cells": sum(not bool(row.get("valid")) for row in selected_cells),
        "blocked_cells": sum(row.get("label") == args.label for row in blocked),
        "requirements": requirement_results(scores, args.bootstrap_samples, args.seed, [row for row in blocked if row.get("label", args.label) == args.label]),
        "spec_decomposition": spec_summary(cells, args.label),
        "prompt_qualification": prompt_qualification(requests, cells, args.label),
        "absolute_category_floors": absolute_category_floors(requests, cells, args.label),
        "per_request": [{"cell_id": row.get("cell_id"), "prompt_id": row.get("prompt_id"), "profile": row.get("profile"), "context": row.get("context"), "concurrency": row.get("concurrency"), **row.get("metrics", {})} for row in requests if row.get("label") == args.label and row.get("block_id") != "warmup"],
        "per_wave": [{"cell_id": row.get("cell_id"), "profile": row.get("profile"), "context": row.get("context"), "concurrency": row.get("concurrency"), "valid": row.get("valid"), "invalid_reasons": row.get("invalid_reasons"), **row.get("metrics", {})} for row in selected_cells],
        "sparkdash_compatibility": [row for path in args.sparkdash for row in read_jsonl(path)],
    }
    qualification_pass = bool(summary["prompt_qualification"]) and all(row["pass"] for row in summary["prompt_qualification"])
    summary["prompt_qualification_pass"] = qualification_pass
    if not qualification_pass:
        for row in summary["requirements"]:
            row["pass"] = False
            row["prompt_qualification_failed"] = True
    for floor in summary["absolute_category_floors"]:
        if not floor["pass"]:
            for row in summary["requirements"]:
                if row["context"] == floor["context"] and row["concurrency"] == 1:
                    row["pass"] = False
                    row.setdefault("category_floor_failures", []).append(floor["group"])
    if args.baseline_label and args.candidate_label:
        summary["paired_deltas"] = paired_deltas(cells, args.baseline_label, args.candidate_label, args.bootstrap_samples, args.seed)
        summary["guardrails"] = guardrails(requests, cells, args.baseline_label, args.candidate_label)
        summary["guardrails_pass"] = bool(summary["guardrails"]) and all(row["pass"] for row in summary["guardrails"])
        for row in summary["paired_deltas"]:
            row["optimization_accepted"] = row["faster_over_3pct"] and summary["guardrails_pass"]
    write_json_atomic(args.json_output, summary)
    args.markdown_output.write_text(markdown(summary), encoding="utf-8")
    print(args.markdown_output)


if __name__ == "__main__":
    main()
