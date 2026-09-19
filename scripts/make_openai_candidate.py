#!/usr/bin/env python3
"""Author a candidate recipe for an OpenAI-compatible server engine.

`make_tabbyapi_candidate.py` covers TabbyAPI, whose configuration is a mounted
YAML asset. vLLM and SGLang take their configuration as argv instead, so this
writes the same recipe shape with the server arguments recorded in `draft_launch`
rather than a config asset. The candidate carries no claims: `omp_registry_record.py`
promotes `draft_launch` to `launch` and fills capabilities and serving from the
measured acceptance, and `make trust` decides the status.

    python3 scripts/make_openai_candidate.py \
        --engine vllm --hardware rtx-pro-4500-blackwell-32gb \
        --repo ornith-ai/Ornith-1.5-9B --revision <40hex> \
        --model-instance ornith-ai-ornith-1-5-9b \
        --served-name Ornith-1.5-9B --ctx 131072 --port 8000 \
        --image ghcr.io/0xsero/vllm-openai@sha256:<64hex> \
        --serve-argv '["vllm","serve",...]' \
        --id ornith15-9b-rtxpro4500-vllm-tp1 \
        --capability chat --capability reasoning --capability tools
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

DIGEST = re.compile(r"@sha256:[0-9a-f]{64}$")
REVISION = re.compile(r"^[0-9a-f]{40}$")
SLUG = re.compile(r"^[a-z0-9][a-z0-9.-]*$")
# Every image this repository publishes, with the workflow run that built it, so a
# candidate records where its container came from instead of asserting nothing.
IMAGE_PROVENANCE = {
    "ghcr.io/0xsero/vllm-openai": {
        "kind": "self-built-attested",
        "source": "https://github.com/0xSero/local-ai-images",
        "dockerfile": "https://github.com/0xSero/local-ai-images/blob/main/vllm-openai/Dockerfile",
        "workflow": "https://github.com/0xSero/local-ai-images/actions/runs/35441177733",
    },
    "ghcr.io/0xsero/sglang": {
        "kind": "self-built-attested",
        "source": "https://github.com/0xSero/local-ai-images",
        "dockerfile": "https://github.com/0xSero/local-ai-images/blob/main/sglang/Dockerfile",
        "workflow": "https://github.com/0xSero/local-ai-images/actions/runs/35441996218",
    },
    "ghcr.io/theroyallab/tabbyapi": {
        "kind": "upstream-published",
        "source": "https://github.com/theroyallab/tabbyAPI",
        "dockerfile": "https://github.com/theroyallab/tabbyAPI",
        "workflow": None,
    },
}

TEMPLATES = {"vllm": "openai-server-vllm-v1", "sglang": "openai-server-sglang-v1"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                    formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--registry", type=Path, default=Path("."))
    parser.add_argument("--engine", required=True, choices=("vllm", "sglang"))
    parser.add_argument("--hardware", required=True)
    parser.add_argument("--repo", required=True, help="model repository, e.g. ornith-ai/Ornith-1.5-9B")
    parser.add_argument("--revision", required=True, help="full 40-hex commit hash")
    parser.add_argument("--model-instance", required=True, help="model-instance id")
    parser.add_argument("--served-name", required=True)
    parser.add_argument("--ctx", type=int, required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--image", required=True, help="digest-pinned image reference")
    parser.add_argument("--serve-argv", required=True, help="JSON array of the server argv")
    parser.add_argument("--id", required=True)
    parser.add_argument("--capability", action="append", default=[],
                        choices=("chat", "reasoning", "tools", "vision"))
    parser.add_argument("--engine-version", default=None)
    parser.add_argument("--weights-subdir", default=None)
    parser.add_argument("--description", default=None)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    if not DIGEST.search(args.image):
        print("error: --image must be pinned by digest", file=sys.stderr)
        return 2
    if not REVISION.match(args.revision):
        print("error: --revision must be a full 40-hex commit hash", file=sys.stderr)
        return 2
    if not SLUG.match(args.id) or not SLUG.match(args.hardware):
        print("error: --id and --hardware must be registry slugs", file=sys.stderr)
        return 2
    argv_list = json.loads(args.serve_argv)
    if not isinstance(argv_list, list) or not argv_list:
        print("error: --serve-argv must be a non-empty JSON array", file=sys.stderr)
        return 2

    repository = args.image.rsplit("@sha256:", 1)[0]
    provenance = IMAGE_PROVENANCE.get(repository)
    if provenance is None:
        print(f"error: no provenance is recorded for {repository}", file=sys.stderr)
        return 2

    now = utc_now()
    source = [{"captured_at": now, "kind": "campaign-run",
               "url": "https://github.com/0xSero/inference-index"}]
    recipe = {
        "schema_version": "local-ai-registry/v1",
        "id": args.id,
        "recipe_source": "0xsero",
        "status": "candidate",
        "model_instance_id": args.model_instance,
        "hardware_id": args.hardware,
        "hardware_count": 1,
        "engine": {
            "name": args.engine,
            "version": args.engine_version,
            "graph_mode": "full-and-piecewise",
        },
        "capabilities": {name: (name in args.capability) for name in
                         ("chat", "reasoning", "tools", "vision")},
        "serving": {
            "max_context_tokens": args.ctx,
            "max_concurrency": None,
            "tensor_parallel": 1,
        },
        "launch": {"kind": "reference", "container": {
            "image": None, "digest": None, "runtime": None,
            "state": "none", "reason": "draft-pending-acceptance", "source": [],
        }},
        "draft_launch": {
            "kind": "docker",
            "image": args.image,
            "arguments": argv_list,
            "host_port": args.port,
            "container_port": args.port,
            "accelerator_backend": "nvidia",
            "synthesized": {
                "template": TEMPLATES[args.engine],
                "generated_at": now,
                "image_provenance": provenance,
            },
        },
        "speed_sweep_ids": [],
        "metadata": {},
        "provenance": {"captured_at": now, "sources": [
            {"captured_at": now, "kind": "normalized-recipe",
             "url": "https://github.com/0xSero/local-ai-registry"}]},
        "facts": {},
    }
    if args.weights_subdir:
        recipe["metadata"]["weights_subdir"] = args.weights_subdir
    if args.description:
        recipe["description"] = args.description

    path = args.registry / "registry" / "recipe" / f"{args.id}.json"
    if path.exists() and not args.force:
        print(f"error: {path} exists; pass --force to overwrite", file=sys.stderr)
        return 2
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(recipe, indent=2, sort_keys=True) + "\n")
    print(args.id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
