#!/usr/bin/env python3
"""Emit the recipe file the Omarchy plugin vendors.

One entry per hardware id: the single validated, recommended, single-GPU
docker recipe for that card, joined flat with its model instance, model,
hardware match data, and acceptance speed — plus every other validated
docker recipe for that card that passes the plugin's gate, exported as
`recipes` alternates (tensor parallelism becomes the card claim). The
plugin vendors this file and can refresh the published copy. It re-gates
every entry on load.

Fails when a hardware id has more than one recommended recipe. Warns on
stderr about hardware that has validated recipes but no recommended one,
which is the curation queue, and about validated recipes left out of the
alternates because the plugin's gate would refuse them.

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
# The gateway every launch pairs with the engine. Built and attested by github.com/0xSero/local-ai-images.
GATEWAY_IMAGE = "ghcr.io/0xsero/gateway@sha256:6b3f953f12cd32b0e2351515999c6c3312d4732692473607565e8296fd35226a"
GATEWAY_PROVENANCE = {
    "kind": "self-built-attested",
    "source": "https://github.com/0xSero/local-ai-images",
    "dockerfile": "https://github.com/0xSero/local-ai-images/blob/main/gateway/Dockerfile",
    "workflow": "https://github.com/0xSero/local-ai-images/actions/runs/35164534977",
    "attestation": f"gh attestation verify oci://{GATEWAY_IMAGE} -o 0xSero",
}
# Minimum NVIDIA driver per image family, from each image's CUDA version (NVIDIA_REQUIRE_CUDA):
# SGLang dev-cu12 is CUDA 12.9 (needs 575+); the vLLM image is CUDA 12.8 (570+); llama.cpp
# server-cuda12 failed CUDA init on 550 and ran on 570+; TabbyAPI cu13 ships forward-compat for 535+.
MIN_DRIVER = [
    ("lmsysorg/sglang", "575.0"),
    ("vllm/vllm-openai", "570.0"),
    ("ghcr.io/ggml-org/llama.cpp", "570.0"),
    ("ghcr.io/0xsero/tabbyapi-exl3", "535.0"),
    ("ghcr.io/theroyallab/tabbyapi", "535.0"),
]


def min_driver(image):
    for prefix, version in MIN_DRIVER:
        if image.startswith(prefix):
            return version
    return ""
NORM = re.compile(r"nvidia|geforce|intel|amd|radeon|generation|workstation|edition|[0-9]+gb|[^a-z0-9]")
DIGEST_PINNED = re.compile(r"@sha256:[0-9a-f]{64}$")
REVISION_PINNED = re.compile(r"^[0-9a-f]{40,64}$")
FORBIDDEN_ARGUMENT = re.compile(r"enforce.eager|disable.?cuda.?graph", re.IGNORECASE)
PLACEHOLDER_OK = re.compile(r"^\$\{(MODEL_ROOT|CACHE_ROOT)\}$")


def norm(name):
    return NORM.sub("", name.lower())


def card_count(recipe):
    # The registry owns the claim, including engines configured by environment or YAML.
    if recipe.get("hardware_count"):
        return recipe["hardware_count"] if recipe["hardware_count"] > 1 else None
    args = " ".join(str(a) for a in (recipe.get("launch") or {}).get("arguments") or [])
    m = re.search(r"(?:--tensor-parallel-size|--tp-size|--tp|-tp)[= ](\d+)", args)
    n = int(m.group(1)) if m else 1
    return n if n > 1 else None


def plugin_refusal(recipe, instance):
    """Mirror the plugin's gate (lib/recipes.sh gate_reason): only recipes the plugin
    would actually launch ship as alternates. Returns a refusal string or None."""
    launch = recipe.get("launch") or {}
    if not DIGEST_PINNED.search(launch.get("image") or ""):
        return "image is not digest-pinned"
    if not REVISION_PINNED.fullmatch((instance or {}).get("revision") or ""):
        return "model revision is not pinned"
    if (launch.get("network_mode") or "bridge") != "bridge":
        return f"requires {launch.get('network_mode')} networking"
    if (launch.get("ipc") or "") == "host":
        return "requires host IPC"
    if launch.get("cap_add"):
        return "requires extra kernel capabilities"
    if launch.get("security_opt"):
        return "requires a weakened security profile"
    if not isinstance(launch.get("container_port"), int):
        return "invalid container port"
    for argument in launch.get("arguments") or []:
        if isinstance(argument, str) and FORBIDDEN_ARGUMENT.search(argument):
            return "disallowed launch argument"
    for placeholder in re.findall(r"\$\{[^}]*\}", json.dumps(launch)):
        if not PLACEHOLDER_OK.fullmatch(placeholder):
            return f"needs an unsupported placeholder {placeholder}"
    for mount in launch.get("mounts") or []:
        source = str((mount or {}).get("source") or "")
        if source.startswith(("${MODEL_ROOT}/", "${CACHE_ROOT}/")):
            if ".." in source:
                return f"mounts unsafe host path {source}"
            if source.startswith("${MODEL_ROOT}/") and not (mount or {}).get("read_only"):
                return "model weights must be mounted read-only"
        elif source == "~/.cache/huggingface" or source.startswith("~/.cache/huggingface/"):
            if ".." in source:
                return f"mounts unsafe host path {source}"
        elif source == "/dev/dri/by-path":
            pass
        elif source.startswith("asset/"):
            name = source[len("asset/"):]
            if "/" in name or ".." in name or not (REG / "asset" / name).is_file():
                return f"asset {name} is not shipped"
        else:
            return f"mounts unsafe host path {source}"
    return None


def load(collection):
    return {p.stem: json.loads(p.read_text()) for p in (REG / collection).glob("*.json")}


def registry_stamp():
    """(commit, ISO date) of the last commit that touched registry/, so regenerating on an unrelated
    commit is a no-op and CI can require the committed export to be current."""
    try:
        out = subprocess.run(["git", "-C", str(ROOT), "log", "-1", "--format=%H %cI", "--", "registry"], capture_output=True, text=True, check=True).stdout.split()
        when = dt.datetime.fromisoformat(out[1]).astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        return out[0], when
    except Exception:
        return "", dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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
            "kvTokens": (recipe.get("serving") or {}).get("kv_cache_tokens") or 0,
            "concurrency": (recipe.get("serving") or {}).get("max_concurrency") or 0,
        },
        "speed": {"tps": speed_tps(sweeps, recipe)},
        "minDriver": min_driver(launch["image"]) if hardware.get("accelerator_backend") == "nvidia" else "",
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
        if recipe.get("status") != "validated" or launch.get("kind") != "docker":
            continue
        by_hardware.setdefault(recipe["hardware_id"], []).append(recipe)
        if recipe.get("recommended") and recipe.get("hardware_count", 1) == 1:
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
        alternates = []
        for alt in by_hardware.get(hardware_id, []):
            if alt["id"] == recipe["id"]:
                continue
            alt_instance = instances.get(alt["model_instance_id"])
            alt_model = models.get((alt_instance or {}).get("model_id"))
            if not (alt_instance and alt_model):
                print(f"queue: {alt['id']}: unresolved instance or model", file=sys.stderr)
                continue
            refusal = plugin_refusal(alt, alt_instance)
            if refusal:
                print(f"skip: {alt['id']}: {refusal}", file=sys.stderr)
                continue
            exported_alt = entry(alt, alt_instance, alt_model, hw, sweeps)
            cards = card_count(alt)
            if cards:
                exported_alt["cards"] = cards
            alternates.append(exported_alt)
        alternates.sort(key=lambda e: e["id"])
        out[hardware_id] = {
            "match": {
                "backend": hw.get("accelerator_backend"),
                "vramGb": (hw.get("memory") or {}).get("vram_gb"),
                "names": names,
                "name": hw["name"],
            },
            "recipe": entry(recipe, instance, model, hw, sweeps),
            **({"recipes": alternates} if alternates else {}),
        }

    for hardware_id in sorted(set(by_hardware) - set(eligible)):
        print(f"queue: {hardware_id} has {len(by_hardware[hardware_id])} validated recipes, none recommended", file=sys.stderr)
    if errors:
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        return 1

    # config assets the recipes mount, shipped inline so the plugin needs no registry checkout
    assets = {}
    for exported in out.values():
        for recipe_entry in [exported["recipe"]] + exported.get("recipes", []):
            for mount in recipe_entry["launch"]["mounts"]:
                source = str(mount.get("source") or "")
                if source.startswith("asset/"):
                    name = source[len("asset/"):]
                    assets[name] = (REG / "asset" / name).read_text()
    stamp = registry_stamp()
    document = {
        "schemaVersion": SCHEMA,
        "registryCommit": stamp[0],
        "generatedAt": stamp[1],
        "gateway": {"image": GATEWAY_IMAGE, "provenance": GATEWAY_PROVENANCE},
        "assets": assets,
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
