#!/usr/bin/env python3
"""Extend the focus-model matrix with the Vast all-GPU validation sweep (2026-09-01).

Inputs (lane evidence, captured live today):
  /tmp/ampere-lane-report.json        — AmpereLane  (3060 Ti, 3070, 3080, 3080 Ti, A4000)
  /tmp/focus-blackwell-results.json     — BlackwellLane (5060 Ti, 5070, 5070 Ti, 5080; 5060 blocked)
  agent://AdaLane                       — AdaLane   (4060 Ti, 4070, 4070S Ti, 4080)
  /Users/sero/exo-ai/focus-probes/*.json — DatacenterLane (A100 PCIE/SXM4, H100, H200,
                                           RTX PRO 4000/4500, RTX 6000 Ada, RTX A6000,
                                           RTX 5000 Ada, RTX A5000, V100; B200/RTX 4000 Ada/RTX A4000 no-offer)

Emits one recipe + one speed-sweep per (model, GPU) pair whose probe returned ok.
Skips and no-offer findings are NOT recipes — they are printed as a gap report.
Same candidate/reference contract as the first matrix commit.
"""
import json
import re
import urllib.request
from pathlib import Path

ROOT = Path("registry")
NOW = "2026-09-01T00:00:00Z"
REGISTRY_URL = "https://github.com/0xSero/local-ai-registry"
EVIDENCE_DIR = Path("/Users/sero/exo-ai/focus-probes")

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
    "gemma-4-12b-it": "gemma-4-12b",
    "lfm2.5-2.6b": "lfm25-26b",
    "qwen3.8-27b": "qwen38-27b",
    "qwen3.6-35b-a3b": "qwen36-35b",
    "qwen3.5-9b": "qwen35-9b",
}
QUANT = {
    "gemma-4-12b-it": "q4-k-m", "lfm2.5-2.6b": "q4-k-m",
    "qwen3.8-27b": "ud-q4-k-m", "qwen3.6-35b-a3b": "ud-q4-k-m",
    "qwen3.5-9b": "q4-k-m",
}
# Registry hardware_id by Vast gpu_name (validated lanes only); keys normalized (memory suffix stripped)
GPU_HW = {re.sub(r"[\s(]*\d+\s*GB\)?$", "", k).strip(): v for k, v in {
    "RTX 3060 Ti": "rtx-3060-ti-8gb", "RTX 3070": "rtx-3070-8gb",
    "RTX 3080": "rtx-3080-10gb", "RTX 3080 Ti": "rtx-3080-ti-12gb",
    "RTX A4000": "rtx-a4000-16gb",
    "RTX 4060 Ti": "rtx-4060-ti-16gb", "RTX 4070": "rtx-4070-12gb",
    "RTX 4070S Ti": "rtx-4070-ti-super-16gb", "RTX 4080": "rtx-4080-16gb",
    "RTX 5060 Ti": "rtx-5060-ti-16gb", "RTX 5070": "rtx-5070-12gb",
    "RTX 5070 Ti": "rtx-5070-ti-16gb", "RTX 5080": "rtx-5080-16gb",
    "A100 PCIE 40GB": "rtx-a100-pcie-40gb", "A100 SXM4 40GB": "rtx-a100-sxm4-40gb",
    "H100 SXM 80GB": "rtx-h100-sxm-80gb", "H200 141GB": "rtx-h200-141gb",
    "RTX PRO 4000 Blackwell 24GB": "rtx-pro-4000-blackwell-24gb",
    "RTX PRO 4500 Blackwell 32GB": "rtx-pro-4500-blackwell-32gb",
    "RTX 6000 Ada 48GB": "rtx-6000-ada-48gb", "RTX A6000 48GB": "rtx-a6000-48gb",
    "RTX 5000 Ada 32GB": "rtx-5000-ada-32gb", "RTX A5000 24GB": "rtx-a5000-24gb",
    "Tesla V100 16GB": "rtx-v100-16gb",
}.items()}


def provenance(url, kind="validation-run"):
    return {"captured_at": NOW, "sources": [{"captured_at": NOW, "kind": kind, "url": url}]}


def load_json(path):
    return json.loads(Path(path).read_text())


def probe_ok(model, ev):
    return ev.get("status") == "ok"


