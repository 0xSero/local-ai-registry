#!/usr/bin/env python3
"""Keep exactly one recommended recipe per hardware id.

Among validated, single-GPU docker recipes on each card, prefer the engine
order below (EXL3 on TabbyAPI or SGLang ahead of llama.cpp, per the V1 plan),
then the largest context, then the most recent acceptance. Every other recipe
on that card loses the flag. Prints the resulting table; --dry-run only prints.

    python3 scripts/recommend.py [--dry-run] [--only <hardware-id>]...
"""

import argparse
import json
import sys
from pathlib import Path

REG = Path(__file__).resolve().parent.parent / "registry"
ENGINE_RANK = {"tabbyapi": 0, "sglang": 1, "vllm": 2, "llama.cpp": 3, "llama-cpp": 3}
# V1 tier map: the card's VRAM picks the model; a card falls back down the tiers when its own tier has no validated recipe
TIERS = [
    (32, ["qwen3-8-27b", "qwen3-6-35b-a3b"]),
    (24, ["gemma-4-12b-it", "gemma-4-12b"]),
    (12, ["qwen3-5-9b"]),
    (0, ["lfm2-5-2-6b"]),
]


def tier_models(vram_gb):
    """Model ids in preference order for a card: its own tier first, then each lower tier."""
    order = []
    for floor, models in TIERS:
        if vram_gb >= floor:
            order += models
    return order


def rank(recipe, models):
    model = recipe["_model_id"]
    tier = models.index(model) if model in models else len(models)
    engine = ((recipe.get("engine") or {}).get("name") or "").lower()
    ctx = (recipe.get("serving") or {}).get("max_context_tokens") or 0
    accepted = ((recipe.get("metadata") or {}).get("acceptance") or {}).get("accepted_at") or ""
    return (tier, ENGINE_RANK.get(engine, 9), -ctx, accepted and -int(accepted.replace("-", "").replace(":", "").replace("T", "").replace("Z", "") or 0))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--only", action="append", default=[])
    args = parser.parse_args()

    by_hardware = {}
    for path in sorted((REG / "recipe").glob("*.json")):
        recipe = json.loads(path.read_text())
        launch = recipe.get("launch") or {}
        if recipe.get("status") != "validated" or launch.get("kind") != "docker" or recipe.get("hardware_count", 1) != 1:
            continue
        if (launch.get("network_mode") or "bridge") != "bridge" or launch.get("ipc") == "host":
            continue  # the plugin gate refuses these; never recommend them
        instance_path = REG / "model-instance" / f"{recipe['model_instance_id']}.json"
        recipe["_model_id"] = json.loads(instance_path.read_text()).get("model_id") if instance_path.exists() else ""
        by_hardware.setdefault(recipe["hardware_id"], []).append((path, recipe))

    changed = 0
    for hardware_id, entries in sorted(by_hardware.items()):
        if args.only and hardware_id not in args.only:
            continue
        hw = json.loads((REG / "hardware" / f"{hardware_id}.json").read_text())
        models = tier_models((hw.get("memory") or {}).get("vram_gb") or 0)
        entries.sort(key=lambda e: rank(e[1], models))
        for _, recipe in entries:
            recipe.pop("_model_id", None)
        winner = entries[0][1]["id"]
        for path, recipe in entries:
            want = recipe["id"] == winner
            if bool(recipe.get("recommended")) != want:
                changed += 1
                if not args.dry_run:
                    if want:
                        recipe["recommended"] = True
                    else:
                        recipe.pop("recommended", None)
                    path.write_text(json.dumps(recipe, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
        top = entries[0][1]
        print(f"{hardware_id:30} {winner:50} {((top.get('engine') or {}).get('name') or ''):10} ctx={(top.get('serving') or {}).get('max_context_tokens')}")
    print(f"{'would change' if args.dry_run else 'changed'} {changed} flag(s)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
