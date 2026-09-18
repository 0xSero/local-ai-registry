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
TABBY_IMAGE = "ghcr.io/theroyallab/tabbyapi:cu13@sha256:1c13dd17416660856e9962aeee8498827f0acd604eb36795128a03ddfe03c6ef"
# The cu13 image built 2026-09-13 bundles tabbyAPI 53da7919 and ExLlamaV3
# v1.5.0+cu132.torch2.11.0 (its pyproject `cu13` extra), verified from the OCI
# config and the upstream pyproject on 2026-09-18.
TABBY_ENGINE = {"graph_mode": "piecewise", "name": "tabbyapi", "version": "0.0.1+53da7919"}
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
    if re.fullmatch(r"[0-9.]+bpw", branch):
        precision = f"{float(bpw.group(1)):g} bpw" if bpw else branch
        instance_id = f"{slug(repo)}--{slug(precision)}"
    else:
        # Self-calibrated branches (SC_4.00bpw_H5) and their quantized-vision
        # twins (SC_4.00bpw_H5_V6) are distinct artifacts from the plain branch
        # at the same bpw, with their own revision and byte count. Keeping the
        # branch in the identity stops a recipe pinning the wrong one.
        precision = branch.replace("_", " ")
        instance_id = f"{slug(repo)}--{slug(branch)}"
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


def ensure_asset(asset_id, model_name, ctx, cache_mode, purpose, vision=False, reasoning=False,
                 tool_format=None, draft_mode="disabled", max_batch_size=2,
                 start_in_reasoning="auto", vision_offload=False, autosplit_reserve=None,
                 cache_headroom=1024):
    # ExLlamaV3 refuses a request whose prompt plus output needs more pages than
    # the cache holds, and it counts in whole 256-token pages. With
    # cache_size == max_seq_len a request that fills the window asks for one page
    # more than exists ("Job requires 1025 pages (only 1024 available)"), so the
    # cache is sized above the window instead of exactly at it.
    cache_size = ctx + cache_headroom
    extra = []
    if vision:
        extra.append("  vision: true")
        if vision_offload:
            extra.append("  vision_offload: true")
    if reasoning:
        extra.append("  reasoning: true")
        extra.append(f"  start_in_reasoning: {start_in_reasoning}")
        extra.append("  reasoning_start_token: \" thinking\"")
        extra.append("  reasoning_end_token: \"</think>\"")
        extra.append("  template_vars_default:")
        extra.append("    enable_thinking: true")
    if tool_format:
        extra.append(f"  tool_format: {tool_format}")
    reserve = f"  autosplit_reserve: [{autosplit_reserve}]\n" if autosplit_reserve else "  autosplit_reserve: [192]\n"
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
  cache_size: {cache_size}
  cache_mode: {cache_mode}
  tensor_parallel: false
  gpu_split_auto: true
{reserve}  chunk_size: 2048
  output_chunking: true
  max_batch_size: {max_batch_size}
{chr(10).join(extra) + chr(10) if extra else ""}
draft_model:
  draft_mode: {draft_mode}

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
    parser.add_argument("--vision", action="store_true", help="claim and enable the vision tower")
    parser.add_argument("--reasoning", action="store_true", help="enable the reasoning parser and default thinking")
    parser.add_argument("--tool-format", help="TabbyAPI tool_format, e.g. qwen3_coder")
    parser.add_argument("--draft-mode", default="disabled", choices=("disabled", "model", "mtp", "ngram"))
    parser.add_argument("--max-batch-size", type=int, default=2)
    parser.add_argument("--start-in-reasoning", default="auto", choices=("auto", "always", "never"),
                        help="always for Qwen3.8: its template opens  thinking before generation")
    parser.add_argument("--vision-offload", action="store_true",
                        help="keep vision weights in pinned host RAM when the tower does not fit")
    parser.add_argument("--autosplit-reserve", type=int, help="MB reserved per GPU during autosplit")
    parser.add_argument("--cache-headroom", type=int, default=1024,
                        help="extra KV tokens so a window-filling request still has pages")
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
    bbq = re.fullmatch(r"[0-9.]+bpw", args.branch)
    bpw_slug = f"{float(bpw.group(1)):g}bpw" if (bpw and bbq) else slug(args.branch)
    served = args.served_name or f"{args.repo.split('/')[-1].replace('-exl3', '')}-EXL3-{bpw_slug}"
    instance = ensure_instance(args.repo, args.branch, args.model, served)
    model_slug = slug(args.repo.split("/")[-1].replace("-exl3", "")).replace("-", "")
    ctx_slug = f"{args.ctx // 1024}k"
    asset_id = f"{model_slug}-exl3-{bpw_slug}-{ctx_slug}-{args.cache.lower()}-tabbyapi-config"
    ensure_asset(asset_id, served, args.ctx, args.cache,
                 f"TabbyAPI server configuration for {served} at {args.ctx} tokens with {args.cache} cache; bridge networking; mounted at /app/config.yml.",
                 vision=args.vision, reasoning=args.reasoning, tool_format=args.tool_format,
                 draft_mode=args.draft_mode, max_batch_size=args.max_batch_size,
                 start_in_reasoning=args.start_in_reasoning, vision_offload=args.vision_offload,
                 autosplit_reserve=args.autosplit_reserve, cache_headroom=args.cache_headroom)
    recipe_id = args.id or f"{model_slug}-exl3-{bpw_slug}-{hardware_slug(args.hardware)}-tabbyapi-tp1"
    path = REG / "recipe" / f"{recipe_id}.json"
    if path.exists() and not args.force:
        raise SystemExit(f"{recipe_id} exists; pass --force to overwrite")
    weights_dir = f"${{MODEL_ROOT}}/{slug(served)}"
    recipe = {
        "schema_version": "local-ai-registry/v1", "id": recipe_id, "recipe_source": "0xsero", "status": "candidate",
        "model_instance_id": instance["id"], "hardware_id": args.hardware, "hardware_count": 1,
        "engine": TABBY_ENGINE,
        "capabilities": {"chat": True, "reasoning": True if args.reasoning else None,
                        "tools": True if args.tool_format else None, "vision": bool(args.vision)},
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
            "synthesized": {"template": "tabbyapi-exl3-bridge-v1", "generated_at": NOW,
                            "image_provenance": f"upstream:{args.image.split('@')[0]}"},
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
