#!/usr/bin/env python3
"""Create a bridge-networked TabbyAPI (ExLlamaV3) candidate for one card.

Writes, as needed: the model-instance for an EXL3 branch of a Hugging Face
repo, a TabbyAPI config asset (yml + json record) for the requested context
and cache mode, and the candidate recipe. The launch contract mirrors the
validated Gemma-4 TabbyAPI recipes except that it uses bridge networking and
binds 0.0.0.0, which is what the Omarchy plugin's safety gate accepts.

    python3 scripts/make_tabbyapi_candidate.py \
        --repo turboderp/Qwen3.5-9B-exl3 --branch 4.00bpw --model qwen3-5-9b \
        --hardware rtx-4080-16gb --ctx 262144 --cache Q4 [--served-name NAME] [--id ID]

The instance revision is the branch's commit as of now, fetched from the
Hugging Face API, so the recipe pins exactly what was validated.
"""

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
import urllib.request
from pathlib import Path

REG = Path(__file__).resolve().parent.parent / "registry"
NOW = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
TABBY_IMAGE = "ghcr.io/theroyallab/tabbyapi:cu13@sha256:ffa8388f310d3c8a2727c66d14a76bb663fdb99a2a49e68a43c3bebb5a3e53f1"
TABBY_ENGINE = {"graph_mode": "piecewise", "name": "tabbyapi", "version": "0.0.1+e632af41"}
SOURCE = {"kind": "normalized-recipe", "url": "https://github.com/0xSero/local-ai-registry", "captured_at": NOW}


def hf(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "local-ai-registry"}), timeout=60) as r:
        return json.load(r)


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def hardware_slug(hardware_id):
    return "".join(p for p in hardware_id.split("-") if not p.endswith("gb") and p != "blackwell")


