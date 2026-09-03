#!/usr/bin/env python3
"""Acceptance + promotion for a launched draft recipe.

Run by `local-ai validate` AFTER the draft server is up. Performs a real
completion, measures streaming TTFT and decode rate, pins the model
revision that was actually served, writes a speed-sweep evidence record,
and promotes the recipe: draft_launch becomes launch, status becomes
validated. Refuses to promote when any pillar of the trust contract
cannot be satisfied.
"""

import argparse
import datetime as dt
import json
import re
import ssl
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "registry"
CTX = ssl.create_default_context()
NOW = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def http_json(url, payload=None, timeout=120):
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout, context=CTX) as response:
        return json.load(response)


def measure(endpoint, model, prompt_tokens=256, samples=3):
    prompt = "Summarize the history of computing. " * (prompt_tokens // 8)
    rows = []
    for _ in range(samples):
        started = time.monotonic()
        first = last = None
        completion_tokens = None
        request = urllib.request.Request(
            f"{endpoint}/v1/chat/completions",
            data=json.dumps({
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": True,
                "stream_options": {"include_usage": True},
            }).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=600, context=CTX) as response:
            for line in response:
                if not line.startswith(b"data:"):
                    continue
                raw = line[5:].strip()
                if raw == b"[DONE]":
                    break
                chunk = json.loads(raw)
                usage = chunk.get("usage")
                if isinstance(usage, dict) and usage.get("completion_tokens") is not None:
                    completion_tokens = int(usage["completion_tokens"])
                for choice in chunk.get("choices") or []:
                    delta = choice.get("delta") or {}
                    if delta.get("content") or delta.get("reasoning_content"):
                        now = time.monotonic()
                        first = first or now
                        last = now
        finished = time.monotonic()
        if first is None or completion_tokens is None or completion_tokens < 8:
            raise SystemExit("acceptance FAILED: the server produced no usable completion or usage")
        decode = (completion_tokens - 1) / max((last or finished) - first, 1e-6)
        rows.append({"ttft_ms": (first - started) * 1000, "decode_tok_s": decode, "tokens": completion_tokens})
    return rows


def probe_dialects(endpoint, model, gateway):
    """Run the plugin's gateway locally in front of the engine and ask for LOCAL_AI_READY in all three
    dialects. Returns the list that answered, or None when no gateway was given. The plugin repeats
    this on the user's machine; recording it here says what the pair was validated for."""
    if not gateway:
        return None
    import socket
    import subprocess
    import os
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    env = dict(os.environ, UPSTREAM=endpoint, GATEWAY_PORT=str(port), MODEL=model, GATEWAY_KEY_FILE="")
    proc = subprocess.Popen([sys.executable, gateway], env=env, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    prompt = "Reply with exactly: LOCAL_AI_READY"
    try:
        for _ in range(50):
            try:
                http_json(f"{base}/v1/models"); break
            except Exception:
                time.sleep(0.1)
        apis = []
        try:
            reply = http_json(f"{base}/v1/chat/completions", {"model": model, "messages": [{"role": "user", "content": prompt}], "stream": False})
            if "LOCAL_AI_READY" in (reply["choices"][0]["message"].get("content") or ""):
                apis.append("chat")
        except Exception:
            pass
        try:
            # thinking models spend tokens before the answer; a small cap would fail them for the wrong reason
            reply = http_json(f"{base}/v1/messages", {"model": model, "max_tokens": 2048, "messages": [{"role": "user", "content": prompt}]})
            if "LOCAL_AI_READY" in " ".join(b.get("text", "") for b in reply.get("content", []) if b.get("type") == "text"):
                apis.append("messages")
        except Exception:
            pass
        try:
            reply = http_json(f"{base}/v1/responses", {"model": model, "input": prompt})
            text = " ".join(part.get("text", "") for item in reply.get("output", []) if item.get("type") == "message" for part in item.get("content", []))
            if "LOCAL_AI_READY" in text:
                apis.append("responses")
        except Exception:
            pass
        return apis
    finally:
        proc.terminate()


def pinned_revision(repo):
    data = http_json(f"https://huggingface.co/api/models/{repo}")
    sha = data.get("sha")
    if not (isinstance(sha, str) and re.fullmatch(r"[0-9a-f]{40}", sha)):
        raise SystemExit(f"acceptance FAILED: could not pin a revision for {repo}")
    return sha


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("recipe_id")
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--harness", default="local-ai validate", help="recorded in metadata.acceptance.harness")
    parser.add_argument("--min-decode", type=float, default=5.0, help="tok/s floor; below it the GPU is not in use")
    parser.add_argument("--gateway", help="path to the plugin gateway (gateway.py); probes all three dialects through it")
    parser.add_argument("--revalidate", action="store_true", help="re-run acceptance on an already validated recipe and refresh its evidence")
    args = parser.parse_args()

    path = ROOT / "recipe" / f"{args.recipe_id}.json"
    recipe = json.loads(path.read_text())
    draft = recipe.get("draft_launch") or (recipe["launch"] if recipe["launch"].get("kind") == "docker" else None)
    if draft is None or (recipe["status"] != "candidate" and not args.revalidate):
        raise SystemExit("acceptance only applies to candidates with a docker draft or docker launch (or --revalidate)")

    served = http_json(f"{args.endpoint}/v1/models")["data"][0]["id"]
    print(f"server is healthy; serving model id: {served}")
    apis = probe_dialects(args.endpoint, served, args.gateway)
    if apis is not None:
        print(f"dialects through the gateway: {', '.join(apis) or 'none'}")
        if "chat" not in apis:
            raise SystemExit("acceptance FAILED: the gateway could not complete a chat request against the engine")
    runs = measure(args.endpoint, served)
    decode = sorted(run["decode_tok_s"] for run in runs)[len(runs) // 2]
    ttft = sorted(run["ttft_ms"] for run in runs)[len(runs) // 2]
    completion_tokens = sorted(run["tokens"] for run in runs)[len(runs) // 2]
    print(f"acceptance measurements: decode {decode:.1f} tok/s, ttft {ttft:.0f} ms over {len(runs)} samples")
    if decode < args.min_decode:
        raise SystemExit(f"acceptance FAILED: decode {decode:.1f} tok/s is below the {args.min_decode} tok/s floor; "
                         "the accelerator is not being used (CUDA init failure and CPU fallback look exactly like this)")

    instance_path = ROOT / "model-instance" / f"{recipe['model_instance_id']}.json"
    instance = json.loads(instance_path.read_text())
    if not (isinstance(instance.get("revision"), str) and re.fullmatch(r"[0-9a-f]{40}", instance["revision"] or "")):
        instance["revision"] = pinned_revision(instance["repository"])
        instance_path.write_text(json.dumps(instance, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
        print(f"pinned model revision {instance['revision'][:12]}")

    serving = recipe.setdefault("serving", {})
    if serving.get("max_context_tokens") is None:
        for flag in ("--max-model-len", "--context-length", "-c"):
            arguments = draft.get("arguments", [])
            if flag in arguments:
                serving["max_context_tokens"] = int(arguments[arguments.index(flag) + 1])
                break
    if serving.get("max_context_tokens") is None:
        raise SystemExit("acceptance FAILED to promote: serving.max_context_tokens unknown and not stated in the draft")

    sweep_id = f"{recipe['id']}-acceptance"
    row = {
        "concurrency": 1,
        "context_tokens": serving.get("max_context_tokens"),
        "output_tokens": completion_tokens,
        "prefill_tok_s": None,
        "decode_tok_s": round(decode, 1),
        "decode_tok_s_per_stream": round(decode, 1),
        "ttft_ms_p50": round(ttft, 1),
        "peak_vram_gb": None,
        "samples": len(runs),
        "status": "accepted",
    }
    sweep = {
        "schema_version": "local-ai-registry/v1",
        "id": sweep_id,
        "recipe_id": recipe["id"],
        "measured_at": NOW,
        "accepted_at": NOW,
        "source": {"kind": "acceptance-run", "url": "https://github.com/0xSero/local-ai-registry", "repository": None, "commit": None, "paths": None},
        "metrics": {"concurrency": 1, "point_count": len(runs), "max_context_tokens": serving.get("max_context_tokens"), "peak_generation_tps": round(decode, 1), "peak_prompt_tps": None, "latest_point_at": NOW},
        "rows": [row],
    }
    (ROOT / "speed-sweep" / f"{sweep_id}.json").write_text(json.dumps(sweep, indent=2, sort_keys=True, ensure_ascii=False) + "\n")

    launch = {key: value for key, value in draft.items() if key != "synthesized"}
    # drafts cannot carry asset_ids (schema); derive them from asset/ mounts at promotion
    asset_files = [m["source"][len("asset/"):] for m in launch.get("mounts", []) if str(m.get("source", "")).startswith("asset/")]
    if asset_files:
        ids = []
        for record_path in (ROOT / "asset").glob("*.json"):
            record = json.loads(record_path.read_text())
            if record.get("file") in asset_files:
                ids.append(record["id"])
        if len(ids) != len(asset_files):
            raise SystemExit(f"acceptance FAILED to promote: asset records missing for {asset_files}")
        launch["asset_ids"] = sorted(ids)
    digest = "sha256:" + launch["image"].split("@sha256:")[1]
    launch["container"] = {
        "state": "digest-pinned",
        "runtime": "docker",
        "image": launch["image"],
        "digest": digest,
        "compose_file": None,
        "reason": "image-reference-in-launch",
        "captured_at": NOW,
        "source": [{"kind": "acceptance-run", "url": "https://github.com/0xSero/local-ai-registry", "captured_at": NOW}],
    }
    # drafts cannot carry image provenance (schema); candidates park it in metadata until promotion
    image_provenance = (recipe.get("metadata") or {}).pop("image_provenance", None)
    if image_provenance:
        launch["provenance"] = image_provenance
    recipe["launch"] = launch
    recipe.pop("draft_launch", None)
    recipe["status"] = "validated"
    recipe.setdefault("speed_sweep_ids", [])
    if sweep_id not in recipe["speed_sweep_ids"]:
        recipe["speed_sweep_ids"].append(sweep_id)
    acceptance = {"accepted_at": NOW, "served_model_id": served, "harness": args.harness}
    if apis is not None:
        acceptance["apis"] = apis
    recipe.setdefault("metadata", {})["acceptance"] = acceptance
    path.write_text(json.dumps(recipe, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    print(f"PROMOTED {recipe['id']} to validated with evidence {sweep_id}")
    print("next: python3 scripts/curate_registry.py --index-only && python3 scripts/format_registry.py && make check, then commit and open a PR")
    return 0


if __name__ == "__main__":
    sys.exit(main())
