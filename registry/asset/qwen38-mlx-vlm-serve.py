#!/usr/bin/env python3
"""Run pinned MLX-VLM with allocation guidance and a final-prefill cache audit.

All arguments pass through to mlx_vlm.server.cli.main(). The default MLX
allocation guideline is min(27 GiB, the device's recommended working set),
with a 256 MiB allocator cache. QWEN38_MEMORY_LIMIT_GIB can lower or override
the guideline, but must be positive and no larger than that working set.
MLX's allocation guideline is not a hard process/RSS limit or a no-swap guard.

JSON audit lines contain only runtime/device metadata and cache dimensions,
never prompts, token IDs, tensor contents, environment dumps, or local paths.
"""

from __future__ import annotations

import functools
import importlib.metadata
import json
import math
import os
import re
import sys
from collections import Counter

GIB = 1024**3
MIB = 1024**2
RUNTIME_VERSION = "0.7.3"
RUNTIME_REVISION = "573562df9fd9259047e3dc793e6b48be23389221"
MEMORY_ENV = "QWEN38_MEMORY_LIMIT_GIB"


def emit(record):
    print(json.dumps(record, sort_keys=True, allow_nan=False), file=sys.stderr, flush=True)


def runtime_metadata():
    versions = {}
    for name in (
        "mlx-vlm", "mlx", "mlx-metal", "mlx-lm", "transformers",
        "tokenizers", "huggingface-hub", "numpy", "safetensors",
    ):
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    if versions["mlx-vlm"] != RUNTIME_VERSION:
        raise RuntimeError(f"This wrapper requires mlx-vlm=={RUNTIME_VERSION}.")
    direct = importlib.metadata.distribution("mlx-vlm").read_text("direct_url.json")
    commit = json.loads(direct or "{}").get("vcs_info", {}).get("commit_id")
    if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise RuntimeError("Install MLX-VLM from the pinned Git commit in the runtime lock.")
    if commit != RUNTIME_REVISION:
        raise RuntimeError("MLX-VLM source commit differs from the pinned runtime.")
    return {"distributions": versions, "mlx_vlm_source_revision": commit}


def memory_limit_bytes(recommended, override):
    if not isinstance(recommended, int) or recommended <= 0:
        raise RuntimeError("A positive Metal recommended working set is required.")
    if override is None:
        return min(27 * GIB, recommended)
    try:
        gib = float(override)
    except (TypeError, ValueError):
        raise ValueError(f"{MEMORY_ENV} must be a positive number.") from None
    if not math.isfinite(gib) or gib <= 0 or gib * GIB > recommended:
        raise ValueError(f"{MEMORY_ENV} must be positive and within the recommended working set.")
    limit = int(gib * GIB)
    if limit < 1:
        raise ValueError(f"{MEMORY_ENV} must specify at least one byte.")
    return limit


def configure_memory(mx):
    info = mx.device_info()
    recommended = info.get("max_recommended_working_set_size")
    memory_limit = memory_limit_bytes(recommended, os.environ.get(MEMORY_ENV))
    cache_limit = min(256 * MIB, memory_limit)
    mx.set_memory_limit(memory_limit)
    mx.set_cache_limit(cache_limit)
    return {
        "device": {
            name: info.get(name) for name in (
                "device_name", "architecture", "memory_size",
                "max_recommended_working_set_size", "max_buffer_length",
            )
        },
        "mlx_memory_limit_bytes": memory_limit,
        "mlx_allocator_cache_limit_bytes": cache_limit,
        "mlx_memory_limit_is_hard_process_cap": False,
    }


def _offset_list(value):
    if value is None:
        return None
    result = value.tolist() if hasattr(value, "tolist") else value
    return [int(v) for v in result] if isinstance(result, list) else [int(result)]


def _cache_bytes_metadata(cache):
    # Some runtime cache classes inherit an unimplemented nbytes property.
    # Do not fall back to cache.state: obtaining it may slice/copy tensors.
    try:
        value = cache.nbytes
    except (AttributeError, NotImplementedError):
        return None, "nbytes_not_supported"
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        return None, "nbytes_not_a_nonnegative_integer"
    return value, None


