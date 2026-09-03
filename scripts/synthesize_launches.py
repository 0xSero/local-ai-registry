#!/usr/bin/env python3
"""Synthesize draft docker launches for observed reference candidates.

The observed recipe stays exactly what it is — evidence with
launch.kind reference. This adds draft_launch: a mechanically generated,
UNVERIFIED docker contract built from the candidate's own facts (model
repository, quantization, tensor parallel, context) and an image digest
already audited elsewhere in this registry. Drafts exist for one
purpose: `local-ai validate <id>` runs them on the target hardware and
promotes the recipe only after a real completion and speed acceptance.

NVIDIA-only for now (vllm, sglang, llama.cpp with GGUF-hosting repos,
single-GPU llama.cpp only). Run from the repository root; idempotent.
"""

import datetime as dt
import json
import re
from pathlib import Path

ROOT = Path("registry")
NOW = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

# Digest-pinned Linux images and entrypoints verified from their remote image
# configs. The companion recipe IDs preserve the registry's image lineage.
IMAGES = {
    "vllm": (
        "vllm/vllm-openai@sha256:0a51ea5b4ae2dc5d81890e5173f54203d2a3ae0cfffe51b8fd2afd4391bfd967",
        "deepseek-fp8-rtx-pro-6000-blackwell-96gb-vllm-tp1",
        "vllm",
    ),
    "sglang": (
        "lmsysorg/sglang:dev-cu13@sha256:6cd4635214f279e0a43019f88e3120d407567640a58aa7dcc0085e3d91402cc4",
        "gemma-4-12b-it-nvfp4-rtxpro6000-sglang-tp1",
        "/opt/nvidia/nvidia_entrypoint.sh",
    ),
    "llama.cpp": (
        "ghcr.io/ggml-org/llama.cpp:server-cuda12-b10481@sha256:b2497f8834f5ecb4e38530f6bf2734b8e0be107ff48e4720145911c86930f2ce",
        "gemma-4-12b-q4-k-m-rtx-3060-12gb-llama-cpp-tp1",
        "/app/llama-server",
    ),
}
IMAGE_CONFIG_SOURCES = {
    "vllm": "https://registry-1.docker.io/v2/vllm/vllm-openai/manifests/sha256:0a51ea5b4ae2dc5d81890e5173f54203d2a3ae0cfffe51b8fd2afd4391bfd967",
    "sglang": "https://registry-1.docker.io/v2/lmsysorg/sglang/manifests/sha256:6cd4635214f279e0a43019f88e3120d407567640a58aa7dcc0085e3d91402cc4",
    "llama.cpp": "https://ghcr.io/v2/ggml-org/llama.cpp/manifests/sha256:b2497f8834f5ecb4e38530f6bf2734b8e0be107ff48e4720145911c86930f2ce",
}
CACHE_MOUNT = {"source": "~/.cache/huggingface", "target": "/root/.cache/huggingface", "read_only": False}
GGUF_QUANT = re.compile(r"^(I?Q[0-9][A-Z0-9_]*|F16|BF16|F32)$", re.IGNORECASE)


def base(template, engine_key, host_port, container_port, arguments, environment=None):
    image, provenance, entrypoint = IMAGES[engine_key]
    return {
        "kind": "docker",
        "image": image,
        "entrypoint": entrypoint,
        "arguments": arguments,
        "environment": environment or {},
        "mounts": [dict(CACHE_MOUNT)],
        "host_port": host_port,
        "container_port": container_port,
        "ipc": "host",
        "shm_size": "16g",
        "accelerator_backend": "nvidia",
        "synthesized": {"template": template, "generated_at": NOW, "image_provenance": provenance},
    }


