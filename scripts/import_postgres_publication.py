#!/usr/bin/env python3

import argparse
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path


SCHEMA = "local-ai-registry/v1"
SOURCE = "exo-postgres"
HARDWARE = {
    "m3_24_10c": "apple-m3-24gb",
    "m3_max_128_40c": "apple-m3-max-128gb",
    "m3_ultra_96_60c": "apple-m3-ultra-96gb-60c",
    "m3_ultra_512_80c": "apple-m3-ultra-96gb-80c",
    "m4_pro_64_20c": "apple-m4-pro-48gb",
    "m4_max_36_32c": "apple-m4-max-36gb",
    "m4_max_128_40c": "apple-m4-max-128gb",
    "m5_pro_64_20c": "apple-m5-pro-64gb",
    "m5_max_128_40c": "apple-m5-max-128gb",
}


def slug(value, limit=140):
    value = re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", value.lower())).strip("-")
    if len(value) <= limit:
        return value
    digest = hashlib.sha256(value.encode()).hexdigest()[:12]
    return f"{value[:limit - 13].rstrip('-')}-{digest}"


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def rows(path):
    with path.open() as source:
        for line in source:
            if line.strip():
                yield json.loads(line)


def params(name):
    values = [float(value) for value in re.findall(r"(?:^|[-_])(\d+(?:\.\d+)?)b(?:$|[-_])", name.lower())]
    return max(values) if values else None


def active_params(name):
    match = re.search(r"(?:^|[-_])a(\d+(?:\.\d+)?)b(?:$|[-_])", name.lower())
    return float(match.group(1)) if match else None


def engine_name(value):
    return "llama.cpp" if value in ("llama_cpp", "llamacpp") else value


def format_name(model_id, engine):
    lower = model_id.lower()
    if ".gguf" in lower:
        return "GGUF"
    if engine == "mlx" or "mlx" in lower:
        return "MLX"
    return None


def metric_row(run, context_key, decode_key, memory_key, ttft=False):
    context = run.get(context_key)
    decode = run.get(decode_key)
    memory = run.get(memory_key)
    if context is None and decode is None and memory is None:
        return None
    return {
        "concurrency": run.get("concurrency"),
        "context_tokens": context,
        "output_tokens": None,
        "prefill_tok_s": None,
        "decode_tok_s": decode,
        "decode_tok_s_per_stream": None,
        "ttft_ms_p50": run.get("ttft32k_seconds") * 1000 if ttft and run.get("ttft32k_seconds") is not None else None,
        "peak_vram_gb": int(memory) / 2**30 if memory is not None else None,
        "samples": 1,
        "status": "observed",
    }


