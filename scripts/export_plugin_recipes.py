#!/usr/bin/env python3
"""Emit the recipe file the Omarchy plugin vendors.

One entry per hardware id: the single validated, recommended, single-GPU
docker recipe for that card, joined flat with its model instance, model,
hardware match data, and acceptance speed. The plugin never fetches the
registry; it ships this file and re-gates every entry on load.

Fails when a hardware id has more than one recommended recipe. Warns on
stderr about hardware that has validated recipes but no recommended one,
which is the curation queue.

    python3 scripts/export_plugin_recipes.py [--out recipes.json]
"""

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REG = ROOT / "registry"
SCHEMA = "omarchy-local-ai/recipes/1"
NORM = re.compile(r"nvidia|geforce|intel|amd|radeon|generation|workstation|edition|[0-9]+gb|[^a-z0-9]")


def norm(name):
    return NORM.sub("", name.lower())


def load(collection):
    return {p.stem: json.loads(p.read_text()) for p in (REG / collection).glob("*.json")}


def registry_commit():
    try:
        return subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return ""


def speed_tps(sweeps, recipe):
    for sweep_id in recipe.get("speed_sweep_ids") or []:
        sweep = sweeps.get(sweep_id) or {}
        tps = (sweep.get("metrics") or {}).get("peak_generation_tps")
        if isinstance(tps, (int, float)) and tps > 0:
            return int(tps)
    return 0


def served_name(recipe, instance):
    arguments = (recipe.get("launch") or {}).get("arguments") or []
    if "--served-model-name" in arguments:
        return arguments[arguments.index("--served-model-name") + 1]
    return instance.get("served_name") or instance.get("repository")


def entry(recipe, instance, model, hardware, sweeps):
    launch = recipe["launch"]
    weights = instance.get("weights") or {}
    return {
        "id": recipe["id"],
        "model": {
            "id": model["id"],
            "name": model.get("name") or model["id"],
            "repository": instance.get("repository"),
            "revision": instance.get("revision"),
            "servedName": served_name(recipe, instance),
            "precision": weights.get("precision") or "?",
            "sizeGb": weights.get("size_gb") or 0,
        },
        "engine": (recipe.get("engine") or {}).get("name"),
        "capabilities": recipe.get("capabilities") or {},
        "serving": {
            "ctxTokens": (recipe.get("serving") or {}).get("max_context_tokens") or 0,
            "concurrency": (recipe.get("serving") or {}).get("max_concurrency") or 0,
        },
        "speed": {"tps": speed_tps(sweeps, recipe)},
        "weights": {
            # where the plugin puts the download under a ${MODEL_ROOT} mount; TabbyAPI loads <mount>/<model_name>
            "subdir": (recipe.get("metadata") or {}).get("weights_subdir") or "",
        },
        "image": {
            "provenance": (launch.get("provenance") or {}).get("kind") or "upstream",
            "attestation": (launch.get("provenance") or {}).get("attestation"),
        },
        "launch": {
            "image": launch["image"],
            "containerPort": launch.get("container_port"),
            "entrypoint": launch.get("entrypoint"),
            "arguments": launch.get("arguments") or [],
            "environment": launch.get("environment") or {},
            "mounts": launch.get("mounts") or [],
            "shm": launch.get("shm_size"),
            "ipc": launch.get("ipc"),
            "networkMode": launch.get("network_mode"),
            "capAdd": launch.get("cap_add") or [],
            "securityOpt": launch.get("security_opt") or [],
        },
        "validated": {
            "harness": ((recipe.get("metadata") or {}).get("acceptance") or {}).get("harness"),
            "acceptedAt": ((recipe.get("metadata") or {}).get("acceptance") or {}).get("accepted_at"),
        },
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="-", help="output path; - for stdout")
    args = parser.parse_args()

    recipes, instances, models, hardware, sweeps = (load(c) for c in ("recipe", "model-instance", "model", "hardware", "speed-sweep"))
    eligible = {}
    by_hardware = {}
    for recipe in recipes.values():
        launch = recipe.get("launch") or {}
        if recipe.get("status") != "validated" or launch.get("kind") != "docker" or recipe.get("hardware_count", 1) != 1:
            continue
        by_hardware.setdefault(recipe["hardware_id"], []).append(recipe)
        if recipe.get("recommended"):
            eligible.setdefault(recipe["hardware_id"], []).append(recipe)

    errors = []
    out = {}
    for hardware_id, picks in sorted(eligible.items()):
        if len(picks) > 1:
            errors.append(f"{hardware_id}: {len(picks)} recommended recipes: " + ", ".join(r["id"] for r in picks))
            continue
        recipe = picks[0]
        hw = hardware.get(hardware_id)
        instance = instances.get(recipe["model_instance_id"])
        model = models.get((instance or {}).get("model_id"))
        if not (hw and instance and model):
            errors.append(f"{recipe['id']}: unresolved hardware, instance, or model")
            continue
        names = sorted({norm(hw["name"])} | {norm(a) for a in hw.get("aliases") or []})
        out[hardware_id] = {
            "match": {
                "backend": hw.get("accelerator_backend"),
                "vramGb": (hw.get("memory") or {}).get("vram_gb"),
                "names": names,
                "name": hw["name"],
            },
            "recipe": entry(recipe, instance, model, hw, sweeps),
        }

    for hardware_id in sorted(set(by_hardware) - set(eligible)):
        print(f"queue: {hardware_id} has {len(by_hardware[hardware_id])} validated recipes, none recommended", file=sys.stderr)
    if errors:
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        return 1

    document = {
        "schemaVersion": SCHEMA,
        "registryCommit": registry_commit(),
        "generatedAt": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "hardware": out,
    }
    text = json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if args.out == "-":
        sys.stdout.write(text)
    else:
        Path(args.out).write_text(text)
        print(f"wrote {args.out}: {len(out)} hardware ids", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
