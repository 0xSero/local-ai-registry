#!/usr/bin/env python3
"""Derive a candidate recipe for another hardware id from an existing recipe.

The launch contract (validated `launch`, or a candidate's `draft_launch`) is
copied as the new candidate's `draft_launch`. Nothing about the source's
evidence is carried over: no speed sweeps, no acceptance metadata, no facts.
The clone is a candidate until `validate_runpod.py` or `local-ai validate`
accepts it on the target card.

    python3 scripts/clone_candidate.py <source-recipe-id> <hardware-id>
        [--id <new-id>] [--instance <model-instance-id>] [--ctx <tokens>]
        [--set-arg FLAG VALUE]... [--description TEXT]
"""

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

REG = Path(__file__).resolve().parent.parent / "registry"
NOW = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
CTX_FLAGS = ("-c", "--ctx-size", "--max-model-len", "--context-length")


def read(collection, identifier):
    path = REG / collection / f"{identifier}.json"
    if not path.exists():
        raise SystemExit(f"no {collection} record {identifier}")
    return json.loads(path.read_text())


def hardware_slug(hardware_id):
    # rtx-3090-24gb -> rtx3090 ; rtx-pro-4000-blackwell-24gb -> rtxpro4000 ; rtx-2000-ada-16gb -> rtx2000ada
    parts = [p for p in hardware_id.split("-") if not p.endswith("gb") and p != "blackwell"]
    return "".join(parts)


def derive_id(source_id, source_hw, target_hw):
    for old in (source_hw, hardware_slug(source_hw)):
        if old in source_id:
            return source_id.replace(old, hardware_slug(target_hw) if old != source_hw else target_hw)
    return f"{source_id}-{hardware_slug(target_hw)}"


def set_arg(arguments, flag, value):
    if flag in arguments:
        arguments[arguments.index(flag) + 1] = value
    else:
        arguments += [flag, value]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source_id")
    parser.add_argument("hardware_id")
    parser.add_argument("--id")
    parser.add_argument("--instance", help="use a different model-instance id")
    parser.add_argument("--ctx", type=int, help="context tokens; sets the engine's context flag and serving.max_context_tokens")
    parser.add_argument("--set-arg", nargs=2, action="append", default=[], metavar=("FLAG", "VALUE"))
    parser.add_argument("--description")
    parser.add_argument("--force", action="store_true", help="overwrite an existing candidate with this id")
    args = parser.parse_args()

    source = read("recipe", args.source_id)
    read("hardware", args.hardware_id)
    launch = source.get("launch") or {}
    contract = launch if launch.get("kind") == "docker" else source.get("draft_launch")
    if not contract:
        raise SystemExit(f"{args.source_id} has no docker launch or draft_launch to clone")
    # draft_launch schema: no container/provenance/network_mode, ipc only as a string, synthesized required
    contract = {k: v for k, v in contract.items()
                if k not in ("container", "synthesized", "provenance", "network_mode", "ipc")}
    contract.setdefault("kind", "docker")
    contract["synthesized"] = {"template": "clone-candidate-v1", "generated_at": NOW, "image_provenance": source["id"]}
    arguments = list(contract.get("arguments") or [])
    for flag, value in args.set_arg:
        set_arg(arguments, flag, value)
    serving = dict(source.get("serving") or {})
    if args.ctx:
        flag = next((f for f in CTX_FLAGS if f in arguments), None)
        if flag is None:
            raise SystemExit("--ctx given but the contract has no context flag to set")
        set_arg(arguments, flag, str(args.ctx))
        serving["max_context_tokens"] = args.ctx
    contract["arguments"] = arguments

    instance_id = args.instance or source["model_instance_id"]
    instance = read("model-instance", instance_id)
    if args.instance:
        # the model changed: point the engine at the new repository
        for flag in ("--model", "-hf", "--model-path"):
            if flag in arguments:
                value = instance["repository"]
                quant = (instance.get("weights") or {}).get("format") or ""
                if flag == "-hf" and re.fullmatch(r"I?Q[0-9][A-Z0-9_]*|F16|BF16", quant, re.IGNORECASE):
                    value = f"{value}:{quant}"  # llama.cpp -hf repo:quant pins which GGUF is fetched
                arguments[arguments.index(flag) + 1] = value
        if "--revision" in arguments and instance.get("revision"):
            arguments[arguments.index("--revision") + 1] = instance["revision"]
        if "--served-model-name" in arguments and instance.get("served_name"):
            arguments[arguments.index("--served-model-name") + 1] = instance["served_name"]

    new_id = args.id or derive_id(source["id"], source["hardware_id"], args.hardware_id)
    path = REG / "recipe" / f"{new_id}.json"
    if path.exists() and not args.force:
        existing = json.loads(path.read_text())
        if existing.get("status") == "validated":
            raise SystemExit(f"{new_id} already exists and is validated; refusing to overwrite")
        raise SystemExit(f"{new_id} already exists; pass --force to overwrite the candidate")

    source_ref = {"kind": "normalized-recipe", "url": "https://github.com/0xSero/local-ai-registry", "captured_at": NOW}
    recipe = {
        "schema_version": "local-ai-registry/v1",
        "id": new_id,
        "recipe_source": "0xsero",
        "status": "candidate",
        "model_instance_id": instance_id,
        "hardware_id": args.hardware_id,
        "hardware_count": 1,
        "engine": source["engine"],
        "capabilities": source.get("capabilities") or {"chat": None, "reasoning": None, "tools": None, "vision": None},
        "serving": {"kv_cache_tokens": None, "max_concurrency": serving.get("max_concurrency"),
                    "max_context_tokens": serving.get("max_context_tokens"), "tensor_parallel": 1},
        "launch": {"kind": "reference", "container": {
            "state": "none", "runtime": None, "image": None, "digest": None, "compose_file": None,
            "reason": "draft-pending-acceptance", "captured_at": NOW, "source": [source_ref]}},
        "draft_launch": contract,
        "speed_sweep_ids": [],
        "metadata": {"derived_from": source["id"]},
        "provenance": {"captured_at": NOW, "sources": [source_ref]},
        "facts": {},
        "description": args.description or (
            f"Candidate derived from {source['id']} for {args.hardware_id}; the launch contract is copied, "
            f"the evidence is not. Pending acceptance on the target card."),
    }
    path.write_text(json.dumps(recipe, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    print(new_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
