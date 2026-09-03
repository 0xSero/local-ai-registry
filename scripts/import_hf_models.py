#!/usr/bin/env python3
"""Import fully identified leaderboard models from immutable Hugging Face data.

Benchmark rows join models only through registered Hugging Face repositories.
This importer accepts a JSON array of ``owner/repository`` strings and creates
records only when every model field can be populated exactly:

* the repository resolves publicly at a full immutable revision;
* current and immutable-revision safetensors parameter totals agree;
* the resolved config proves a dense causal model with all parameters active;
* both current and lifetime download counts are present; and
* the parameter metadata is not a packed/partial count.

Anything incomplete or ambiguous is skipped. The importer never creates null
fields. Redirected repositories are reported so callers can add the historical
repository to ``scripts/model_aliases.json`` before restamping benchmarks.

Usage: ``python3 scripts/import_hf_models.py roots.json``. Then run
``scripts/stamp_benchmark_models.py`` and the format/index/validation pipeline.
"""

import concurrent.futures
import datetime as dt
import json
import re
import sys
import urllib.parse
from pathlib import Path
from typing import Any

from enrich_benchmark_aliases import (
    base_repositories,
    fetch as fetch_lineage,
)
from enrich_hf_active_params import (
    README as MODEL_CARD,
    parameter_pair_from_card,
    request as request_bytes,
)
from enrich_hf_metadata import (
    all_parameters_active_in_dense_model,
    architecture,
    fetch as fetch_metadata,
    fetch_revision_payload,
    named_active_params,
    params_look_packed,
)

API = (
    "https://huggingface.co/api/models/{repo}?blobs=true"
    "&expand%5B%5D=sha&expand%5B%5D=config&expand%5B%5D=downloads"
    "&expand%5B%5D=downloadsAllTime&expand%5B%5D=safetensors"
)
RESOLVE = "https://huggingface.co/{repo}/resolve/{revision}/config.json"
REGISTRY = Path("registry/model")


def slug(value: str) -> str:
    return (
        re.sub(r"-+", "-", re.sub(r"[^a-z0-9.]+", "-", value.lower()))
        .strip("-")
        .replace(".", "-")
    )


def family_of(basename: str) -> str:
    match = re.match(r"[A-Za-z]+", basename)
    if match is None:
        raise ValueError(f"model family unavailable for {basename}")
    return match.group(0).lower()


def source(kind: str, url: str, captured_at: str) -> dict[str, str]:
    return {"captured_at": captured_at, "kind": kind, "url": url}


def provenance(captured_at: str, *sources: dict[str, str]) -> dict[str, Any]:
    return {"captured_at": captured_at, "sources": list(sources)}


def fetch(
    requested_repo: str,
) -> tuple[
    str,
    str | None,
    dict[str, Any] | None,
    dict[str, Any] | None,
    str | None,
    str | None,
    str | None,
    dict[str, Any] | None,
    str | None,
]:
    _, payload, error = fetch_metadata((requested_repo, True))
    if payload is None:
        return requested_repo, None, None, None, None, None, None, None, error
    canonical_repo = payload.get("id")
    if not isinstance(canonical_repo, str) or "/" not in canonical_repo:
        canonical_repo = requested_repo
    revision = payload.get("sha")
    if not isinstance(revision, str) or re.fullmatch(r"[0-9a-f]{40}", revision) is None:
        return (
            requested_repo,
            canonical_repo,
            payload,
            None,
            None,
            None,
            None,
            None,
            "immutable repository revision unavailable",
        )
    revision_payload, revision_url = fetch_revision_payload(canonical_repo, revision)
    if revision_payload is None:
        return (
            requested_repo,
            canonical_repo,
            payload,
            None,
            revision_url,
            None,
            None,
            None,
            "immutable revision metadata unavailable",
        )
    card_url = None
    card_markdown = None
    lineage_payload = None
    if architecture(payload) == "moe":
        card_url = MODEL_CARD.format(
            repo=urllib.parse.quote(canonical_repo, safe="/"),
            revision=revision,
        )
        card = request_bytes(card_url)
        if card is not None:
            card_markdown = card.decode(errors="replace")
        _, candidate_lineage, lineage_error = fetch_lineage(canonical_repo)
        if (
            lineage_error is None
            and candidate_lineage is not None
            and candidate_lineage.get("sha") == revision
        ):
            lineage_payload = candidate_lineage
    return (
        requested_repo,
        canonical_repo,
        payload,
        revision_payload,
        revision_url,
        card_markdown,
        card_url,
        lineage_payload,
        None,
    )


def rounded_params(total: int) -> float | int:
    value = round(total / 1e9, 2) if total < 10e9 else round(total / 1e9)
    return round(total / 1e9, 3) if value <= 0 else value