def prefill_audit(processing, generated, mx):
    """Read final-prefill metadata; do not copy or change any cache tensor."""
    prompt_tokens = [int(n) for n in processing._prompt_tokens_per_row]
    cached_tokens = [int(n) for n in processing._cached_tokens_per_row]
    caches = generated.prompt_cache
    layers = getattr(getattr(processing.model, "model", None), "layers", [])
    model_type = getattr(processing.model, "model_type", None)
    mapped = (
        model_type in ("qwen3_5", "qwen3_5_text")
        and len(layers) == len(caches)
        and bool(layers)
        and all(isinstance(getattr(layer, "is_linear", None), bool) for layer in layers)
    )
    validate = mapped and len(prompt_tokens) == 1
    rows, errors, verified_attention_layers = [], [], []
    for index, cache in enumerate(caches):
        kind = type(cache).__name__
        is_linear = layers[index].is_linear if mapped else None
        retained = getattr(cache, "_idx", None)
        offsets = _offset_list(getattr(cache, "offset", None))
        if retained is None and offsets is not None and len(offsets) == 1:
            retained = offsets[0]
        cache_bytes, cache_bytes_reason = _cache_bytes_metadata(cache)
        row = {
            "layer": index, "cache_class": kind, "is_linear": is_linear,
            "retained_tokens": int(retained) if retained is not None else None,
            "offset": offsets, "bits": getattr(cache, "bits", None),
            "key_bits": getattr(cache, "key_bits", None),
            "value_bits": getattr(cache, "value_bits", None),
            "cache_bytes": cache_bytes,
            "cache_bytes_unavailable_reason": cache_bytes_reason,
        }
        rows.append(row)
        if validate and not is_linear:
            errors_before = len(errors)
            if "Rotating" in kind or getattr(cache, "max_size", None) is not None:
                errors.append(f"layer {index}: rotating/windowed attention cache")
            if row["retained_tokens"] != prompt_tokens[0] or offsets != prompt_tokens:
                errors.append(f"layer {index}: retained cache does not match prompt length")
            if len(errors) == errors_before:
                verified_attention_layers.append(index)
    hidden = getattr(generated, "hidden", None)
    record = {
        "event": "qwen38_prefill_audit", "schema_version": 1,
        "prompt_tokens_per_row": prompt_tokens,
        "cached_tokens_per_row": cached_tokens,
        "prefill_processed_columns": int(processing._processed_prompt_columns),
        "hidden_shape": list(hidden.shape) if hidden is not None else None,
        "cache_class_counts": dict(Counter(row["cache_class"] for row in rows)),
        "cache_bytes": sum(row["cache_bytes"] for row in rows if row["cache_bytes"] is not None),
        "cache_bytes_is_partial": any(row["cache_bytes"] is None for row in rows),
        "cache_bytes_unknown_layers": [row["layer"] for row in rows if row["cache_bytes"] is None],
        "layers": rows,
        "single_row_qwen_mapping_verified": validate,
        "full_attention_cache_retained": not errors if validate else None,
        "full_attention_layers_verified": verified_attention_layers,
        "errors": errors,
        "mlx_active_bytes": mx.get_active_memory(),
        "mlx_peak_bytes": mx.get_peak_memory(),
        "mlx_allocator_cache_bytes": mx.get_cache_memory(),
    }
    return record


def install_cache_audit(mx):
    from mlx_vlm.generate.ar import PromptProcessingBatch

    original = PromptProcessingBatch.generate
    if getattr(original, "_qwen38_audited", False):
        return

    @functools.wraps(original)
    def audited_generate(self, *args, **kwargs):
        generated = original(self, *args, **kwargs)
        record = prefill_audit(self, generated, mx)
        emit(record)
        if record["errors"]:
            raise RuntimeError("Qwen3.8 final-prefill cache retention audit failed.")
        return generated

    audited_generate._qwen38_audited = True
    PromptProcessingBatch.generate = audited_generate


def main():
    # Uvicorn reload creates another process without this instrumentation.
    if "--reload" in sys.argv[1:]:
        raise ValueError("--reload is incompatible with the cache-audited wrapper.")
    metadata = runtime_metadata()
    import mlx.core as mx

    if not mx.metal.is_available():
        raise RuntimeError("This recipe requires an Apple Silicon Metal device.")
    metadata.update(configure_memory(mx))
    metadata.update(event="qwen38_runtime_startup", schema_version=1)
    emit(metadata)
    install_cache_audit(mx)
    from mlx_vlm.server.cli import main as server_main

    server_main()


if __name__ == "__main__":
    main()
