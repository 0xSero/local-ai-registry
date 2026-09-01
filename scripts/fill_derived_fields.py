#!/usr/bin/env python3
"""Fill only values that are deterministically derivable from registry records."""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from typing import Any

from import_localmaxxing import server_capacity, workload_concurrency

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "registry"
REGISTRY_URL = "https://github.com/0xSero/local-ai-registry"
M1_BANDWIDTH_SOURCE = "https://www.macrumors.com/guide/m1-vs-m2-chip/"


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def save(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n")


def known_fact(reason: str, captured_at: str, url: str = REGISTRY_URL) -> dict[str, Any]:
    return {
        "provenance": {
            "captured_at": captured_at,
            "sources": [{"captured_at": captured_at, "kind": "registry-derived", "url": url}],
        },
        "reason": reason,
        "state": "known",
    }

def unknown_fact(reason: str, captured_at: str, url: str = REGISTRY_URL) -> dict[str, Any]:
    return {
        "provenance": {
            "captured_at": captured_at,
            "sources": [{"captured_at": captured_at, "kind": "source-semantics", "url": url}],
        },
        "reason": reason,
        "state": "unknown",
    }




def fill_benchmarks() -> tuple[int, int]:
    organisations = variants = 0
    for path in sorted((REGISTRY / "benchmark").glob("*.json")):
        record = load(path)
        changed = False
        for row in record.get("rows", []):
            root = row.get("root")
            if row.get("org") is None and isinstance(root, str) and root.count("/") == 1:
                row["org"] = root.split("/", 1)[0]
                organisations += 1
                changed = True
            if row.get("variant") is None and isinstance(root, str) and root.count("/") == 1:
                row["variant"] = root.split("/", 1)[1]
                variants += 1
                changed = True
        if changed:
            save(path, record)
    return organisations, variants


def fill_recipes(captured_at: str) -> int:
    instances = {path.stem: load(path) for path in (REGISTRY / "model-instance").glob("*.json")}
    hardware = {path.stem: load(path) for path in (REGISTRY / "hardware").glob("*.json")}
    updates = 0
    for path in sorted((REGISTRY / "recipe").glob("*.json")):
        record = load(path)
        if record.get("description") is not None:
            continue
        instance = instances.get(record.get("model_instance_id"), {})
        device = hardware.get(record.get("hardware_id"), {})
        model_name = instance.get("served_name") or record.get("model_instance_id")
        hardware_name = device.get("name") or record.get("hardware_id")
        engine = (record.get("engine") or {}).get("name")
        tp = (record.get("serving") or {}).get("tensor_parallel")
        if not all(isinstance(value, str) and value for value in (model_name, hardware_name, engine)):
            continue
        suffix = f" with tensor parallelism {tp}" if isinstance(tp, int) else ""
        record["description"] = f"{engine} recipe for {model_name} on {hardware_name}{suffix}."
        record.setdefault("facts", {})["description"] = known_fact("derived-from-recipe-identifiers", captured_at)
        save(path, record)
        updates += 1
    return updates

def correct_localmaxxing_concurrency_semantics(captured_at: str) -> tuple[int, int]:
    recipe_updates = 0
    sweep_updates = 0
    for path in sorted((REGISTRY / "recipe").glob("*.json")):
        record = load(path)
        if record.get("recipe_source") != "localmaxxing":
            continue
        serving = record.get("serving")
        metadata = record.get("metadata")
        local_metadata = metadata.get("localmaxxing") if isinstance(metadata, dict) else None
        if not isinstance(serving, dict) or not isinstance(local_metadata, dict):
            continue

        engine_name = str((record.get("engine") or {}).get("name") or "")
        source_row = {
            "engine": {"engineName": engine_name},
            "batchSize": local_metadata.get("batch_size"),
            "engineFlags": {"commandSnippet": local_metadata.get("observed_command")},
            "notes": local_metadata.get("notes"),
        }
        concurrency = workload_concurrency(source_row)
        capacity = server_capacity(source_row, concurrency)
        changed = False
        fact = (record.get("facts") or {}).get("serving.max_concurrency")
        if (
            capacity is None
            and isinstance(fact, dict)
            and fact.get("state") == "known"
            and fact.get("reason") == "server-capacity-derived-from-source-evidence"
            and isinstance(serving.get("max_concurrency"), int)
            and serving["max_concurrency"] > 0
        ):
            capacity = serving["max_concurrency"]
        if (
            not isinstance(fact, dict)
            and "batch_size" not in local_metadata
            and serving.get("max_concurrency") is not None
        ):
            local_metadata["batch_size"] = serving.get("max_concurrency")
            changed = True
        if serving.get("max_concurrency") != capacity:
            serving["max_concurrency"] = capacity
            changed = True

        if capacity is None:
            reason = "server-capacity-not-evidenced"
        else:
            reason = "server-capacity-derived-from-source-evidence"
        expected_state = "unknown" if capacity is None else "known"
        if (
            not isinstance(fact, dict)
            or fact.get("reason") != reason
            or fact.get("state") != expected_state
        ):
            source_url = ((record.get("launch") or {}).get("url") or REGISTRY_URL)
            fact_builder = unknown_fact if capacity is None else known_fact
            record.setdefault("facts", {})["serving.max_concurrency"] = fact_builder(
                reason, captured_at, source_url
            )
            changed = True
        if changed:
            save(path, record)
            recipe_updates += 1

        for sweep_id in record.get("speed_sweep_ids") or []:
            sweep_path = REGISTRY / "speed-sweep" / f"{sweep_id}.json"
            if not sweep_path.exists():
                continue
            sweep = load(sweep_path)
            sweep_changed = False
            for row in sweep.get("rows") or []:
                if row.get("concurrency") != concurrency:
                    row["concurrency"] = concurrency
                    sweep_changed = True
            metrics = sweep.get("metrics")
            if isinstance(metrics, dict) and metrics.get("concurrency") != concurrency:
                metrics["concurrency"] = concurrency
                sweep_changed = True
            if sweep_changed:
                save(sweep_path, sweep)
                sweep_updates += 1
    return recipe_updates, sweep_updates


def fill_sweep_metrics() -> int:
    file_updates = 0
    for path in sorted((REGISTRY / "speed-sweep").glob("*.json")):
        record = load(path)
        rows = record.get("rows")
        metrics = record.get("metrics")
        if not isinstance(rows, list) or not isinstance(metrics, dict):
            continue
        changed = False
        derived: dict[str, Any] = {
            "point_count": len(rows),
            "max_context_tokens": max((row["context_tokens"] for row in rows if isinstance(row.get("context_tokens"), int)), default=None),
            "peak_generation_tps": max((row["decode_tok_s"] for row in rows if isinstance(row.get("decode_tok_s"), (int, float))), default=None),
            "peak_prompt_tps": max((row["prefill_tok_s"] for row in rows if isinstance(row.get("prefill_tok_s"), (int, float))), default=None),
            "latest_point_at": record.get("measured_at"),
        }
        for key, value in derived.items():
            if metrics.get(key) is None and value is not None:
                metrics[key] = value
                changed = True
        if changed:
            save(path, record)
            file_updates += 1
    return file_updates


def fill_sweep_engine_versions() -> int:
    recipe_versions: dict[str, str] = {}
    for path in (REGISTRY / "recipe").glob("*.json"):
        recipe = load(path)
        version = (recipe.get("engine") or {}).get("version")
        if isinstance(version, str) and version not in ("", "unknown"):
            recipe_versions[recipe["id"]] = version

    updates = 0
    for path in sorted((REGISTRY / "speed-sweep").glob("*.json")):
        sweep = load(path)
        metrics = sweep.get("metrics")
        if (
            not isinstance(metrics, dict)
            or metrics.get("inference_engine_version") not in (None, "", "unknown")
        ):
            continue
        version = recipe_versions.get(sweep.get("recipe_id"))
        if version is None:
            continue
        metrics["inference_engine_version"] = version
        save(path, sweep)
        updates += 1
    return updates


def fill_per_stream_decode() -> tuple[int, int]:
    """Derive missing per-stream decode from aggregate decode and concurrency."""
    file_updates = 0
    row_updates = 0
    for path in sorted((REGISTRY / "speed-sweep").glob("*.json")):
        record = load(path)
        changed = False
        for row in record.get("rows") or []:
            concurrency = row.get("concurrency")
            decode = row.get("decode_tok_s")
            if (
                isinstance(concurrency, int)
                and concurrency > 0
                and isinstance(decode, (int, float))
                and row.get("decode_tok_s_per_stream") is None
            ):
                row["decode_tok_s_per_stream"] = round(decode / concurrency, 3)
                row_updates += 1
                changed = True
        if changed:
            save(path, record)
            file_updates += 1
    return file_updates, row_updates


def fill_localmaxxing_sources_and_runtime(captured_at: str) -> tuple[int, int, int]:
    recipes = {
        path.stem: (path, load(path))
        for path in (REGISTRY / "recipe").glob("*.json")
    }
    sweep_updates = version_updates = graph_updates = 0
    for recipe_id, (path, record) in sorted(recipes.items()):
        if record.get("recipe_source") != "localmaxxing":
            continue
        launch = record.get("launch") or {}
        metadata = record.get("metadata") or {}
        local_metadata = metadata.get("localmaxxing") or {}
        run_id = launch.get("run_id") or local_metadata.get("run_id")
        source_url = (
            f"https://www.localmaxxing.com/en/runs/{run_id}"
            if isinstance(run_id, str) and run_id
            else REGISTRY_URL
        )

        if isinstance(run_id, str) and run_id:
            for sweep_id in record.get("speed_sweep_ids") or []:
                sweep_path = REGISTRY / "speed-sweep" / f"{sweep_id}.json"
                if not sweep_path.exists():
                    continue
                sweep = load(sweep_path)
                source = sweep.get("source")
                if (
                    isinstance(source, dict)
                    and source.get("repository") == "https://www.localmaxxing.com"
                    and not source.get("paths")
                ):
                    source["paths"] = [f"/en/runs/{run_id}"]
                    save(sweep_path, sweep)
                    sweep_updates += 1

        engine = record.get("engine")
        changed = False
        if isinstance(engine, dict) and engine.get("version") in (None, "", "unknown"):
            draft = record.get("draft_launch") or {}
            synthesized = draft.get("synthesized") or {}
            source_recipe_id = synthesized.get("image_provenance")
            source_recipe = recipes.get(source_recipe_id)
            if source_recipe:
                source_engine = source_recipe[1].get("engine") or {}
                source_version = source_engine.get("version")
                if (
                    source_engine.get("name") == engine.get("name")
                    and source_version not in (None, "", "unknown")
                ):
                    engine["version"] = source_version
                    record.setdefault("facts", {})["engine.version"] = known_fact(
                        "copied-from-synthesized-image-provenance",
                        captured_at,
                        str((source_recipe[1].get("launch") or {}).get("url") or REGISTRY_URL),
                    )
                    version_updates += 1
                    changed = True
            if engine.get("version") in (None, "", "unknown"):
                notes = str(local_metadata.get("notes") or "")
                commit_match = re.search(
                    r"\bcommit\s+([0-9a-f]{7,40})\b",
                    notes,
                    re.IGNORECASE,
                )
                if commit_match:
                    engine["version"] = commit_match.group(1).lower()
                    record.setdefault("facts", {})["engine.version"] = known_fact(
                        "explicit-engine-commit-in-source-notes",
                        captured_at,
                        source_url,
                    )
                    version_updates += 1
                    changed = True

        if isinstance(engine, dict) and engine.get("graph_mode") is None:
            command = str(local_metadata.get("observed_command") or "")
            notes = str(local_metadata.get("notes") or "")
            explicit_eager = bool(re.search(r"(?:^|\s)--enforce-eager(?:\s|$)", command))
            explicit_eager = explicit_eager or bool(
                re.search(r"(?<!no --)\benforce-eager\b", notes, re.IGNORECASE)
            )
            explicit_eager = explicit_eager or "Eager execution (CUDA graph profiling OOM" in notes
            graph_mode = "eager" if explicit_eager else None
            graph_reason = "explicit-eager-execution-in-source"
            if graph_mode is None:
                mode_match = re.search(
                    r"cudagraph_mode[\\\"'\s:=]+([a-z_]+)",
                    command,
                    re.IGNORECASE,
                )
                if mode_match:
                    graph_mode = mode_match.group(1).lower().replace("_", "-")
                    graph_reason = "explicit-cudagraph-mode-in-observed-command"
            if graph_mode is not None:
                engine["graph_mode"] = graph_mode
                record.setdefault("facts", {})["engine.graph_mode"] = known_fact(
                    graph_reason,
                    captured_at,
                    source_url,
                )
                graph_updates += 1
                changed = True
        if changed:
            save(path, record)
    return sweep_updates, version_updates, graph_updates


def fill_out_of_stock_quantities() -> tuple[int, int]:
    file_updates = 0
    observation_updates = 0
    for path in sorted((REGISTRY / "price").glob("*/*.json")):
        record = load(path)
        changed = False
        for observation in record.get("observations") or []:
            if observation.get("in_stock") is False and observation.get("quantity") is None:
                observation["quantity"] = 0
                observation_updates += 1
                changed = True
        if changed:
            save(path, record)
            file_updates += 1
    return file_updates, observation_updates


def postgres_ttft_row(metrics: dict[str, Any]) -> dict[str, Any] | None:
    seconds = metrics.get("ttft32k_seconds")
    context = metrics.get("ttft32k_context_tokens")
    if not isinstance(seconds, (int, float)) or not isinstance(context, int):
        return None
    return {
        "concurrency": metrics.get("concurrency"),
        "context_tokens": context,
        "output_tokens": None,
        "prefill_tok_s": None,
        "decode_tok_s": None,
        "decode_tok_s_per_stream": None,
        "ttft_ms_p50": seconds * 1000,
        "peak_vram_gb": None,
        "samples": 1,
        "status": "observed",
    }


def repair_postgres_ttft() -> tuple[int, int]:
    file_updates = 0
    row_updates = 0
    for path in sorted((REGISTRY / "speed-sweep").glob("pg-*-sweep.json")):
        record = load(path)
        metrics = record.get("metrics")
        rows = record.get("rows")
        if not isinstance(metrics, dict) or not isinstance(rows, list):
            continue
        target = postgres_ttft_row(metrics)
        if target is None:
            continue
        changed = False
        combined = any(
            row.get("context_tokens") == target["context_tokens"]
            and row.get("ttft_ms_p50") == target["ttft_ms_p50"]
            and any(
                row.get(key) is not None
                for key in ("prefill_tok_s", "decode_tok_s", "peak_vram_gb")
            )
            for row in rows
        )
        if combined:
            filtered = [
                row
                for row in rows
                if not (
                    row.get("context_tokens") == target["context_tokens"]
                    and row.get("ttft_ms_p50") == target["ttft_ms_p50"]
                    and all(
                        row.get(key) is None
                        for key in ("prefill_tok_s", "decode_tok_s", "peak_vram_gb")
                    )
                )
            ]
            if len(filtered) != len(rows):
                row_updates += len(rows) - len(filtered)
                record["rows"] = rows = filtered
                changed = True
        else:
            for row in rows:
                if (
                    row.get("ttft_ms_p50") is not None
                    and row.get("context_tokens") != target["context_tokens"]
                ):
                    row["ttft_ms_p50"] = None
                    row_updates += 1
                    changed = True
            if not any(
                row.get("context_tokens") == target["context_tokens"]
                and row.get("ttft_ms_p50") == target["ttft_ms_p50"]
                and row.get("decode_tok_s") is None
                for row in rows
            ):
                rows.append(target)
                row_updates += 1
                changed = True
        if changed:
            save(path, record)
            file_updates += 1
    return file_updates, row_updates


def explicit_precision(value: str) -> str | None:
    upper = value.upper().replace("-", "_")
    compact = re.sub(r"[^A-Z0-9]", "", upper)
    match = re.search(r"(UD|AD)?IQ(\d)(XXS|XS|NL|S|M)", compact)
    if match:
        prefix = f"{match.group(1)}-" if match.group(1) else ""
        return f"{prefix}IQ{match.group(2)}_{match.group(3)}"
    match = re.search(r"(UD|AD)?Q(\d)K(XL|S|M|L|P)", compact)
    if match:
        prefix = f"{match.group(1)}-" if match.group(1) else ""
        return f"{prefix}Q{match.group(2)}_K_{match.group(3)}"
    match = re.search(r"PQ(\d)(\d)", compact)
    if match:
        return f"PQ{match.group(1)}_{match.group(2)}"
    match = re.search(r"(?<![A-Z])Q(\d)(\d)(?![A-Z0-9])", compact)
    if match:
        return f"Q{match.group(1)}_{match.group(2)}"
    patterns = (
        r"(?:MXFP4_MOE|MXFP4|NVFP4|ROCMFP4|BF16|FP16|FP8|W4A16|INT4)",
        r"(?:MLX_)?(?:2BIT|4BIT|8BIT)",
        r"(?:^|[^A-Z0-9])(Q8)(?:$|[^A-Z0-9])",
    )
    for pattern in patterns:
        match = re.search(pattern, upper)
        if match:
            value = match.group(1) if match.lastindex else match.group(0)
            return value.replace("MLX_", "MLX-").replace("_BIT", "bit")
    return None


VERIFIED_INSTANCE_PRECISIONS = {
    "mlx-community-nemotron-3-ultra-550b-a55b--unknown": "mixed-int4-int8-bf16",
}


def fill_instance_representation(captured_at: str) -> tuple[int, int]:
    format_updates = 0
    precision_updates = 0
    for path in sorted((REGISTRY / "model-instance").glob("*.json")):
        record = load(path)
        weights = record.get("weights")
        if not isinstance(weights, dict):
            continue
        evidence = " ".join(
            str(value or "")
            for value in (
                record.get("repository"),
                record.get("served_name"),
                weights.get("artifact"),
                record.get("id"),
            )
        )
        verified_precision = VERIFIED_INSTANCE_PRECISIONS.get(record.get("id"))
        precision = verified_precision or explicit_precision(evidence)
        source_url = str(
            record.get("url")
            or (
                f"https://huggingface.co/{record.get('repository')}"
                if isinstance(record.get("repository"), str)
                and record["repository"].count("/") == 1
                else REGISTRY_URL
            )
        )
        changed = False
        if weights.get("precision") in (None, "", "unknown") and precision:
            weights["precision"] = precision
            record.setdefault("facts", {})["weights.precision"] = known_fact(
                (
                    "published-mixed-precision-model-card"
                    if verified_precision
                    else "explicit-artifact-precision-label"
                ),
                captured_at,
                source_url,
            )
            precision_updates += 1
            changed = True
        if weights.get("format") in (None, ""):
            upper = evidence.upper()
            effective_precision = precision or explicit_precision(str(weights.get("precision") or ""))
            gguf_precision = isinstance(effective_precision, str) and bool(
                re.match(r"^(?:(?:UD|AD)-)?(?:IQ|Q|PQ)", effective_precision, re.IGNORECASE)
            )
            if ".GGUF" in upper or "-GGUF" in upper or "/GGUF" in upper or gguf_precision:
                weights["format"] = "GGUF"
                record.setdefault("facts", {})["weights.format"] = known_fact(
                    "explicit-gguf-artifact-or-quantization", captured_at, source_url
                )
                format_updates += 1
                changed = True
        if changed:
            save(path, record)
    return format_updates, precision_updates


CANONICAL_MODEL_REPOSITORIES = {
    "gemma-4-12b-q4km": "unsloth/gemma-4-12b-it-GGUF",
    "kimi-k2-5": "moonshotai/Kimi-K2.5",
    "gemma-4-31b-v2": "jdfelo/gemma-4-31B-v2-MLX-4bit",
    "qwen2-72b-instruct-q4km": "Qwen/Qwen2-72B-Instruct-GGUF",
    "diffusiongemma-26b-a4b": "google/diffusiongemma-26B-A4B-it",
    "llama-3-3-70b-instruct-q4km": "bartowski/Llama-3.3-70B-Instruct-GGUF",
    "holo-3-1-35b-a3b": "Hcompany/Holo-3.1-35B-A3B-GGUF",
    "nemotron-cascade-2-30b-a3b": "nvidia/Nemotron-Cascade-2-30B-A3B",
    "qwen3-32b": "Qwen/Qwen3-32B",
    "gemma-4-e4b": "google/gemma-4-E4B",
    "qwen2-5-72b-instruct-q4km": "Qwen/Qwen2.5-72B-Instruct-GGUF",
    "qwen2-5-7b": "Qwen/Qwen2.5-7B",
    "nvidia-nemotron-3-super-120b-a12b": "nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-BF16",
    "qwen3-5-35b-a3b": "Qwen/Qwen3.5-35B-A3B",
    "llama-3-1-nemotron-70b-q4km": "nvidia/Llama-3.1-Nemotron-70B-Instruct-HF",
    "bonsai-27b": "prism-ml/Bonsai-27B-gguf",
    "qwen3-235b-a22b-ud-q3kxl": "Qwen/Qwen3-235B-A22B",
    "qwen3-6-35b-a3b-ud-iq3xxs": "Qwen/Qwen3.6-35B-A3B",
    "qwen3-6-35b-a3b-ud-iq4xs": "Qwen/Qwen3.6-35B-A3B",
    "qwen3-6-35b-a3b-ud-iq2xxs": "Qwen/Qwen3.6-35B-A3B",
    "qwen3-8-27b-ud-q4km": "Qwen/Qwen3.8-27B",
    "nvidia-nemotron-3-5": "nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-BF16",
}


def fill_canonical_model_repositories(captured_at: str) -> int:
    updates = 0
    for model_id, repository in CANONICAL_MODEL_REPOSITORIES.items():
        path = REGISTRY / "model" / f"{model_id}.json"
        if not path.exists():
            continue
        record = load(path)
        identity = record.get("huggingface") or {}
        if identity.get("repository") not in (None, "", repository):
            continue
        if (
            identity.get("repository") == repository
            and identity.get("reason") == "hf-api-confirmed-public"
            and record.get("url") == identity.get("url")
        ):
            continue
        url = f"https://huggingface.co/{repository}"
        source = {
            "captured_at": captured_at,
            "kind": "huggingface-api",
            "url": f"https://huggingface.co/api/models/{repository}",
        }
        record["huggingface"] = {
            "repository": repository,
            "url": url,
            "status": "known",
            "link_type": "repository",
            "reason": "hf-api-confirmed-public",
            "provenance": {
                "captured_at": captured_at,
                "sources": [source],
            },
        }
        record["url"] = url
        record.setdefault("facts", {})["url"] = known_fact(
            "hf-api-confirmed-public", captured_at, source["url"]
        )
        save(path, record)
        updates += 1
    return updates


def fill_m1_memory_bandwidth(captured_at: str) -> int:
    updates = 0
    for identifier in ("apple-m1-8gb", "apple-m1-16gb"):
        path = REGISTRY / "hardware" / f"{identifier}.json"
        record = load(path)
        memory = record.get("memory")
        if not isinstance(memory, dict) or memory.get("bandwidth_gb_per_s") is not None:
            continue
        memory["bandwidth_gb_per_s"] = 68.25
        record.setdefault("facts", {})["memory.bandwidth_gb_per_s"] = {
            "state": "known",
            "reason": "published-m1-unified-memory-bandwidth",
            "provenance": {
                "captured_at": captured_at,
                "sources": [
                    {
                        "captured_at": captured_at,
                        "kind": "technical-publication",
                        "url": M1_BANDWIDTH_SOURCE,
                    }
                ],
            },
        }
        save(path, record)
        updates += 1
    return updates


def fill_exact_hardware_prices() -> int:
    updates = 0
    for path in sorted((REGISTRY / "hardware").glob("*.json")):
        record = load(path)
        commercial = record.get("commercial")
        if (
            not isinstance(commercial, dict)
            or commercial.get("exact_configuration_price") is not None
            or "exact_configuration_price" not in commercial
        ):
            continue
        prices = commercial.get("prices") or []
        products = record.get("product_names") or []
        gpu_cores = (record.get("accelerator") or {}).get("gpu_cores")
        memory_gb = (record.get("memory") or {}).get("vram_gb")
        if (
            len(prices) != 1
            or len(products) != 1
            or not isinstance(gpu_cores, int)
            or not isinstance(memory_gb, int)
        ):
            continue
        price = prices[0]
        configuration = str(price.get("configuration") or "")
        if not (
            re.search(rf"(?<!\d){gpu_cores}-core GPU\b", configuration, re.IGNORECASE)
            and re.search(rf"(?<!\d){memory_gb}\s*GB\b", configuration, re.IGNORECASE)
            and isinstance(price.get("amount"), (int, float))
            and isinstance(price.get("currency"), str)
            and isinstance(price.get("source"), dict)
        ):
            continue
        commercial["exact_configuration_price"] = {
            "amount": price["amount"],
            "currency": price["currency"],
        }
        captured_at = price.get("captured_at")
        record.setdefault("facts", {})["commercial.exact_configuration_price"] = {
            "state": "known",
            "reason": "exact-vendor-base-configuration-price",
            "provenance": {
                "captured_at": captured_at,
                "sources": [price["source"]],
            },
        }
        save(path, record)
        updates += 1
    return updates


def main() -> int:
    captured_at = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    organisations, variants = fill_benchmarks()
    descriptions = fill_recipes(captured_at)
    localmaxxing_recipes, localmaxxing_sweeps = correct_localmaxxing_concurrency_semantics(captured_at)
    sweeps = fill_sweep_metrics()
    sweep_engine_versions = fill_sweep_engine_versions()
    per_stream_files, per_stream_rows = fill_per_stream_decode()
    source_paths, engine_versions, graph_modes = fill_localmaxxing_sources_and_runtime(captured_at)
    price_files, zero_quantities = fill_out_of_stock_quantities()
    ttft_files, ttft_rows = repair_postgres_ttft()
    formats, precisions = fill_instance_representation(captured_at)
    canonical_repositories = fill_canonical_model_repositories(captured_at)
    m1_bandwidth = fill_m1_memory_bandwidth(captured_at)
    exact_hardware_prices = fill_exact_hardware_prices()
    print(
        f"benchmark organisations: {organisations}; variants: {variants}; "
        f"recipe descriptions: {descriptions}; "
        f"LocalMaxxing concurrency recipes: {localmaxxing_recipes}; sweeps: {localmaxxing_sweeps}; "
        f"sweep files: {sweeps}; sweep engine versions: {sweep_engine_versions}; "
        f"per-stream files: {per_stream_files}; rows: {per_stream_rows}; "
        f"source paths: {source_paths}; engine versions: {engine_versions}; graph modes: {graph_modes}; "
        f"price files: {price_files}; zero quantities: {zero_quantities}; "
        f"Postgres TTFT files: {ttft_files}; rows: {ttft_rows}; "
        f"weight formats: {formats}; precisions: {precisions}; "
        f"canonical model repositories: {canonical_repositories}; "
        f"M1 memory bandwidth: {m1_bandwidth}; exact hardware prices: {exact_hardware_prices}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
