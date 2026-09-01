#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path("registry")


def rates(ev):
    decode = None
    if ev.get("eval_duration_ns"):
        decode = round(ev["eval_count"] / ev["eval_duration_ns"] * 1e9, 1)
    prefill = None
    if ev.get("prompt_eval_duration_ns"):
        prefill = round(ev["prompt_eval_count"] / ev["prompt_eval_duration_ns"] * 1e9, 1)
    ttft = None
    if ev.get("load_duration_ns"):
        ttft = round(ev["load_duration_ns"] / 1e6, 1)
    return decode, prefill, ttft


def nested(d, *keys):
    for k in keys:
        if not isinstance(d, dict):
            return {}
        d = d.get(k) or {}
    return d


def main():
    fixed = 0
    for recipe_path in sorted((ROOT / "recipe").glob("*ollama-tp1.json")):
        recipe = json.loads(recipe_path.read_text())
        ev = nested(recipe, "metadata", "validation", "evidence")
        if not ev.get("eval_duration_ns"):
            continue
        decode, prefill, ttft = rates(ev)
        sweep_path = ROOT / "speed-sweep" / (recipe["id"] + "-sweep.json")
        if not sweep_path.exists():
            print("skip (no sweep): " + recipe["id"])
            continue
        sweep = json.loads(sweep_path.read_text())
        rows = sweep.get("rows") or [None]
        row = rows[0]
        m = sweep.get("metrics") or {}
        changed = False
        if row:
            for field, value in (
                ("decode_tok_s", decode),
                ("decode_tok_s_per_stream", decode),
                ("prefill_tok_s", prefill),
                ("ttft_ms_p50", ttft),
            ):
                if value is not None and row.get(field) != value:
                    row[field] = value
                    changed = True
        for field, value in (("peak_generation_tps", decode), ("peak_prompt_tps", prefill)):
            if value is not None and m.get(field) != value:
                m[field] = value
                changed = True
        if changed:
            sweep_path.write_text(json.dumps(sweep, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
            fixed += 1
            print("fixed " + recipe["id"])
    print("sweeps fixed: " + str(fixed))


if __name__ == "__main__":
    main()
