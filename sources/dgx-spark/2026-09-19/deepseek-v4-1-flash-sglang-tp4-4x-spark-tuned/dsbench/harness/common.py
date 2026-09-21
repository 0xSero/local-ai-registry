#!/usr/bin/env python3
"""Shared, dependency-free helpers for dsbench."""
from __future__ import annotations

import hashlib
import json
import math
import os
import random
import statistics
import tempfile
from pathlib import Path
from typing import Any, Iterable, Sequence


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def sha256(value: bytes | str) -> str:
    if isinstance(value, str):
        value = value.encode()
    return hashlib.sha256(value).hexdigest()


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    rows = []
    with Path(path).open(encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    raise ValueError(f"{path}:{number}: invalid JSON: {exc}") from exc
    return rows


def append_jsonl(path: str | Path, row: dict[str, Any]) -> None:
    """Append and fsync one immutable receipt."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    data = canonical_json(row) + b"\n"
    fd = os.open(target, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o644)
    try:
        os.write(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)


def write_json_atomic(path: str | Path, value: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=target.name + ".", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False).encode() + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def percentile(values: Sequence[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return ordered[low]
    return ordered[low] * (high - position) + ordered[high] * (position - low)


def geometric_mean(values: Iterable[float], weights: Iterable[float] | None = None) -> float | None:
    vals = list(values)
    if not vals or any(value <= 0 for value in vals):
        return None
    wts = list(weights) if weights is not None else [1.0] * len(vals)
    if len(wts) != len(vals) or sum(wts) <= 0:
        raise ValueError("geometric mean weights do not match values")
    return math.exp(sum(weight * math.log(value) for value, weight in zip(vals, wts)) / sum(wts))


def cluster_bootstrap(
    rows: Sequence[dict[str, Any]], value_key: str, *, samples: int = 10_000, seed: int = 41
) -> tuple[float, float, float]:
    """Median CI, resampling boots and then blocks within sampled boots."""
    usable = [row for row in rows if row.get(value_key) is not None]
    if not usable:
        raise ValueError("no bootstrap observations")
    by_boot: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for row in usable:
        boot = str(row.get("boot_id", "unknown"))
        block = str(row.get("block_id", "unknown"))
        by_boot.setdefault(boot, {}).setdefault(block, []).append(row)
    boots = sorted(by_boot)
    rng = random.Random(seed)
    estimates: list[float] = []
    for _ in range(samples):
        drawn: list[float] = []
        for boot in rng.choices(boots, k=len(boots)):
            blocks = sorted(by_boot[boot])
            for block in rng.choices(blocks, k=len(blocks)):
                drawn.extend(float(row[value_key]) for row in by_boot[boot][block])
        estimates.append(statistics.median(drawn))
    return (
        statistics.median(float(row[value_key]) for row in usable),
        float(percentile(estimates, 0.025)),
        float(percentile(estimates, 0.975)),
    )


def paired_bootstrap(
    pairs: Sequence[dict[str, Any]], *, samples: int = 10_000, seed: int = 41
) -> tuple[float, float, float]:
    return cluster_bootstrap(pairs, "delta_pct", samples=samples, seed=seed)