def ensure_instance(repo, branch, model_id, served_name):
    info = hf(f"https://huggingface.co/api/models/{repo}/revision/{branch}?blobs=true")
    revision = info["sha"]
    size_gb = round(sum(s.get("size") or 0 for s in info["siblings"]) / 1073741824, 2)
    bpw = re.search(r"(\d+(?:\.\d+)?)bpw", branch)
    precision = f"{float(bpw.group(1)):g} bpw" if bpw else branch
    instance_id = f"{slug(repo)}--{slug(precision)}"
    path = REG / "model-instance" / f"{instance_id}.json"
    api = f"https://huggingface.co/api/models/{repo}"
    record = {
        "schema_version": "local-ai-registry/v1", "id": instance_id, "kind": "quant", "model_id": model_id,
        "repository": repo, "revision": revision, "served_name": served_name, "url": f"https://huggingface.co/{repo}",
        "weights": {"format": "EXL3", "precision": precision, "size_gb": size_gb},
        "huggingface": {"link_type": "repository", "repository": repo, "url": f"https://huggingface.co/{repo}", "status": "known",
                        "reason": "hf-api-confirmed-public",
                        "provenance": {"captured_at": NOW, "sources": [{"kind": "huggingface-api", "url": api, "captured_at": NOW}]}},
        "provenance": {"captured_at": NOW, "sources": [{"kind": "normalized-model-instance", "url": f"https://huggingface.co/{repo}", "captured_at": NOW}]},
        "facts": {
            "revision": {"state": "known", "reason": "huggingface-branch-head-at-capture",
                         "provenance": {"captured_at": NOW, "sources": [{"kind": "huggingface-api", "url": f"{api}/refs", "captured_at": NOW}]}},
            "weights.size_gb": {"state": "known", "reason": "huggingface-logical-artifact-blob-size-sum",
                                "provenance": {"captured_at": NOW, "sources": [{"kind": "huggingface-api", "url": f"{api}/revision/{revision}?blobs=true", "captured_at": NOW}]}},
        },
    }
    if path.exists():
        existing = json.loads(path.read_text())
        if existing.get("revision") != revision:
            print(f"note: {instance_id} exists at revision {existing.get('revision','')[:12]}; keeping it (branch head is now {revision[:12]})", file=sys.stderr)
        return existing
    path.write_text(json.dumps(record, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    print(f"instance {instance_id} @ {revision[:12]} ({size_gb} GB)", file=sys.stderr)
    return record


def ensure_asset(asset_id, model_name, ctx, cache_mode, purpose):
    yml = f"""network:
  host: 0.0.0.0
  port: 5000
  disable_auth: true
  disable_fetch_requests: true
  send_tracebacks: false
  api_servers: ["OAI"]
  sse_ping_interval: 15

logging:
  log_prompt: false
  log_generation_params: false
  log_requests: false
  log_chat_completion_requests: false

model:
  model_dir: /workspace/models
  inline_model_loading: false
  use_dummy_models: false
  model_name: {model_name}
  backend: exllamav3
  max_seq_len: {ctx}
  cache_size: {ctx}
  cache_mode: {cache_mode}
  tensor_parallel: false
  gpu_split_auto: true
  autosplit_reserve: [192]
  chunk_size: 2048
  output_chunking: true
  max_batch_size: 2

draft_model:
  draft_mode: disabled

sampling:
  override_preset:

memory:
  sysmem_recurrent_cache: 4096
  sysmem_kv_cache: 0
  cuda_malloc_async: true
"""
    (REG / "asset" / f"{asset_id}.yml").write_text(yml)
    record = {"schema_version": "local-ai-registry/v1", "id": asset_id, "file": f"{asset_id}.yml", "filename": "config.yml",
              "media_type": "application/yaml", "purpose": purpose,
              "sha256": hashlib.sha256(yml.encode()).hexdigest(), "size_bytes": len(yml.encode())}
    (REG / "asset" / f"{asset_id}.json").write_text(json.dumps(record, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    return record


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--branch", required=True, help="EXL3 branch, e.g. 4.00bpw")
    parser.add_argument("--model", required=True, help="registry model id")
    parser.add_argument("--hardware", required=True, help="registry hardware id")
    parser.add_argument("--ctx", type=int, required=True)
    parser.add_argument("--cache", default="Q4", help="ExLlamaV3 cache mode: Q4, Q6, Q8, FP16")
    parser.add_argument("--served-name", help="model folder and served id; default derived from the repo and branch")
    parser.add_argument("--id")
    parser.add_argument("--image", default=TABBY_IMAGE, help="digest-pinned image; default is the upstream TabbyAPI image")
    parser.add_argument("--image-provenance", help="JSON: {kind, source, dockerfile, workflow, attestation} for a self-built image")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if not re.search(r"@sha256:[0-9a-f]{64}$", args.image):
        raise SystemExit("--image must be digest-pinned")
    provenance = json.loads(args.image_provenance) if args.image_provenance else None

    if not (REG / "model" / f"{args.model}.json").exists():
        raise SystemExit(f"no model record {args.model}")
    if not (REG / "hardware" / f"{args.hardware}.json").exists():
        raise SystemExit(f"no hardware record {args.hardware}")
    bpw = re.search(r"(\d+(?:\.\d+)?)bpw", args.branch)
    bpw_slug = f"{float(bpw.group(1)):g}bpw" if bpw else slug(args.branch)
    served = args.served_name or f"{args.repo.split('/')[-1].replace('-exl3', '')}-EXL3-{bpw_slug}"
    instance = ensure_instance(args.repo, args.branch, args.model, served)
    model_slug = slug(args.repo.split("/")[-1].replace("-exl3", "")).replace("-", "")
    ctx_slug = f"{args.ctx // 1024}k"
    asset_id = f"{model_slug}-exl3-{bpw_slug}-{ctx_slug}-{args.cache.lower()}-tabbyapi-config"
    ensure_asset(asset_id, served, args.ctx, args.cache,
                 f"TabbyAPI server configuration for {served} at {args.ctx} tokens with {args.cache} cache; bridge networking; mounted at /app/config.yml.")
    recipe_id = args.id or f"{model_slug}-exl3-{bpw_slug}-{hardware_slug(args.hardware)}-tabbyapi-tp1"
    path = REG / "recipe" / f"{recipe_id}.json"
    if path.exists() and not args.force:
        raise SystemExit(f"{recipe_id} exists; pass --force to overwrite")
    weights_dir = f"${{MODEL_ROOT}}/{slug(served)}"
    recipe = {
        "schema_version": "local-ai-registry/v1", "id": recipe_id, "recipe_source": "0xsero", "status": "candidate",
        "model_instance_id": instance["id"], "hardware_id": args.hardware, "hardware_count": 1,
        "engine": TABBY_ENGINE,
        "capabilities": {"chat": True, "reasoning": None, "tools": None, "vision": False},
        "serving": {"kv_cache_tokens": args.ctx, "max_concurrency": 2, "max_context_tokens": args.ctx, "tensor_parallel": 1},
        "launch": {"kind": "reference", "container": {"state": "none", "runtime": None, "image": None, "digest": None, "compose_file": None,
                                                       "reason": "draft-pending-acceptance", "captured_at": NOW, "source": [SOURCE]}},
        "draft_launch": {
            "kind": "docker", "image": args.image, "accelerator_backend": "nvidia",
            "entrypoint": "/opt/venv/bin/python3", "arguments": ["main.py", "--config", "/app/config.yml"],
            "environment": {"NVIDIA_VISIBLE_DEVICES": "all"},
            "mounts": [{"read_only": True, "source": weights_dir, "target": "/workspace/models"},
                       {"read_only": True, "source": f"asset/{asset_id}.yml", "target": "/app/config.yml"}],
            "host_port": 5000, "container_port": 5000, "shm_size": "8g",
            "synthesized": {"template": "tabbyapi-exl3-bridge-v1", "generated_at": NOW, "image_provenance": "gemma-4-12b-it-exl3-4bpw-rtx3090-tabbyapi-tp1"},
        },
        "speed_sweep_ids": [],
        "metadata": {"weights_subdir": served, **({"image_provenance": provenance} if provenance else {})},
        "provenance": {"captured_at": NOW, "sources": [SOURCE]}, "facts": {},
        "description": f"Candidate: {served} on one {args.hardware} via TabbyAPI/ExLlamaV3, {args.ctx} tokens, {args.cache} cache, bridge networking. Pending acceptance on the card.",
    }
    path.write_text(json.dumps(recipe, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    print(recipe_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