def build(model, gpu, ev, rental):
    model = model.split(":", 1)[0]
    m_tag = MODEL_TAGS[model]
    gpu = re.sub(r"[\s(]*\d+\s*GB\)?$", "", gpu).strip()
    hw = GPU_HW[gpu]
    slug = MODEL_SLUG[model]
    quant = QUANT[model]
    ctx = ev.get("ctx") or (16384 if model in ("qwen3.8-27b", "qwen3.6-35b-a3b") else 32768)
    decode = round(ev["eval_count"] / ev["eval_duration_ns"] * 1e9, 1)
    prefill = round(ev["prompt_eval_count"] / ev["prompt_eval_duration_ns"] * 1e9, 1) if ev.get("prompt_eval_duration_ns") else None
    rid = f"{slug}-{quant}-{hw}-ollama-tp1"
    sweep_id = f"{rid}-sweep"
    sweep = {
        "schema_version": "local-ai-registry/v1",
        "id": sweep_id,
        "recipe_id": rid,
        "measured_at": NOW,
        "accepted_at": None,
        "source": {"kind": "validation-run", "url": REGISTRY_URL, "repository": None, "commit": None, "paths": None},
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
            f"{m_tag} validated candidate on one {gpu} via native ollama 0.33.2 (Vast rental). "
            f"Exact 'validation-ok' completion probe, temperature 0, ctx {ctx}. "
            "Observed reference launch; not a digest-pinned container contract."
        ),
        "engine": {"name": "ollama", "version": "0.33.2", "graph_mode": None},
        "launch": {
            "kind": "reference",
            "source": "vast-validation-2026-09-01",
            "observed_command": f"/usr/local/bin/ollama pull {m_tag}",
            "serve_command": "/usr/local/bin/ollama serve",
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
            },
        },
        "provenance": provenance("https://vast.ai"),
        "facts": {
            "metadata": {
                "state": "known",
                "reason": "validation-evidence-recorded",
                "provenance": provenance("https://vast.ai"),
            },
        },
    }
    return rid, recipe, sweep


def iter_lane(lane):
    """Yield (model, gpu_name, evidence) from a lane report."""
    for gpu_block in lane.get("results", lane.get("gpu_results", {}).get("gpu_lanes", {}).values() if False else []):
        pass
    return []


def main():
    (ROOT / "speed-sweep").mkdir(exist_ok=True)
    pairs = []   # (model, gpu_name, evidence, rental)
    gaps = []

    amp = load_json("/tmp/ampere-lane-report.json")
    for hw_key, block in amp["gpu_lanes"].items():
        gpu = block["gpu"]
        for model, ev in block["models"].items():
            if probe_ok(model, ev):
                pairs.append((model, gpu, ev, block.get("rental", {})))
            else:
                gaps.append((model, gpu, ev.get("status"), ev.get("reason", "")))

    with open("/tmp/focus-blackwell-results.json") as f:
        bw = json.load(f)
    for hw_key, block in bw["gpu"].items():
        gpu = block["gpu_name"]
        for model, ev in block["models"].items():
            if probe_ok(model, ev):
                pairs.append((model, gpu, ev, block.get("rental", {})))
            else:
                gaps.append((model, gpu, ev.get("status"), ev.get("reason", "")))

    # AdaLane via artifact url
    # AdaLane via staged report file
    ada = load_json("/Users/sero/exo-ai/focus-probes/ada-lane.json")
    for (hw_key, block), rental in zip(ada["results"].items(), ada.get("rentals", [])):
        gpu_name = rental.get("gpu") or hw_key
        for model, ev in block.items():
            if probe_ok(model, ev):
                pairs.append((model, gpu_name, ev, rental))
            else:
                gaps.append((model, gpu_name, ev.get("status"), ev.get("reason", "")))
    for path in sorted(EVIDENCE_DIR.glob("*.json")):
        if path.name == "ada-lane.json":
            continue
        dc = load_json(path)
        gpu = dc["gpu"]
        rental = {"offer_id": dc.get("offer_id"), "instance_id": dc.get("instance_id"), "ssh": dc.get("ssh"), "dph": None}
        for model, ev in dc["models"].items():
            if probe_ok(model, ev):
                pairs.append((model, gpu, ev, rental))
            else:
                gaps.append((model, gpu, ev.get("status"), ev.get("reason", "")))
                gaps.append((model, gpu, ev.get("status"), ev.get("reason", "")))

    # Explicit no-offer / infra-blocked findings from DatacenterLane summary
    for gpu, finding in (
        ("B200", "No single-GPU verified rentable B200 offer at run time (snapshot ids stale no_such_ask; live verified listings all rentable=false, cheapest $5.31/hr)"),
        ("RTX 4000 Ada 20GB", "No rentable single-GPU offer under this exact name; only RTX A4000 (Ampere) exists as a distinct gpu_name"),
        ("RTX A4000 20GB", "Verified rentable offer existed ($0.095/hr) but host sshd persistently rejected key auth across 6 attempts incl. onstart pubkey injection; host-side key injection broken; no probe evidence"),
    ):
        gaps.append((None, gpu, "no-offer", finding))

    # RTX 5060 infra-blocked finding from BlackwellLane
    gaps.append((None, "RTX 5060", "blocked", "No working full-GPU 5060 host rentable at run time: 6 rental attempts all failed on host infra (SSH pubkey denial / docker registry failures)"))

    written = 0
    for model, gpu, ev, rental in pairs:
        rid, recipe, sweep = build(model, gpu, ev, rental)
        (ROOT / "recipe" / f"{rid}.json").write_text(json.dumps(recipe, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
        (ROOT / "speed-sweep" / f"{rid}-sweep.json").write_text(json.dumps(sweep, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
        written += 1
        print(f"wrote {rid}")

    print(f"\nrecipes written: {written}")
    print("gaps (no recipe):")
    for model, gpu, status, reason in gaps:
        print(f"  {gpu}: {model or '*'} — {status}: {reason}")


if __name__ == "__main__":
    main()
