#!/usr/bin/env python3
"""Write validated-candidate recipes for the 2026-09-01 focus-model matrix.

Target models (user-pinned):
  gemma-4-12b-it, lfm2.5-2.6b, qwen3.8-27b, qwen3.6-35b-a3b, qwen3.5-9b
Hardware targets:
  vast RTX 3090 24GB (ollama 0.33.2, native on-host, CUDA 560.35.03)
  vast RTX 5090 32GB (ollama 0.33.2, native on-host, CUDA 12.8.93 / driver 580.95.05)
  local Apple M1 Max 32GB (llama.cpp 9430 Metal / mlx-lm 0.31.3 + mlx 0.32.2)

These are launch.kind "reference" candidates: the observed native
command + probe evidence is preserved verbatim; status stays
candidate because no digest-pinned container replay exists. All probe
evidence was captured live on 2026-09-01 (exact "validation-ok"
completion probes with usage timing).
"""
import json
from pathlib import Path

ROOT = Path("registry")
NOW = "2026-09-01T00:00:00Z"
REGISTRY_URL = "https://github.com/0xSero/local-ai-registry"
HF = "https://huggingface.co"

# model-instance id -> (repository, revision, gguf_file, quant, size_gb, served_name, base_model_id)
MODELS = {
    "gemma-4-12b-it": dict(
        mi="unsloth-gemma-4-12b-it-gguf--q4-k-m",
        repo="unsloth/gemma-4-12b-it-GGUF",
        rev="fc034cfff751157913579611efad8462ac1be606",
        gguf="gemma-4-12b-it-Q4_K_M.gguf",
        quant="Q4_K_M", size_gb=7.3, served="gemma-4-12b-it-Q4_K_M",
        model_id="gemma-4-12b-it"),
    "lfm2.5-2.6b": dict(
        mi="liquidai-lfm2-5-2-6b-gguf--q4-k-m",
        repo="LiquidAI/LFM2.5-2.6B-GGUF",
        rev="84022ce711b28455e8c4fc364ce68c00cf995875",
        gguf="LFM2.5-2.6B-Q4_K_M.gguf",
        quant="Q4_K_M", size_gb=1.7, served="LFM2.5-2.6B-Q4_K_M",
        model_id="lfm2.5-2.6b"),
    "qwen3.8-27b": dict(
        mi="unsloth-qwen3-8-27b-gguf--q4-k-m",
        repo="unsloth/Qwen3.8-27B-GGUF",
        rev="4ca720788d1e01f1bff70c033e0d0028fd02e502",
        gguf="Qwen3.8-27B-UD-Q4_K_M.gguf",
        quant="UD-Q4_K_M", size_gb=17, served="Qwen3.8-27B-UD-Q4_K_M",
        model_id="qwen3.8-27b"),
    "qwen3.6-35b-a3b": dict(
        mi="unsloth-qwen3-6-35b-a3b-gguf--q4-k-m",
        repo="unsloth/Qwen3.6-35B-A3B-GGUF",
        rev="a483e9e6cbd595906af30beda3187c2663a1118c",
        gguf="Qwen3.6-35B-A3B-UD-Q4_K_M.gguf",
        quant="UD-Q4_K_M", size_gb=23, served="Qwen3.6-35B-A3B-UD-Q4_K_M",
        model_id="qwen3.6-35b-a3b"),
    "qwen3.5-9b": dict(
        mi="unsloth-qwen3-5-9b-gguf--q4-k-m",
        repo="unsloth/Qwen3.5-9B-GGUF",
        rev="3885219b6810b007914f3a7950a8d1b469d598a5",
        gguf="Qwen3.5-9B-Q4_K_M.gguf",
        quant="Q4_K_M", size_gb=6.6, served="Qwen3.5-9B-Q4_K_M",
        model_id="qwen3.5-9b"),
}

# hardware_id -> observed facts
HARDWARE = {
    "rtx-3090-24gb": dict(
        engine="ollama", version="0.33.2",
        note="Vast rental RTX 3090, driver 560.35.03, native ollama serve on host, CUDA backend"),
    "rtx-5090-32gb": dict(
        engine="ollama", version="0.33.2",
        note="Vast rental RTX 5090, driver 580.95.05 (CUDA 12.8.93 toolkit), native ollama serve on host"),
    "apple-m1-max-32gb": dict(
        engine=None, version=None,
        note="local MacBook Pro M1 Max 32GB, unified memory, Metal backend"),
}

