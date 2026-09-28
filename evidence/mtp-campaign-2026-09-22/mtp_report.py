#!/usr/bin/env python3
"""Before/after table for the MTP campaign from registry data (Markdown to stdout).

Every recipe carrying metadata.mtp_campaign is a campaign recipe. "Before" is the decode rate of the
evidence detached into metadata.previous_evidence (acceptance sweep, or a campaign sweep's peak C1
generation rate); "after" is the new acceptance sweep's decode rate. Both are the acceptance harness's
client-side estimate at ~256 prompt tokens, so they compare like with like.
"""
import json
from pathlib import Path

REG = Path(__file__).resolve().parent.parent / "registry"


def load(coll, rid):
    p = REG / coll / f"{rid}.json"
    return json.loads(p.read_text()) if p.exists() else None


BASE = "de896528"  # campaign base commit: the sweeps as they were before any re-acceptance overwrote them


def load_before(sid):
    """The sweep as committed before the campaign (accept_recipe.py reuses <recipe>-acceptance as the id,
    so a re-validated recipe's old acceptance file is overwritten on disk)."""
    import subprocess
    r = subprocess.run(["git", "show", f"{BASE}:registry/speed-sweep/{sid}.json"], capture_output=True, text=True, cwd=REG.parent)
    return json.loads(r.stdout) if r.returncode == 0 else load("speed-sweep", sid)


def decode_of(sweep_ids, before=False):
    """Median C1 decode tok/s from acceptance rows, else the sweep's peak C1 generation rate."""
    for sid in sweep_ids or []:
        s = load_before(sid) if before else load("speed-sweep", sid)
        if not s:
            continue
        rows = [r for r in s.get("rows") or [] if r.get("concurrency") == 1 and r.get("decode_tok_s")]
        if rows:
            return rows[0]["decode_tok_s"], s.get("source", {}).get("kind") or "campaign"
        m = s.get("metrics") or {}
        peak = m.get("peak_generation_tps")
        if isinstance(peak, dict):
            peak = peak.get("value") or peak.get("tps") or peak.get("tok_s") or next((v for v in peak.values() if isinstance(v, (int, float))), None)
        if peak:
            return peak, "campaign peak"
    return None, None


def main():
    rows = []
    for p in sorted((REG / "recipe").glob("*.json")):
        r = json.loads(p.read_text())
        camp = (r.get("metadata") or {}).get("mtp_campaign")
        if not camp:
            continue
        inst = load("model-instance", r["model_instance_id"]) or {}
        prev = (r.get("metadata") or {}).get("previous_evidence") or {}
        before, bkind = decode_of(prev.get("speed_sweep_ids"), before=True)
        after, akind = (decode_of(r.get("speed_sweep_ids")) if r.get("status") == "validated" else (None, None))
        rows.append({
            "hardware": r["hardware_id"], "recipe": r["id"], "engine": (r.get("engine") or {}).get("name"),
            "model": inst.get("model_id"), "quant": inst.get("served_name") or inst.get("id"),
            "ctx": (r.get("serving") or {}).get("max_context_tokens"),
            "vision": (r.get("capabilities") or {}).get("vision") is True,
            "status": r.get("status"), "recommended": bool(r.get("recommended")),
            "before": before, "before_kind": bkind, "after": after,
            "new": "derived_from" in (r.get("metadata") or {}) and not prev,
            "change": camp.get("change", "")[:90],
        })
    rows.sort(key=lambda x: (x["hardware"], x["recipe"]))
    print("| card | recipe | engine | quant | ctx | vision | before tok/s | after tok/s | status |")
    print("|---|---|---|---|---|---|---|---|---|")
    for x in rows:
        b = f"{x['before']:.1f}" if x["before"] else ("new" if x["new"] else "n/a")
        a = f"{x['after']:.1f}" if x["after"] else "-"
        st = ("validated" if x["status"] == "validated" else "candidate") + (", recommended" if x["recommended"] else "")
        print(f"| {x['hardware']} | {x['recipe']} | {x['engine']} | {x['quant']} | {x['ctx']} | {'yes' if x['vision'] else 'no'} | {b} | {a} | {st} |")
    n_ok = sum(1 for x in rows if x["status"] == "validated")
    print(f"\n{len(rows)} campaign recipes, {n_ok} validated, {sum(1 for x in rows if x['recommended'])} recommended", file=__import__('sys').stderr)


if __name__ == "__main__":
    main()
