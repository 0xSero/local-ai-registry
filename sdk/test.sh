#!/bin/sh
# Both SDKs agree on every card: the right card for its driver name, and the same steps.
set -e
cd "$(dirname "$0")/.."
python3 - <<'PY'
import json, subprocess, sys
sys.path.insert(0, "sdk/python")
import local_ai_registry as L
cat = json.load(open("dist/catalog.json"))
names = {i: c["name"] for i, c in cat["cards"].items()}
for i, c in cat["cards"].items():
    got = L.detect(cat, "NVIDIA GeForce " + c["name"] if c["vendor"] == "nvidia" else c["name"], c["vram_gb"])
    assert got == i, (i, got)
js = subprocess.run(["node", "--input-type=module", "-e", """
import { readFileSync } from "node:fs"; import { detect, steps } from "./sdk/js/index.js";
const cat = JSON.parse(readFileSync("dist/catalog.json"));
const out = {}; for (const [i, c] of Object.entries(cat.cards)) out[i] = [detect(cat, c.name, c.vram_gb), [...c.picks, ...c.more].map((k) => steps({ key: k, ...cat.recipes[k] }))];
console.log(JSON.stringify(out));"""], capture_output=True, text=True, check=True).stdout
n = 0
for i, (got, sts) in json.loads(js).items():
    assert got == i, (i, got)
    for k, st in zip(cat["cards"][i]["picks"] + cat["cards"][i]["more"], sts):
        assert st == L.steps({"key": k, **cat["recipes"][k]}), f"js and python steps differ for {k}"
        n += 1
print(f"sdk ok: {len(cat['cards'])} cards, {n} recipes, js and python agree")
PY
