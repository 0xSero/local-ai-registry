#!/usr/bin/env python3
"""Extend the focus-model matrix with the personally-owned fleet hosts.

Inputs:
  /tmp/linux-fleet-report.json — LinuxFleetLane live probes (pop-os PRO 6000,
      omarchy 3090, spark-2822/de5c/2384 GB10)
  /tmp/apple-tier-fit.json, /tmp/apple-small-fit.json — AppleM4M5Lane/AppleSmallLane
      memory-fit ESTIMATES (no physical host exists; not measurements)

Emits one recipe + one speed-sweep per live-probed (model, host) pair.
Apple tier fits-tables and GB10 OOM/host-offline findings are NOT recipes;
they are emitted as a gap report for the PR description.
"""
import json
import re
from pathlib import Path

ROOT = Path("registry")
NOW = "2026-09-01T00:00:00Z"
REGISTRY_URL = "https://github.com/0xSero/local-ai-registry"

MODEL_TAGS = {
    "gemma-4-12b-it": "hf.co/unsloth/gemma-4-12b-it-GGUF:Q4_K_M",
    "lfm2.5-2.6b": "hf.co/LiquidAI/LFM2.5-2.6B-GGUF:Q4_K_M",
    "qwen3.8-27b": "hf.co/unsloth/Qwen3.8-27B-GGUF:UD-Q4_K_M",
    "qwen3.6-35b-a3b": "hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_M",
    "qwen3.5-9b": "hf.co/unsloth/Qwen3.5-9B-GGUF:Q4_K_M",
}
MODEL_INSTANCE = {
    "gemma-4-12b-it": "unsloth-gemma-4-12b-it-gguf--q4-k-m",
    "lfm2.5-2.6b": "liquidai-lfm2-5-2-6b-gguf--q4-k-m",
    "qwen3.8-27b": "unsloth-qwen3-8-27b-gguf--q4-k-m",
    "qwen3.6-35b-a3b": "unsloth-qwen3-6-35b-a3b-gguf--q4-k-m",
    "qwen3.5-9b": "unsloth-qwen3-5-9b-gguf--q4-k-m",
}
MODEL_SLUG = {
    "gemma-4-12b-it": "gemma-4-12b", "lfm2.5-2.6b": "lfm25-26b",
    "qwen3.8-27b": "qwen38-27b", "qwen3.6-35b-a3b": "qwen36-35b",
    "qwen3.5-9b": "qwen35-9b",
}
QUANT = {
    "gemma-4-12b-it": "q4-k-m", "lfm2.5-2.6b": "q4-k-m",
    "qwen3.8-27b": "ud-q4-k-m", "qwen3.6-35b-a3b": "ud-q4-k-m",
    "qwen3.5-9b": "q4-k-m",
}
HOST_HW = {
    "pop-os": "rtx-pro-6000-blackwell-96gb",
    "omarchy": "rtx-3090-24gb",
    "spark-2822": "dgx-spark-gb10-128gb",
    "spark-de5c": "dgx-spark-gb10-128gb",
    "spark-2384": "dgx-spark-gb10-128gb",
}
HOST_NOTE = {
    "pop-os": ("4x RTX PRO 6000 Blackwell 96GB, local fleet host. CONTENTED: a pre-existing root-owned "
                 "vLLM TP4 job held ~95GB/GPU all session; probes ran with ~2GB free/GPU via Vulkan + CPU offload — "
                 "timings are contended-host numbers, not clean-GPU. GPU 0."),
    "omarchy": ("Single RTX 3090 24GB of four (CUDA_VISIBLE_DEVICES=0), local fleet host; "
                "Arc Pro B70s untouched."),
    "spark-2822": "DGX Spark GB10 aarch64, 128GB unified, local fleet host.",
    "spark-de5c": "DGX Spark GB10 aarch64, 128GB unified, local fleet host.",
    "spark-2384": "DGX Spark GB10 aarch64, 128GB unified, local fleet host; host went offline mid-run.",
}


def provenance(url, kind="validation-run"):
    return {"captured_at": NOW, "sources": [{"captured_at": NOW, "kind": kind, "url": url}]}


def load_json(path):
    return json.loads(Path(path).read_text())


def clean_model(key):
    return key.split(":", 1)[0]


