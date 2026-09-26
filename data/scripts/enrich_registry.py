#!/usr/bin/env python3
"""Populate the shared enrichment contract without inventing source facts."""

import argparse
import json
import re
from pathlib import Path
from urllib.parse import quote


SCHEMA = "local-ai-registry/v1"
CAPTURED_AT = "2026-08-27T06:04:13.773Z"
RECONCILED_AT = "2026-08-27T08:42:38Z"
REGISTRY_SOURCE = "https://github.com/0xSero/local-ai-registry"
PUBLICATION_SOURCE = "https://local.ai"
HF_ACCESS_UNRESOLVED = {
    "0xSero/GLM-5.2-NVFP4-REAP-469B",
    "local/Nex-N2-Pro-NVFP4",
    "local/Qwen3.6-27B-INT8-AutoRound",
    "local/Qwen3.6-27B-int4-AutoRound",
    "local/Qwen3.6-35B-A3B-GGUF",
    "local/Step-3.7-Flash-FP8",
    "local/Step-3.7-Flash-NVFP4",
}
EXACT_ARTIFACT_REPOSITORIES = {
    "bonsai-27b-q1_0": ("prism-ml/Bonsai-27B-gguf", "publication"),
    "bonsai-27b-q1_0-dspark-bf16": ("prism-ml/Bonsai-27B-gguf", "site"),
    "bonsai-27b-q1_0-dspark-q4_1": ("prism-ml/Bonsai-27B-gguf", "site"),
    "gemma-4-12b-q4km": ("unsloth/gemma-4-12b-it-GGUF", "site"),
    "holo-3.1-35b-a3b-q4km": ("Hcompany/Holo-3.1-35B-A3B-GGUF", "site"),
    "llama-3.3-70b-instruct-q4km": ("bartowski/Llama-3.3-70B-Instruct-GGUF", "site"),
    "qwen2.5-72b-instruct-q4km": ("Qwen/Qwen2.5-72B-Instruct-GGUF", "site"),
    "qwen2-72b-instruct-q4km": ("Qwen/Qwen2-72B-Instruct-GGUF", "site"),
    "qwen3.6-35b-a3b-mxfp4-moe": ("unsloth/Qwen3.6-35B-A3B-GGUF", "publication"),
    "ternary-bonsai-27b-pq2_0": ("prism-ml/Ternary-Bonsai-27B-gguf", "publication"),
    "ternary-bonsai-27b-q2_0": ("prism-ml/Ternary-Bonsai-27B-gguf", "publication"),
    "ternary-bonsai-27b-q2_0-dspark-bf16": ("prism-ml/Ternary-Bonsai-27B-gguf", "site"),
}
EXACT_ARTIFACT_INSTANCE_REPOSITORIES = {
    "bonsai-27b-q1-0--q1-0": ("prism-ml/Bonsai-27B-gguf", "publication"),
    "bonsai-27b-q1-0-dspark-bf16--q1-0": ("prism-ml/Bonsai-27B-gguf", "site"),
    "bonsai-27b-q1-0-dspark-q4-1--q1-0": ("prism-ml/Bonsai-27B-gguf", "site"),
    "gemma-4-12b-q4km--unknown": ("unsloth/gemma-4-12b-it-GGUF", "site"),
    "holo-3-1-35b-a3b-q4km--unknown": ("Hcompany/Holo-3.1-35B-A3B-GGUF", "site"),
    "llama-3-3-70b-instruct-q4km--unknown": ("bartowski/Llama-3.3-70B-Instruct-GGUF", "site"),
    "qwen2-5-72b-instruct-q4km--unknown": ("Qwen/Qwen2.5-72B-Instruct-GGUF", "site"),
    "qwen2-72b-instruct-q4km--unknown": ("Qwen/Qwen2-72B-Instruct-GGUF", "site"),
    "qwen3-6-35b-a3b-mxfp4-moe--unknown": ("unsloth/Qwen3.6-35B-A3B-GGUF", "publication"),
    "ternary-bonsai-27b-pq2-0--pq2-0": ("prism-ml/Ternary-Bonsai-27B-gguf", "publication"),
    "ternary-bonsai-27b-q2-0--q2-0": ("prism-ml/Ternary-Bonsai-27B-gguf", "publication"),
    "ternary-bonsai-27b-q2-0-dspark-bf16--q2-0": ("prism-ml/Ternary-Bonsai-27B-gguf", "site"),
}
HF_REPOSITORY = re.compile(r"^[^/\s]+/[^/\s]+$")
DIGEST = re.compile(r"@(?P<digest>sha256:[0-9a-f]{64})$")


