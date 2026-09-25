#!/usr/bin/env python3
"""Seed production with what was already validated: for every card in plugin/v2/recipes.json, its
recommended recipe becomes a production recipe whose engine is `registry@<recipe id>` (the launch is the
validated record's, rendered from the plugin export) and whose proof is the old acceptance, marked
legacy. A lab run of the same card replaces it. Run once; it never overwrites a lab recipe."""
import json, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import lab

ROOT = lab.ROOT
v2 = json.loads((ROOT / "plugin" / "v2" / "recipes.json").read_text())
made = 0
for card, hw in sorted(v2["hardware"].items()):
    e = hw["recipes"][0]
    rec = json.loads((ROOT / "registry" / "recipe" / f"{e['id']}.json").read_text())
    acc = (rec.get("metadata") or {}).get("acceptance") or {}
    tps = None
    for sid in rec.get("speed_sweep_ids") or []:
        sw = ROOT / "registry" / "speed-sweep" / f"{sid}.json"
        if sw.exists():
            tps = (json.loads(sw.read_text()).get("metrics") or {}).get("peak_generation_tps") or tps
            if tps:
                break
    w = e["weights"][0]
    model = re.sub(r"[^a-z0-9.]+", "-", e["name"].lower()).strip("-")
    r = {"model": model, "weights": f"{w['repository']}@{w['revision']}", "engine": f"registry@{e['id']}", "set": {}, "card": card,
         "proof": [{"at": (acc.get("accepted_at") or "")[:10] or None, "on": "legacy", "gates": "load chat",
                    "tps": round(tps, 1) if tps else None, "legacy": True}]}
    ctx = (e.get("serving") or {}).get("ctxTokens") or 0
    out = lab.RECIPES / card / f"{model}.registry.{ctx // 1024}k.json"
    if any(p.name.split(".")[-3] != "registry" for p in (lab.RECIPES / card).glob("*.json")) if (lab.RECIPES / card).exists() else False:
        continue  # a lab recipe exists for this card already
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(r, separators=(",", ":")) + "\n")
    made += 1
print(f"legacy recipes written: {made}")
