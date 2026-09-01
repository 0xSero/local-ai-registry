#!/usr/bin/env python3
"""Enrich registry records from exact Hugging Face repository metadata.

The script uses repository revisions, resolved configs, and blob metadata. It
classifies only explicit causal-language-model configs, never treats missing
MoE markers as dense evidence, and selects one logical weight artifact before
summing its files.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import json
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "registry"
API = (
    "https://huggingface.co/api/models/{repo}?blobs=true"
    "&expand%5B%5D=sha&expand%5B%5D=config&expand%5B%5D=downloads"
    "&expand%5B%5D=downloadsAllTime&expand%5B%5D=safetensors"
)
API_REVISION = "https://huggingface.co/api/models/{repo}/revision/{revision}?blobs=true"
RESOLVE = "https://huggingface.co/{repo}/resolve/{revision}/config.json"
CONTEXT = ssl.create_default_context()
WEIGHT_SUFFIXES = (".safetensors", ".gguf", ".bin", ".pt", ".pth")


def local_huggingface_token() -> str | None:
    try:
        from huggingface_hub import get_token
    except ImportError:
        return None
    return get_token()


HF_TOKEN = local_huggingface_token()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n")


def valid_repo(value: Any) -> bool:
    return (
        isinstance(value, str)
        and value.count("/") == 1
        and not value.startswith(("local/", "http://", "https://"))
    )


def model_repository_work() -> dict[str, bool]:
    result: dict[str, bool] = {}
    for path in (REGISTRY / "model").glob("*.json"):
        row = read_json(path)
        repo = (row.get("huggingface") or {}).get("repository")
        if valid_repo(repo):
            result[repo] = False
    return result



def model_config_work() -> dict[str, bool]:
    result: dict[str, bool] = {}
    for path in (REGISTRY / "model").glob("*.json"):
        row = read_json(path)
        repo = (row.get("huggingface") or {}).get("repository")
        if not valid_repo(repo):
            continue
        architecture_fact = (row.get("facts") or {}).get("architecture")
        architecture_proven = (
            isinstance(architecture_fact, dict)
            and architecture_fact.get("reason") == "resolved-huggingface-config"
        )
        if (
            row.get("architecture") not in ("dense", "moe")
            or not architecture_proven
            or (row.get("active_params") is None and row.get("architecture") == "dense")
        ):
            result[repo] = True
    return result

def instance_repository_work() -> dict[str, bool]:
    result: dict[str, bool] = {}
    for path in (REGISTRY / "model-instance").glob("*.json"):
        row = read_json(path)
        repo = (row.get("huggingface") or {}).get("repository") or row.get("repository")
        weights = row.get("weights") or {}
        size_fact = (row.get("facts") or {}).get("weights.size_gb") or {}
        if valid_repo(repo) and (
            row.get("revision") in (None, "")
            or weights.get("size_gb") is None
            or str(size_fact.get("reason") or "").startswith("huggingface")
            or weights.get("format") in (None, "")
            or weights.get("precision") in (None, "", "unknown")
        ):
            result[repo] = False
    return result


def repository_work() -> dict[str, bool]:
    result: dict[str, bool] = {}
    for path in (REGISTRY / "model").glob("*.json"):
        row = read_json(path)
        repo = (row.get("huggingface") or {}).get("repository")
        if not valid_repo(repo):
            continue
        architecture_fact = (row.get("facts") or {}).get("architecture")
        architecture_proven = (
            isinstance(architecture_fact, dict)
            and architecture_fact.get("reason") == "resolved-huggingface-config"
        )
        needs_config = (
            row.get("architecture") not in ("dense", "moe")
            or not architecture_proven
            or (row.get("active_params") is None and row.get("architecture") == "dense")
        )
        result[repo] = needs_config
    for repo in instance_repository_work():
        result.setdefault(repo, False)
    return result


def request_json(url: str, attempts: int = 5) -> dict[str, Any] | None:
    headers = {"User-Agent": "local-ai-registry/1.0"}
    if HF_TOKEN:
        headers["Authorization"] = f"Bearer {HF_TOKEN}"
    request = urllib.request.Request(url, headers=headers)
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(request, timeout=45, context=CONTEXT) as response:
                payload = json.load(response)
                return payload if isinstance(payload, dict) else None
        except urllib.error.HTTPError as error:
            if error.code in (401, 403, 404):
                return None
            if error.code != 429 or attempt == attempts - 1:
                raise
            delay = int(error.headers.get("Retry-After", "0") or 0) or 2**attempt
            time.sleep(min(delay, 60))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            if attempt == attempts - 1:
                raise
            time.sleep(2**attempt)
    return None


def fetch(item: tuple[str, bool]) -> tuple[str, dict[str, Any] | None, str | None]:
    repo, want_config = item
    api_url = API.format(repo=urllib.parse.quote(repo, safe="/"))
    try:
        payload = request_json(api_url)
        if payload is None:
            return repo, None, "repository unavailable"
        if want_config:
            revision = payload.get("sha") or "main"
            config_url = RESOLVE.format(
                repo=urllib.parse.quote(repo, safe="/"),
                revision=urllib.parse.quote(str(revision), safe=""),
            )
            try:
                config = request_json(config_url, attempts=3)
            except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as error:
                config = None
                payload["_config_error"] = str(error)
            if config is not None:
                payload["_resolved_config"] = config
        return repo, payload, None
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        return repo, None, str(error)


def fetch_revision_payload(repo: str, revision: str) -> tuple[dict[str, Any] | None, str]:
    url = API_REVISION.format(
        repo=urllib.parse.quote(repo, safe="/"),
        revision=urllib.parse.quote(revision, safe=""),
    )
    try:
        payload = request_json(url)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None, url
    resolved = payload.get("sha") if payload is not None else None
    exact = resolved == revision
    immutable_prefix = (
        isinstance(resolved, str)
        and len(revision) >= 7
        and re.fullmatch(r"[0-9a-f]+", revision) is not None
        and resolved.startswith(revision)
    )
    if payload is None or not (exact or immutable_prefix):
        return None, url
    return payload, url


def known_fact(reason: str, url: str, captured_at: str) -> dict[str, Any]:
    return {
        "provenance": {
            "captured_at": captured_at,
            "sources": [{"captured_at": captured_at, "kind": "huggingface-api", "url": url}],
        },
        "reason": reason,
        "state": "known",
    }


def unknown_fact(reason: str, url: str, captured_at: str) -> dict[str, Any]:
    return {
        "provenance": {
            "captured_at": captured_at,
            "sources": [{"captured_at": captured_at, "kind": "huggingface-api", "url": url}],
        },
        "reason": reason,
        "state": "unknown",
    }


def normalized(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())

def precision_tokens(value: Any) -> tuple[str, ...]:
    key = normalized(str(value or ""))
    tokens = [key] if key and key != "unknown" else []
    if key.startswith("gguf"):
        tokens.append(key[4:])
    if key.startswith("unslothdynamic"):
        tokens.append(f"ud{key[len('unslothdynamic'):]}")
    if "nvfp4" in key:
        tokens.append("nvfp4")
    return tuple(dict.fromkeys(token for token in tokens if token))


def config_for(payload: dict[str, Any]) -> dict[str, Any]:
    resolved = payload.get("_resolved_config")
    if isinstance(resolved, dict):
        return resolved
    compact = payload.get("config")
    return compact if isinstance(compact, dict) else {}


def config_pairs(value: Any, prefix: str = "") -> list[tuple[str, Any]]:
    result: list[tuple[str, Any]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            result.append((path.lower(), child))
            result.extend(config_pairs(child, path))
    elif isinstance(value, list):
        for child in value:
            result.extend(config_pairs(child, prefix))
    return result
DENSE_GENERATIVE_CONDITIONAL_CLASSES = {
    "ChatGLMModel",
    "Gemma3ForConditionalGeneration",
    "Gemma3nForConditionalGeneration",
    "Mistral3ForConditionalGeneration",
    "PaliGemmaForConditionalGeneration",
    "Qwen2_5_VLForConditionalGeneration",
    "Qwen2VLForConditionalGeneration",
    "FastConformerModel",
    "GraniteSpeechForConditionalGeneration",
    "GraniteSpeechNarForASR",
    "GraniteSpeechPlusForConditionalGeneration",
    "MoonshineForConditionalGeneration",
    "NVLM_D",
    "Nemotron3_5AsrForRNNT",
    "NemotronAsrStreamingForRNNT",
    "ParakeetForCTC",
    "ParakeetForRNNT",
    "ParakeetForTDT",
    "Qwen2ForSequenceClassification",
    "Qwen2_5OmniModel",
    "Qwen3ASRForConditionalGeneration",
    "T5Gemma2ForConditionalGeneration",
    "VoxtralForConditionalGeneration",
    "VoxtralRealtimeForConditionalGeneration",
    "Wav2Vec2BertModel",
    "Wav2Vec2ForCTC",
    "WhisperForConditionalGeneration",
}




def architecture(payload: dict[str, Any]) -> str | None:
    config = config_for(payload)
    classes = config.get("architectures")
    class_names = [item for item in classes or [] if isinstance(item, str)] if isinstance(classes, list) else []
    labels = class_names[:]
    if isinstance(config.get("model_type"), str):
        labels.append(config["model_type"])
    normalized_labels = [normalized(item) for item in labels]
    explicit_markers = ("moe", "mixtureofexperts", "mixtral", "deepseekv2", "deepseekv3")
    if any(marker in label for label in normalized_labels for marker in explicit_markers):
        return "moe"
    vision_config = config.get("vision_config")
    llm_config = config.get("llm_config")
    if (
        config.get("model_type") == "internvl_chat"
        and isinstance(vision_config, dict)
        and vision_config.get("use_moe") is False
        and isinstance(llm_config, dict)
        and llm_config.get("moe_config") is None
    ):
        return "dense"


    expert_evidence = False
    for key, value in config_pairs(config):
        leaf = key.rsplit(".", 1)[-1]
        if "expert" not in leaf and "moe" not in leaf:
            continue
        if isinstance(value, bool):
            expert_evidence = expert_evidence or value
        elif isinstance(value, (int, float)):
            if "num_experts_per_tok" in leaf or "experts_per_token" in leaf:
                expert_evidence = expert_evidence or value > 0
            else:
                expert_evidence = expert_evidence or value > 1
        elif isinstance(value, (list, dict)):
            expert_evidence = expert_evidence or bool(value)
        elif isinstance(value, str):
            expert_evidence = expert_evidence or value.lower() not in ("", "none", "false", "disabled")
    if expert_evidence:
        return "moe"
    if class_names and all(
        name.endswith("ForCausalLM") or name == "QWenLMHeadModel"
        for name in class_names
    ):
        return "dense"
    if class_names and set(class_names).issubset(
        DENSE_GENERATIVE_CONDITIONAL_CLASSES
    ):
        return "dense"
    if (
        config.get("model_type") == "moonshine_streaming"
        and isinstance(config.get("hidden_size"), (int, float))
        and config["hidden_size"] > 0
        and isinstance(config.get("intermediate_size"), (int, float))
        and config["intermediate_size"] > 0
    ):
        return "dense"
    resolved = payload.get("_resolved_config")
    text_config = config.get("text_config")
    if (
        class_names == ["Qwen3_5ForConditionalGeneration"]
        and isinstance(resolved, dict)
        and isinstance(text_config, dict)
        and text_config.get("model_type") == "qwen3_5_text"
        and isinstance(text_config.get("intermediate_size"), (int, float))
        and text_config["intermediate_size"] > 0
    ):
        return "dense"
    if (
        isinstance(resolved, dict)
        and config.get("model_type") == "gemma4"
        and isinstance(text_config, dict)
        and text_config.get("model_type") == "gemma4_text"
        and text_config.get("enable_moe_block") is False
        and text_config.get("num_experts") is None
    ):
        return "dense"
    return None
def all_parameters_active_in_dense_model(payload: dict[str, Any]) -> bool:
    config = config_for(payload)
    classes = config.get("architectures")
    class_names = (
        [item for item in classes or [] if isinstance(item, str)]
        if isinstance(classes, list)
        else []
    )
    if class_names and all(
        name.endswith("ForCausalLM") or name == "QWenLMHeadModel"
        for name in class_names
    ):
        return True
    return (
        class_names == ["Qwen3_5ForConditionalGeneration"]
        and architecture(payload) == "dense"
    )




FAMILY_PREFIXES = (
    ("deepseek-r1", "deepseek-r1"),
    ("deepseek", "deepseek"),
    ("nvidia-nemotron", "nemotron"),
    ("openreasoning-nemotron", "nemotron"),
    ("nemotron", "nemotron"),
    ("glm", "glm"),
    ("qwen", "qwen"),
    ("gemma", "gemma"),
    ("medgemma", "medgemma"),
    ("internvl", "internvl"),
    ("llama", "llama"),
    ("mistral", "mistral"),
    ("ministral", "ministral"),
    ("ornith", "ornith"),
    ("kimi", "kimi"),
    ("ling", "ling"),
    ("lfm", "lfm"),
    ("liquid", "lfm"),
    ("granite", "granite"),
    ("olmo", "olmo"),
    ("hunyuan", "hunyuan"),
    ("hy-mt", "hunyuan"),
    ("mimo", "mimo"),
    ("laguna", "laguna"),
    ("holo", "holo"),
    ("agents", "agents"),
    ("ui-tars", "ui-tars"),
    ("seed", "seed"),
    ("muse", "muse"),
    ("unlimited-ocr", "unlimited-ocr"),
)


def model_family(name: str) -> str | None:
    lower = name.lower()
    for prefix, family in FAMILY_PREFIXES:
        if lower.startswith(prefix) or f"/{prefix}" in lower:
            return family
    return None


def named_active_params(name: str) -> float | None:
    match = re.search(r"(?:^|[-_])a(\d+(?:\.\d+)?)b(?:$|[-_])", name.lower())
    return float(match.group(1)) if match else None
def named_total_params(name: str) -> float | None:
    values = re.findall(
        r"(?<![a-z0-9])(\d+(?:\.\d+)?)b(?:$|[^a-z0-9])",
        name.lower(),
    )
    return float(values[0]) if len(values) == 1 else None


def params_look_packed(row: dict[str, Any]) -> bool:
    named_total = named_total_params(row.get("name") or "")
    params = row.get("params")
    if not isinstance(named_total, float) or not isinstance(params, (int, float)):
        return False
    if params >= named_total * 0.8:
        return False
    identity = " ".join(
        (
            row.get("name") or "",
            (row.get("huggingface") or {}).get("repository") or "",
        )
    ).lower()
    quantized = any(
        marker in identity
        for marker in (
            "2bit",
            "4bit",
            "8bit",
            "awq",
            "gguf",
            "gptq",
            "int4",
            "mlx",
            "mxfp4",
            "nvfp4",
        )
    )
    return quantized or params < named_total * 0.01




def parameter_billions(payload: dict[str, Any] | None) -> float | int | None:
    if not payload:
        return None
    total = (payload.get("safetensors") or {}).get("total")
    if not isinstance(total, int) or total <= 0:
        return None
    billions = total / 1_000_000_000
    value = round(billions, 2) if total < 10_000_000_000 else round(billions)
    return round(billions, 3) if value <= 0 else value


def blob_size(blob: dict[str, Any]) -> int | None:
    lfs = blob.get("lfs")
    if isinstance(lfs, dict) and isinstance(lfs.get("size"), int):
        return lfs["size"]
    return blob.get("size") if isinstance(blob.get("size"), int) else None


def weight_files(payload: dict[str, Any]) -> list[tuple[str, int]]:
    result: list[tuple[str, int]] = []
    for blob in payload.get("siblings") or []:
        if not isinstance(blob, dict) or not isinstance(blob.get("rfilename"), str):
            continue
        size = blob_size(blob)
        name = blob["rfilename"]
        if size is not None and name.lower().endswith(WEIGHT_SUFFIXES):
            result.append((name, size))
    return result


def artifact_relative(repo: str, artifact: Any) -> str | None:
    if not isinstance(artifact, str) or not artifact:
        return None
    artifact = artifact.split("++", 1)[0]
    prefix = f"{repo}/"
    return artifact[len(prefix):] if artifact.startswith(prefix) else artifact


def representation_supported(
    payload: dict[str, Any], repo: str, weights: dict[str, Any]
) -> bool:
    fmt = normalized(str(weights.get("format") or ""))
    precision = normalized(str(weights.get("precision") or ""))
    requested = f"{fmt} {precision}"
    library = str(payload.get("library_name") or payload.get("libraryName") or "")
    evidence = normalized(
        " ".join(
            (
                repo,
                library,
                json.dumps(payload.get("tags") or []),
                json.dumps(config_for(payload), sort_keys=True),
                json.dumps(payload.get("safetensors") or {}, sort_keys=True),
            )
        )
    )

    if "mlx" in requested:
        return "mlx" in normalized(f"{repo} {library} {' '.join(payload.get('tags') or [])}")

    quant = re.search(r"(?:iq|mq|pq)\d", requested)
    if quant:
        return quant.group(0) in evidence
    low_bit = re.search(r"(?<!\d)([123])bit", requested)
    if low_bit:
        bit = low_bit.group(1)
        return f"{bit}bit" in evidence or f"bits{bit}" in evidence

    checks = (
        (("autoround",), ("autoround",)),
        (("gptq",), ("gptq",)),
        (("awq",), ("awq",)),
        (("exl3",), ("exl3",)),
        (("exl2",), ("exl2",)),
        (("modelopt",), ("modelopt",)),
        (("compressedtensors",), ("compressedtensors",)),
        (("jangtq",), ("jangtq",)),
        (("mixed",), ("mixed",)),
        (("rocmfp4", "rocmfpx"), ("rocmfp4", "rocmfpx")),
        (("nvfp4",), ("nvfp4",)),
        (("mxfp4",), ("mxfp4",)),
        (("int4", "4bit", "w4a16"), ("int4", "4bit", "bits4", "w4a16")),
        (("int8", "8bit", "w8a16"), ("int8", "8bit", "bits8", "w8a16")),
        (("fp8",), ("fp8",)),
        (("fp4",), ("fp4",)),
        (("bf16", "bfloat16"), ("bf16", "bfloat16")),
        (("fp16", "float16"), ("fp16", "float16")),
        (("fp32", "float32"), ("fp32", "float32")),
    )
    for markers, aliases in checks:
        if any(marker in requested for marker in markers):
            return any(alias in evidence for alias in aliases)

    generic_formats = {"", "unknown", "safetensors", "pytorch", "bin", "pt"}
    generic_precisions = generic_formats | {"auto", "native"}
    return fmt in generic_formats and precision in generic_precisions


def logical_artifact(
    payload: dict[str, Any],
    files: list[tuple[str, int]],
    repo: str,
    weights: dict[str, Any],
) -> list[tuple[str, int]]:
    artifact = artifact_relative(repo, weights.get("artifact"))
    if artifact:
        exact = [(name, size) for name, size in files if name == artifact]
        if exact:
            shard = re.match(r"^(.*)-\d{5}-of-(\d{5})(\.[^.]+)$", artifact)
            if not shard:
                return exact
            pattern = re.compile(
                rf"^{re.escape(shard.group(1))}-\d{{5}}-of-{re.escape(shard.group(2))}{re.escape(shard.group(3))}$"
            )
            selected = [(name, size) for name, size in files if pattern.match(name)]
            return selected if len(selected) == int(shard.group(2)) else []
        if not artifact.lower().endswith(WEIGHT_SUFFIXES):
            gguf_stems = [
                (name, size, name[:-5].casefold())
                for name, size in files
                if name.lower().endswith(".gguf")
            ]
            artifact_key = artifact.casefold()
            extensionless = [
                (name, size)
                for name, size, stem in gguf_stems
                if stem == artifact_key
            ]
            if len(extensionless) == 1:
                return extensionless
            suffixed = [
                (name, size)
                for name, size, stem in gguf_stems
                if artifact_key.startswith(f"{stem}-")
            ]
            if len(suffixed) == 1:
                return suffixed


    fmt = normalized(str(weights.get("format") or ""))
    precision_keys = precision_tokens(weights.get("precision"))
    evidence = " ".join(
        (repo, str(weights.get("format") or ""), str(weights.get("precision") or ""), str(artifact or ""))
    ).lower()
    gguf_quant = bool(
        re.search(r"(?:^|[^a-z0-9])(?:(?:ud|ad)[-_]?)?(?:iq|mq|q|pq)\d", evidence)
    )
    explicit_non_gguf = fmt in {"autoround", "mlx", "modelopt", "safetensors"}
    if not explicit_non_gguf and ("gguf" in evidence or gguf_quant):
        candidates = [(name, size) for name, size in files if name.lower().endswith(".gguf")]
        precision_matched = False
        if precision_keys:
            matched = [
                (name, size)
                for name, size in candidates
                if any(key in normalized(name) for key in precision_keys)
            ]
            if not matched:
                return []
            candidates = matched
            precision_matched = True
        if len(candidates) == 1:
            return candidates
        groups: dict[tuple[str, str, str], list[tuple[str, int]]] = {}
        for name, size in candidates:
            shard = re.match(r"^(.*)-\d{5}-of-(\d{5})(\.gguf)$", name, re.IGNORECASE)
            if shard:
                groups.setdefault((shard.group(1), shard.group(2), shard.group(3)), []).append((name, size))
        complete = [group for key, group in groups.items() if len(group) == int(key[1])]
        if len(complete) == 1:
            return complete[0]
        if precision_matched and not groups and candidates and len({size for _, size in candidates}) == 1:
            return candidates[:1]
        return []
    if fmt == "safetensors" and gguf_quant:
        return []


    safetensors = [(name, size) for name, size in files if name.lower().endswith(".safetensors")]
    if safetensors and representation_supported(payload, repo, weights):
        return safetensors
    if fmt in {"pytorch", "bin", "pt"}:
        return [(name, size) for name, size in files if name.lower().endswith((".bin", ".pt", ".pth"))]
    return []


def inferred_format(payload: dict[str, Any], repo: str, row: dict[str, Any]) -> str | None:
    names = [name.lower() for name, _ in weight_files(payload)]
    evidence = " ".join((repo, str(row.get("served_name") or ""), str((row.get("weights") or {}).get("artifact") or ""))).lower()
    if any(name.endswith(".gguf") for name in names) and ("gguf" in evidence or ".gguf" in evidence):
        return "GGUF"
    if repo.lower().startswith("mlx-community/") or "-mlx" in evidence:
        return "MLX"
    if names and all(name.endswith(".safetensors") for name in names):
        return "safetensors"
    if names and all(name.endswith((".bin", ".pt", ".pth")) for name in names):
        return "PyTorch"
    return None


def inferred_precision(payload: dict[str, Any]) -> str | None:
    config = config_for(payload)
    quant = config.get("quantization_config")
    if isinstance(quant, dict):
        method = str(quant.get("quant_method") or "").lower()
        bits = quant.get("bits")
        if method in ("fp8", "nvfp4", "mxfp4"):
            return method.upper()
        if method in ("awq", "gptq") and isinstance(bits, int):
            return f"{method.upper()}-{bits}bit"
    dtype = config.get("torch_dtype") or config.get("dtype")
    mapping = {
        "bfloat16": "BF16",
        "float16": "FP16",
        "float32": "FP32",
    }
    return mapping.get(str(dtype).lower())


def clear_unverified_dense_active_params() -> int:
    updates = 0
    for path in sorted((REGISTRY / "model").glob("*.json")):
        row = read_json(path)
        facts = row.get("facts") or {}
        active_fact = facts.get("active_params")
        architecture_fact = facts.get("architecture")
        verified_dense = (
            row.get("architecture") == "dense"
            and isinstance(architecture_fact, dict)
            and architecture_fact.get("reason")
            in (
                "immutable-model-card-architecture-description",
                "resolved-huggingface-config",
                "exact-huggingface-base-model-lineage",
            )
        )
        if (
            isinstance(active_fact, dict)
            and active_fact.get("reason") == "all-parameters-active-in-dense-model"
            and (not verified_dense or params_look_packed(row))
        ):
            row["active_params"] = None
            row["facts"].pop("active_params", None)
            write_json(path, row)
            updates += 1
    return updates


def restore_proven_dense_active_params() -> int:
    updates = 0
    for path in sorted((REGISTRY / "model").glob("*.json")):
        row = read_json(path)
        architecture_fact = (row.get("facts") or {}).get("architecture")
        if (
            row.get("active_params") is None
            and row.get("architecture") == "dense"
            and not params_look_packed(row)
            and isinstance(row.get("params"), (int, float))
            and isinstance(architecture_fact, dict)
            and architecture_fact.get("reason")
            in (
                "immutable-model-card-architecture-description",
                "resolved-huggingface-config",
                "exact-huggingface-base-model-lineage",
            )
        ):
            row["active_params"] = row["params"]
            row.setdefault("facts", {})["active_params"] = {
                "provenance": architecture_fact["provenance"],
                "reason": "all-parameters-active-in-dense-model",
                "state": "known",
            }
            write_json(path, row)
            updates += 1
    return updates


def update_models(metadata: dict[str, dict[str, Any]], captured_at: str) -> dict[str, int]:
    counts = {
        "params": 0,
        "architectures": 0,
        "architecture_corrections": 0,
        "active_params": 0,
        "families": 0,
        "downloads_last_30d": 0,
        "downloads_all_time": 0,
    }
    for path in sorted((REGISTRY / "model").glob("*.json")):
        row = read_json(path)
        repo = (row.get("huggingface") or {}).get("repository")
        payload = metadata.get(repo) if isinstance(repo, str) else None
        api_url = API.format(repo=repo) if isinstance(repo, str) else "https://huggingface.co"
        changed = False

        family = model_family(row.get("name") or "")
        if row.get("family") in (None, "", "unknown") and family:
            row["family"] = family
            row.setdefault("facts", {})["family"] = known_fact("canonical-model-name-family", api_url, captured_at)
            counts["families"] += 1
            changed = True

        params = parameter_billions(payload)
        if params is not None:
            parameter_fact = known_fact(
                "safetensors-parameter-metadata", api_url, captured_at
            )
            if row.get("params") != params:
                row["params"] = params
                active_fact = (row.get("facts") or {}).get("active_params")
                if (
                    row.get("architecture") == "dense"
                    and not params_look_packed(row)
                    and isinstance(active_fact, dict)
                    and active_fact.get("reason") == "all-parameters-active-in-dense-model"
                ):
                    row["active_params"] = params
                    row.setdefault("facts", {})["active_params"] = known_fact(
                        "all-parameters-active-in-dense-model", api_url, captured_at
                    )
                counts["params"] += 1
                changed = True
            existing_parameter_fact = (row.get("facts") or {}).get("params")
            if (
                not isinstance(existing_parameter_fact, dict)
                or existing_parameter_fact.get("reason") != "safetensors-parameter-metadata"
            ):
                row.setdefault("facts", {})["params"] = parameter_fact
                changed = True
            provenance = row.setdefault(
                "provenance",
                {"captured_at": captured_at, "sources": []},
            )
            provenance_sources = provenance.setdefault("sources", [])
            parameter_source = parameter_fact["provenance"]["sources"][0]
            if not any(
                source.get("kind") == parameter_source["kind"]
                and source.get("url") == parameter_source["url"]
                for source in provenance_sources
                if isinstance(source, dict)
            ):
                provenance_sources.append(parameter_source)
                changed = True

        named_active = named_active_params(row.get("name") or "")
        total_params = row.get("params")
        valid_named_active = (
            payload is not None
            and isinstance(named_active, (int, float))
            and isinstance(total_params, (int, float))
            and 0 < named_active < total_params
        )
        active_fact = (row.get("facts") or {}).get("active_params")
        if (
            isinstance(active_fact, dict)
            and active_fact.get("reason") == "explicit-aNb-model-name"
            and not valid_named_active
            and payload is not None
        ):
            row["active_params"] = None
            row.setdefault("facts", {}).pop("active_params", None)
            changed = True
        classified = architecture(payload) if payload else None
        dense_all_active = (
            classified == "dense"
            and payload is not None
            and all_parameters_active_in_dense_model(payload)
        )
        architecture_reason = (
            "resolved-huggingface-config"
            if classified != "dense" or dense_all_active
            else "resolved-huggingface-topology-config"
        )
        if valid_named_active and classified != "moe":
            classified = "moe"
            architecture_reason = "explicit-active-parameter-model-name"
            dense_all_active = False
        current_architecture = row.get("architecture")
        if classified and current_architecture in (None, "dense", "moe"):
            if current_architecture != classified:
                row["architecture"] = classified
                counts["architectures"] += 1
                if current_architecture is not None:
                    counts["architecture_corrections"] += 1
            architecture_fact = (row.get("facts") or {}).get("architecture")
            if (
                current_architecture != classified
                or not isinstance(architecture_fact, dict)
                or architecture_fact.get("reason") != architecture_reason
            ):
                row.setdefault("facts", {})["architecture"] = known_fact(
                    architecture_reason, api_url, captured_at
                )
                changed = True

        active = named_active if valid_named_active else None
        if (
            active is None
            and classified == "dense"
            and dense_all_active
            and not params_look_packed(row)
        ):
            active = row.get("params")
        if row.get("active_params") is None and isinstance(active, (int, float)):
            row["active_params"] = active
            reason = "explicit-aNb-model-name" if valid_named_active else "all-parameters-active-in-dense-model"
            row.setdefault("facts", {})["active_params"] = known_fact(reason, api_url, captured_at)
            counts["active_params"] += 1
            changed = True

        downloads = row.get("downloads")
        recent_count = payload.get("downloads") if payload else None
        lifetime_count = payload.get("downloadsAllTime") if payload else None
        downloads_changed = False
        if isinstance(downloads, dict):
            if downloads.get("last_30d") is None and isinstance(recent_count, int):
                downloads["last_30d"] = recent_count
                counts["downloads_last_30d"] += 1
                downloads_changed = True
            if downloads.get("all_time") is None and isinstance(lifetime_count, int):
                downloads["all_time"] = lifetime_count
                counts["downloads_all_time"] += 1
                downloads_changed = True
            if downloads_changed:
                downloads["captured_at"] = captured_at
                downloads["source"] = "huggingface-api"
                changed = True

        if changed:
            write_json(path, row)
    return counts


def update_instances(metadata: dict[str, dict[str, Any]], captured_at: str) -> dict[str, int]:
    counts = {
        "revisions": 0,
        "revision_expansions": 0,
        "formats": 0,
        "format_corrections": 0,
        "precisions": 0,
        "sizes": 0,
        "size_corrections": 0,
        "size_fact_upgrades": 0,
        "size_retractions": 0,
    }
    revision_keys: set[tuple[str, str]] = set()
    for path in (REGISTRY / "model-instance").glob("*.json"):
        row = read_json(path)
        repo = (row.get("huggingface") or {}).get("repository") or row.get("repository")
        payload = metadata.get(repo) if isinstance(repo, str) else None
        revision = row.get("revision") or (payload or {}).get("sha")
        if payload is not None and isinstance(repo, str) and isinstance(revision, str):
            revision_keys.add((repo, revision))
    ordered_revision_keys = sorted(revision_keys)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        revision_cache = dict(
            zip(
                ordered_revision_keys,
                pool.map(
                    lambda item: fetch_revision_payload(*item),
                    ordered_revision_keys,
                ),
            )
        )
    revision_failures: set[tuple[str, str]] = set()
    for path in sorted((REGISTRY / "model-instance").glob("*.json")):
        row = read_json(path)
        repo = (row.get("huggingface") or {}).get("repository") or row.get("repository")
        payload = metadata.get(repo) if isinstance(repo, str) else None
        if not payload or not isinstance(repo, str):
            continue
        changed = False
        sha = payload.get("sha")
        revision = row.get("revision")
        adding_revision = revision in (None, "") and isinstance(sha, str) and bool(sha)
        if adding_revision:
            revision = sha
        if not isinstance(revision, str) or not revision:
            continue
        revision_key = (repo, revision)
        payload, api_url = revision_cache[revision_key]
        if payload is None:
            revision_failures.add(revision_key)
            weights = row.get("weights")
            size_fact = (row.get("facts") or {}).get("weights.size_gb") or {}
            if (
                isinstance(weights, dict)
                and isinstance(weights.get("size_gb"), (int, float))
                and str(size_fact.get("reason") or "").startswith("huggingface")
            ):
                weights["size_gb"] = None
                row.setdefault("facts", {})["weights.size_gb"] = unknown_fact(
                    "pinned-huggingface-revision-unavailable-for-verification",
                    api_url,
                    captured_at,
                )
                write_json(path, row)
                counts["size_retractions"] += 1
            continue
        resolved_revision = payload.get("sha")
        expanding_revision = (
            isinstance(resolved_revision, str) and resolved_revision != revision
        )
        if adding_revision or expanding_revision:
            revision = resolved_revision
            row["revision"] = revision
            api_url = API_REVISION.format(
                repo=urllib.parse.quote(repo, safe="/"),
                revision=urllib.parse.quote(revision, safe=""),
            )
            row.setdefault("facts", {})["revision"] = known_fact(
                "huggingface-repository-revision",
                api_url,
                captured_at,
            )
            counts["revisions" if adding_revision else "revision_expansions"] += 1
            changed = True
        weights = row.get("weights")
        if isinstance(weights, dict):
            if weights.get("format") in (None, ""):
                fmt = inferred_format(payload, repo, row)
                if fmt:
                    weights["format"] = fmt
                    row.setdefault("facts", {})["weights.format"] = known_fact("huggingface-weight-filenames", api_url, captured_at)
                    counts["formats"] += 1
                    changed = True
            elif normalized(str(weights.get("format") or "")) == "safetensors":
                files = weight_files(payload)
                if files and all(name.lower().endswith(".gguf") for name, _ in files):
                    weights["format"] = "GGUF"
                    row.setdefault("facts", {})["weights.format"] = known_fact(
                        "huggingface-weight-filenames",
                        api_url,
                        captured_at,
                    )
                    counts["format_corrections"] += 1
                    changed = True
            if weights.get("precision") in (None, "", "unknown"):
                precision = inferred_precision(payload)
                if precision and weights.get("format") not in ("GGUF", "MLX"):
                    weights["precision"] = precision
                    row.setdefault("facts", {})["weights.precision"] = known_fact("resolved-huggingface-config-dtype", api_url, captured_at)
                    counts["precisions"] += 1
                    changed = True
            size_fact = (row.get("facts") or {}).get("weights.size_gb") or {}
            existing_size = weights.get("size_gb")
            may_correct = (
                isinstance(existing_size, (int, float))
                and str(size_fact.get("reason") or "").startswith("huggingface")
            )
            if existing_size is None or may_correct:
                files = weight_files(payload)
                selected = logical_artifact(payload, files, repo, weights)
                if selected:
                    size_gb = round(sum(size for _, size in selected) / 1_000_000_000, 3)
                    current_sources = (
                        (size_fact.get("provenance") or {}).get("sources") or []
                    )
                    immutable_fact = (
                        size_fact.get("reason")
                        == "huggingface-logical-artifact-blob-size-sum"
                        and any(
                            isinstance(source, dict) and source.get("url") == api_url
                            for source in current_sources
                        )
                    )
                    if existing_size != size_gb or not immutable_fact:
                        weights["size_gb"] = size_gb
                        row.setdefault("facts", {})["weights.size_gb"] = known_fact(
                            "huggingface-logical-artifact-blob-size-sum",
                            api_url,
                            captured_at,
                        )
                        if existing_size != size_gb:
                            counts["sizes" if existing_size is None else "size_corrections"] += 1
                        else:
                            counts["size_fact_upgrades"] += 1
                        changed = True
                elif may_correct and files:
                    weights["size_gb"] = None
                    row.setdefault("facts", {})["weights.size_gb"] = unknown_fact(
                        "artifact-not-present-at-pinned-huggingface-revision",
                        api_url,
                        captured_at,
                    )
                    counts["size_retractions"] += 1
                    changed = True
        if changed:
            write_json(path, row)
    counts["revision_fetch_errors"] = len(revision_failures)
    return counts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("repositories", nargs="*", help="optional owner/repository subset")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument(
        "--metadata-only",
        action="store_true",
        help="skip resolved configs; with no repositories, process instances missing metadata",
    )
    modes.add_argument(
        "--models-only",
        action="store_true",
        help="query each model repository once for parameters and download counts",
    )
    modes.add_argument(
        "--configs-only",
        action="store_true",
        help="refresh resolved configs only for models lacking config-backed classification",
    )
    args = parser.parse_args()
    captured_at = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if args.repositories:
        work = {
            repo: not (args.metadata_only or args.models_only)
            for repo in args.repositories
        }
    elif args.metadata_only:
        work = instance_repository_work()
    elif args.models_only:
        work = model_repository_work()
    elif args.configs_only:
        work = model_config_work()
    else:
        work = repository_work()
    cleared_active_params = (
        clear_unverified_dense_active_params()
        if (
            not args.repositories
            and not args.metadata_only
            and not args.models_only
            and not args.configs_only
        )
        else 0
    )
    restored_active_params = restore_proven_dense_active_params()
    metadata: dict[str, dict[str, Any]] = {}
    errors = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        for repo, payload, error in pool.map(fetch, sorted(work.items())):
            if payload is not None:
                metadata[repo] = payload
            else:
                errors += 1
                print(f"WARN {repo}: {error}", file=sys.stderr)
    model_counts = update_models(metadata, captured_at)
    instance_counts = update_instances(metadata, captured_at)
    print(
        f"repos queried: {len(work)}; fetched: {len(metadata)}; errors: {errors}; "
        f"cleared unverified active params: {cleared_active_params}; "
        f"restored proven dense active params: {restored_active_params}; "
        + "; ".join(f"{key}: {value}" for key, value in {**model_counts, **instance_counts}.items())
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
