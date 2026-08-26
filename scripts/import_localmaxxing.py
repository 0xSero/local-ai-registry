#!/usr/bin/env python3

import argparse
import json
import re
from pathlib import Path


SCHEMA = "local-ai-registry/v1"
SOURCE = "https://www.localmaxxing.com"
HARDWARE = {
    "Radeon AI Pro R9700": "radeon-ai-pro-r9700-32gb",
    "GB10 Grace Blackwell": "dgx-spark-gb10-128gb",
    "RTX 3090": "rtx-3090-24gb",
    "RTX PRO 6000 Blackwell": "rtx-pro-6000-blackwell-96gb",
}


def slug(value):
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", value.lower())).strip("-")


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def revision(value):
    return value if re.fullmatch(r"[0-9a-f]{40}", value or "") else None


def import_row(root, row):
    hardware_id = HARDWARE.get(row.get("hardwareGroupLabel"))
    if not hardware_id:
        return False

    artifact = row["model"]
    base = artifact.get("baseModel") or artifact
    model_id = slug(base["displayName"])
    model_path = root / "model" / f"{model_id}.json"
    if not model_path.exists():
        write(model_path, {
            "schema_version": SCHEMA,
            "id": model_id,
            "family": (row["model"].get("family") or "unknown").lower(),
            "name": base["displayName"],
            "params": base.get("params"),
            "active_params": base.get("activeParams"),
            "architecture": "moe" if base.get("isMoE") else "dense",
            "url": f"https://huggingface.co/{base['hfId']}",
        })

    precision = row["engine"].get("quantization") or "unknown"
    instance_id = f"{slug(artifact['hfId'])}--{slug(precision)}"
    instance_path = root / "model-instance" / f"{instance_id}.json"
    if not instance_path.exists():
        write(instance_path, {
            "schema_version": SCHEMA,
            "id": instance_id,
            "model_id": model_id,
            "repository": artifact["hfId"],
            "url": f"https://huggingface.co/{artifact['hfId']}",
            "revision": revision(row.get("modelRevision")),
            "served_name": artifact["displayName"],
            "weights": {"format": precision, "precision": precision, "size_gb": None},
            "kind": "quant" if artifact.get("baseModel") or precision.lower() not in ("bf16", "fp16", "fp32") else "base",
        })

    run_id = row["id"]
    recipe_id = f"{model_id}-{slug(precision)}-{hardware_id}-{slug(row['engine']['engineName'])}-tp{row['hardware'].get('gpuCount') or 1}-{run_id[-8:]}"
    sweep_id = f"{recipe_id}-sweep"
    write(root / "recipe" / f"{recipe_id}.json", {
        "schema_version": SCHEMA,
        "id": recipe_id,
        "recipe_source": "localmaxxing",
        "status": "candidate",
        "description": "Observed LocalMaxxing result. It is evidence for compatibility, not an executable launch contract.",
        "model_instance_id": instance_id,
        "hardware_id": hardware_id,
        "hardware_count": row["hardware"].get("gpuCount") or 1,
        "engine": {
            "name": row["engine"]["engineName"],
            "version": row["engine"].get("engineVersion"),
            "graph_mode": None,
        },
        "launch": {
            "kind": "reference",
            "source": "localmaxxing",
            "run_id": run_id,
            "url": f"{SOURCE}/en/runs/{run_id}",
        },
        "serving": {
            "tensor_parallel": row["hardware"].get("gpuCount") or 1,
            "max_context_tokens": row.get("contextLength"),
            "max_concurrency": row.get("batchSize"),
            "kv_cache_tokens": None,
        },
        "capabilities": {"chat": None, "reasoning": None, "tools": None, "vision": None},
        "speed_sweeps_ids": [sweep_id],
        "metadata": {
            "localmaxxing": {
                "run_id": run_id,
                "hardware_label": row.get("hardwareGroupLabel"),
                "revision_unpinned": revision(row.get("modelRevision")) is None,
                "notes": row.get("notes"),
            }
        },
    })
    write(root / "speed-sweeps" / f"{sweep_id}.json", {
        "schema_version": SCHEMA,
        "id": sweep_id,
        "recipe_id": recipe_id,
        "measured_at": row.get("createdAt"),
        "accepted_at": None,
        "source": {"repository": SOURCE, "commit": None, "paths": [f"/en/runs/{run_id}"]},
        "rows": [{
            "concurrency": row.get("batchSize") or 1,
            "context_tokens": row.get("contextLength"),
            "output_tokens": row.get("outputTokens"),
            "prefill_tok_s": row.get("tokSPrefill"),
            "decode_tok_s": row.get("tokSOut"),
            "decode_tok_s_per_stream": None,
            "ttft_ms_p50": row.get("ttftMs"),
            "peak_vram_gb": row.get("peakVramGb"),
            "samples": 1,
            "status": "observed",
        }],
    })
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input")
    parser.add_argument("--root", default="registry")
    args = parser.parse_args()
    rows = json.loads(Path(args.input).read_text())
    root = Path(args.root)
    imported = sum(import_row(root, row) for row in rows)
    print(f"imported {imported} of {len(rows)} supported rows")


if __name__ == "__main__":
    main()
