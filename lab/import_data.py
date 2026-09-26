#!/usr/bin/env python3
"""Bring a recipe validated before the lab from data/ into production, exactly as it was validated:
its launch becomes a frozen profile in registry/engines/, and a recipe points at it with a legacy proof.
A lab run of the card later replaces it.

    lab/import_data.py <data recipe id> <model id in registry/models.json>

Launches that need more than a plain container say so in the profile: `flags` (host IPC or networking),
`machines` (several computers, one per rank) or `kind: host` (a program, not a container)."""
import json, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import lab

D = lab.ROOT / "data" / "registry"
load = lambda p: json.loads(Path(p).read_text())


def freeze(rid, model):
    r = load(D / "recipe" / f"{rid}.json")
    L = r["launch"]
    mi = load(D / "model-instance" / f"{r['model_instance_id']}.json")
    acc = (r.get("metadata") or {}).get("acceptance") or {}
    tps = None
    for sid in r.get("speed_sweep_ids") or []:
        f = D / "speed-sweep" / f"{sid}.json"
        if f.exists():
            tps = (load(f).get("metrics") or {}).get("peak_generation_tps") or tps
    ctx = (r.get("serving") or {}).get("max_context_tokens") or 0
    engine = r["engine"]["name"].lower()
    if L["kind"] == "host":
        tag = r["metadata"].get("flm_tag")
        prof = {"kind": "host", "engine": engine, "about": f"{mi['served_name']} on {r['hardware_id']}, as validated in {rid}",
                "command": [engine, "serve", tag, "--port", str(L["container_port"])], "install": "https://github.com/FastFlowLM/FastFlowLM",
                "port": L["container_port"], "ctx": ctx, "seqs": 1, "vision": False, "backend": L.get("accelerator_backend")}
    else:
        weights, config, flags = [], None, []
        for m in L.get("mounts") or []:
            src = m["source"]
            if src.startswith("${MODEL_ROOT}/"):
                weights.append({"repo": mi["repository"], "revision": mi["revision"], "at": m["target"], "layout": "dir"})
            elif "huggingface" in src:
                weights.append({"repo": mi["repository"], "revision": mi["revision"], "at": m["target"], "layout": "hub"})
            elif src.startswith("asset/"):
                config = {"at": m["target"], "text": (D / src).read_text()}
        if L.get("ipc") == "host":
            flags.append("--ipc host")
        if L.get("network_mode") == "host" or r["hardware_count"] > 1 and "nnodes" in " ".join(L.get("arguments") or []):
            flags.append("--network host")
        prof = {"engine": engine, "about": f"{mi['served_name']} as validated in {rid}", "image": L["image"], "backend": L.get("accelerator_backend"),
                "port": L["container_port"], "entrypoint": L.get("entrypoint"), "args": L.get("arguments") or [], "env": L.get("environment") or {},
                "shm": L.get("shm_size"), "weights": weights, "config": config, "ctx": ctx, "seqs": 1,
                "vision": bool((r.get("capabilities") or {}).get("vision")), "cards": 1}
        if flags:
            prof["flags"] = flags
        if "--nnodes" in prof["args"]:
            prof["machines"] = r["hardware_count"]
    base = re.sub(r"[^a-z0-9.]+", "-", f"{engine}-{model}-{mi['weights'].get('precision') or mi['weights']['format']}-{ctx // 1024}k".lower()).strip("-")
    name, n = base, 2
    while (lab.ENGINES / f"{name}.json").exists() and load(lab.ENGINES / f"{name}.json").get("frozen_from") != [rid]:
        name, n = f"{base}-v{n}", n + 1
    prof = {"id": name, **prof, "frozen_from": [rid]}
    (lab.ENGINES / f"{name}.json").write_text(json.dumps(prof, indent=2) + "\n")
    digest = prof["image"].split("@sha256:")[1][:12] if prof.get("image") and "@sha256:" in prof["image"] else "host"
    recipe = {"model": model, "weights": f"{mi['repository']}@{mi['revision']}" if mi.get("revision") else "baked-into-image",
              "engine": f"{name}@{digest}", "set": {}, "card": r["hardware_id"],
              "proof": [{"at": (acc.get("accepted_at") or "")[:10] or None, "on": "legacy", "gates": "load chat" + (" reasoning tools" if (r.get("capabilities") or {}).get("tools") else ""),
                         "tps": round(tps, 1) if tps else None, "legacy": True}]}
    out = lab.recipe_path(recipe, lab.render(recipe))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(recipe, separators=(",", ":")) + "\n")
    print(f"{rid} -> {out.relative_to(lab.ROOT)} (profile {name})")


if __name__ == "__main__":
    freeze(sys.argv[1], sys.argv[2])
