#!/usr/bin/env python3
"""Fill existing LocalMaxxing records from their exact live run IDs.

The script never creates records and never replaces non-null values. It only
fills fields already present in the registry when the leaderboard still exposes
the exact referenced run.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

from import_localmaxxing import evidenced_sweep_metrics, server_capacity, workload_concurrency
from sweep_metrics import derive_metrics

SOURCE = "https://www.localmaxxing.com"
USER_AGENT = "local-ai-registry-enrichment/1.0 (+https://github.com/0xSero/local-ai-registry)"


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def save(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n")


def fetch_page(offset: int, limit: int) -> dict[str, Any]:
    url = f"{SOURCE}/api/leaderboard?limit={limit}&offset={offset}"
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        value = json.loads(response.read().decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"unexpected LocalMaxxing response at offset {offset}")
    return value


def fetch_rows(cache: Path | None) -> list[dict[str, Any]]:
    if cache is not None and cache.exists():
        value = json.loads(cache.read_text())
        if not isinstance(value, list) or not all(isinstance(row, dict) for row in value):
            raise ValueError(f"invalid LocalMaxxing cache: {cache}")
        return value

    by_id: dict[str, dict[str, Any]] = {}
    expected_total = 0
    limit = 200
    for attempt in range(5):
        offset = 0
        while True:
            page = fetch_page(offset, limit)
            batch = page.get("rows") or []
            if not isinstance(batch, list) or not all(isinstance(row, dict) for row in batch):
                raise ValueError(f"invalid LocalMaxxing rows at offset {offset}")
            total = page.get("total")
            if not isinstance(total, int) or total < 0:
                raise ValueError(f"invalid LocalMaxxing total at offset {offset}: {total!r}")
            expected_total = max(expected_total, total)
            for row in batch:
                run_id = row.get("id")
                if not isinstance(run_id, str) or not run_id:
                    raise ValueError(f"LocalMaxxing row at offset {offset} has no run ID")
                by_id[run_id] = row
            offset += len(batch)
            if not batch or offset >= total:
                break
            time.sleep(0.12)
        if len(by_id) >= expected_total:
            break
        time.sleep(0.5 * (attempt + 1))

    complete = len(by_id) >= expected_total
    if not complete:
        print(
            "WARN LocalMaxxing pagination remained unstable after five passes: "
            f"using {len(by_id)} unique exact runs for a reported total of {expected_total}",
            file=sys.stderr,
        )
    rows = [by_id[run_id] for run_id in sorted(by_id)]
    if cache is not None and complete:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(rows, ensure_ascii=False))
    return rows


def fill(container: dict[str, Any], key: str, value: Any) -> bool:
    if key not in container or container[key] not in (None, "") or value in (None, ""):
        return False
    container[key] = value
    return True


def known_fact(reason: str, captured_at: str, url: str) -> dict[str, Any]:
    return {
        "provenance": {
            "captured_at": captured_at,
            "sources": [
                {
                    "captured_at": captured_at,
                    "kind": "leaderboard-run",
                    "url": url,
                }
            ],
        },
        "reason": reason,
        "state": "known",
    }

def run_text(live: dict[str, Any]) -> str:
    flags = live.get("engineFlags") or {}
    return " ".join(
        value
        for value in (flags.get("commandSnippet"), live.get("notes"))
        if isinstance(value, str) and value
    )



def version_from_run(engine_name: Any, live: dict[str, Any]) -> str | None:
    text = run_text(live)
    patterns: list[tuple[str, Any]]
    if engine_name == "llama.cpp":
        patterns = [
            (
                r"\bllama\.cpp\s+(?:build\s+)?(b\d+)(?:\s*[/\(]\s*([0-9a-f]{7,40})\)?)?",
                lambda match: match.group(1)
                + (f" / {match.group(2)}" if match.group(2) else ""),
            ),
            (
                r"\bllama\.cpp\b[^\n.;]{0,160}\bcommit\s+([0-9a-f]{7,40})\b",
                lambda match: match.group(1),
            ),
        ]
    elif engine_name == "ollama":
        patterns = [
            (
                r"\bOllama(?:\s+version)?\s+v?(\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?)\b",
                lambda match: match.group(1),
            )
        ]
    elif engine_name == "lmstudio":
        patterns = [
            (
                r"\bLM\s*Studio(?:\s+version)?\s+v?(\d+\.\d+(?:\.\d+)?(?:\+\d+)?)\b",
                lambda match: match.group(1),
            )
        ]
    elif engine_name == "vllm":
        patterns = [
            (
                r"\bvLLM(?:\s+version)?\s+v?(\d+\.\d+(?:\.\d+)?(?:[0-9A-Za-z.+-]*))\b",
                lambda match: match.group(1),
            )
        ]
    elif engine_name == "mlx":
        patterns = [
            (
                r"\b(oMLX)\s+v?(\d+\.\d+(?:\.\d+)?(?:[0-9A-Za-z.+-]*))\b",
                lambda match: f"{match.group(1)} {match.group(2)}",
            ),
            (
                r"\b(mlx-(?:lm|vlm))\s+v?(\d+\.\d+(?:\.\d+)?(?:[0-9A-Za-z.+-]*))\b",
                lambda match: f"{match.group(1)} {match.group(2)}",
            ),
            (
                r"\bMLX\s+v?(\d+\.\d+(?:\.\d+)?(?:[0-9A-Za-z.+-]*))\b",
                lambda match: match.group(1),
            ),
        ]
    else:
        return None

    values = {
        formatter(match)
        for pattern, formatter in patterns
        for match in re.finditer(pattern, text, re.IGNORECASE)
    }
    return next(iter(values)) if len(values) == 1 else None

def backend_from_run(live: dict[str, Any]) -> str | None:
    text = run_text(live)
    patterns = {
        "vulkan": (
            r"\bbackend\s*[=:]\s*vulkan\b",
            r"\bruntime\s*[=:]\s*(?:radv\s+)?vulkan\b",
            r"\bvulkan\s+backend\b",
            r"build[-_/]vulkan",
        ),
        "cuda": (
            r"\bbackend\s*[=:]\s*cuda\b",
            r"\bruntime\s*[=:]\s*cuda\b",
            r"\bcuda\s+backend\b",
            r"build[-_/]cuda",
            r"\bCUDA_VISIBLE_DEVICES\b",
        ),
        "rocm": (
            r"\bbackend\s*[=:]\s*rocm\b",
            r"\bruntime\s*[=:]\s*rocm\b",
            r"\brocm\s+backend\b",
            r"build[-_/]rocm",
            r"\bROCR_VISIBLE_DEVICES\b",
        ),
        "metal": (
            r"\bbackend\s*[=:]\s*metal\b",
            r"\bruntime\s*[=:]\s*metal\b",
            r"\bmetal\s+backend\b",
            r"build[-_/]metal",
        ),
        "xpu": (
            r"\bbackend\s*[=:]\s*xpu\b",
            r"\bruntime\s*[=:]\s*xpu\b",
            r"\bxpu\s+backend\b",
            r"\bONEAPI_DEVICE_SELECTOR\b",
            r"\bZE_AFFINITY_MASK\b",
        ),
    }
    values = {
        backend
        for backend, backend_patterns in patterns.items()
        if any(re.search(pattern, text, re.IGNORECASE) for pattern in backend_patterns)
    }
    return next(iter(values)) if len(values) == 1 else None






def enrich_recipe(
    record: dict[str, Any],
    live: dict[str, Any],
    captured_at: str,
) -> tuple[bool, CounterLike]:
    updates: CounterLike = {}
    changed = False
    run_id = live["id"]
    run_url = f"{SOURCE}/en/runs/{run_id}"
    engine = record.get("engine")
    live_engine = live.get("engine") or {}
    if isinstance(engine, dict):
        live_version = live_engine.get("engineVersion")
        reason = "exact-live-run-engine-version"
        if live_version is None:
            live_version = version_from_run(engine.get("name"), live)
            reason = "explicit-engine-version-in-live-run-evidence"
        if fill(engine, "version", live_version):
            updates["engine.version"] = 1
            record.setdefault("facts", {})["engine.version"] = known_fact(
                reason, captured_at, run_url
            )
            changed = True

    serving = record.get("serving")
    observed_concurrency = workload_concurrency(live)
    capacity = server_capacity(live, observed_concurrency)
    if isinstance(serving, dict):
        if fill(serving, "max_context_tokens", live.get("contextLength")):
            updates["serving.max_context_tokens"] = 1
            record.setdefault("facts", {})["serving.max_context_tokens"] = known_fact(
                "exact-live-run-context-length", captured_at, run_url
            )
            changed = True
        if fill(serving, "max_concurrency", capacity):
            updates["serving.max_concurrency"] = 1
            record.setdefault("facts", {})["serving.max_concurrency"] = known_fact(
                "server-capacity-derived-from-source-evidence", captured_at, run_url
            )
            changed = True

    metadata = record.get("metadata")
    local = metadata.get("localmaxxing") if isinstance(metadata, dict) else None
    flags = live.get("engineFlags") or {}
    if isinstance(local, dict):
        mappings = {
            "run_id": run_id,
            "hardware_label": live.get("hardwareGroupLabel"),
            "batch_size": live.get("batchSize"),
            "notes": live.get("notes"),
            "backend": live_engine.get("backend") or backend_from_run(live),
            "observed_command": flags.get("commandSnippet"),
        }
        for key, value in mappings.items():
            if fill(local, key, value):
                updates[f"metadata.{key}"] = 1
                changed = True
        stored_flags = local.get("engine_flags")
        if isinstance(stored_flags, dict) and isinstance(flags, dict):
            for key in stored_flags:
                if fill(stored_flags, key, flags.get(key)):
                    updates[f"metadata.engine_flags.{key}"] = 1
                    changed = True

    return changed, updates


CounterLike = dict[str, int]


def merge_counts(target: CounterLike, source: CounterLike) -> None:
    for key, value in source.items():
        target[key] = target.get(key, 0) + value


def matching_sweep_row(
    rows: list[dict[str, Any]], live: dict[str, Any]
) -> dict[str, Any] | None:
    if len(rows) == 1 and isinstance(rows[0], dict):
        return rows[0]
    context = live.get("contextLength")
    candidates = [
        row
        for row in rows
        if isinstance(row, dict) and row.get("context_tokens") in (None, context)
    ]
    return candidates[0] if len(candidates) == 1 else None


def enrich_sweep(
    record: dict[str, Any],
    live: dict[str, Any],
    engine_version: Any,
) -> tuple[bool, CounterLike]:
    updates: CounterLike = {}
    changed = False
    if fill(record, "measured_at", live.get("createdAt")):
        updates["measured_at"] = 1
        changed = True

    rows = record.get("rows") or []
    row = matching_sweep_row(rows, live) if isinstance(rows, list) else None
    concurrency = workload_concurrency(live)
    evidenced_metrics = evidenced_sweep_metrics(live)
    if row is not None:
        values = {
            "concurrency": concurrency,
            "context_tokens": live.get("contextLength"),
            "output_tokens": live.get("outputTokens"),
            "prefill_tok_s": (
                live.get("tokSPrefill")
                if live.get("tokSPrefill") is not None
                else evidenced_metrics.get("prefill_tok_s")
            ),
            "decode_tok_s": live.get("tokSOut"),
            "ttft_ms_p50": live.get("ttftMs"),
            "peak_vram_gb": live.get("peakVramGb"),
        }
        for key, value in values.items():
            if fill(row, key, value):
                updates[f"rows.{key}"] = 1
                changed = True
        decode = row.get("decode_tok_s")
        row_concurrency = row.get("concurrency")
        if (
            row.get("decode_tok_s_per_stream") is None
            and isinstance(decode, (int, float))
            and isinstance(row_concurrency, int)
            and row_concurrency > 0
        ):
            row["decode_tok_s_per_stream"] = decode / row_concurrency
            updates["rows.decode_tok_s_per_stream"] = 1
            changed = True

    metrics = record.get("metrics")
    if isinstance(metrics, dict):
        derived = derive_metrics(rows, record.get("measured_at"))
        derived["inference_engine_version"] = engine_version
        for key, value in derived.items():
            if fill(metrics, key, value):
                updates[f"metrics.{key}"] = 1
                changed = True
    return changed, updates


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", type=Path, default=Path("registry"))
    parser.add_argument("--cache", type=Path)
    args = parser.parse_args()

    captured_at = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    live_rows = fetch_rows(args.cache)
    by_id = {row["id"]: row for row in live_rows}
    totals: CounterLike = {}
    matched = 0
    missing = 0
    recipe_files = 0
    sweep_files = 0

    for recipe_path in sorted((args.registry / "recipe").glob("*.json")):
        recipe = load(recipe_path)
        if recipe.get("recipe_source") != "localmaxxing":
            continue
        launch = recipe.get("launch") or {}
        metadata = recipe.get("metadata") or {}
        local = metadata.get("localmaxxing") or {}
        run_id = launch.get("run_id") or local.get("run_id")
        live = by_id.get(run_id)
        if live is None:
            missing += 1
            continue
        matched += 1
        recipe_changed, counts = enrich_recipe(recipe, live, captured_at)
        merge_counts(totals, counts)
        if recipe_changed:
            save(recipe_path, recipe)
            recipe_files += 1

        engine_version = (recipe.get("engine") or {}).get("version")
        for sweep_id in recipe.get("speed_sweep_ids") or []:
            sweep_path = args.registry / "speed-sweep" / f"{sweep_id}.json"
            if not sweep_path.exists():
                continue
            sweep = load(sweep_path)
            sweep_changed, counts = enrich_sweep(sweep, live, engine_version)
            merge_counts(totals, counts)
            if sweep_changed:
                save(sweep_path, sweep)
                sweep_files += 1

    print(
        f"live rows: {len(live_rows)}; matched recipes: {matched}; missing runs: {missing}; "
        f"recipe files updated: {recipe_files}; sweep files updated: {sweep_files}"
    )
    print("field updates: " + json.dumps(totals, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