def exact_lineage_activity(
    canonical_repo: str,
    payload: dict[str, Any],
    lineage_payload: dict[str, Any] | None,
    total: int,
    captured_at: str,
) -> tuple[float | int, tuple[dict[str, Any], ...]] | None:
    if lineage_payload is None or lineage_payload.get("sha") != payload.get("sha"):
        return None
    config = payload.get("_resolved_config") or payload.get("config") or {}
    classes = config.get("architectures") if isinstance(config, dict) else None
    class_names = [item for item in classes or [] if isinstance(item, str)]
    tags = set(lineage_payload.get("tags") or [])
    if not (
        class_names
        and all(name.endswith("ForCausalLM") for name in class_names)
    ) and not tags.intersection({"image-text-to-text", "text-generation"}):
        return None
    bases = base_repositories(lineage_payload)
    if not bases:
        return None
    records_by_repo: dict[str, list[dict[str, Any]]] = {}
    for path in REGISTRY.glob("*.json"):
        row = json.loads(path.read_text())
        repo = (row.get("huggingface") or {}).get("repository")
        if isinstance(repo, str):
            records_by_repo.setdefault(repo.lower(), []).append(row)
    mapped: dict[str, dict[str, Any]] = {}
    for base in bases:
        records = records_by_repo.get(base.lower()) or []
        if len(records) != 1:
            return None
        mapped[records[0]["id"]] = records[0]
    if len(mapped) != 1:
        return None
    base = next(iter(mapped.values()))
    base_params = base.get("params")
    active = base.get("active_params")
    active_fact = (base.get("facts") or {}).get("active_params") or {}
    base_sources = (active_fact.get("provenance") or {}).get("sources") or []
    target_params = total / 1e9
    if not (
        base.get("architecture") == "moe"
        and isinstance(base_params, (int, float))
        and abs(target_params - float(base_params))
        <= max(0.5, float(base_params) * 0.05)
        and isinstance(active, (int, float))
        and 0 < active <= target_params
        and active_fact.get("state") == "known"
        and base_sources
    ):
        return None
    revision = payload["sha"]
    lineage_source = source(
        "huggingface-model-card",
        (
            f"https://huggingface.co/{urllib.parse.quote(canonical_repo, safe='/')}"
            f"/blob/{revision}/README.md"
        ),
        captured_at,
    )
    sources: list[dict[str, Any]] = [lineage_source]
    seen = {(lineage_source["kind"], lineage_source["url"])}
    for item in base_sources:
        if not isinstance(item, dict):
            continue
        key = (item.get("kind"), item.get("url"))
        if key in seen:
            continue
        seen.add(key)
        sources.append(item)
    return active, tuple(sources)


def build_record(
    canonical_repo: str,
    payload: dict[str, Any],
    revision_payload: dict[str, Any],
    revision_url: str,
    card_markdown: str | None,
    card_url: str | None,
    lineage_payload: dict[str, Any] | None,
    captured_at: str,
) -> tuple[dict[str, Any] | None, str | None]:
    total = (payload.get("safetensors") or {}).get("total")
    revision_total = (revision_payload.get("safetensors") or {}).get("total")
    if not isinstance(total, int) or total <= 0:
        return None, "no safetensors parameter count"
    if revision_total != total:
        return None, "current and immutable parameter totals disagree"
    topology = architecture(payload)
    basename = canonical_repo.split("/")[-1]
    params = rounded_params(total)
    if params_look_packed({"name": basename, "params": params}):
        return None, "safetensors parameter count is packed or partial"
    active_sources_override: tuple[dict[str, Any], ...] | None = None
    if topology == "dense" and all_parameters_active_in_dense_model(payload):
        active_params: float | int = params
        active_reason = "all-parameters-active-in-dense-model"
    elif topology == "moe":
        pair = (
            None
            if card_markdown is None
            else parameter_pair_from_card(card_markdown, total / 1e9)
        )
        named_active = named_active_params(basename)
        if pair is not None:
            active_params = pair[1]
            active_reason = "exact-model-card-active-parameters"
        elif (
            isinstance(named_active, (int, float))
            and 0 < named_active < total / 1e9
        ):
            active_params = named_active
            active_reason = "explicit-aNb-model-name"
        else:
            lineage = exact_lineage_activity(
                canonical_repo, payload, lineage_payload, total, captured_at
            )
            if lineage is None:
                return None, "exact MoE active-parameter count unavailable"
            active_params, active_sources_override = lineage
            active_reason = "exact-base-lineage-moe-topology"
    else:
        return None, "topology or active-parameter count is not exact"
    downloads = payload.get("downloads")
    lifetime_downloads = payload.get("downloadsAllTime")
    if not isinstance(downloads, int) or not isinstance(lifetime_downloads, int):
        return None, "download counts unavailable"
    revision = payload["sha"]
    encoded_repo = urllib.parse.quote(canonical_repo, safe="/")
    api_url = API.format(repo=encoded_repo)
    config_url = RESOLVE.format(
        repo=encoded_repo,
        revision=urllib.parse.quote(revision, safe=""),
    )
    model_url = f"https://huggingface.co/{canonical_repo}"
    api_source = source("huggingface-api", api_url, captured_at)
    revision_source = source("huggingface-api", revision_url, captured_at)
    config_source = source("huggingface-config", config_url, captured_at)
    if active_sources_override is not None:
        active_sources = active_sources_override
    elif active_reason == "exact-model-card-active-parameters":
        if card_url is None:
            return None, "immutable model-card provenance unavailable"
        active_sources = (
            source("huggingface-model-card", card_url, captured_at),
            config_source,
        )
    else:
        active_sources = (revision_source, config_source)
    return {
        "active_params": active_params,
        "architecture": topology,
        "downloads": {
            "all_time": lifetime_downloads,
            "captured_at": captured_at,
            "last_30d": downloads,
            "source": "huggingface-api",
        },
        "facts": {
            "active_params": {
                "provenance": provenance(captured_at, *active_sources),
                "reason": active_reason,
                "state": "known",
            },
            "architecture": {
                "provenance": provenance(captured_at, config_source),
                "reason": "resolved-huggingface-config",
                "state": "known",
            },
            "params": {
                "provenance": provenance(captured_at, revision_source),
                "reason": "immutable-safetensors-parameter-metadata",
                "state": "known",
            },
        },
        "family": family_of(basename),
        "huggingface": {
            "link_type": "repository",
            "provenance": provenance(captured_at, api_source),
            "reason": "hf-api-confirmed-public",
            "repository": canonical_repo,
            "status": "known",
            "url": model_url,
        },
        "id": slug(basename),
        "name": basename,
        "params": params,
        "provenance": provenance(captured_at, api_source, revision_source),
        "schema_version": "local-ai-registry/v1",
        "url": model_url,
    }, None


