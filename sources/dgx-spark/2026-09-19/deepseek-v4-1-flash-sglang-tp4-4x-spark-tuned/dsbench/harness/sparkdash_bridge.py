#!/usr/bin/env python3
"""sparkDash compatibility lane; excluded from the dsbench requirement score."""
from __future__ import annotations

import argparse
import json
import statistics
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any

if __package__:
    from .common import append_jsonl, canonical_json
else:
    from common import append_jsonl, canonical_json

PROMPTS = {
    "structured": "Count from 1 to 200. Output only the numbers, separated by spaces. No other text.",
    "prose": "Write a detailed step-by-step explanation of how a hash map works, including collision handling, resizing, and time complexity. Be thorough.",
    "code": "Output only Python source code. No comments, no docstrings, no markdown fences. Write functions clamp_00 through clamp_49. Each function is exactly:\ndef clamp_NN(x, lo=0, hi=1):\n    if x < lo:\n        return lo\n    if x > hi:\n        return hi\n    return x\nChange only the function name suffix (00, 01, … 49). One blank line between functions. No other text.",
}


def stream(base_url: str, model: str, prompt: str, tokens: int) -> dict[str, Any]:
    body = {
        "model": model, "messages": [{"role": "user", "content": prompt}],
        "max_tokens": tokens, "min_tokens": tokens, "ignore_eos": True,
        "temperature": 0, "top_p": 1, "stream": True,
        "stream_options": {"include_usage": True},
        "chat_template_kwargs": {"enable_thinking": False, "thinking": False, "thinking_mode": "disabled"},
    }
    request = urllib.request.Request(base_url.rstrip("/") + "/v1/chat/completions", canonical_json(body), {"Content-Type": "application/json"})
    sent = time.monotonic_ns()
    first = last = None
    usage = None
    with urllib.request.urlopen(request, timeout=600) as response:
        for raw in response:
            line = raw.decode("utf-8", errors="replace").strip()
            if not line.startswith("data:") or line == "data: [DONE]":
                continue
            event = json.loads(line[5:])
            usage = event.get("usage") or usage
            for choice in event.get("choices") or []:
                delta = choice.get("delta") or {}
                if delta.get("content") or delta.get("reasoning_content") or delta.get("reasoning"):
                    now = time.monotonic_ns()
                    first = first or now
                    last = now
    completion = (usage or {}).get("completion_tokens", 0)
    rate = (completion - 1) / ((last - first) / 1e9) if first and last and last > first else 0.0
    return {"decode_tps": rate, "completion_tokens": completion, "ttft_ms": (first - sent) / 1e6 if first else None, "first_ns": first, "last_ns": last}


def wave(base_url: str, model: str, prompt_type: str, concurrency: int, tokens: int) -> dict[str, Any]:
    base = PROMPTS[prompt_type]
    prompts = [base] if concurrency == 1 else [f"{base} (stream {index + 1}/{concurrency})" for index in range(concurrency)]
    barrier = threading.Barrier(concurrency)
    results: list[dict[str, Any] | None] = [None] * concurrency
    def worker(index: int) -> None:
        try:
            barrier.wait(timeout=30)
            results[index] = stream(base_url, model, prompts[index], tokens)
        except Exception as exc:
            results[index] = {"error": f"{type(exc).__name__}: {exc}"}
    threads = [threading.Thread(target=worker, args=(index,)) for index in range(concurrency)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    ok = [row for row in results if row and not row.get("error") and row.get("first_ns")]
    aggregate = sum(row["completion_tokens"] - 1 for row in ok) / ((max(row["last_ns"] for row in ok) - min(row["first_ns"] for row in ok)) / 1e9) if ok else 0.0
    return {
        "lane": "sparkDash compatibility; excluded from real-use requirement",
        "prompt_type": prompt_type, "concurrency": concurrency, "tokens": tokens,
        "per_stream_mean_tps": statistics.mean(row["decode_tps"] for row in ok) if ok else 0.0,
        "aggregate_wave_tps": aggregate,
        "ttft_median_ms": statistics.median(row["ttft_ms"] for row in ok) if ok else None,
        "ok": len(ok), "failed": concurrency - len(ok), "streams": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://10.10.10.12:8888")
    parser.add_argument("--model", default="deepseek-v4.1-flash")
    parser.add_argument("--types", default="prose,code,structured")
    parser.add_argument("--concurrencies", default="1,8")
    parser.add_argument("--reps", type=int, default=3)
    parser.add_argument("--tokens", type=int, default=256)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error(f"refusing to append to existing receipt: {args.output}")
    for prompt_type in args.types.split(","):
        stream(args.base_url, args.model, PROMPTS[prompt_type], 32)  # exact one warmup per prompt type
        for concurrency in map(int, args.concurrencies.split(",")):
            repetitions = args.reps if concurrency == 1 else 1
            waves = [wave(args.base_url, args.model, prompt_type, concurrency, args.tokens) for _ in range(repetitions)]
            chosen = sorted(waves, key=lambda row: row["aggregate_wave_tps"])[len(waves) // 2]
            chosen["all_aggregate_runs"] = [row["aggregate_wave_tps"] for row in waves]
            append_jsonl(args.output, chosen)
            print(f"{prompt_type} C{concurrency}: {chosen['aggregate_wave_tps']:.2f} aggregate tok/s")


if __name__ == "__main__":
    main()