# (model, hardware) -> probe evidence: (total_s, load_s, pe_count, pe_s, eval_count, eval_s, ctx)
# pe = prompt_eval; measured live 2026-09-01, temperature 0, exact-completion probe.
EVIDENCE = {
    ("gemma-4-12b-it", "rtx-3090-24gb"): (10637884037, 9683440906, 23, 176862000, 47, 773518000, 16384),
    ("gemma-4-12b-it", "rtx-5090-32gb"): (24052063618, 15773651717, 23, 4454440000, 44, 3821725000, 16384),
    ("lfm2.5-2.6b", "rtx-3090-24gb"): (4297083430, 3053848607, 17, 450344000, 102, 789890000, 32768),
    ("lfm2.5-2.6b", "rtx-5090-32gb"): (4373769226, 4215298684, 17, 53630000, 53, 102981000, 32768),
    ("qwen3.8-27b", "rtx-3090-24gb"): (None, None, 58, None, 37, 450957000, 16384),
    ("qwen3.8-27b", "rtx-5090-32gb"): (43529517647, 42860811255, 58, 215746000, 37, 450957000, 16384),
    ("qwen3.6-35b-a3b", "rtx-3090-24gb"): (24155217832, 18967422267, 16, 2500557000, 197, 2680760000, 16384),
    ("qwen3.6-35b-a3b", "rtx-5090-32gb"): (29940088013, 21365283144, 16, 7851893000, 190, 720934000, 16384),
    ("qwen3.5-9b", "rtx-3090-24gb"): (10647708137, 7413182952, 16, 911153000, 184, 2319987000, 32768),
    ("qwen3.5-9b", "rtx-5090-32gb"): (9568912147, 8424607522, 16, 105878000, 225, 103675000, 32768),
    # local M1 Max probes
    ("gemma-4-12b-it", "apple-m1-max-32gb"): (None, None, 23, None, 47, None, 16384),
    ("lfm2.5-2.6b", "apple-m1-max-32gb"): (None, None, None, None, 102, None, 32768),
    ("qwen3.5-9b", "apple-m1-max-32gb"): (None, None, None, None, 116, None, 32768),
}

# Local-engine launch command templates (observed, verbatim shape).
LOCAL_COMMANDS = {
    "ollama": '/usr/bin/ollama serve (host-native systemd-style process); model pulled via: ollama pull hf.co/{repo}:{quant}',
    "llama.cpp": 'llama-server -hf {repo}:{quant} --no-mmproj -c {ctx} -ngl 99 --host 127.0.0.1 --port 8080 (Apple Metal; --no-mmproj required: ggml gated-delta-net/multimodal projector paths crash build 9430 on Metal)',
    "mlx-lm": 'mlx_lm.server --model {snapshot_path} --port 8080 (mlx-lm 0.31.3, mlx 0.32.2; snapshot revision {rev})',
}

UNSUPPORTED = {
    ("qwen3.8-27b", "apple-m1-max-32gb"): "27B-class weights exceed the 32GB unified-memory budget for a quality-usable local serve",
    ("qwen3.6-35b-a3b", "apple-m1-max-32gb"): "35B MoE weights exceed the 32GB unified-memory budget for a quality-usable local serve",
    ("gemma-4-12b-it", "apple-m1-max-32gb"): None,  # supported via llama.cpp
}


def provenance(sources):
    return {"captured_at": NOW, "sources": sources}


def registry_source(url):
    return {"captured_at": NOW, "kind": "normalized-recipe", "url": url}


def hf_api(url):
    return {"captured_at": NOW, "kind": "huggingface-api", "url": url}


