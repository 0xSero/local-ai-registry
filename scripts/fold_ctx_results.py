#!/_#!/usr/bin/env python3
"""Fold the ctx-ceiling campaign into the focus-model matrix.

Inputs (all under /Users/sero/exo-ai/focus-probes/):
  ctx-vast.json    — CtxVastLane: 4 rentals x ladder
  ctx-fleet.json   — CtxFleetLane: pop-os, omarchy, spark-2822, spark-de5c
  ctx-apple.json    — CtxAppleLane: M1 Max 32GB (llama.cpp + mlx-lm)

Updates each existing ollama-tp1 / llamacpp / mlxml recipe for these
(model, hardware) pairs with a metadata.ctx_ceiling block carrying the
MEASURED ladder result. Also bumps serving.max_context_tokens to the
measured ceiling (never lowers an existing higher value). Pairs without a
live measurement are left untouched; the campaign findings are
printed as a gap report.
"""
import json
from pathlib import Path

ROOT = Path("registry")
NOW = "2026-09-01T00:00:00Z"
DIR = Path("/Users/sero/exo-ai/focus-probes")

MODEL_TAGS = {
    "gemma": "gemma-4-12b-it",
    "lfm": "lfm2.5-2.6b",
    "qwen3.5": "qwen3.5-9b",
    "qwen3.8": "qwen3.8-27b",
    "qwen3.6": "qwen3.6-35b-a3b",
}
GPU_MAP = [
    # (source, gpu_name-in-report, registry hardware_id, engine)
    ("ctx-vast.json", "RTX 3080 Ti 12GB", "rtx-3080-ti-12gb", "ollama"),
    ("ctx-vast.json", "RTX A4000 16GB", "rtx-a4000-16gb", "ollama"),
    ("ctx-vast.json", "RTX 5080 16GB", "rtx-5080-16gb", "ollama"),
    ("ctx-vast.json", "RTX 5090 32GB", "rtx-5090-32gb", "ollama"),
    ("ctx-fleet.json", "pop-os", "rtx-pro-6000-blackwell-96gb", "ollama"),
    ("ctx-fleet.json", "omarchy", "rtx-3090-24gb", "ollama"),
    ("ctx-fleet.json", "spark-2822", "dgx-spark-gb10-128gb", "ollama"),
    ("ctx-fleet.json", "spark-de5c", "dgx-spark-gb10-128gb", "ollama"),
    ("ctx-apple.json", "m1-max-llamacpp-gemma", "apple-m1-max-32gb", "llama.cpp"),
    ("ctx-apple.json", "m1-max-llamacpp-lfm", "apple-m1-max-32gb", "llama.cpp"),
    ("ctx-apple.json", "m1-max-mlx-qwen35", "apple-m1-max-32gb", "mlx-lm"),
]


def load(name):
    return json.loads((DIR / name).read_text())


def model_results(blob):
    """Normalize the per-model entries of any lane report."""
    out = {}
    if isinstance(blob, dict):
        for k, v in blob.items():
            if isinstance(v, dict) and ("max_ok_ctx" in v or "status" in v):
                out[k.split(":", 1)[0]] = v
    elif isinstance(blob, list):
        for e in blob:
            if isinstance(e, dict) and "model" in e:
                out[e["model"]] = e
    return out


