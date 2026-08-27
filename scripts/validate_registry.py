#!/usr/bin/env python3

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path


COLLECTIONS = ("hardware", "model", "model-instance", "recipe", "speed-sweeps")
SCHEMA = "local-ai-registry/v1"
FORBIDDEN_LAUNCH = ("--enforce-eager", "disable-cuda-graph", "disable-prefill-cuda-graph")
HF_REPOSITORY = re.compile(r"^[^/\s]+/[^/\s]+$")
HF_URL = re.compile(r"^https://huggingface\.co/[^/]+/[^/]+/?$")
HF_SEARCH = re.compile(r"^https://huggingface\.co/models\?search=.+$")
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


def load_collection(root, name, errors):
    records = {}
    for path in sorted((root / name).glob("*.json")):
        try:
            record = json.loads(path.read_text())
        except json.JSONDecodeError as error:
            errors.append(f"{path}: invalid JSON: {error}")
            continue
        identifier = record.get("id")
        if identifier != path.stem:
            errors.append(f"{path}: id {identifier!r} does not match filename")
        if record.get("schema_version") != SCHEMA:
            errors.append(f"{path}: schema_version must be {SCHEMA}")
        if identifier in records:
            errors.append(f"{path}: duplicate id {identifier}")
        records[identifier] = record
    return records


def require_reference(record, field, collection, errors):
    identifier = record.get(field)
    if identifier not in collection:
        errors.append(f"{record.get('id')}: unresolved {field} {identifier!r}")


def valid_timestamp(value):
    if not isinstance(value, str):
        return False
    try:
        dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        return value.endswith("Z")
    except ValueError:
        return False


def validate_provenance(value, label, errors):
    if not isinstance(value, dict):
        errors.append(f"{label}: provenance must be an object")
        return
    if not value.get("sources"):
        errors.append(f"{label}: provenance has no sources")
    if not isinstance(value.get("sources"), list):
        errors.append(f"{label}: provenance sources must be a list")
        return
    for source in value.get("sources", []):
        if not isinstance(source, dict) or not source.get("kind") or not source.get("url"):
            errors.append(f"{label}: provenance source requires kind and url")
        elif not isinstance(source["url"], str) or not re.match(r"^[a-z][a-z0-9+.-]*:", source["url"]):
            errors.append(f"{label}: provenance source URL is malformed")
        elif "captured_at" in source and not valid_timestamp(source["captured_at"]):
            errors.append(f"{label}: provenance source captured_at must be RFC3339 UTC")
    if not valid_timestamp(value.get("captured_at")):
        errors.append(f"{label}: provenance captured_at must be RFC3339 UTC")


def validate_facts(record, errors):
    identifier = record.get("id")
    facts = record.get("facts")
    if not isinstance(facts, dict):
        errors.append(f"{identifier}: facts must be an object")
        return
    for path, fact in facts.items():
        label = f"{identifier}: facts.{path}"
        if not isinstance(fact, dict):
            errors.append(f"{label} must be an object")
            continue
        if fact.get("state") not in ("known", "unknown", "unavailable", "not_applicable"):
            errors.append(f"{label}: invalid state")
        reason = fact.get("reason")
        structured_reason = isinstance(reason, dict) and isinstance(reason.get("code"), str) and bool(reason.get("code")) and isinstance(reason.get("detail"), str) and bool(reason.get("detail"))
        if fact.get("state") != "known" and not ((isinstance(reason, str) and bool(reason)) or structured_reason):
            errors.append(f"{label}: missing reason")
        if fact.get("state") == "known" and "value" not in fact:
            errors.append(f"{label}: known fact has no value")
        validate_provenance(fact.get("provenance"), label, errors)


def validate_huggingface(record, errors):
    identifier = record.get("id")
    identity = record.get("huggingface")
    label = f"{identifier}: huggingface"
    if not isinstance(identity, dict):
        errors.append(f"{label} identity is missing")
        return
    status = identity.get("status")
    repository = identity.get("repository")
    url = identity.get("url")
    link_type = identity.get("link_type")
    if status not in ("known", "unknown", "unavailable"):
        errors.append(f"{label}: invalid status")
    identity_reason = identity.get("reason")
    identity_structured_reason = isinstance(identity_reason, dict) and isinstance(identity_reason.get("code"), str) and bool(identity_reason.get("code")) and isinstance(identity_reason.get("detail"), str) and bool(identity_reason.get("detail"))
    if not ((isinstance(identity_reason, str) and bool(identity_reason)) or identity_structured_reason):
        errors.append(f"{label}: missing reason")
    validate_provenance(identity.get("provenance"), label, errors)
    hf_sources = (identity.get("provenance") or {}).get("sources", []) if isinstance(identity.get("provenance"), dict) else []
    source_kinds = {s.get("kind") for s in hf_sources if isinstance(s, dict)}
    if link_type == "repository":
        if not isinstance(repository, str) or not HF_REPOSITORY.fullmatch(repository) or not isinstance(url, str) or not HF_URL.fullmatch(url):
            errors.append(f"{label}: repository link must contain a valid owner/repo and canonical URL")
        elif url.rstrip("/") != f"https://huggingface.co/{repository}":
            errors.append(f"{label}: URL does not match repository")
        if status == "known" and "huggingface-api" not in source_kinds:
            errors.append(f"{label}: known repository requires a Hugging Face API source")
    elif link_type == "search":
        if repository is not None or not isinstance(url, str) or not HF_SEARCH.fullmatch(url):
            errors.append(f"{label}: search link must have null repository and HF search URL")
    else:
        errors.append(f"{label}: invalid link_type")