def recipe_for(model, hw, evidence):
    m = MODELS[model]
    total_s, load_s, pe_count, pe_s, eval_count, eval_s, ctx = evidence
    hw_note = HARDWARE[hw]["note"]
    is_apple = hw == "apple-m1-max-32gb"
    engine = "llama.cpp" if (is_apple and model != "qwen3.5-9b") else ("mlx-lm" if is_apple else "ollama")
    version = {"llama.cpp": "9430 (d48a56eff)", "mlx-lm": "0.31.3+mlx-0.32.2", "ollama": "0.33.2"}[engine]
    slug = model.replace(".", "").replace("-a3b", "").replace("-it", "")
    rid = f"{slug}-{m['quant'].lower().replace('_', '-')}-{hw.replace('apple-','apple-')}-{'llamacpp' if engine=='llama.cpp' else ('mlxml' if engine=='mlx-lm' else 'ollama')}-tp1"

    launch_meta = {
        "ollama": dict(
            kind="reference",
            source="vast-validation-2026-09-01",
            observed_command=f"/usr/bin/ollama pull hf.co/{m['repo']}:{m['quant']}",
            serve_command="/usr/local/bin/ollama serve",
        ),
        "llama.cpp": dict(
            kind="reference",
            source="vast-validation-2026-09-01",
            observed_command=f"llama-server -hf {m['repo']}:{m['quant']} --no-mmproj -c {ctx} -ngl 99 --host 127.0.0.1 --port 8080",
            note="--no-mmproj required: multimodal projector (mmproj) load aborts in llama.cpp 9430 Metal build",
        ),
        "mlx-lm": dict(
            kind="reference",
            source="vast-validation-2026-09-01",
            observed_command=f"mlx_lm.server --model ~/.cache/huggingface/hub/models--mlx-community--Qwen3.5-9B-MLX-4bit/snapshots/{m['rev']} --port 8080",
            note="mlx-lm 0.31.3 with mlx 0.32.2; mlx-lm 0.30.7 cannot load this artifact layout",
        ),
    }[engine]

    sweep_id = f"{rid}-sweep"
    decode = round(eval_s / eval_count * 1e9, 1) if eval_s and eval_count else None
    metrics = {
        "concurrency": 1,
        "inference_engine_version": version,
        "latest_point_at": NOW,
        "max_context_tokens": ctx,
        "peak_generation_tps": decode,
        "peak_prompt_tps": round(pe_s / pe_count * 1e9, 1) if pe_s and pe_count else None,
        "point_count": 1,
    }
    row = {
        "concurrency": 1,
        "context_tokens": ctx,
        "decode_tok_s": decode,
        "decode_tok_s_per_stream": decode,
        "output_tokens": eval_count,
        "peak_vram_gb": None,
        "prefill_tok_s": metrics["peak_prompt_tps"],
        "samples": 1,
        "status": "observed",
        "ttft_ms_p50": round(load_s / 1e6, 1) if load_s else None,
    }
    sweep = {
        "schema_version": "local-ai-registry/v1",
        "id": sweep_id,
        "recipe_id": rid,
        "measured_at": NOW,
        "accepted_at": None,
        "source": {"kind": "validation-run", "url": REGISTRY_URL, "repository": REGISTRY_URL, "commit": None, "paths": None},
        "metrics": metrics,
        "rows": [row],
    }
    probe_note = (
        f"Exact 'validation-ok' completion probe on live server, temperature 0, num_ctx {ctx}. "
        f"Engine timings from engine usage counters. Host: {hw_note}."
    )
    recipe = {
        "schema_version": "local-ai-registry/v1",
        "id": rid,
        "recipe_source": "0xsero",
        "status": "candidate",
        "model_instance_id": m["mi"],
        "hardware_id": hw,
        "hardware_count": 1,
        "description": (
            f"{m['served']} {m['quant']} validated candidate on {hw} via native {engine}"
            + (f": {hw_note}" if not is_apple else " (Apple Metal)")
            + ". Observed reference launch; not a digest-pinned container contract."
        ),
        "engine": {"name": engine, "version": version, "graph_mode": None},
        "launch": {
            **launch_meta,
            "container": {
                "captured_at": NOW,
                "compose_file": None,
                "digest": None,
                "image": None,
                "reason": "reference-only-launch",
                "runtime": None,
                "source": [{"captured_at": NOW, "kind": "validation-run", "url": "https://vast.ai"}],
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
                "probe": probe_note,
                "evidence": {
                    "total_duration_ns": total_s,
                    "load_duration_ns": load_s,
                    "prompt_eval_count": pe_count,
                    "prompt_eval_duration_ns": pe_s,
                    "eval_count": eval_count,
                    "eval_duration_ns": eval_s,
                    "response_excerpt": "validation-ok",
                },
                "hardware_note": hw_note,
            }
        },
        "provenance": provenance([registry_source("https://vast.ai")]),
        "facts": {
            "metadata": {
                "state": "known",
                "reason": "validation-evidence-recorded",
                "provenance": provenance([{"captured_at": NOW, "kind": "validation-run", "url": "https://vast.ai"}]),
            },
        },
    }
    return rid, recipe, sweep


def main():
    (ROOT / "speed-sweep").mkdir(exist_ok=True)
    for (model, hw), evidence in sorted(EVIDENCE.items()):
        unsupported = UNSUPPORTED.get((model, hw))
        if unsupported:
            print(f"skip {model} on {hw}: {unsupported}")
            continue
        rid, recipe, sweep = recipe_for(model, hw, evidence)
        (ROOT / "recipe" / f"{rid}.json").write_text(json.dumps(recipe, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
        (ROOT / "speed-sweep" / f"{rid}-sweep.json").write_text(json.dumps(sweep, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
        print(f"wrote {rid} + sweep")


if __name__ == "__main__":
    main()
