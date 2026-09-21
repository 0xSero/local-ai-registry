#!/usr/bin/env python3
"""Concurrent-window throughput from dsbench receipts.

`aggregate_wave_tps` spans the earliest first token to the latest last token, so with EOS respected
(streams of very different lengths) it includes a long tail where only one stream is still decoding.
That is not comparable with sustained-load aggregates such as LIL or sparkDash.

This computes, per cell, the throughput over the window in which ALL C streams were decoding:
    window = [max_i(first_token_i), min_i(last_token_i)]
    tokens  = sum over streams of tokens emitted inside that window (from SSE event timestamps)
    concurrent_window_tps = tokens / window_length
plus the per-stream rate inside that window. Requires no re-run: it reads requests.jsonl.

Usage: concurrent_window.py <run-dir> [<run-dir> ...]
"""
import json, sys, statistics
from pathlib import Path


def stream_events(row):
    """(monotonic seconds, tokens_in_event) for events that carried generated text."""
    out = []
    previous = None
    for event in row.get("events") or []:
        kind = event.get("kind") or ""
        if kind in ("metadata", "done") or not kind:
            continue
        usage = ((event.get("data") or {}).get("usage") or {})
        completion = usage.get("completion_tokens")
        tokens = None
        if isinstance(completion, int) and completion > 0:
            tokens = completion - previous if previous is not None else completion
            previous = completion
        out.append((event["monotonic_ns"] / 1e9, tokens))
    return out


def cell_concurrent_window(rows):
    series = [stream_events(row) for row in rows]
    series = [s for s in series if len(s) >= 2]
    if len(series) != len(rows) or not series:
        return None
    start = max(s[0][0] for s in series)
    end = min(s[-1][0] for s in series)
    if end <= start:
        return None
    total = 0.0
    per_stream = []
    for events, row in zip(series, rows):
        inside = [(t, n) for t, n in events if start <= t <= end]
        if len(inside) < 2:
            return None
        counted = [n for _, n in inside[1:] if n]
        if counted:
            tokens = float(sum(counted))
        else:  # no per-event usage: fall back to the stream's average token rate
            metrics = row.get("metrics") or {}
            rate = metrics.get("decode_tps")
            if not rate:
                return None
            tokens = rate * (inside[-1][0] - inside[0][0])
        span = inside[-1][0] - inside[0][0]
        if span <= 0:
            return None
        total += tokens
        per_stream.append(tokens / span)
    return dict(window_s=round(end - start, 2), concurrent_window_tps=round(total / (end - start), 1),
                median_stream_tps=round(statistics.median(per_stream), 1), streams=len(per_stream))


def main():
    for root in sys.argv[1:]:
        root = Path(root)
        cells = {}
        for line in (root / "requests.jsonl").read_text().splitlines():
            row = json.loads(line)
            cells.setdefault(row.get("cell_id"), []).append(row)
        print(f"# {root.name}")
        print(f"{'cell':34s} {'C':>2s} {'window_s':>9s} {'conc_tps':>9s} {'med_stream':>11s}")
        for cell_id, rows in cells.items():
            if cell_id.startswith("warmup"):
                continue
            result = cell_concurrent_window(rows)
            label = cell_id.split("-a")[0]
            if not result:
                print(f"{label:34s} {len(rows):2d} {'-':>9s} {'-':>9s} {'-':>11s}")
                continue
            print(f"{label:34s} {result['streams']:2d} {result['window_s']:9.2f} {result['concurrent_window_tps']:9.1f} {result['median_stream_tps']:11.1f}")


if __name__ == "__main__":
    main()