def validate_container(recipe, errors):
    identifier = recipe.get("id")
    launch = recipe.get("launch", {})
    container = launch.get("container")
    label = f"{identifier}: launch.container"
    if not isinstance(container, dict):
        errors.append(f"{label} is missing")
        return
    state = container.get("state")
    if state not in ("digest-pinned", "mutable", "indirect", "none"):
        errors.append(f"{label}: invalid state")
    if not container.get("reason"):
        errors.append(f"{label}: missing reason")
    if not isinstance(container.get("source"), list) or not container.get("source"):
        errors.append(f"{label}: source is required")
    for source in container.get("source", []):
        if not isinstance(source, dict) or not source.get("kind") or not source.get("url"):
            errors.append(f"{label}: malformed source")
    if not valid_timestamp(container.get("captured_at")):
        errors.append(f"{label}: captured_at must be RFC3339 UTC")
    kind = launch.get("kind")
    if kind == "reference" and state != "none":
        errors.append(f"{identifier}: reference launch must have container state none")
    if kind == "docker":
        image = launch.get("image")
        if not image:
            errors.append(f"{identifier}: Docker launch has no image")
        expected = "digest-pinned" if isinstance(image, str) and re.search(r"@sha256:[0-9a-f]{64}$", image) else "mutable"
        if state != expected:
            errors.append(f"{identifier}: Docker container state does not match image digest")
        if state == "digest-pinned" and (not isinstance(container.get("digest"), str) or not DIGEST.fullmatch(container["digest"])):
            errors.append(f"{identifier}: digest-pinned Docker launch has malformed digest")
        if state == "mutable" and container.get("digest") is not None:
            errors.append(f"{identifier}: mutable Docker launch cannot claim a digest")
    elif kind == "docker-compose":
        if not (launch.get("compose") or {}).get("file"):
            errors.append(f"{identifier}: compose launch has no compose file")
        if state not in ("indirect", "digest-pinned"):
            errors.append(f"{identifier}: compose launch has ambiguous container state")
        if container.get("compose_file") != (launch.get("compose") or {}).get("file"):
            errors.append(f"{identifier}: compose container provenance does not identify launch compose file")
    elif kind not in ("reference", "docker", "docker-compose") and state != "none":
        errors.append(f"{identifier}: non-container launch must have container state none")
    if state == "none" and any(container.get(field) is not None for field in ("runtime", "image", "digest", "compose_file")):
        errors.append(f"{identifier}: container state none must not carry runtime/image/digest/compose_file")


