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
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from enrich_benchmark_aliases import API, base_repositories, fetch
from enrich_hf_metadata import (
    all_parameters_active_in_dense_model,
    architecture as classify_architecture,
    fetch as fetch_metadata,
    parameter_billions,
)

REGISTRY = Path(__file__).resolve().parents[1] / "registry"
MODEL_DIR = REGISTRY / "model"
SUPPORTED_TAGS = {"image-text-to-text", "text-generation"}
CARD_LINEAGE = re.compile(
    r"(?im)^\s*(?:[-*]\s*)?(?:\*\*)?(?:original|base)\s+model(?:\*\*)?\s*:\s*"
    r"(?:\[[^\]]*\]\()?<?https://huggingface\.co/"
    r"(?P<repo>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)"
)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n")


def params_agree(left: float, right: float) -> bool:
    return abs(left - right) <= max(0.5, right * 0.05)


def fetch_card_base(
    item: tuple[str, str],
) -> tuple[str, set[str], str | None]:
    repo, revision = item
    url = (
        f"https://huggingface.co/{urllib.parse.quote(repo, safe='/')}"
        f"/resolve/{revision}/README.md"
    )
    request = urllib.request.Request(
        url, headers={"User-Agent": "local-ai-registry/1.0"}
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            card = response.read().decode("utf-8", errors="replace")
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as error:
        return repo, set(), str(error)
    bases = {match.group("repo").rstrip(".") for match in CARD_LINEAGE.finditer(card)}
    return repo, bases, None




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
        for repo, payload, error in pool.map(
            fetch, sorted({item[2] for item in candidates})
        ):
            if error is not None or payload is None:
                errors += 1
                continue
            payloads[repo.lower()] = payload
    card_bases: dict[str, set[str]] = {}
    card_work = [
        (repo, payload["sha"])
        for repo, payload in payloads.items()
        if not base_repositories(payload)
        and isinstance(payload.get("sha"), str)
        and re.fullmatch(r"[0-9a-f]{40}", payload["sha"])
        and set(payload.get("tags") or []).intersection(SUPPORTED_TAGS)
    ]
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        for repo, bases, error in pool.map(fetch_card_base, card_work):
            if error is not None:
                errors += 1
            if len(bases) == 1:
                card_bases[repo.lower()] = bases


    base_repos = sorted(
        {
            base
            for repo, payload in payloads.items()
            for base in (
                base_repositories(payload)
                or card_bases.get(repo.lower(), set())
            )
        }
    )
    base_payloads: dict[str, dict[str, Any]] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        for repo, payload, error in pool.map(
            fetch_metadata, ((repo, True) for repo in base_repos)
        ):
            if error is not None or payload is None:
                errors += 1
                continue
            base_payloads[repo.lower()] = payload

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

        bases = base_repositories(payload) or card_bases.get(repo.lower(), set())
        if not bases:
            no_lineage += 1
            continue

        architecture: str | None = None
        active: float | int | None = None
        base_params: float | int | None = None
        base_sources: list[dict[str, Any]] = []

        mapped: dict[str, tuple[Path, dict[str, Any]]] = {}
        all_mapped = True
        for base in bases:
            records = by_repo.get(base.lower()) or []
            if len(records) != 1:
                all_mapped = False
                break
            base_path, base_row = records[0]
            mapped[base_row["id"]] = (base_path, base_row)

        if all_mapped and len(mapped) == 1:
            _, base_row = next(iter(mapped.values()))
            architecture = base_row.get("architecture")
            active = base_row.get("active_params")
            base_params = base_row.get("params")
            active_fact = (base_row.get("facts") or {}).get("active_params") or {}
            if active_fact.get("state") == "known":
                base_sources = [
                    source
                    for source in (active_fact.get("provenance") or {}).get("sources") or []
                    if isinstance(source, dict)
                ]
        elif len(bases) == 1:
            base_repo = next(iter(bases))
            base_payload = base_payloads.get(base_repo.lower())
            if base_payload is not None:
                architecture = classify_architecture(base_payload)
                base_params = parameter_billions(base_payload)
                base_sha = base_payload.get("sha")
                if (
                    architecture == "dense"
                    and all_parameters_active_in_dense_model(base_payload)
                    and isinstance(base_params, (int, float))
                    and isinstance(base_sha, str)
                    and re.fullmatch(r"[0-9a-f]{40}", base_sha)
                ):
                    active = base_params
                    base_sources = [
                        {
                            "captured_at": captured_at,
                            "kind": "huggingface-api",
                            "url": (
                                f"https://huggingface.co/api/models/"
                                f"{urllib.parse.quote(base_repo, safe='/')}"
                                f"/revision/{base_sha}?blobs=true"
                            ),
                        },
                        {
                            "captured_at": captured_at,
                            "kind": "huggingface-config",
                            "url": (
                                f"https://huggingface.co/"
                                f"{urllib.parse.quote(base_repo, safe='/')}"
                                f"/blob/{base_sha}/config.json"
                            ),
                        }
                    ]
        elif all_mapped:
            ambiguous += 1
            continue

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

        target_params = row.get("params")
        if (
            row.get("active_params") is None
            and row.get("architecture") == architecture
            and isinstance(active, (int, float))
            and isinstance(target_params, (int, float))
            and isinstance(base_params, (int, float))
            and 0 < active <= base_params
            and params_agree(float(target_params), float(base_params))
            and base_sources
        ):
            sources = [lineage_source]
            seen = {(lineage_source["kind"], lineage_source["url"])}
            for source in base_sources:
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
        f"ambiguous: {ambiguous}; card lineages: {len(card_bases)}; "
        f"unsupported task: {unsupported}; no mapped lineage: {no_lineage}; "
        f"errors: {errors}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