def main():
    (ROOT / "speed-sweep").mkdir(exist_ok=True)
    findings = []
    updated = 0
    for fname, gpu_key, hw, engine in GPU_MAP:
        report = load(fname)
        # results may live at top level per host or nested per rental
        entries = {}
        def walk(o):
            if isinstance(o, dict):
                for k, v in o.items():
                    if k in MODEL_TAGS and isinstance(v, dict):
                        entries[k] = v
                    elif isinstance(v, (dict, list)):
                        walk(v)
            elif isinstance(o, list):
                for v in o:
                    if isinstance(v, dict) and v.get("model") in MODEL_TAGS:
                        entries[v["model"]] = v
                    walk(v)
        if fname == "ctx-vast.json":
            # scope per-rental: match this tuple's GPU name against the rental record
            entries = {}
            for rental in report.get("rentals", []):
                if rental.get("gpu") != gpu_key:
                    continue
                for item in rental.get("results", []):
                    if isinstance(item, dict) and item.get("model") in MODEL_TAGS:
                        entries[item["model"]] = item
        else:
            walk(report)
        # fleet lane: compact string format "max_ok / oom X (detail) / rate"
        if fname == "ctx-apple.json":
            # gpu_key forms: "m1-max-llamacpp-gemma" | "m1-max-llamacpp-lfm" | "m1-max-mlx-qwen35"
            parts = gpu_key.split("-")
            engine_key = parts[2] if len(parts) > 2 else None  # llamacpp | mlx
            model_key = parts[3] if len(parts) > 3 else None   # gemma | lfm | qwen35
            engine_name = {"llamacpp": "llama.cpp", "mlx": "mlx-lm"}.get(engine_key)
            model_short = {"gemma": "gemma", "lfm": "lfm", "qwen35": "qwen3.5"}.get(model_key)
            entries = {}
            if engine_name and model_short:
                block = report.get("engines", {}).get(engine_name, {}).get("models", {}).get(model_short)
                if isinstance(block, dict):
                    entries[model_short] = block
        if not entries and fname == "ctx-fleet.json":
            for host_key_full, block in report.items():
                if host_key_full in ("campaign", "GB10 note", "cleanup"):
                    continue
                short_host = host_key_full.split(" (", 1)[0].strip()
                if short_host != gpu_key:
                    continue
                for short, s in block.items():
                    ev = {"status": "ok"}
                    head = s.split(" / ", 1)[0]
                    ev["max_ok_ctx"] = int(head) if head.isdigit() else None
                    rest = s.split(" / ", 1)[1] if " / " in s else ""
                    if rest.startswith("oom"):
                        ev["oom_ctx"] = None if "none" in rest else rest.split(" ", 2)[-1] if len(rest.split(" ")) > 2 else rest
                        if "none" not in rest:
                            ev["status"] = "partial"
                            ev["note"] = rest
                    entries[short] = ev
        by_model = {}
        for k, v in entries.items():
            key = k.split(":", 1)[0].split(" (", 1)[0].strip()
            by_model.setdefault(key, v)
        for short, ev in by_model.items():
            model = MODEL_TAGS.get(short)
            if model is None:
                findings.append((fname, short, "unknown-model", str(ev)[:120]))
                continue
            status = ev.get("status", "ok")
            if status not in ("ok", "partial"):
                findings.append((gpu_key, model, status, ev.get("note", ev.get("reason", ""))))
                continue
            max_ok = ev.get("max_ok_ctx")
            if not isinstance(max_ok, int):
                findings.append((gpu_key, model, "no-measured-ceiling", str(ev)[:160]))
                continue
            tim = ev.get("timings") or {}
            # locate the recipe file: engine-specific suffix ordering
            QUANT_MAP = {
                'gemma-4-12b-it': 'q4-k-m',
                'lfm2.5-2.6b': 'q4-k-m',
                'qwen3.8-27b': 'ud-q4-k-m',
                'qwen3.6-35b-a3b': 'ud-q4-k-m',
                'qwen3.5-9b': 'q4-k-m',
            }
            ENG_MAP = {'ollama': 'ollama', 'llama.cpp': 'llamacpp', 'mlx-lm': 'mlxml'}
            slug = model.replace('.', '').replace('-it', '').replace('-a3b', '')
            rid = slug + '-' + QUANT_MAP[model] + '-' + hw + '-' + ENG_MAP[engine] + '-tp1'

            rpath = ROOT / "recipe" / f"{rid}.json"
            if not rpath.exists():
                findings.append((gpu_key, model, "recipe-not-found", rid))
                continue
            recipe = json.loads(rpath.read_text())
            block = {
                "measured_at": NOW,
                "method": "ctx-ladder-binary-search (16384 doubling to failure), ctx_probe.py v3 strict acceptance",
                "max_ok_ctx": max_ok,
                "oom_ctx": ev.get("oom_ctx"),
                "timings": tim,
                "source": {"kind": "ctx-ceiling-run", "url": "https://github.com/0xSero/local-ai-registry", "captured_at": NOW},
            }
            recipe.setdefault("metadata", {})["ctx_ceiling"] = block
            serving = recipe.setdefault("serving", {})
            cur = serving.get("max_context_tokens")
            if cur is None or cur < max_ok:
                serving["max_context_tokens"] = max_ok
            # keep timings fresh in metadata.validation.evidence only if the ceiling run provided ns-free second timings
            if tim.get("eval_duration_s") is not None:
                evd = recipe.setdefault("metadata", {}).setdefault("validation", {}).setdefault("evidence", {})
                evd["ctx_ceiling_timings_s"] = tim
            rpath.write_text(json.dumps(recipe, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
            updated += 1
            print(f"updated {rid} -> ctx {max_ok}")

    print(f"\nrecipes updated: {updated}")
    print("findings (no measurement, left untouched):")
    for g, m, s, r in findings:
        print(f"  {g}: {m} — {s}: {r[:160]}")


if __name__ == "__main__":
    main()
