#!/usr/bin/env python3
"""Build dist/catalog.json from the production recipes: every card, its setups (one card, four cards in one machine,
two machines, ...), each with its picks (at most 3, one per model, the first recommended) and the rest of its recipes
(more), and each recipe with its rendered launch. The card's own `picks` and `more` are its one-card setup, so a
client that runs one card never sees a recipe that needs several. `--check` fails if it is stale.

Ranking on a card: family order in registry/models.json, then the newest model, then decode speed. A model
older than max_age_days, or outside the families, is never picked. Standard library only."""
import datetime as dt, hashlib, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import lab

ROOT = lab.ROOT
OUT = ROOT / "dist" / "catalog.json"


def label(hw, n, machines):
    """How people say a setup: "RTX PRO 6000 Blackwell", "4 × RTX PRO 6000 Blackwell (one machine)", "2 × DGX Spark GB10"."""
    name = hw["name"]
    if machines > 1:
        return f"{machines} × {name}" + (f" ({n} cards each)" if n > 1 else "")
    return f"{n} × {name} (one machine)" if n > 1 else name


def build(today=None):
    today = today or dt.date.today()
    meta = json.loads((ROOT / "registry" / "models.json").read_text())
    fam = {f: i for i, f in enumerate(meta["families"])}
    cards, recipes = {}, {}
    for f in sorted(lab.RECIPES.rglob("*.json")):
        r = json.loads(f.read_text())
        m = meta["models"].get(r["model"])
        old = 2 if r["proof"][0].get("reported") else 1 if r["proof"][0].get("legacy") else 0
        if old != 1 and (not m or m["family"] not in fam or (today - dt.date.fromisoformat(m["released"])).days > meta["max_age_days"]):
            continue
        key = str(f.relative_to(lab.RECIPES).with_suffix(""))
        recipes[key] = {**r, "launch": lab.render(r)}
        # a lab recipe ranks above a legacy one, and a legacy one above one reported by its publisher
        mf = (fam.get(m["family"], len(fam)), -dt.date.fromisoformat(m["released"]).toordinal()) if m else (len(fam), 0)
        rank = (old, *mf)
        launch = recipes[key]["launch"]
        setup = (launch.get("cards") or 1, launch.get("machines") or 1)
        cards.setdefault(r["card"], {}).setdefault(setup, []).append((*rank, -(r["proof"][0]["tps"] or 0), r["model"], key))
    out_cards = {}
    for card, by_setup in sorted(cards.items()):
        hw = lab.card(card)
        setups = []
        for (n, machines), rows in sorted(by_setup.items(), key=lambda s: (s[0][0] * s[0][1], s[0][1])):  # smallest first
            picks, seen = [], set()
            for *_, model, key in sorted(rows):
                if model not in seen and len(picks) < 3:
                    picks.append(key)
                    seen.add(model)
            more = [key for *_, key in sorted(rows) if key not in picks]  # every other recipe for the setup, best first
            setups.append({"cards": n, "machines": machines, "label": label(hw, n, machines), "vram_gb": hw["vram_gb"] * n * machines,
                           "picks": picks, "more": more})
        one = next((s for s in setups if s["cards"] == s["machines"] == 1), {"picks": [], "more": []})
        out_cards[card] = {**{k: hw[k] for k in ("name", "vendor", "backend", "vram_gb", "bandwidth_gb_s", "match")},
                           "picks": one["picks"], "more": one["more"], "setups": setups}
    used = {k for c in out_cards.values() for s in c["setups"] for k in s["picks"] + s["more"]}
    body = {"schema": "local-ai-registry/catalog/4", "models": meta["models"], "builds": meta.get("builds", {}), "cards": out_cards,
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