def synthesize(recipe, instance):
    engine = recipe["engine"]["name"].lower()
    repo = instance.get("repository")
    if not isinstance(repo, str) or "/" not in repo:
        return None, "no usable repository"
    serving = recipe.get("serving") or {}
    tp = serving.get("tensor_parallel") or recipe.get("hardware_count") or 1
    ctx = serving.get("max_context_tokens")

    if engine == "vllm":
        arguments = ["serve", "--model", repo, "--tensor-parallel-size", str(tp), "--host", "0.0.0.0", "--port", "8000"]
        if isinstance(ctx, int) and ctx > 0:
            arguments += ["--max-model-len", str(ctx)]
        return base("vllm-openai-v1", "vllm", 8000, 8000, arguments), None

    if engine == "sglang":
        arguments = ["python3", "-m", "sglang.launch_server", "--model-path", repo, "--tp", str(tp), "--host", "0.0.0.0", "--port", "30000"]
        if isinstance(ctx, int) and ctx > 0:
            arguments += ["--context-length", str(ctx)]
        draft = base("sglang-launch-server-v1", "sglang", 30000, 30000, arguments)
        return draft, None

    if engine == "llama.cpp":
        if tp != 1:
            return None, "llama.cpp draft limited to single GPU"
        quant = (instance.get("weights") or {}).get("format") or ""
        if "gguf" not in repo.lower():
            return None, "repository does not host GGUF artifacts"
        spec = f"{repo}:{quant}" if GGUF_QUANT.fullmatch(quant or "") else repo
        arguments = ["-hf", spec, "--n-gpu-layers", "999", "--host", "0.0.0.0", "--port", "8080"]
        if isinstance(ctx, int) and ctx > 0:
            arguments += ["-c", str(ctx)]
        draft = base("llama-cpp-server-v1", "llama.cpp", 8080, 8080, arguments, {"LLAMA_CACHE": "/root/.cache/huggingface"})
        return draft, None

    return None, f"no template for engine {engine}"


def entrypoint_fact(source_url):
    return {
        "state": "known",
        "reason": "linux-amd64-container-config-entrypoint",
        "provenance": {
            "captured_at": NOW,
            "sources": [
                {
                    "captured_at": NOW,
                    "kind": "container-config",
                    "url": source_url,
                }
            ],
        },
    }


def main():
    created = skipped = 0
    reasons = {}
    for path in sorted((ROOT / "recipe").glob("*.json")):
        recipe = json.loads(path.read_text())
        if recipe["status"] != "candidate" or recipe["launch"].get("kind") != "reference":
            continue
        hardware = json.loads((ROOT / "hardware" / f"{recipe['hardware_id']}.json").read_text())
        if hardware["vendor"] != "nvidia":
            continue
        instance = json.loads((ROOT / "model-instance" / f"{recipe['model_instance_id']}.json").read_text())
        draft, reason = synthesize(recipe, instance)
        if draft is None:
            skipped += 1
            reasons[reason] = reasons.get(reason, 0) + 1
            continue

        existing = recipe.get("draft_launch")
        if (
            isinstance(existing, dict)
            and (existing.get("synthesized") or {}).get("template")
            == (draft.get("synthesized") or {}).get("template")
        ):
            generated_at = (existing.get("synthesized") or {}).get("generated_at")
            if generated_at:
                draft["synthesized"]["generated_at"] = generated_at

        engine_key = recipe["engine"]["name"].lower()
        if engine_key == "sglang":
            engine_key = "sglang"
        fact = (recipe.get("facts") or {}).get("draft_launch.entrypoint")
        source_url = IMAGE_CONFIG_SOURCES[engine_key]
        expected_fact_source = (
            ((fact or {}).get("provenance") or {}).get("sources") or [{}]
        )[0].get("url")
        fact_changed = (
            not isinstance(fact, dict)
            or fact.get("state") != "known"
            or fact.get("reason") != "linux-amd64-container-config-entrypoint"
            or expected_fact_source != source_url
        )
        draft_changed = existing != draft
        if not draft_changed and not fact_changed:
            continue
        recipe["draft_launch"] = draft
        if fact_changed:
            recipe.setdefault("facts", {})["draft_launch.entrypoint"] = entrypoint_fact(source_url)
        path.write_text(json.dumps(recipe, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
        created += 1
    print(f"drafts written: {created}; skipped: {skipped}")
    for reason, count in sorted(reasons.items(), key=lambda kv: -kv[1]):
        print(f"  skip: {reason}: {count}")


if __name__ == "__main__":
    main()