def existing_repositories() -> dict[str, str]:
    result: dict[str, str] = {}
    for path in REGISTRY.glob("*.json"):
        row = json.loads(path.read_text())
        repo = (row.get("huggingface") or {}).get("repository")
        if isinstance(repo, str):
            result[repo.lower()] = path.stem
    return result


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: import_hf_models.py roots.json", file=sys.stderr)
        return 2
    roots = json.loads(Path(sys.argv[1]).read_text())
    if not isinstance(roots, list) or not all(isinstance(item, str) for item in roots):
        print("roots file must contain a JSON string array", file=sys.stderr)
        return 2
    captured_at = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    ids_to_repos = {
        path.stem: (
            json.loads(path.read_text()).get("huggingface") or {}
        ).get("repository")
        for path in REGISTRY.glob("*.json")
    }
    repos_to_ids = existing_repositories()
    created = skipped = renamed = redirects = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        for (
            requested_repo,
            canonical_repo,
            payload,
            revision_payload,
            revision_url,
            card_markdown,
            card_url,
            lineage_payload,
            error,
        ) in pool.map(fetch, sorted(set(roots))):
            if error or canonical_repo is None or payload is None or revision_payload is None:
                print(f"SKIP {requested_repo}: {error}", file=sys.stderr)
                skipped += 1
                continue
            if canonical_repo.lower() in repos_to_ids:
                print(
                    f"EXISTS {requested_repo}: {repos_to_ids[canonical_repo.lower()]}",
                    file=sys.stderr,
                )
                skipped += 1
                continue
            record, reason = build_record(
                canonical_repo,
                payload,
                revision_payload,
                revision_url or "",
                card_markdown,
                card_url,
                lineage_payload,
                captured_at,
            )
            if record is None:
                print(f"SKIP {requested_repo}: {reason}", file=sys.stderr)
                skipped += 1
                continue
            identifier = record["id"]
            if identifier in ids_to_repos:
                identifier = f"{slug(canonical_repo.split('/')[0])}-{identifier}"
                if identifier in ids_to_repos:
                    print(
                        f"COLLISION {requested_repo}: id {identifier} already exists",
                        file=sys.stderr,
                    )
                    skipped += 1
                    continue
                record["id"] = identifier
                renamed += 1
            ids_to_repos[identifier] = canonical_repo
            repos_to_ids[canonical_repo.lower()] = identifier
            (REGISTRY / f"{identifier}.json").write_text(
                json.dumps(record, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
            )
            if canonical_repo.lower() != requested_repo.lower():
                print(
                    f"REDIRECT {requested_repo} -> {canonical_repo} -> {identifier}",
                    file=sys.stderr,
                )
                redirects += 1
            created += 1
    print(
        f"created {created} complete models; skipped {skipped}; "
        f"renamed ids {renamed}; redirects {redirects}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
