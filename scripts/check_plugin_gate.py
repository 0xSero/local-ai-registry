#!/usr/bin/env python3
"""Run the Omarchy local-ai plugin's recipe gate against every validated Docker recipe.

The plugin (basecamp/omarchy PR #8836) refuses to launch a recipe unless it
passes a safety gate: the record chain must resolve, the image must be
digest-pinned, the model revision must be pinned, and every mount source must
be a portable path — a ${MODEL_ROOT}/${CACHE_ROOT} placeholder, a ~/.cache
path, the /dev/dri/by-path device directory, or a repo-relative asset.
Absolute host paths are blocked. This script mirrors that gate so a registry
change that would silently block recipes in the plugin fails CI here instead.
"""

import argparse
import json
import re
import sys
from pathlib import Path

DIGEST_PINNED = re.compile(r"@sha256:[0-9a-f]{64}$")
REVISION_PINNED = re.compile(r"^[0-9a-f]{40,64}$")
FORBIDDEN_ARGUMENT = re.compile(r"enforce.eager|disable.?cuda.?graph", re.IGNORECASE)
PLACEHOLDER_MOUNT = re.compile(r"^\$\{(MODEL_ROOT|CACHE_ROOT)\}/[^\0]+$")


def load(path, errors):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError) as error:
        errors.append(f"{path}: unreadable record: {error}")
        return None


def check_mount_source(identifier, source, root, errors):
    if not isinstance(source, str) or not source:
        errors.append(f"{identifier}: mount has no source")
        return
    if ".." in source:
        errors.append(f"{identifier}: mount source escapes its boundary: {source}")
        return
    if PLACEHOLDER_MOUNT.fullmatch(source):
        return
    if source.startswith("~/.cache/"):
        return
    if source == "/dev/dri/by-path":
        return
    if source.startswith(("/", "~")):
        errors.append(f"{identifier}: plugin blocks absolute mount source {source}")
        return
    asset = (root / source).resolve()
    if root.resolve() not in asset.parents or not asset.is_file():
        errors.append(f"{identifier}: mount source is not a registry asset: {source}")


def check_recipe(root, recipe, errors):
    identifier = recipe.get("id")
    launch = recipe.get("launch") or {}

    instance = load(root / "model-instance" / f"{recipe.get('model_instance_id')}.json", errors)
    if instance is None:
        return
    if load(root / "model" / f"{instance.get('model_id')}.json", errors) is None:
        return
    if load(root / "hardware" / f"{recipe.get('hardware_id')}.json", errors) is None:
        return

    if not DIGEST_PINNED.search(launch.get("image") or ""):
        errors.append(f"{identifier}: plugin gate requires a digest-pinned image")
    if not REVISION_PINNED.fullmatch(instance.get("revision") or ""):
        errors.append(f"{identifier}: plugin gate requires a pinned model revision")
    if not isinstance(launch.get("container_port"), int):
        errors.append(f"{identifier}: plugin gate requires a numeric container_port")
    for argument in launch.get("arguments") or []:
        if isinstance(argument, str) and FORBIDDEN_ARGUMENT.search(argument):
            errors.append(f"{identifier}: plugin gate forbids launch argument {argument!r}")
    for mount in launch.get("mounts") or []:
        check_mount_source(identifier, (mount or {}).get("source"), root, errors)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", default="registry")
    args = parser.parse_args()
    root = Path(args.root)

    errors = []
    checked = 0
    for path in sorted((root / "recipe").glob("*.json")):
        recipe = load(path, errors)
        if not recipe or recipe.get("status") != "validated":
            continue
        if (recipe.get("launch") or {}).get("kind") != "docker":
            continue
        checked += 1
        check_recipe(root, recipe, errors)

    if errors:
        print("\n".join(errors), file=sys.stderr)
        raise SystemExit(1)
    print(f"plugin gate clean: {checked} validated docker recipes")


if __name__ == "__main__":
    main()