def source(kind, url=REGISTRY_SOURCE, captured_at=CAPTURED_AT):
    return {"kind": kind, "url": url, "captured_at": captured_at}


def provenance(kind, url=REGISTRY_SOURCE):
    return {"sources": [source(kind, url)], "captured_at": CAPTURED_AT}


def write(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def facts_for(value, prefix=""):
    facts = {}
    if isinstance(value, dict):
        if not value and prefix:
            facts[prefix] = {"state": "unknown", "reason": "not-observed", "provenance": provenance("registry-enrichment")}
        for key, child in value.items():
            if key in {"facts", "provenance", "huggingface", "container"}:
                continue
            path = f"{prefix}.{key}" if prefix else key
            facts.update(facts_for(child, path))
    elif isinstance(value, list):
        if not value and prefix:
            facts[prefix] = {"state": "unknown", "reason": "not-observed", "provenance": provenance("registry-enrichment")}
        for child in value:
            facts.update(facts_for(child, prefix + "[]"))
    elif value is None or value == "":
        reason = "not-observed"
        if prefix.endswith("revision"):
            reason = "artifact-revision-not-pinned"
        elif prefix.endswith("url"):
            reason = "canonical-url-not-published"
        elif prefix.endswith("size_gb"):
            reason = "artifact-size-not-published"
        elif ".capabilities." in f".{prefix}.":
            reason = "capability-not-verified"
        elif prefix.endswith("version") or prefix.endswith("graph_mode"):
            reason = "runtime-detail-not-published"
        elif prefix.endswith("kv_cache_tokens"):
            reason = "kv-cache-capacity-not-published"
        facts[prefix] = {"state": "unknown", "reason": reason, "provenance": provenance("registry-enrichment")}
    return facts


def hf_identity(repository, status=None, reason=None, link=None, link_type=None):
    if HF_REPOSITORY.fullmatch(repository or ""):
        public = repository not in HF_ACCESS_UNRESOLVED
        return {
            "repository": repository,
            "url": f"https://huggingface.co/{repository}",
            "status": status or ("unknown" if not public else "known"),
            "link_type": "repository",
            "reason": reason or ("hf-api-access-unresolved" if not public else "hf-api-confirmed-public"),
            "provenance": provenance("huggingface-api", f"https://huggingface.co/api/models/{repository}"),
        }
    query = quote(repository or "unknown", safe="")
    return {
        "repository": None,
        "url": link or f"https://huggingface.co/models?search={query}",
        "status": status or "unavailable",
        "link_type": link_type or "search",
        "reason": reason or "repository-not-an-owner-repo",
        "provenance": provenance("huggingface-search", link or f"https://huggingface.co/models?search={query}"),
    }


def enrich_models(root):
    for path in sorted((root / "model").glob("*.json")):
        row = json.loads(path.read_text())
        url = row.get("url")
        match = re.fullmatch(r"https://huggingface\.co/([^/\s]+)/([^/\s]+)/?", url or "")
        if match:
            identity = hf_identity(f"{match.group(1)}/{match.group(2)}")
        else:
            identity = hf_identity(row.get("name"), status="unknown", reason="canonical-model-repository-not-published")
        row["huggingface"] = identity
        row["provenance"] = provenance("normalized-model", url or REGISTRY_SOURCE)
        row["facts"] = facts_for(row)
        row["schema_version"] = SCHEMA
        write(path, row)


def enrich_instances(root):
    for path in sorted((root / "model-instance").glob("*.json")):
        row = json.loads(path.read_text())
        artifact_label = (row.get("weights") or {}).get("artifact")
        exact = EXACT_ARTIFACT_INSTANCE_REPOSITORIES.get(row.get("id")) or EXACT_ARTIFACT_REPOSITORIES.get(row.get("repository")) or EXACT_ARTIFACT_REPOSITORIES.get(artifact_label)
        if exact:
            repository, evidence = exact
            row["repository"] = repository
            row["url"] = f"https://huggingface.co/{repository}"
            identity = hf_identity(repository)
            identity["reason"] = "exact-artifact-match-from-publication" if evidence == "publication" else "exact-artifact-match-from-live-site"
            evidence_url = "https://local.ai" if evidence == "publication" else "https://local.ai/models"
            evidence_at = CAPTURED_AT if evidence == "publication" else "2026-08-27T07:40:30Z"
            identity["provenance"]["sources"].insert(0, source(f"local-ai-{evidence}", evidence_url, evidence_at))
            identity["provenance"]["captured_at"] = RECONCILED_AT
            identity["provenance"]["sources"][-1]["captured_at"] = RECONCILED_AT
            row["huggingface"] = identity
        else:
            row["huggingface"] = hf_identity(row.get("repository"))
        row["provenance"] = provenance("normalized-model-instance", row.get("url") or REGISTRY_SOURCE)
        row["facts"] = facts_for(row)
        row["schema_version"] = SCHEMA
        write(path, row)


def launch_source(recipe):
    launch = recipe.get("launch") or {}
    launch_source_value = launch.get("source")
    if isinstance(launch_source_value, dict) and isinstance(launch_source_value.get("repository"), str) and launch_source_value["repository"].startswith(("https://", "http://")):
        return launch_source_value["repository"]
    if isinstance(launch_source_value, str) and launch_source_value.startswith(("https://", "http://")):
        return launch_source_value
    if recipe.get("recipe_source") == "localmaxxing":
        return launch.get("url") or "https://www.localmaxxing.com/en/leaderboard"
    if recipe.get("recipe_source") == "exo-postgres":
        return PUBLICATION_SOURCE
    return REGISTRY_SOURCE


def container_for(recipe):
    launch = recipe.get("launch") or {}
    kind = launch.get("kind")
    image = launch.get("image")
    digest_match = DIGEST.search(image or "")
    compose = launch.get("compose") or {}
    if kind == "docker":
        state = "digest-pinned" if digest_match else "mutable"
        reason = "image-reference-in-launch" if digest_match else "image-tag-without-content-digest"
        return {"state": state, "runtime": "docker", "image": image, "digest": digest_match.group("digest") if digest_match else None, "compose_file": None, "source": [source("recipe-launch", launch_source(recipe))], "captured_at": CAPTURED_AT, "reason": reason}
    if kind == "docker-compose":
        return {"state": "indirect", "runtime": "docker-compose", "image": image, "digest": digest_match.group("digest") if digest_match else None, "compose_file": compose.get("file"), "source": [source("recipe-launch", launch_source(recipe))], "captured_at": CAPTURED_AT, "reason": "compose-manifest-resolves-image-outside-normalized-record"}
    return {"state": "none", "runtime": None, "image": None, "digest": None, "compose_file": None, "source": [source("recipe-launch", launch_source(recipe))], "captured_at": CAPTURED_AT, "reason": "non-container-launch-kind" if kind != "reference" else "reference-only-launch"}


def enrich_recipes(root):
    for path in sorted((root / "recipe").glob("*.json")):
        row = json.loads(path.read_text())
        launch = dict(row.get("launch") or {})
        launch["container"] = container_for(row)
        row["launch"] = launch
        row["provenance"] = provenance("normalized-recipe", launch_source(row))
        row["facts"] = facts_for(row)
        row["schema_version"] = SCHEMA
        write(path, row)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", default="registry")
    args = parser.parse_args()
    root = Path(args.root)
    enrich_models(root)
    enrich_instances(root)
    enrich_recipes(root)


if __name__ == "__main__":
    main()
