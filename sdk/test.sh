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
const out = {}; for (const [i, c] of Object.entries(cat.cards)) { const k = c.picks[0]; out[i] = [detect(cat, c.name, c.vram_gb), steps({ key: k, ...cat.recipes[k] })]; }
console.log(JSON.stringify(out));"""], capture_output=True, text=True, check=True).stdout
for i, (got, st) in json.loads(js).items():
    k = cat["cards"][i]["picks"][0]
    assert got == i, (i, got)
    assert st == L.steps({"key": k, **cat["recipes"][k]}), f"js and python steps differ for {k}"
print(f"sdk ok: {len(cat['cards'])} cards, js and python agree")
PY