def import_publication(publication, root):
    manifest = json.loads((publication / "manifest.json").read_text())
    publication_id = manifest["publicationId"]
    model_rows = {row["model_id"]: row for row in rows(publication / "pg_read_models.jsonl")}
    speed_rows = [row for row in rows(publication / "pg_read_speed_runs.jsonl") if row.get("hardware_key") in HARDWARE]
    groups = defaultdict(list)
    instance_records = {}
    model_records = {}

    for run in speed_rows:
        source_id = run["model_id"]
        source = model_rows[source_id]
        base_id = slug(source.get("base_model_family") or source["route_slug"])
        repository = source.get("hf_repo") or source_id
        precision = source.get("quantization") or "unknown"
        instance_id = f"{slug(source_id)}--{slug(precision)}"
        base_name = source.get("base_model_family") or source["display_name"]
        model_records[base_id] = {
            "schema_version": SCHEMA,
            "id": base_id,
            "family": source["family"],
            "name": base_name,
            "params": params(base_name),
            "active_params": active_params(base_name),
            "architecture": "moe" if active_params(base_name) is not None else None,
            "url": f"https://huggingface.co/{repository}" if "/" in repository else None,
        }
        instance_records[instance_id] = {
            "schema_version": SCHEMA,
            "id": instance_id,
            "model_id": base_id,
            "repository": repository,
            "url": f"https://huggingface.co/{repository}" if "/" in repository else None,
            "revision": None,
            "served_name": source["display_name"],
            "weights": {
                "format": format_name(source_id, run["inference_engine"]),
                "precision": precision,
                "size_gb": None,
                "artifact": source_id,
                "source": SOURCE,
                "publication_id": publication_id,
            },
            "kind": "base" if precision.lower() in ("bf16", "fp16", "fp32") else "quant",
        }
        key = (instance_id, HARDWARE[run["hardware_key"]], engine_name(run["inference_engine"]))
        groups[key].append(run)

    for identifier, record in model_records.items():
        path = root / "model" / f"{identifier}.json"
        if not path.exists():
            write(path, record)
    for identifier, record in instance_records.items():
        path = root / "model-instance" / f"{identifier}.json"
        existing = json.loads(path.read_text()) if path.exists() else {}
        owned = existing.get("metadata", {}).get("source") == SOURCE or existing.get("weights", {}).get("source") == SOURCE
        if not path.exists() or owned:
            write(path, record)

    wanted_recipes = set()
    wanted_sweeps = set()
    for (instance_id, hardware_id, engine), evidence in sorted(groups.items()):
        key = "|".join((instance_id, hardware_id, engine))
        recipe_id = f"pg-{slug(instance_id, 72)}-{hardware_id}-{slug(engine)}-{hashlib.sha256(key.encode()).hexdigest()[:10]}"
        sweep_ids = []
        for run in sorted(evidence, key=lambda item: item["run_id"]):
            sweep_id = f"pg-{run['run_id']}-sweep"
            sweep_ids.append(sweep_id)
            wanted_sweeps.add(sweep_id)
            selected = [
                metric_row(run, "decode8k_context_tokens", "decode8k_tps", "memory8k_bytes"),
                metric_row(run, "decode32k_context_tokens", "decode32k_tps", "peak_memory_bytes", True),
                metric_row(run, "decode_max_context_tokens", "decode_max_context_tps", "memory_max_context_bytes"),
            ]
            selected = [row for row in selected if row is not None]
            selected = list({json.dumps(row, sort_keys=True): row for row in selected}.values())
            if not selected:
                selected = [{
                    "concurrency": run.get("concurrency"),
                    "context_tokens": run.get("max_context_tokens"),
                    "output_tokens": None,
                    "prefill_tok_s": run.get("peak_prompt_tps"),
                    "decode_tok_s": run.get("peak_generation_tps"),
                    "decode_tok_s_per_stream": None,
                    "ttft_ms_p50": None,
                    "peak_vram_gb": int(run["peak_memory_bytes"]) / 2**30 if run.get("peak_memory_bytes") is not None else None,
                    "samples": 1,
                    "status": "observed",
                }]
            write(root / "speed-sweeps" / f"{sweep_id}.json", {
                "schema_version": SCHEMA,
                "id": sweep_id,
                "recipe_id": recipe_id,
                "measured_at": run.get("latest_point_at"),
                "accepted_at": None,
                "source": {"repository": "https://local.ai", "commit": None, "paths": [f"publication:{publication_id}", f"run:{run['run_id']}"]},
                "metrics": {key: value for key, value in run.items() if key not in ("publication_id", "run_id", "model_id", "hardware_key", "inference_engine")},
                "rows": selected,
            })
        versions = sorted({run.get("inference_engine_version") for run in evidence if run.get("inference_engine_version") not in (None, "", "unknown")})
        max_context = max((run.get("max_context_tokens") or 0 for run in evidence), default=0) or None
        max_concurrency = max((run.get("concurrency") or 1 for run in evidence), default=1)
        wanted_recipes.add(recipe_id)
        write(root / "recipe" / f"{recipe_id}.json", {
            "schema_version": SCHEMA,
            "id": recipe_id,
            "recipe_source": SOURCE,
            "status": "candidate",
            "description": "Measured compatibility from the local.ai Postgres publication. Launch arguments are not promoted into an executable contract.",
            "model_instance_id": instance_id,
            "hardware_id": hardware_id,
            "hardware_count": 1,
            "engine": {"name": engine, "version": versions[0] if len(versions) == 1 else None, "graph_mode": None},
            "launch": {"kind": "reference", "source": SOURCE, "publication_id": publication_id, "run_ids": sorted(run["run_id"] for run in evidence)},
            "serving": {"tensor_parallel": 1, "max_context_tokens": max_context, "max_concurrency": max_concurrency, "kv_cache_tokens": None},
            "capabilities": {"chat": None, "reasoning": None, "tools": None, "vision": None},
            "speed_sweeps_ids": sweep_ids,
            "metadata": {"postgres": {"publication_id": publication_id, "hardware_key": evidence[0]["hardware_key"], "source_model_id": evidence[0]["model_id"], "run_count": len(evidence)}},
        })

    for path in (root / "recipe").glob("*.json"):
        record = json.loads(path.read_text())
        if record.get("recipe_source") == SOURCE and record["id"] not in wanted_recipes:
            path.unlink()
    for path in (root / "speed-sweeps").glob("pg-*-sweep.json"):
        if path.stem not in wanted_sweeps:
            path.unlink()
    print(f"imported {len(speed_rows)} Mac runs into {len(groups)} candidate recipes from {publication_id}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("publication")
    parser.add_argument("--root", default="registry")
    args = parser.parse_args()
    import_publication(Path(args.publication), Path(args.root))


if __name__ == "__main__":
    main()
