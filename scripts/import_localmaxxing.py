#!/usr/bin/env python3

import argparse
import json
import re
from pathlib import Path

from sweep_metrics import derive_metrics


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

def _concurrency_evidence(row):
    flags = row.get("engineFlags") or {}
    command = flags.get("commandSnippet") if isinstance(flags.get("commandSnippet"), str) else ""
    notes = row.get("notes") if isinstance(row.get("notes"), str) else ""
    return command, "\n".join(value for value in (command, notes) if value)


def evidenced_sweep_metrics(row):
    """Return metrics stated unambiguously in the exact run notes."""
    _, evidence = _concurrency_evidence(row)
    values = set()
    for pattern in (
        r"\bPP\s*=\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*(?:tok(?:en)?s?/?s|t/s)\b",
        r"\bPrompt processing\s*(?:=|:)?\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*(?:tok(?:en)?s?/?s|t/s)\b",
    ):
        for match in re.finditer(pattern, evidence, re.IGNORECASE):
            values.add(float(match.group(1).replace(",", "")))
    return {"prefill_tok_s": next(iter(values))} if len(values) == 1 else {}




def workload_concurrency(row):
    command, evidence = _concurrency_evidence(row)
    patterns = (
        r"\bagents?\s*=\s*(\d+)\b",
        r"\bconcurrent\s+throughput\b[^.\n;]{0,80}\bbatch\s*(?:=|:)\s*(\d+)\b",
        r"\b(\d+)\s+concurrent\b[^\n.;]{0,80}\b(?:requests?|clients?|agents?|streams?)\b",
        r"\bat\s+concurrency\s*(?:=|:)?\s*(\d+)\b",
        r"\bconcurrency\s*(?:=|:)\s*(\d+)\b",
        r"(?:^|[\s,;])c\s*=\s*(\d+)\b",
    )
    for pattern in patterns:
        match = re.search(pattern, evidence, re.IGNORECASE)
        if match:
            return int(match.group(1))
    batch_size = row.get("batchSize")
    if (
        isinstance(batch_size, int)
        and re.search(
            r"\bbatch\s*size\b[^\n.;]{0,40}\b(?:is|means|represents)\b[^\n.;]{0,40}\bconcurrent\b",
            evidence,
            re.IGNORECASE,
        )
    ):
        return batch_size
    if re.search(r"\bsingle[-_ ](?:stream|request|client)\b", evidence, re.IGNORECASE):
        return 1
    engine_name = str((row.get("engine") or {}).get("engineName") or "").lower()
    if "llama" in engine_name or "llama-bench" in command.lower():
        return 1
    return None


def _explicit_positive_integers(command, options):
    values = set()
    option_pattern = "|".join(re.escape(option) for option in options)
    for match in re.finditer(
        rf"(?:^|\s)(?:{option_pattern})(?:=|\s+)(\d+)\b",
        command,
        re.IGNORECASE,
    ):
        value = int(match.group(1))
        if value > 0:
            values.add(value)
    return values


def server_capacity(row):
    command, _ = _concurrency_evidence(row)
    values = _explicit_positive_integers(
        command,
        ("--parallel", "-np", "--max-num-seqs", "--max-concurrency"),
    )
    return next(iter(values)) if len(values) == 1 else None


def server_context_limit(row):
    command, _ = _concurrency_evidence(row)
    direct_values = _explicit_positive_integers(
        command,
        ("--max-model-len", "--context-length", "--max-context-length"),
    )
    llama_values = _explicit_positive_integers(command, ("--ctx-size", "-c"))
    llama_parallel = _explicit_positive_integers(command, ("--parallel", "-np"))
    if len(llama_values) == 1:
        llama_context = next(iter(llama_values))
        if len(llama_parallel) == 1:
            parallel = next(iter(llama_parallel))
            if llama_context % parallel != 0:
                return None
            llama_context //= parallel
        direct_values.add(llama_context)
    return next(iter(direct_values)) if len(direct_values) == 1 else None


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
    concurrency = workload_concurrency(row)
    evidenced_metrics = evidenced_sweep_metrics(row)
    capacity = server_capacity(row)
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
            "max_context_tokens": server_context_limit(row),
            "max_concurrency": capacity,
            "kv_cache_tokens": None,
        },
        "capabilities": {"chat": None, "reasoning": None, "tools": None, "vision": None},
        "speed_sweep_ids": [sweep_id],
        "metadata": {
            "localmaxxing": {
                "run_id": run_id,
                "hardware_label": row.get("hardwareGroupLabel"),
                "revision_unpinned": revision(row.get("modelRevision")) is None,
                "notes": row.get("notes"),
                "observed_command": (row.get("engineFlags") or {}).get("commandSnippet"),
                "batch_size": row.get("batchSize"),
            }
        },
    })
    sweep_rows = [{
        "concurrency": concurrency,
        "context_tokens": row.get("contextLength"),
        "output_tokens": row.get("outputTokens"),
        "prefill_tok_s": row.get("tokSPrefill") if row.get("tokSPrefill") is not None else evidenced_metrics.get("prefill_tok_s"),
        "decode_tok_s": row.get("tokSOut"),
        "decode_tok_s_per_stream": None,
        "ttft_ms_p50": row.get("ttftMs"),
        "peak_vram_gb": row.get("peakVramGb"),
        "samples": 1,
        "status": "observed",
    }]
    write(root / "speed-sweep" / f"{sweep_id}.json", {
        "schema_version": SCHEMA,
        "id": sweep_id,
        "recipe_id": recipe_id,
        "measured_at": row.get("createdAt"),
        "accepted_at": None,
        "source": {"repository": SOURCE, "commit": None, "paths": [f"/en/runs/{run_id}"]},
        "metrics": derive_metrics(sweep_rows, row.get("createdAt")),
        "rows": sweep_rows,
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
