#!/usr/bin/env python3

import argparse
import json
import re
import sys
from pathlib import Path


COLLECTIONS = ("hardware", "model", "model-instance", "recipe", "speed-sweeps")
SCHEMA = "local-ai-registry/v1"
FORBIDDEN_LAUNCH = ("--enforce-eager", "disable-cuda-graph", "disable-prefill-cuda-graph")


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

    for record in data["model-instance"].values():
        require_reference(record, "model_id", data["model"], errors)

    for recipe in data["recipe"].values():
        require_reference(recipe, "model_instance_id", data["model-instance"], errors)
        require_reference(recipe, "hardware_id", data["hardware"], errors)
        for sweep_id in recipe.get("speed_sweeps_ids", []):
            if sweep_id not in data["speed-sweeps"]:
                errors.append(f"{recipe['id']}: unresolved speed_sweeps_ids {sweep_id!r}")
        status = recipe.get("status")
        launch = recipe.get("launch", {})
        kind = launch.get("kind")
        if status not in ("candidate", "validated"):
            errors.append(f"{recipe['id']}: invalid status {status!r}")
        if recipe.get("recipe_source") == "localmaxxing":
            if status != "candidate" or kind != "reference":
                errors.append(f"{recipe['id']}: LocalMaxxing rows must be reference-only candidates")
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

    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    counts = " ".join(f"{name}={len(data[name])}" for name in COLLECTIONS)
    print(f"registry valid: {counts}")
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", default="registry")
    args = parser.parse_args()
    raise SystemExit(validate(Path(args.root)))


if __name__ == "__main__":
    main()
