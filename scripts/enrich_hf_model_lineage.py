#!/usr/bin/env python3
"""Fill model topology only from exact Hugging Face base-model lineage.

A target is updated only when its immutable model-card metadata names base
repositories that all resolve to one registry model, that base has a known
topology, and the target is tagged for text generation or image-to-text use.
Speech-only and unresolved lineage remain unclassified.
"""

from __future__ import annotations

import concurrent.futures
import datetime as dt
import json
import re
import sys
import urllib.parse
from pathlib import Path
from typing import Any

from enrich_benchmark_aliases import API, base_repositories, fetch

REGISTRY = Path(__file__).resolve().parents[1] / "registry"
MODEL_DIR = REGISTRY / "model"
SUPPORTED_TAGS = {"image-text-to-text", "text-generation"}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n")


def params_agree(left: float, right: float) -> bool:
    return abs(left - right) <= max(0.5, right * 0.05)


def main() -> int:
    captured_at = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    by_repo: dict[str, list[tuple[Path, dict[str, Any]]]] = {}
    candidates: list[tuple[Path, dict[str, Any], str]] = []

    for path in sorted(MODEL_DIR.glob("*.json")):
        row = read_json(path)
        repo = (row.get("huggingface") or {}).get("repository")
        if isinstance(repo, str) and repo.count("/") == 1:
            by_repo.setdefault(repo.lower(), []).append((path, row))
            if row.get("architecture") is None or row.get("active_params") is None:
                candidates.append((path, row, repo))

    requested = {repo.lower() for repo in sys.argv[1:]}
    if requested:
        candidates = [item for item in candidates if item[2].lower() in requested]

    payloads: dict[str, dict[str, Any]] = {}
    errors = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        for repo, payload, error in pool.map(fetch, sorted({item[2] for item in candidates})):
            if error is not None or payload is None:
                errors += 1
                continue
            payloads[repo.lower()] = payload

    architecture_updates = active_updates = param_updates = ambiguous = unsupported = no_lineage = 0
    for path, row, repo in candidates:
        payload = payloads.get(repo.lower())
        if payload is None:
            continue
        sha = payload.get("sha")
        tags = set(payload.get("tags") or [])
        if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha):
            no_lineage += 1
            continue
        if not tags.intersection(SUPPORTED_TAGS):
            unsupported += 1
            continue

        bases = base_repositories(payload)
        if not bases:
            no_lineage += 1
            continue
        mapped: dict[str, tuple[Path, dict[str, Any]]] = {}
        for base in bases:
            records = by_repo.get(base.lower()) or []
            if len(records) != 1:
                mapped.clear()
                break
            base_path, base_row = records[0]
            mapped[base_row["id"]] = (base_path, base_row)
        if not mapped:
            no_lineage += 1
            continue
        if len(mapped) != 1:
            ambiguous += 1
            continue

        _, base_row = next(iter(mapped.values()))
        architecture = base_row.get("architecture")
        if architecture not in ("dense", "moe"):
            no_lineage += 1
            continue

        source_url = (
            f"https://huggingface.co/{urllib.parse.quote(repo, safe='/')}"
            f"/blob/{sha}/README.md"
        )
        lineage_source = {
            "captured_at": captured_at,
            "kind": "huggingface-model-card",
            "url": source_url,
        }
        changed = False
        if row.get("architecture") is None:
            row["architecture"] = architecture
            row.setdefault("facts", {})["architecture"] = {
                "provenance": {
                    "captured_at": captured_at,
                    "sources": [lineage_source],
                },
                "reason": "exact-huggingface-base-model-lineage",
                "state": "known",
            }
            architecture_updates += 1
            changed = True

        active = base_row.get("active_params")
        target_params = row.get("params")
        base_params = base_row.get("params")
        active_fact = (base_row.get("facts") or {}).get("active_params") or {}
        base_sources = (active_fact.get("provenance") or {}).get("sources") or []
        if (
            row.get("active_params") is None
            and row.get("architecture") == architecture
            and architecture in ("dense", "moe")
            and isinstance(active, (int, float))
            and isinstance(target_params, (int, float))
            and isinstance(base_params, (int, float))
            and 0 < active <= base_params
            and params_agree(float(target_params), float(base_params))
            and active_fact.get("state") == "known"
            and base_sources
        ):
            sources = [lineage_source]
            seen = {(lineage_source["kind"], lineage_source["url"])}
            for source in base_sources:
                if not isinstance(source, dict):
                    continue
                key = (source.get("kind"), source.get("url"))
                if key in seen:
                    continue
                seen.add(key)
                sources.append(source)
            if target_params != base_params:
                row["params"] = base_params
                row.setdefault("facts", {})["params"] = {
                    "provenance": {
                        "captured_at": captured_at,
                        "sources": sources,
                    },
                    "reason": "exact-base-lineage-parameter-count",
                    "state": "known",
                }
                param_updates += 1
                changed = True
            row["active_params"] = active
            row.setdefault("facts", {})["active_params"] = {
                "provenance": {
                    "captured_at": captured_at,
                    "sources": sources,
                },
                "reason": f"exact-base-lineage-{architecture}-topology",
                "state": "known",
            }
            active_updates += 1
            changed = True

        if changed:
            write_json(path, row)

    print(
        f"candidates: {len(candidates)}; architecture updates: {architecture_updates}; "
        f"parameter updates: {param_updates}; active parameter updates: {active_updates}; "
        f"ambiguous: {ambiguous}; "
        f"unsupported task: {unsupported}; no mapped lineage: {no_lineage}; "
        f"errors: {errors}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
