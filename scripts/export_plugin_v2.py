#!/usr/bin/env python3
"""Export the plugin catalog, schema 2: only what a launch consumes.

Schema 1 (scripts/export_plugin_recipes.py) carries every launch field a record has, and the
plugin refuses the dangerous ones at run time. Schema 2 turns that around: the file can only
express what the plugin will run, so nothing in it needs refusing.

    - mounts and devices are not data. A recipe names its weights (repository, revision, layout,
      where they go in the container), at most one config asset, and at most one scratch path.
      The plugin derives every host path from those and from the GPUs the user chose.
    - no IPC, capabilities, security options, network mode or device lists exist in the schema.
    - evidence (provenance text, acceptance records, speed) stays in the registry.
    - docker recipes only.

One hardware entry per line, so a recipe change is a one-line diff in the plugin repository.

    python3 scripts/export_plugin_v2.py --out plugin/v2/recipes.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import export_plugin_recipes as v1  # noqa: E402

SCHEMA = "omarchy-local-ai/recipes/2"
HUB_MOUNT = "~/.cache/huggingface"


def weights_item(repository, revision, size_gb, layout, mount_path, subdir="", files=""):
    return {
        "repository": repository,
        "revision": revision,
        "sizeGb": round(float(size_gb or 0), 3),
        "layout": layout,          # "dir": the files as they are; "hub": the Hub cache tree
        "mountPath": mount_path,   # where that directory appears in the container
        "dir": subdir,             # dir layout: the files live under this name inside the mount
        "files": files,            # dir layout: one file (a GGUF) out of a repository of many, or ""
    }


def entry(recipe, instance, model, hardware):
    """The schema-2 recipe, or a refusal string when the record cannot be expressed."""
    launch = recipe.get("launch") or {}
    if (launch.get("kind") or "docker") != "docker":
        return "host recipes are not exported"
    weights, asset, scratch = [], None, None
    subdir = (recipe.get("metadata") or {}).get("weights_subdir") or ""
    served = v1.served_name(recipe, instance) or ""
    files = served.rsplit("/", 1)[-1] if served.endswith(".gguf") else ""
    for mount in launch.get("mounts") or []:
        source = str((mount or {}).get("source") or "")
        target = str((mount or {}).get("target") or "")
        if source.startswith("${MODEL_ROOT}/"):
            provision = (mount or {}).get("provision")
            if provision:
                weights.append(weights_item(provision.get("repository"), provision.get("revision"),
                                            provision.get("size_gb"), "dir", target))
            else:
                # A mount whose target already names the subdirectory holds the files at its root:
                # mount the parent instead, so the files stay where the launch arguments point.
                if subdir and target.rstrip("/").endswith("/" + subdir):
                    target = target.rstrip("/")[: -len(subdir) - 1] or "/"
                weights.append(weights_item(instance.get("repository"), instance.get("revision"),
                                            (instance.get("weights") or {}).get("size_gb"), "dir",
                                            target, subdir, files))
        elif source == HUB_MOUNT or source.startswith(HUB_MOUNT + "/"):
            weights.append(weights_item(instance.get("repository"), instance.get("revision"),
                                        (instance.get("weights") or {}).get("size_gb"), "hub", target))
        elif source.startswith("${CACHE_ROOT}/"):
            if scratch:
                return "more than one scratch mount"
            scratch = target
        elif source.startswith("asset/"):
            if asset:
                return "more than one asset"
            name = source[len("asset/"):]
            path = v1.REG / "asset" / name
            if "/" in name or ".." in name or not path.is_file():
                return f"asset {name} is not shipped"
            asset = {"name": name, "mountPath": target, "text": path.read_text()}
        elif source == "/dev/dri/by-path":
            continue   # derived from the chosen GPUs
        else:
            return f"mount {source} cannot be expressed"
    # no weights mount means the image carries the model: nothing to download, nothing to mount
    for w in weights:
        if not (w["repository"] and v1.REVISION_PINNED.fullmatch(w["revision"] or "")):
            return "weights are not pinned to a revision"
    image = launch.get("image") or ""
    if not v1.DIGEST_PINNED.search(image):
        return "image is not digest-pinned"
    if not isinstance(launch.get("container_port"), int):
        return "invalid container port"
    serving = recipe.get("serving") or {}
    return {
        "id": recipe["id"],
        "name": model.get("name") or model["id"],
        "engine": (recipe.get("engine") or {}).get("name"),
        "servedName": served,
        "sizeGb": round(sum(w["sizeGb"] for w in weights), 3),
        "cards": v1.card_count(recipe) or 1,
        "image": image,
        "minDriver": v1.min_driver(image) if hardware.get("accelerator_backend") == "nvidia" else "",
        "weights": weights,
        "asset": asset,
        "scratch": scratch,
        "launch": {
            "entrypoint": launch.get("entrypoint"),
            "arguments": launch.get("arguments") or [],
            "environment": launch.get("environment") or {},
            "port": launch.get("container_port"),
            "shm": launch.get("shm_size"),
        },
        "serving": {
            "ctxTokens": serving.get("max_context_tokens") or 0,
            "kvTokens": serving.get("kv_cache_tokens") or 0,
        },
        "capabilities": recipe.get("capabilities") or {},
    }


def build():
    recipes, instances, models, hardware = (v1.load(c) for c in ("recipe", "model-instance", "model", "hardware"))
    recommended, by_hardware = {}, {}
    for recipe in recipes.values():
        if not v1.plugin_exportable(recipe) or (recipe.get("launch") or {}).get("kind") == "host":
            continue
        by_hardware.setdefault(recipe["hardware_id"], []).append(recipe)
        if recipe.get("recommended") and recipe.get("hardware_count", 1) == 1:
            recommended.setdefault(recipe["hardware_id"], []).append(recipe)
    errors, out = [], {}
    for hardware_id, picks in sorted(recommended.items()):
        if len(picks) > 1:
            errors.append(f"{hardware_id}: {len(picks)} recommended recipes: " + ", ".join(r["id"] for r in picks))
            continue
        hw = hardware.get(hardware_id)
        if not hw:
            errors.append(f"{hardware_id}: no hardware record")
            continue
        exported = []
        ordered = picks + sorted((r for r in by_hardware[hardware_id] if r["id"] != picks[0]["id"]), key=lambda r: r["id"])
        for recipe in ordered:
            instance = instances.get(recipe["model_instance_id"])
            model = models.get((instance or {}).get("model_id"))
            if not (instance and model):
                msg = f"{recipe['id']}: unresolved instance or model"
                if recipe is picks[0]:
                    errors.append(msg)
                else:
                    print(f"skip: {msg}", file=sys.stderr)
                continue
            refusal = v1.plugin_refusal(recipe, instance)
            result = refusal or entry(recipe, instance, model, hw)
            if isinstance(result, str):
                if recipe is picks[0]:
                    errors.append(f"{recipe['id']}: {result}")
                else:
                    print(f"skip: {recipe['id']}: {result}", file=sys.stderr)
                continue
            exported.append(result)
        if not exported:
            continue
        names = sorted({v1.norm(hw["name"])} | {v1.norm(a) for a in hw.get("aliases") or []})
        out[hardware_id] = {
            "match": {
                "backend": hw.get("accelerator_backend"),
                "name": hw["name"],
                "names": names,
                "vramGb": (hw.get("memory") or {}).get("vram_gb"),
            },
            "recipes": exported,   # the first is the recommended one
        }
    for hardware_id in sorted(set(by_hardware) - set(recommended)):
        print(f"queue: {hardware_id} has {len(by_hardware[hardware_id])} validated recipes, none recommended", file=sys.stderr)
    return out, errors


def render(document):
    """The header pretty, then one hardware entry per line."""
    head = {k: document[k] for k in ("schemaVersion", "registryCommit", "generatedAt", "gateway")}
    lines = [json.dumps(head, indent=2, sort_keys=True, ensure_ascii=False)[:-2].rstrip() + ",", '  "hardware": {']
    items = sorted(document["hardware"].items())
    for i, (hardware_id, entry_) in enumerate(items):
        comma = "," if i < len(items) - 1 else ""
        lines.append(f'    {json.dumps(hardware_id)}: {json.dumps(entry_, sort_keys=True, separators=(",", ":"), ensure_ascii=False)}{comma}')
    lines.append("  }")
    lines.append("}")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="-", help="output path; - for stdout")
    args = parser.parse_args()
    out, errors = build()
    if errors:
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        return 1
    stamp = v1.registry_stamp()
    document = {
        "schemaVersion": SCHEMA,
        "registryCommit": stamp[0],
        "generatedAt": stamp[1],
        "gateway": {"image": v1.GATEWAY_IMAGE},
        "hardware": out,
    }
    text = render(document)
    json.loads(text)   # the one-entry-per-line writer must still be JSON
    if args.out == "-":
        sys.stdout.write(text)
    else:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text)
        recipes = sum(len(h["recipes"]) for h in out.values())
        print(f"wrote {args.out}: {len(out)} hardware ids, {recipes} recipes", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