def build(host, model_key, ev):
    model = clean_model(model_key)
    m_tag = MODEL_TAGS[model]
    hw = HOST_HW[host]
    slug = MODEL_SLUG[model]
    quant = QUANT[model]
    rid = f"{slug}-{quant}-{hw}-ollama-tp1"
    ctx = ev["ctx"]
    decode = round(ev["eval_count"] / ev["eval_duration_ns"] * 1e9, 1)
    prefill = round(ev["prompt_eval_count"] / ev["prompt_eval_duration_ns"] * 1e9, 1) if ev.get("prompt_eval_duration_ns") else None
    sweep_id = f"{rid}-sweep"
    sweep = {
        "schema_version": "local-ai-registry/v1",
        "id": sweep_id,
        "recipe_id": rid,
        "measured_at": NOW,
        "accepted_at": None,
        "source": provenance("https://github.com/0xSero/local-ai-registry", "fleet-validation-run"),
        "metrics": {
            "concurrency": 1,
            "inference_engine_version": "0.33.2",
            "latest_point_at": NOW,
            "max_context_tokens": ctx,
            "peak_generation_tps": decode,
            "peak_prompt_tps": prefill,
            "point_count": 1,
        },
        "rows": [{
            "concurrency": 1,
            "context_tokens": ctx,
            "decode_tok_s": decode,
            "decode_tok_s_per_stream": decode,
            "output_tokens": ev["eval_count"],
            "peak_vram_gb": None,
            "prefill_tok_s": prefill,
            "samples": 1,
            "status": "observed",
            "ttft_ms_p50": round(ev["load_duration_ns"] / 1e6, 1),
        }],
    }
    recipe = {
        "schema_version": "local-ai-registry/v1",
        "id": rid,
        "recipe_source": "0xsero",
        "status": "candidate",
        "model_instance_id": MODEL_INSTANCE[model],
        "hardware_id": hw,
        "hardware_count": 1,
        "description": (
            f"{m_tag} validated candidate on one {host} GPU via native ollama 0.33.2 (local fleet host). "
            f"Exact 'validation-ok' completion probe, temperature 0, ctx {ctx}. "
            "Observed reference launch; not a digest-pinned container contract."
        ),
        "engine": {"name": "ollama", "version": "0.33.2", "graph_mode": None},
        "launch": {
            "kind": "reference",
            "source": "fleet-validation-2026-09-01",
            "observed_command": f"~/ollama-fleet/bin/ollama pull {m_tag}",
            "serve_command": "~/ollama-fleet/bin/ollama serve",
            "container": {
                "captured_at": NOW,
                "compose_file": None,
                "digest": None,
                "image": None,
                "reason": "reference-only-launch",
                "runtime": None,
                "source": [{"captured_at": NOW, "kind": "fleet-validation-run", "url": "https://github.com/0xSero/ai-fleet"}],
                "state": "none",
            },
        },
        "serving": {
            "kv_cache_tokens": None,
            "max_concurrency": 1,
            "max_context_tokens": ctx,
            "tensor_parallel": 1,
        },
        "capabilities": {"chat": True, "reasoning": None, "tools": None, "vision": None},
        "speed_sweep_ids": [sweep_id],
        "metadata": {
            "validation": {
                "date": "2026-09-01",
                "probe": f"Exact 'validation-ok' completion probe on live server, temperature 0, num_ctx {ctx}",
                "evidence": {
                    "total_duration_ns": ev["total_duration_ns"],
                    "load_duration_ns": ev["load_duration_ns"],
                    "prompt_eval_count": ev["prompt_eval_count"],
                    "prompt_eval_duration_ns": ev.get("prompt_eval_duration_ns"),
                    "eval_count": ev["eval_count"],
                    "eval_duration_ns": ev["eval_duration_ns"],
                    "response_excerpt": "validation-ok",
                },
                "hardware_note": HOST_NOTE[host],
            },
        },
        "provenance": provenance("https://github.com/0xSero/ai-fleet"),
        "facts": {
            "metadata": {
                "state": "known",
                "reason": "fleet-validation-evidence-recorded",
                "provenance": provenance("https://github.com/0xSero/ai-fleet"),
            },
        },
    }
    return rid, recipe, sweep


def main():
    fleet = load_json("/tmp/linux-fleet-report.json")
    (ROOT / "speed-sweep").mkdir(exist_ok=True)
    gaps = []
    written = 0
    for host, block in fleet.items():
        if host in ("cleanup", "engine", "probe_contract"):
            continue
        if host not in HOST_HW:
            gaps.append((host, None, "not-probeable", json.dumps(block)[:160]))
            continue
        for model_key, ev in block.get("models", {}).items():
            model = clean_model(model_key)
            status = ev.get("status")
            if status == "ok":
                rid, recipe, sweep = build(host, model_key, ev)
                (ROOT / "recipe" / f"{rid}.json").write_text(json.dumps(recipe, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
                (ROOT / "speed-sweep" / f"{rid}-sweep.json").write_text(json.dumps(sweep, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
                written += 1
                print(f"wrote {rid}")
            else:
                gaps.append((host, model, status, ev.get("reason", "")))

    # Apple fits-tables: gap findings only (no recipes — estimates, no physical host)
    for path, label in (("/tmp/apple-tier-fit.json", "apple-higher-tiers"), ("/tmp/apple-small-fit.json", "apple-small-tiers")):
        fit = load_json(path)
        gaps.append((label, None, "estimate-only", json.dumps(fit)[:400]))

    print(f"\nrecipes written: {written}")
    print("gap findings:")
    for host, model, status, reason in gaps:
        print(f"  {host}: {model or '*'} — {status}: {reason[:200]}")


if __name__ == "__main__":
    main()
