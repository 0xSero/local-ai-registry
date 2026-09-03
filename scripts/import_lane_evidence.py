"""Import audited lane experiment evidence into registry recipes + speed sweeps.

Reads the four lane reports (Ampere, Ada 4070, 4070-STI, 4080, Blackwell-final),
derives tok/s + TtFT from the raw ollama counters, and writes one candidate
recipe + one speed-sweep per measured (model, GPU) pair. Only pairs whose
hardware exists in the registry are imported; skips and blocked lanes are
recorded in a notes file, never invented.
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "registry"
SCHEMA = "local-ai-registry/v1"
NOW = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

REPORTS = {
    "ampere": Path("/tmp/ampere-lane-report.json"),
    "ada-4070": Path("/tmp/ada-4070-probes.jsonl"),
    "ada-4070sti": Path("/tmp/ada-4070sti-probes.jsonl"),
    "ada-4080": Path("/tmp/ada-4080-probes.jsonl"),
    "blackwell": Path("/tmp/focus-blackwell-final.json"),
}

# lane gpu key -> registry hardware id
GPU_MAP = {
    "rtx3060ti": "rtx-3060-ti-8gb",
    "rtx3070": "rtx-3070-8gb",
    "rtx3080": "rtx-3080-10gb",
    "rtx3080ti": "rtx-3080-ti-12gb",
    "rtxa4000": None,
    "rtx5060ti": "rtx-5060-ti-16gb",
    "rtx5070": "rtx-5070-12gb",
    "rtx5070ti": "rtx-5070-ti-16gb",
    "rtx5080": "rtx-5080-16gb",
    "rtx4070": "rtx-4070-12gb",
    "rtx4070sti": "rtx-4070-12gb",  # STI variant, same registry SKU
    "rtx4080": "rtx-4080-16gb",
}

# model tag -> (registry model id, registry model-instance id)
# The lane runs pulled unsloth GGUF builds; instance ids are the existing
# registry records for those weights families.
MODEL_MAP = {
    "gemma-4-12b-it": "unsloth-gemma-4-12b-it-gguf--q4-k-m",
    "lfm2.5-2.6b": "liquidai-lfm2-5-2-6b-gguf--q8-0",
    "qwen3.5-9b": "unsloth-qwen3-5-9b-gguf--q4-k-m",
    "qwen3.8-27b": "unsloth-qwen3-8-27b-gguf--ud-q4-k-m",
    "qwen3.6-35b-a3b": "unsloth-qwen3-6-35b-a3b-gguf--ud-q4-k-m",
}

ENGINE_VERSION = "0.33.2"


def slug(value):
    return re.sub(r"[^a-z0-9]+", "-", str(value).lower()).strip("-")


def model_instance_id(model_tag):
    return MODEL_MAP[model_tag]


def recipe_id_for(model_tag, hardware_id):
    mi = model_instance_id(model_tag)
    return f"{mi}-{hardware_id}-ollama-tp1"


def load_probes_jsonl(path):
    """Parse PROBE header + JSON block pairs from a probe transcript."""
    text = path.read_text(errors="replace")
    entries = []
    for m in re.finditer(r"=== PROBE (\S+) ctx=(\d+) ===\s*(\{.*?\})\s*(?====|\Z)", text, re.S):
        ref, ctx, block = m.group(1), int(m.group(2)), m.group(3)
        body = json.loads(block)
        label = ref.rsplit("/", 1)[-1].split(":")[0]
        # strip trailing weight-format tokens (e.g. "-GGUF") so tags match
        for suffix in ("-GGUF", "-gguf"):
            if label.lower().endswith(suffix):
                label = label[: -len(suffix)]
        norm = lambda v: slug(v).replace("-", "")
        for tag in MODEL_MAP:
            if norm(tag) == norm(label) or norm(tag) in norm(label):
                entries.append((tag, ctx, body))
                break
    return entries




def counters(body):
    def tok_s(count, duration_ns):
        return round(count / (duration_ns / 1e9), 2) if duration_ns else None
    return {
        "decode_tok_s": tok_s(body.get("eval_count"), body.get("eval_duration")),
        "decode_tok_s_per_stream": tok_s(body.get("eval_count"), body.get("eval_duration")),
        "prefill_tok_s": tok_s(body.get("prompt_eval_count"), body.get("prompt_eval_duration")),
        "ttft_ms_p50": round(body.get("prompt_eval_duration") / 1e6, 1) if body.get("prompt_eval_duration") else None,
        "output_tokens": body.get("eval_count"),
        "samples": 1,
    }


def main():
    reg_hw = {p.stem for p in (REGISTRY / "hardware").glob("*.json")}
    measurements = []  # (gpu_key, model_tag, ctx, body, source_label)
    skips = []

    amp = json.loads(REPORTS["ampere"].read_text())
    for gpu_key, lane in amp["gpu_lanes"].items():
        hw = GPU_MAP.get(gpu_key)
        for model_tag, m in lane["models"].items():
            if m.get("status", "ok").startswith("skip"):
                skips.append((gpu_key, model_tag, m.get("status")))
                continue
            if m.get("status") != "ok" or not hw:
                continue
            measurements.append((gpu_key, model_tag, m["ctx"], m, "ampere-lane"))

    bw = json.loads(REPORTS["blackwell"].read_text())
    for gpu_key, lane in bw.items():
        if not isinstance(lane, dict) or "models" not in lane:
            continue
        if lane.get("status") == "blocked":
            skips.append((gpu_key, "ALL", f"blocked: {lane.get('attempts')} rental attempts failed"))
            continue
        for model_tag, m in lane["models"].items():
            if m.get("status") == "skip":
                skips.append((gpu_key, model_tag, m.get("reason")))
                continue
            hw = GPU_MAP.get(gpu_key)
            if m.get("status") != "ok" or not hw:
                continue
            measurements.append((gpu_key, model_tag, m["ctx"], m, "focus-blackwell"))

    for lane_key in ("ada-4070", "ada-4070sti", "ada-4080"):
        for model_tag, ctx, body in load_probes_jsonl(REPORTS[lane_key]):
            measurements.append((lane_key, model_tag, ctx, body, lane_key))
        text = REPORTS[lane_key].read_text(errors="replace")
        for m in re.finditer(r"=== PROBE (\S+) ctx=\d+ ===\s*PROBE_ERROR", text):
            label = m.group(1).rsplit("/", 1)[-1].split(":")[0]
            for tag in MODEL_MAP:
                if slug(tag).replace("-", "") == slug(label).replace("-", ""):
                    skips.append((lane_key, tag, "PROBE_ERROR (recorded)"))
                    break

    written = 0
    seen = set()
    for gpu_key, model_tag, ctx, body, source_label in measurements:
        hw = GPU_MAP.get(gpu_key)
        if hw not in reg_hw:
            continue
        rid = recipe_id_for(model_tag, hw)
        if rid in seen:
            continue
        seen.add(rid)
        row = counters(body)
        row.update({"concurrency": 1, "context_tokens": ctx, "status": "observed", "peak_vram_gb": None})
        sid = f"{rid}-sweep"
        (REGISTRY / "speed-sweep" / f"{sid}.json").write_text(json.dumps({
            "accepted_at": None,
            "id": sid,
            "measured_at": NOW,
            "metrics": {
                "concurrency": 1,
                "inference_engine_version": ENGINE_VERSION,
                "latest_point_at": NOW,
                "max_context_tokens": ctx,
                "peak_generation_tps": row["decode_tok_s"],
                "peak_prompt_tps": row["prefill_tok_s"],
                "point_count": 1,
            },
            "recipe_id": rid,
            "rows": [row],
            "schema_version": SCHEMA,
            "source": {
                "commit": None,
                "kind": "lane-experiment",
                "paths": [f"docs/notes/lane-ollama-evidence-{source_label}.json"],
                "repository": "https://github.com/0xSero/local-ai-registry",
            },
        }, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
        mi = model_instance_id(model_tag)
        (REGISTRY / "recipe" / f"{rid}.json").write_text(json.dumps({
            "capabilities": {k: None for k in ("chat", "reasoning", "tools", "vision")},
            "description": f"Measured ollama run of {model_tag} on a rented {hw.replace('-', ' ').title()} via the registry lane campaign.",
            "engine": {"graph_mode": None, "name": "ollama", "version": ENGINE_VERSION},
            "facts": {},
            "hardware_count": 1,
            "hardware_id": hw,
            "id": rid,
            "launch": {
                "container": {
                    "captured_at": NOW,
                    "compose_file": None,
                    "digest": None,
                    "image": None,
                    "reason": "observed-lane-run",
                    "runtime": None,
                    "source": [{"captured_at": NOW, "kind": "lane-experiment", "url": "https://github.com/0xSero/local-ai-registry/blob/main/docs/notes/lane-ollama-evidence.md"}],
                    "state": "none",
                },
                "kind": "reference",
                "url": f"https://console.vast.ai/instances/?label={source_label}",
            },
            "model_instance_id": mi,
            "provenance": {"captured_at": NOW, "sources": [{"captured_at": NOW, "kind": "lane-experiment", "url": f"https://console.vast.ai/instances/?label={source_label}"}]},
            "recipe_source": "lane-experiment",
            "schema_version": SCHEMA,
            "serving": {"kv_cache_tokens": None, "max_concurrency": None, "max_context_tokens": ctx, "tensor_parallel": 1},
            "speed_sweep_ids": [sid],
            "status": "candidate",
        }, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
        written += 1

    notes = {"schema_version": "local-ai-registry/lane-evidence-notes/v1",
            "skips": [{"gpu": g, "model": m, "reason": r} for g, m, r in skips],
            "written_at": NOW}
    (ROOT / "docs/notes/lane-ollama-evidence.md").write_text(
        "# Lane campaign evidence\n\n"
        "Measured ollama probe runs from the registry lane campaign\n"
        "(Ampere, Ada, Blackwell lanes). Raw counters and audit notes live in\n"
        "this repository's history; skips below are honest capacity or probe failures.\n\n"
        f"## Honest skips ({len(skips)})\n\n"
        + "\n".join(f"- `{g}` / `{m}`: {r}" for g, m, r in skips)
        + "\n")
    print(f"imported {written} measured pairs; skips recorded: {len(skips)}")


if __name__ == "__main__":
    main()
