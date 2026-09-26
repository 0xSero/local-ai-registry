#!/usr/bin/env python3
"""plugin/v2/recipes.json for the Omarchy Local AI plugin (schema omarchy-local-ai/recipes/2), generated from
dist/catalog.json: each card's picks, recommended first. Recipes validated before the lab keep their original ids,
so running deployments stay recognised. `--check` fails if it is stale. Standard library only."""
import json, subprocess, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import lab

ROOT = lab.ROOT
OUT = ROOT / "plugin" / "v2" / "recipes.json"
GATEWAY = "ghcr.io/0xsero/gateway@sha256:d9743fcca4a9b8dd7f8fa18945ce6e5026f00dcab50b0727edd51690b88d4f32"
MIN_DRIVER = {"tabbyapi": "575.0", "sglang": "570.0", "vllm": "570.0", "llama.cpp": "535.0"}


def entry(key, r, meta):
    p = lab.profile(r["engine"])
    L = lab.render(r)
    caps = {"chat": True, "reasoning": "reasoning" in r["proof"][0]["gates"], "tools": "tools" in r["proof"][0]["gates"], "vision": L["vision"]}
    if "plugin" in p:  # a launch frozen from a validated recipe: its own export fields
        x = p["plugin"]
        rid = p["ids"].get(r["card"]) or f"{Path(key).name}.{r['card']}"
        weights = [{"repository": w["repo"], "revision": w["revision"], **xw} for w, xw in zip(L["weights"], x["weights"])]
        return {"id": rid, "name": x["name"], "family": x["family"], "format": x["format"], "engine": x["engine"], "servedName": x["servedName"],
                "sizeGb": x["sizeGb"], "cards": L.get("cards", 1), "image": L["image"], "minDriver": x["minDriver"], "weights": weights,
                "asset": {"name": x["asset"], "mountPath": L["config"]["at"], "text": L["config"]["text"]} if L["config"] else None,
                "scratch": x["scratch"], "launch": {"entrypoint": L["entrypoint"], "arguments": L["args"], "environment": L["env"], "port": L["port"], "shm": L["shm"]},
                "serving": x["serving"], "capabilities": {**x["capabilities"], **{k: v for k, v in caps.items() if v}}}
    m = meta["models"][r["model"]]
    b = meta["builds"][r["weights"]]
    name = L["weights"]["at"].rsplit("/", 1)[1]
    return {"id": f"{Path(key).name}.{r['card']}", "name": m["name"], "family": m["family"], "format": b["format"], "engine": p["engine"],
            "servedName": name, "sizeGb": b["size_gb"], "cards": 1, "image": L["image"], "minDriver": MIN_DRIVER.get(p["engine"], ""),
            "weights": [{"repository": L["weights"]["repo"], "revision": L["weights"]["revision"], "sizeGb": b["size_gb"], "layout": "dir",
                         "mountPath": L["weights"]["at"].rsplit("/", 1)[0], "dir": name, "files": ""}],
            "asset": {"name": f"{Path(key).name}.config.yml", "mountPath": L["config"]["at"], "text": L["config"]["text"]},
            "scratch": None, "launch": {"entrypoint": L["entrypoint"], "arguments": L["args"], "environment": L["env"], "port": L["port"], "shm": L["shm"]},
            "serving": {"ctxTokens": L["ctx"], "kvTokens": L["ctx"] * L["seqs"] + 1024 * L["seqs"]}, "capabilities": caps}


def build():
    cat = json.loads((ROOT / "dist" / "catalog.json").read_text())
    meta = json.loads((ROOT / "registry" / "models.json").read_text())
    hw = {}
    for card, c in sorted(cat["cards"].items()):
        if c["backend"] == "metal":
            continue  # Omarchy is Linux/container-only; native launches remain in catalog/SDKs.
        hw[card] = {"match": c["match"],
                    "recipes": [entry(k, cat["recipes"][k], meta) for k in c["picks"]]}
    head = {"schemaVersion": "omarchy-local-ai/recipes/2", "registryCommit": None, "generatedAt": None, "gateway": {"image": GATEWAY}}
    lines = ["{"] + [f'  {json.dumps(k)}: {json.dumps(v, ensure_ascii=False)},' for k, v in head.items()] + ['  "hardware": {']
    lines += [f'    {json.dumps(k)}: {json.dumps(v, ensure_ascii=False, separators=(",", ":"))}' + ("," if i < len(hw) - 1 else "") for i, (k, v) in enumerate(hw.items())]
    return "\n".join(lines + ["  }", "}"]) + "\n"


if __name__ == "__main__":
    text = build()
    if "--check" in sys.argv:
        ok = OUT.exists() and OUT.read_text() == text
        print("plugin/v2/recipes.json is current" if ok else "plugin/v2/recipes.json is stale: run lab/export_plugin.py")
        sys.exit(0 if ok else 1)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text)
    json.loads(text)
    print(f"wrote {OUT.relative_to(ROOT)}: {len(text)} bytes")