def validate(root):
    errors = []
    data = {name: load_collection(root, name, errors) for name in COLLECTIONS}

    for record in data["hardware"].values():
        for field in ("vendor", "name", "kind", "accelerator_backend", "memory", "sources"):
            if field not in record:
                errors.append(f"{record.get('id')}: missing hardware.{field}")
        capacity = record.get("memory", {}).get("vram_gb")
        if not isinstance(capacity, (int, float)) or capacity <= 0:
            errors.append(f"{record.get('id')}: memory.vram_gb must be positive")
        if "facts" in record:
            validate_facts(record, errors)
        availability = (record.get("commercial") or {}).get("availability")
        if availability is not None:
            if not isinstance(availability, dict) or availability.get("state") not in ("known", "unknown", "unavailable", "not_applicable"):
                errors.append(f"{record.get('id')}: commercial availability has invalid state")
            elif availability.get("state") != "known" and not availability.get("reason"):
                errors.append(f"{record.get('id')}: commercial availability requires a reason when not known")

    for record in data["model-instance"].values():
        require_reference(record, "model_id", data["model"], errors)
        validate_huggingface(record, errors)
        validate_provenance(record.get("provenance"), f"{record.get('id')}", errors)
        validate_facts(record, errors)

    for record in data["model"].values():
        validate_huggingface(record, errors)
        validate_provenance(record.get("provenance"), f"{record.get('id')}", errors)
        validate_facts(record, errors)

    for recipe in data["recipe"].values():
        require_reference(recipe, "model_instance_id", data["model-instance"], errors)
        require_reference(recipe, "hardware_id", data["hardware"], errors)
        validate_provenance(recipe.get("provenance"), f"{recipe.get('id')}", errors)
        validate_facts(recipe, errors)
        validate_container(recipe, errors)
        for sweep_id in recipe.get("speed_sweeps_ids", []):
            if sweep_id not in data["speed-sweeps"]:
                errors.append(f"{recipe['id']}: unresolved speed_sweeps_ids {sweep_id!r}")
        status = recipe.get("status")
        launch = recipe.get("launch", {})
        kind = launch.get("kind")
        if status not in ("candidate", "validated"):
            errors.append(f"{recipe['id']}: invalid status {status!r}")
        if recipe.get("recipe_source") in ("localmaxxing", "exo-postgres"):
            if status != "candidate" or kind != "reference":
                errors.append(f"{recipe['id']}: observed imports must be reference-only candidates")
            if "command_snippet" in json.dumps(launch).lower():
                errors.append(f"{recipe['id']}: candidate launch contains a command snippet")
        if status == "validated":
            if kind == "reference":
                errors.append(f"{recipe['id']}: validated recipe cannot use a reference launch")
            instance = data["model-instance"].get(recipe.get("model_instance_id"), {})
            if not instance.get("revision"):
                errors.append(f"{recipe['id']}: validated recipe has an unpinned model revision")
            if not recipe.get("speed_sweeps_ids"):
                errors.append(f"{recipe['id']}: validated recipe has no speed evidence")
            if kind == "docker" and not re.search(r"@sha256:[0-9a-f]{64}$", launch.get("image", "")):
                errors.append(f"{recipe['id']}: validated Docker launch has no image digest")
            if kind == "script" and not re.search(r"(?:^|/)[0-9a-f]{40}/", launch.get("script", {}).get("file", "")):
                errors.append(f"{recipe['id']}: validated script launch has no commit pin")
            launch_text = json.dumps(launch).lower()
            for forbidden in FORBIDDEN_LAUNCH:
                if forbidden in launch_text:
                    errors.append(f"{recipe['id']}: validated launch contains forbidden option {forbidden}")

    for sweep in data["speed-sweeps"].values():
        require_reference(sweep, "recipe_id", data["recipe"], errors)
        if not sweep.get("rows"):
            errors.append(f"{sweep['id']}: speed sweep has no rows")
        for row in sweep.get("rows", []):
            for field in ("decode_tok_s", "prefill_tok_s", "ttft_ms_p50", "peak_vram_gb"):
                value = row.get(field)
                if value is not None and (not isinstance(value, (int, float)) or value < 0):
                    errors.append(f"{sweep['id']}: {field} must be non-negative or null")

    prices = {}
    for path in sorted((root / "price").glob("*/*.json")):
        try:
            record = json.loads(path.read_text())
        except json.JSONDecodeError as error:
            errors.append(f"{path}: invalid JSON: {error}")
            continue
        identifier = record.get("id")
        if identifier in prices:
            errors.append(f"{path}: duplicate id {identifier}")
        prices[identifier] = record
        if record.get("schema_version") != SCHEMA:
            errors.append(f"{path}: schema_version must be {SCHEMA}")
        if not record.get("observations"):
            errors.append(f"{identifier}: price record has no observations")
        if not valid_timestamp(record.get("observed_at")):
            errors.append(f"{identifier}: observed_at must be RFC3339 UTC")
        currency = (record.get("region") or {}).get("currency")
        for hardware in record.get("hardware", []):
            if hardware.get("id") not in data["hardware"]:
                errors.append(f"{identifier}: unresolved hardware {hardware.get('id')!r}")
            if hardware.get("match_scope") not in ("exact", "family"):
                errors.append(f"{identifier}: invalid hardware match_scope")
        for observation in record.get("observations", []):
            if observation.get("currency") != currency:
                errors.append(f"{identifier}: observation currency does not match region")
            if not isinstance(observation.get("amount"), (int, float)) or observation["amount"] <= 0:
                errors.append(f"{identifier}: observation amount must be positive")
            if not valid_timestamp(observation.get("observed_at")):
                errors.append(f"{identifier}: observation observed_at must be RFC3339 UTC")
            if not isinstance(observation.get("url"), str) or not re.match(r"^https?://", observation["url"]):
                errors.append(f"{identifier}: observation URL is malformed")

    index_path = root / "index.json"
    try:
        index = json.loads(index_path.read_text())
    except (FileNotFoundError, json.JSONDecodeError) as error:
        errors.append(f"{index_path}: invalid or missing index: {error}")
        index = {}
    if index.get("schema_version") != SCHEMA:
        errors.append("index.json: wrong schema_version")
    for name in COLLECTIONS:
        expected = sorted(identifier for identifier in data[name] if identifier)
        actual = index.get("collections", {}).get(name)
        if actual != expected:
            errors.append(f"index.json: {name} collection is stale")
        count_key = name.replace("-", "_")
        if index.get("counts", {}).get(count_key) != len(expected):
            errors.append(f"index.json: {count_key} count is stale")
    expected_prices = sorted(identifier for identifier in prices if identifier)
    if index.get("collections", {}).get("price") != expected_prices:
        errors.append("index.json: price collection is stale")
    if index.get("counts", {}).get("price") != len(expected_prices):
        errors.append("index.json: price count is stale")

    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    counts = " ".join(f"{name}={len(data[name])}" for name in COLLECTIONS) + f" price={len(prices)}"
    print(f"registry valid: {counts}")
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", default="registry")
    args = parser.parse_args()
    raise SystemExit(validate(Path(args.root)))


if __name__ == "__main__":
    main()
