#!/usr/bin/env python3
"""Import par1-cs13 2× W7800 48GB lab evidence as candidate recipes.

Reads LocalMaxxing/registry-data/w7800-local-ai-registry/. Writes hardware,
missing model-instances, recipes, and speed-sweeps. launch.kind is reference;
status stays candidate. Lemonade docker contracts are added only by
accept_recipe.py after a live /v1 run, not by this importer. Then:

    python3 scripts/format_registry.py
    python3 scripts/curate_registry.py --index-only
    python3 scripts/format_registry.py
    python3 scripts/validate_registry.py
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from enrich_registry import facts_for
from sweep_metrics import derive_metrics
from tokenize_observed_command import parse_observed_command, tokenized_record

REG = Path(__file__).resolve().parent.parent / "registry"
PKG = Path(__file__).resolve().parents[2] / "registry-data" / "w7800-local-ai-registry"
NOW = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
HW = "radeon-pro-w7800-48gb"
AMD = "https://www.amd.com/en/products/graphics/workstations/radeon-pro/w7800-48gb.html"
REGISTRY = "https://github.com/0xSero/local-ai-registry"
VENDOR = {
    "captured_at": NOW,
    "kind": "vendor",
    "publisher": "AMD",
    "url": AMD,
}

# slug -> (stock instance, mtp instance)
INSTANCES = {
    "qwen36-27b-q4-k-m": ("unsloth-qwen3-6-27b-gguf--q4-k-m", "unsloth-qwen3-6-27b-mtp-gguf--q4-k-m"),
    "qwen36-27b-q4-k-s": ("unsloth-qwen3-6-27b-gguf--q4-k-s", "unsloth-qwen3-6-27b-mtp-gguf--q4-k-s"),
    "qwen36-27b-q4-k-xl": ("unsloth-qwen3-6-27b-gguf--ud-q4-k-xl", "unsloth-qwen3-6-27b-mtp-gguf--ud-q4-k-xl"),
    "qwen36-27b-q6-k": ("unsloth-qwen3-6-27b-mtp-gguf--q6-k", "unsloth-qwen3-6-27b-mtp-gguf--q6-k"),
    "qwen36-27b-iq4-xs": ("unsloth-qwen3-6-27b-mtp-gguf--iq4-xs", "unsloth-qwen3-6-27b-mtp-gguf--iq4-xs"),
    "qwen38-27b-ud-q4-k-m": ("unsloth-qwen3-8-27b-gguf--ud-q4-k-m", "unsloth-qwen3-8-27b-gguf--ud-q4-k-m"),
    "qwen38-27b-ud-q4-k-xl": ("unsloth-qwen3-8-27b-gguf--ud-q4-k-xl", "unsloth-qwen3-8-27b-gguf--ud-q4-k-xl"),
    "qwen38-q6": ("orcarouter-qwen3-8-27b-uncensored-gguf--q6-k", "orcarouter-qwen3-8-27b-uncensored-gguf--q6-k"),
    "qwen38-q8": ("orcarouter-qwen3-8-27b-uncensored-gguf--q8-0", "orcarouter-qwen3-8-27b-uncensored-gguf--q8-0"),
    "qwen36-35b-a3b-q4-k-m": ("unsloth-qwen3-6-35b-a3b-gguf--ud-q4-k-m", "unsloth-qwen3-6-35b-a3b-mtp-gguf--q4-k-m"),
    "qwen36-35b-a3b-q4-k-s": (
        "unsloth-qwen3-6-35b-a3b-gguf-qwen3-6-35b-a3b-ud-q4-k-s-gguf--unknown",
        "unsloth-qwen3-6-35b-a3b-mtp-gguf--q4-k-s",
    ),
    "qwen36-35b-a3b-iq4-xs": (
        "unsloth-qwen3-6-35b-a3b-gguf-qwen3-6-35b-a3b-ud-iq4-xs-gguf--iq4xs",
        "unsloth-qwen3-6-35b-a3b-mtp-gguf--ud-iq4-xs",
    ),
    "gemma4-26b-a4b-q4-k-s": (
        "unsloth-gemma-4-26b-a4b-it-gguf--q4-k-s",
        "unsloth-gemma-4-26b-a4b-it-gguf--q4-k-s",
    ),
    "gemma4-26b-a4b-q4-k-xl": (
        "unsloth-gemma-4-26b-a4b-it-gguf--ud-q4-k-xl",
        "unsloth-gemma-4-26b-a4b-it-gguf--ud-q4-k-xl",
    ),
    "qwen3-coder-30b-a3b-q4-k-m": (
        "unsloth-qwen3-coder-30b-a3b-instruct-gguf--q4-k-m",
        "unsloth-qwen3-coder-30b-a3b-instruct-gguf--q4-k-m",
    ),
    "ornith-q5": ("ornith-ai-ornith-1-5-35b-a3b-gguf--q5-k-m", "ornith-ai-ornith-1-5-35b-a3b-gguf--q5-k-m"),
}

CLONE_INSTANCES = [
    ("unsloth-qwen3-6-27b-mtp-gguf--q4-k-m", "unsloth-qwen3-6-27b-mtp-gguf--q4-k-s", "Q4_K_S"),
    ("orcarouter-qwen3-8-27b-uncensored-gguf--iq2-xxs", "orcarouter-qwen3-8-27b-uncensored-gguf--q6-k", "Q6_K"),
    ("orcarouter-qwen3-8-27b-uncensored-gguf--iq2-xxs", "orcarouter-qwen3-8-27b-uncensored-gguf--q8-0", "Q8_0"),
    ("ornith-ai-ornith-1-5-35b-a3b-gguf--q4-k-m", "ornith-ai-ornith-1-5-35b-a3b-gguf--q5-k-m", "Q5_K_M"),
]


def dump(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n")


def known(unit: str | None = None) -> dict:
    row = {
        "state": "known",
        "provenance": {"captured_at": NOW, "sources": [VENDOR]},
    }
    if unit:
        row["unit"] = unit
    return row


def unknown_commercial(detail: str) -> dict:
    return {
        "state": "unknown",
        "reason": {"code": "not-captured", "detail": detail},
        "provenance": {"captured_at": NOW, "sources": [VENDOR]},
    }


def dense(value: float, structured: bool = True) -> dict:
    out = {
        "dense": {
            "provenance": {"captured_at": NOW, "sources": [VENDOR]},
            "state": "known",
            "unit": "tflops",
            "value": value,
        }
    }
    if structured:
        out["structured_2_4"] = unpublished("structured 2:4")
    return out


def unpublished(label: str) -> dict:
    return {
        "provenance": {"captured_at": NOW, "sources": [VENDOR]},
        "reason": {
            "code": "not-published",
            "detail": f"No {label} throughput was published for this exact accelerator; no FLOPS inferred.",
        },
        "state": "unknown",
        "unit": "tflops",
    }


def observed_command(series: str, tp: int) -> str:
    split = "-sm none" if tp == 1 else "-sm tensor -ts 0.5,0.5"
    if series == "mtp":
        return f"llama-server --spec-type draft-mtp --spec-draft-n-max 3 -ngl 99 --flash-attn on {split}"
    if series == "tuned":
        return (
            f"llama-bench -p 512 -n 128 -r 5 -ngl 99 -fa on -b 8192 -ub 64 "
            f"-ctk q8_0 -ctv q8_0 --poll 0 {split}"
        )
    return f"llama-bench -p 512 -n 128 -r 5 -ngl 99 -fa on -b 2048 -ub 512 {split}"


def write_hardware() -> None:
    dump(
        REG / "hardware" / f"{HW}.json",
        {
            "accelerator": {"count": 1, "unit": "GPU"},
            "accelerator_backend": "amd-rocm",
            "aliases": ["radeon pro w7800", "w7800 48gb"],
            "captured_at": "2026-09-06",
            "commercial": {
                "availability": unknown_commercial(
                    "Current purchasable availability was not validated for this partner_workstation_systems channel."
                ),
                "channel_status": "partner_workstation_systems",
                "current_stock": None,
                "current_street_price": None,
                "msrp": None,
                "prices": [],
            },
            "compute": {
                "architecture": "AMD RDNA 3",
                "compute_units": 70,
                "stats": {
                    "bf16": {"unknown": unpublished("bf16")},
                    "fp16": dense(90.4),
                    "fp32": dense(45.2),
                    "fp8": {"unknown": unpublished("fp8")},
                    "int4": dense(181, structured=False),
                    "int8": dense(90.4, structured=False),
                    "tf32": {"unknown": unpublished("tf32")},
                },
                "stream_processors": 4480,
            },
            "facts": {
                "accelerator.count": known("GPU"),
                "commercial.availability": unknown_commercial(
                    "Current purchasable availability was not validated for this partner_workstation_systems channel."
                ),
                "commercial.channel_status": known(),
                "commercial.current_stock": unknown_commercial("Audit availability note: unknown."),
                "commercial.current_street_price": unknown_commercial(
                    "No current validated retailer offer captured"
                ),
                "commercial.msrp": unknown_commercial("No manufacturer launch price captured"),
                "commercial.prices": unknown_commercial("No manufacturer launch price captured"),
                "compute.architecture": known(),
                "compute.compute_units": known(),
                "compute.stream_processors": known(),
                "memory.bandwidth_gb_per_s": known(),
                "memory.vram_gb": known(),
                "memory.vram_type": known(),
            },
            "family": "radeon-pro-w7800",
            "id": HW,
            "kind": "discrete",
            "memory": {
                "bandwidth_gb_per_s": 864,
                "cpu_memory_gb": None,
                "vram_gb": 48,
                "vram_type": "GDDR6",
            },
            "name": "Radeon PRO W7800",
            "product_names": [],
            "products": [],
            "schema_version": "local-ai-registry/v1",
            "sources": [VENDOR],
            "vendor": "amd",
        },
    )


def clone_instance(src_id: str, new_id: str, precision: str) -> None:
    dest = REG / "model-instance" / f"{new_id}.json"
    if dest.exists():
        return
    src = json.loads((REG / "model-instance" / f"{src_id}.json").read_text())
    src["id"] = new_id
    src["weights"]["format"] = precision
    src["weights"]["precision"] = precision
    src["weights"]["size_gb"] = None
    facts = src.get("facts") or {}
    facts.pop("weights.size_gb", None)
    src["facts"] = facts
    dump(dest, src)


def recipe_and_sweep(sweep_path: Path) -> None:
    sweep = json.loads(sweep_path.read_text())
    rid = sweep["recipe_id"]
    series = "stock"
    slug = None
    if "-lemonade-" in rid:
        series = "lemonade"
    elif "-kernel-anvil-" in rid:
        series = "tuned"
    elif "-mtp-" in rid:
        series = "mtp"
    # recover organizer slug from filename prefix before hardware id
    stem = sweep_path.name.replace(f"-{HW}-", "|").split("|")[0]
    # stem is registry_stem e.g. qwen3-6-27b-q4-k-m
    # map back via ARTIFACTS registry_stem — invert INSTANCES keys via package artifacts
    artifacts = json.loads((PKG / "artifacts.json").read_text())
    for s, art in artifacts.items():
        if art["registry_stem"] == stem:
            slug = s
            break
    if slug is None or slug not in INSTANCES:
        raise SystemExit(f"unmapped sweep {sweep_path.name} stem={stem}")
    stock_id, mtp_id = INSTANCES[slug]
    instance_id = mtp_id if series == "mtp" else stock_id
    if not (REG / "model-instance" / f"{instance_id}.json").exists():
        raise SystemExit(f"missing model-instance {instance_id}")

    engines = {
        "stock": ("c060ca9", "llama-bench-pp512-tg128"),
        "lemonade": ("b1323-95ef7fc", "llama-bench-pp512-tg128"),
        "tuned": ("c060ca9+smithy", "llama-bench-pp512-tg128-ub64-q8kv"),
        "mtp": ("c060ca9", "llama-server-completion-draft-mtp"),
    }
    version, decode_mode = engines[series]
    tp = sweep.get("hardware_count") or 1
    notes = (sweep.get("source") or {}).get("notes") or ""
    rows_in = sweep.get("rows") or []
    command = observed_command(series, tp)
    tokenized = tokenized_record(parse_observed_command(command))
    out_rows = []
    for r in rows_in:
        out_rows.append(
            {
                "concurrency": 1,
                "context_tokens": r.get("context_tokens"),
                "decode_tok_s": r.get("decode_tok_s"),
                "decode_tok_s_per_stream": r.get("decode_tok_s_per_stream") or r.get("decode_tok_s"),
                "output_tokens": r.get("output_tokens") if r.get("output_tokens") is not None else 128,
                "peak_vram_gb": None,
                "prefill_tok_s": r.get("prefill_tok_s"),
                "samples": r.get("samples") or 5,
                "status": "observed",
                "ttft_ms_p50": None,
            }
        )
    metrics = derive_metrics(out_rows, latest_point_at=sweep.get("measured_at"))
    metrics["inference_engine_version"] = version
    metrics["decode_mode"] = decode_mode
    src_metrics = sweep.get("metrics") or {}
    if src_metrics.get("max_context_tokens"):
        metrics["max_context_tokens"] = max(
            int(metrics.get("max_context_tokens") or 0),
            int(src_metrics["max_context_tokens"]),
        )
    for key in (
        "decode8k_tps",
        "decode8k_context_tokens",
        "decode32k_tps",
        "decode32k_context_tokens",
        "max_prompt_tokens",
    ):
        if src_metrics.get(key) is not None:
            metrics[key] = src_metrics[key]
    max_ctx = int(metrics.get("max_context_tokens") or 0) or None

    recipe = {
        "capabilities": {"chat": None, "reasoning": None, "tools": None, "vision": None},
        "description": "Observed llama.cpp HIP run. Evidence for compatibility, not an executable launch contract.",
        "engine": {"graph_mode": None, "name": "llama.cpp", "version": version},
        "facts": {},
        "hardware_count": tp,
        "hardware_id": HW,
        "id": rid,
        "launch": {
            "container": {
                "captured_at": NOW,
                "compose_file": None,
                "digest": None,
                "image": None,
                "reason": "reference-only-launch",
                "runtime": None,
                "source": [{"captured_at": NOW, "kind": "recipe-launch", "url": REGISTRY}],
                "state": "none",
            },
            "kind": "reference",
            "source": "0xsero",
        },
        "metadata": {
            "lab": {
                "backend": "rocm",
                "hardware_label": "Radeon PRO W7800 48GB",
                "host": "par1-cs13",
                "notes": notes,
                "observed_command": command,
                "raw_path": (sweep.get("source") or {}).get("paths", [None])[0],
                "series": series,
                "tokenized": tokenized,
            }
        },
        "model_instance_id": instance_id,
        "provenance": {
            "captured_at": NOW,
            "sources": [{"captured_at": NOW, "kind": "normalized-recipe", "url": REGISTRY}],
        },
        "recipe_source": "0xsero",
        "schema_version": "local-ai-registry/v1",
        "serving": {
            "kv_cache_tokens": None,
            "max_concurrency": 1,
            "max_context_tokens": max_ctx,
            "tensor_parallel": tp,
        },
        "speed_sweep_ids": [sweep["id"]],
        "status": "candidate",
    }
    recipe["facts"] = facts_for(recipe)
    dump(REG / "recipe" / f"{rid}.json", recipe)

    dump(
        REG / "speed-sweep" / f"{sweep['id']}.json",
        {
            "accepted_at": None,
            "id": sweep["id"],
            "measured_at": sweep.get("measured_at"),
            "metrics": metrics,
            "recipe_id": rid,
            "rows": out_rows,
            "schema_version": "local-ai-registry/v1",
            "source": {
                "commit": None,
                "kind": "lab-measurement",
                "notes": notes,
                "paths": (sweep.get("source") or {}).get("paths"),
                "repository": REGISTRY,
            },
        },
    )


def main() -> int:
    if not PKG.is_dir():
        raise SystemExit(f"missing package {PKG}")
    write_hardware()
    for src, dest, prec in CLONE_INSTANCES:
        clone_instance(src, dest, prec)
    sweeps = sorted((PKG / "speed-sweeps").glob("*.json"))
    for path in sweeps:
        recipe_and_sweep(path)
    print(f"wrote hardware {HW}, {len(CLONE_INSTANCES)} instances (if missing), {len(sweeps)} recipes+sweeps")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
