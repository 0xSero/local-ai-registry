#!/usr/bin/env python3
"""Build dist/catalog.json from the production recipes: every card, its picks (at most 3, one per model,
the first recommended) and each picked recipe with its rendered launch. `--check` fails if it is stale.

Ranking on a card: family order in lab/models.json, then the newest model, then decode speed. A model
older than max_age_days, or outside the families, is never picked. Standard library only."""
import datetime as dt, hashlib, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import lab

ROOT = lab.ROOT
OUT = ROOT / "dist" / "catalog.json"


def build(today=None):
    today = today or dt.date.today()
    meta = json.loads((ROOT / "lab" / "models.json").read_text())
    fam = {f: i for i, f in enumerate(meta["families"])}
    cards, recipes = {}, {}
    for f in sorted(lab.RECIPES.rglob("*.json")):
        r = json.loads(f.read_text())
        m = meta["models"].get(r["model"])
        if not m or m["family"] not in fam:
            continue
        if (today - dt.date.fromisoformat(m["released"])).days > meta["max_age_days"]:
            continue
        key = f"{r['card']}/{f.stem}"
        recipes[key] = {**r, "launch": lab.render(r)}
        cards.setdefault(r["card"], []).append((fam[m["family"]], -dt.date.fromisoformat(m["released"]).toordinal(), -r["proof"][0]["tps"], r["model"], key))
    out_cards = {}
    for card, rows in sorted(cards.items()):
        hw = json.loads((lab.CARDS / f"{card}.json").read_text())
        picks, seen = [], set()
        for *_, model, key in sorted(rows):
            if model not in seen and len(picks) < 3:
                picks.append(key)
                seen.add(model)
        out_cards[card] = {"name": hw.get("name"), "vendor": hw.get("vendor"), "backend": hw.get("accelerator_backend"),
                           "vram_gb": (hw.get("memory") or {}).get("vram_gb"), "names": hw.get("product_names") or [], "picks": picks}
    used = {k for c in out_cards.values() for k in c["picks"]}
    body = {"schema": "local-ai-registry/catalog/3", "models": meta["models"], "cards": out_cards,
            "recipes": {k: v for k, v in sorted(recipes.items()) if k in used}}
    text = json.dumps(body, separators=(",", ":"), sort_keys=True)
    return json.dumps({**body, "sha256": hashlib.sha256(text.encode()).hexdigest()}, separators=(",", ":"), sort_keys=True) + "\n"


if __name__ == "__main__":
    text = build()
    if "--check" in sys.argv:
        ok = OUT.exists() and OUT.read_text() == text
        print("dist/catalog.json is current" if ok else "dist/catalog.json is stale: run lab/catalog.py")
        sys.exit(0 if ok else 1)
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(text)
    print(f"wrote {OUT.relative_to(ROOT)}: {len(text)} bytes")
