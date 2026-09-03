#!/usr/bin/env python3
"""Measure OpenAI-compatible chat prefill and decode at natural completion.

The runner reports the actual prompt and completion token counts returned by the
server, streaming TTFT, per-stream decode rate, aggregate output throughput,
and selected SGLang Prometheus counter deltas. It never sends an output-length
cap; every request runs until the model returns its natural finish condition.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import threading
import time
import urllib.request
from dataclasses import dataclass
from typing import Any


def request_json(url: str, body: dict[str, Any] | None = None, timeout: float = 30) -> Any:
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="GET" if data is None else "POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.load(response)


def request_text(url: str, timeout: float = 30) -> str:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return response.read().decode()


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(q * len(ordered)) - 1))
    return ordered[index]


def metric_snapshot(root: str) -> dict[str, float]:
    result: dict[str, float] = {}
    for line in request_text(f"{root}/metrics").splitlines():
        if not line or line.startswith("#") or not line.startswith("sglang:"):
            continue
        sample, raw_value = line.rsplit(" ", 1)
        if 'tp_rank="' in sample and 'tp_rank="0"' not in sample:
            continue
        try:
            value = float(raw_value)
        except ValueError:
            continue
        if sample.startswith("sglang:cache_hit_rate{"):
            result["cache_hit_rate"] = value
        elif sample.startswith("sglang:gen_throughput{"):
            result["gen_throughput"] = value
        elif sample.startswith("sglang:kv_used_tokens{"):
            result["kv_used_tokens"] = value
        elif sample.startswith("sglang:kv_available_tokens{"):
            result["kv_available_tokens"] = value
        elif sample.startswith("sglang:realtime_tokens_total{"):
            if 'mode="prefill_compute"' in sample:
                result["realtime_prefill_compute_tokens"] = value
            elif 'mode="decode"' in sample:
                result["realtime_decode_tokens"] = value
        elif sample.startswith("sglang:prefill_effective_tokens_total{"):
            for mode in ("input", "device_hit", "host_hit", "storage_hit"):
                if f'mode="{mode}"' in sample:
                    result[f"prefill_effective_{mode}_tokens"] = value
        elif sample.startswith("sglang:per_stage_req_latency_seconds_sum{") and 'stage="prefill_forward"' in sample:
            result["prefill_forward_seconds"] = value
        elif sample.startswith("sglang:prompt_tokens_total{") and 'is_streaming="true"' in sample:
            result["api_prompt_tokens"] = value
        elif sample.startswith("sglang:generation_tokens_total{") and 'is_streaming="true"' in sample:
            result["api_generation_tokens"] = value
    return result


def metric_delta(before: dict[str, float], after: dict[str, float]) -> dict[str, float]:
    gauges = {"cache_hit_rate", "gen_throughput", "kv_used_tokens", "kv_available_tokens"}
    keys = set(before) | set(after)
    return {
        key: after.get(key, 0.0) if key in gauges else after.get(key, 0.0) - before.get(key, 0.0)
        for key in sorted(keys)
    }


def token_count(root: str, model: str, content: str) -> int:
    result = request_json(
        f"{root}/tokenize",
        {"model": model, "messages": [{"role": "user", "content": content}]},
    )
    return int(result["count"])


def sized_prompt(root: str, model: str, target: int, salt: str) -> tuple[str, int]:
    unit = "The benchmark records deterministic serving behavior and hardware utilization. "
    low, high = 0, max(1, target)
    while token_count(root, model, f"Run {salt}. " + unit * high) < target:
        high *= 2
    while low + 1 < high:
        mid = (low + high) // 2
        count = token_count(root, model, f"Run {salt}. " + unit * mid)
        if count < target:
            low = mid
        else:
            high = mid
    candidates = []
    for repeats in {low, high}:
        content = f"Run {salt}. " + unit * repeats
        candidates.append((content, token_count(root, model, content)))
    return min(candidates, key=lambda item: abs(item[1] - target))


@dataclass
class StreamResult:
    index: int
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    ttft_seconds: float | None = None
    decode_seconds: float | None = None
    elapsed_seconds: float = 0.0
    finish_reason: str | None = None
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        row = vars(self).copy()
        if self.completion_tokens and self.decode_seconds and self.decode_seconds > 0:
            row["decode_tok_s"] = self.completion_tokens / self.decode_seconds
        else:
            row["decode_tok_s"] = None
        return row


def run_stream(
    index: int,
    start: threading.Barrier,
    url: str,
    model: str,
    content: str,
    rows: list[StreamResult],
) -> None:
    body = {
        "model": model,
        "messages": [{"role": "user", "content": content}],
        "temperature": 0.0,
        "stream": True,
        "stream_options": {"include_usage": True},
        "chat_template_kwargs": {"enable_thinking": False},
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
    )
    row = StreamResult(index=index)
    try:
        start.wait(timeout=30)
        begun = time.perf_counter()
        first = last = None
        with urllib.request.urlopen(req, timeout=600) as response:
            for raw in response:
                line = raw.decode(errors="replace").strip()
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                chunk = json.loads(payload)
                usage = chunk.get("usage")
                if usage:
                    row.prompt_tokens = int(usage.get("prompt_tokens") or row.prompt_tokens)
                    row.completion_tokens = int(usage.get("completion_tokens") or row.completion_tokens)
                    row.total_tokens = int(usage.get("total_tokens") or row.total_tokens)
                for choice in chunk.get("choices") or []:
                    delta = choice.get("delta") or {}
                    if delta.get("content") or delta.get("reasoning_content"):
                        now = time.perf_counter()
                        first = first or now
                        last = now
                    if choice.get("finish_reason"):
                        row.finish_reason = choice["finish_reason"]
        ended = time.perf_counter()
        row.elapsed_seconds = ended - begun
        row.ttft_seconds = None if first is None else first - begun
        row.decode_seconds = None if first is None else max((last or ended) - first, 1e-9)
    except Exception as exc:  # surfaced in the JSON result
        row.error = f"{type(exc).__name__}: {exc}"
    rows.append(row)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--endpoint", default="http://127.0.0.1:8000")
    parser.add_argument("--model", required=True)
    parser.add_argument("--concurrency", type=int, required=True)
    parser.add_argument("--isl", type=int, required=True, help="target input sequence length")
    parser.add_argument("--shared-prefix", action="store_true", help="reuse one prompt to exercise prefix-cache hits")
    parser.add_argument("--summary-only", action="store_true", help="omit per-request rows from stdout")
    parser.add_argument("--label", required=True)
    args = parser.parse_args()

    root = args.endpoint.rstrip("/")
    prompts: list[tuple[str, int]] = []
    for index in range(args.concurrency):
        salt = args.label if args.shared_prefix else f"{args.label}-{index}"
        prompts.append(sized_prompt(root, args.model, args.isl, salt))

    before = metric_snapshot(root)
    barrier = threading.Barrier(args.concurrency + 1)
    rows: list[StreamResult] = []
    threads = [
        threading.Thread(
            target=run_stream,
            args=(index, barrier, f"{root}/v1/chat/completions", args.model, prompts[index][0], rows),
        )
        for index in range(args.concurrency)
    ]
    for thread in threads:
        thread.start()
    wall_start = time.perf_counter()
    barrier.wait(timeout=30)
    for thread in threads:
        thread.join(timeout=660)
    wall = time.perf_counter() - wall_start
    after = metric_snapshot(root)
    delta = metric_delta(before, after)

    complete = [row for row in rows if row.error is None]
    prompt_tokens = sum(row.prompt_tokens for row in complete)
    completion_tokens = sum(row.completion_tokens for row in complete)
    decode_rates = [row.completion_tokens / row.decode_seconds for row in complete if row.decode_seconds]
    ttfts = [row.ttft_seconds for row in complete if row.ttft_seconds is not None]
    prefill_seconds = delta.get("prefill_forward_seconds", 0.0)
    prefill_compute_tokens = delta.get("realtime_prefill_compute_tokens", 0.0)
    result = {
        "label": args.label,
        "requested": {
            "concurrency": args.concurrency,
            "isl": args.isl,
            "completion_policy": "natural",
            "shared_prefix": args.shared_prefix,
        },
        "measured": {
            "wall_seconds": wall,
            "ok_requests": len(complete),
            "failed_requests": len(rows) - len(complete),
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "aggregate_output_tok_s": completion_tokens / wall if wall else None,
            "output_tokens_per_minute": completion_tokens / wall * 60 if wall else None,
            "total_api_tokens_per_minute": (prompt_tokens + completion_tokens) / wall * 60 if wall else None,
            "per_stream_decode_tok_s_median": statistics.median(decode_rates) if decode_rates else None,
            "per_stream_decode_tok_s_p05": percentile(decode_rates, 0.05),
            "ttft_seconds_median": statistics.median(ttfts) if ttfts else None,
            "ttft_seconds_p95": percentile(ttfts, 0.95),
            "server_prefill_compute_tok_s": prefill_compute_tokens / prefill_seconds if prefill_seconds > 0 else None,
            "cache_hit_rate": delta.get("cache_hit_rate"),
            "server_gen_throughput_last": delta.get("gen_throughput"),
        },
        "server_metric_delta": delta,
        "tokenized_prompt_counts": [count for _, count in prompts],
        "requests": [] if args.summary_only else [row.as_dict() for row in sorted(rows, key=lambda item: item.index)],
    }
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
