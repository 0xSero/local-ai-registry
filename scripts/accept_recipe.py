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
import math
import re
import shlex
import ssl
import sys
import time
import urllib.error
import urllib.request
from contextlib import nullcontext
from pathlib import Path

from import_localmaxxing import server_context_limit
from sweep_metrics import derive_metrics

ROOT = Path(__file__).resolve().parent.parent / "registry"
CTX = ssl.create_default_context()


def http_json(url, payload=None, timeout=120):
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout, context=CTX) as response:
        return json.load(response)


def measure(endpoint, model, prompt_tokens=256, samples=3, request_body=None, raw_output=None):
    prompt = "Summarize the history of computing. " * (prompt_tokens // 8)
    body = dict(request_body) if request_body is not None else {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
    }
    body.setdefault("model", model)
    if body["model"] != model or body.get("n", 1) != 1:
        raise ValueError("acceptance requires one completion from the selected model")
    body["stream"] = True
    body["stream_options"] = {**(body.get("stream_options") or {}), "include_usage": True}
    url = f"{endpoint}/v1/chat/completions"
    rows = []
    # Line-buffered JSONL preserves completed samples and partial responses on failure.
    output = Path(raw_output).open("x", encoding="utf-8", buffering=1) if raw_output else nullcontext(None)
    with output as raw_file:
        def record(event, sample, elapsed_ms, **data):
            if raw_file is not None:
                raw_file.write(json.dumps({
                    "event": event, "sample": sample,
                    "at": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
                    "elapsed_ms": elapsed_ms, **data,
                }, ensure_ascii=False) + "\n")

        for sample in range(1, samples + 1):
            started_at = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
            started = time.monotonic()
            first = last = None
            usage, timings = {}, {}
            content, reasoning, response_models = [], [], set()
            finish_reason = None
            done = False
            request = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
            record("request", sample, 0, url=url, body=body)
            try:
                with urllib.request.urlopen(request, timeout=600, context=CTX) as response:
                    for line in response:
                        received = time.monotonic()
                        record("sse", sample, (received - started) * 1000, line=line.decode("utf-8", errors="replace"))
                        if not line.startswith(b"data:"):
                            continue
                        raw = line[5:].strip()
                        if raw == b"[DONE]":
                            done = True
                            break
                        chunk = json.loads(raw)
                        if chunk.get("error"):
                            raise RuntimeError(f"server error: {chunk['error']}")
                        if chunk.get("model"):
                            response_models.add(chunk["model"])
                        if isinstance(chunk.get("usage"), dict):
                            usage.update(chunk["usage"])
                        if isinstance(chunk.get("timings"), dict):
                            timings.update(chunk["timings"])
                        for choice in chunk.get("choices") or []:
                            if choice.get("index", 0) != 0:
                                raise RuntimeError("server returned more than one completion")
                            delta = choice.get("delta") or {}
                            if (delta.get("content") or delta.get("reasoning_content") or any(
                                    (call.get("function") or {}).get("name") or (call.get("function") or {}).get("arguments")
                                    for call in delta.get("tool_calls") or [])):
                                if first is None:
                                    first = received
                                last = received
                            content.append(delta.get("content") or "")
                            reasoning.append(delta.get("reasoning_content") or "")
                            if choice.get("finish_reason") is not None:
                                finish_reason = choice["finish_reason"]
                finished = time.monotonic()
                prompt_count = usage.get("prompt_tokens")
                completion_tokens = usage.get("completion_tokens")
                if (first is None or type(prompt_count) is not int or prompt_count < 0
                        or type(completion_tokens) is not int or completion_tokens < 8):
                    raise RuntimeError("the server produced no usable completion or token usage")
                if not done or finish_reason is None:
                    raise RuntimeError("the completion stream ended without a finish reason and [DONE]")
                interval = last - first
                # SSE chunks may batch tokens: this is a client estimate, not server decode time.
                client_decode = (completion_tokens - 1) / interval if interval > 0 else None
                server_decode = timings.get("predicted_per_second")
                server_prefill = timings.get("prompt_per_second")
                for value in (server_decode, server_prefill):
                    if value is not None and (type(value) not in (int, float) or not math.isfinite(value) or value < 0):
                        raise RuntimeError("server reported an invalid timing rate")
                if server_decode == 0:
                    raise RuntimeError("server reported a zero decode rate")
                if server_decode is None and client_decode is None:
                    raise RuntimeError("no server decode timing or measurable client decode interval")
                result = {
                    "started_at": started_at, "elapsed_ms": (finished - started) * 1000,
                    "ttft_ms": (first - started) * 1000,
                    "decode_tok_s": server_decode if server_decode is not None else client_decode,
                    "decode_method": "timings.predicted_per_second" if server_decode is not None else "client_post_first_token_estimate",
                    "client_decode_ms": interval * 1000, "client_decode_tok_s": client_decode,
                    "server_decode_tok_s": server_decode, "server_prefill_tok_s": server_prefill,
                    "prompt_tokens": prompt_count, "tokens": completion_tokens,
                    "usage": usage, "timings": timings, "response_model_ids": sorted(response_models),
                    "finish_reason": finish_reason, "content": "".join(content), "reasoning_content": "".join(reasoning),
                }
                rows.append(result)
                record("result", sample, (finished - started) * 1000, result=result)
            except (Exception, KeyboardInterrupt) as exc:
                error = {"type": type(exc).__name__, "message": str(exc)}
                if isinstance(exc, urllib.error.HTTPError):
                    error["response_body"] = exc.read().decode("utf-8", errors="replace")
                record("error", sample, (time.monotonic() - started) * 1000, error=error)
                raise
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
    parser.add_argument("--min-decode", type=float, default=5.0, help="minimum accepted decode tok/s")
    parser.add_argument("--gateway", help="path to the plugin gateway (gateway.py); probes all three dialects through it")
    parser.add_argument("--revalidate", action="store_true", help="re-run acceptance on an already validated recipe and refresh its evidence")
    parser.add_argument("--request-json", type=Path, help="chat request body; model defaults to the served id, streaming usage is enabled")
    parser.add_argument("--raw-output", type=Path, help="new JSONL file for requests, timestamped SSE lines, results, and errors")
    args = parser.parse_args()

    path = ROOT / "recipe" / f"{args.recipe_id}.json"
    recipe = json.loads(path.read_text())
    draft = recipe.get("draft_launch") or (recipe["launch"] if recipe["launch"].get("kind") in ("docker", "script") else None)
    if draft is None or (recipe["status"] != "candidate" and not args.revalidate):
        raise SystemExit("acceptance only applies to candidates with a docker draft, docker launch, or pinned script launch (or --revalidate)")
    if draft.get("kind") == "script":
        if not re.search(r"(?:^|/)[0-9a-f]{40}/", str((draft.get("script") or {}).get("file") or "")):
            raise SystemExit("acceptance FAILED: native script must be commit-pinned before acceptance")
        if not isinstance((recipe.get("serving") or {}).get("max_context_tokens"), int):
            raise SystemExit("acceptance FAILED: native script must state serving.max_context_tokens")
        native_instance = json.loads((ROOT / "model-instance" / f"{recipe['model_instance_id']}.json").read_text())
        if not re.fullmatch(r"[0-9a-f]{40}", str(native_instance.get("revision") or "")):
            raise SystemExit("acceptance FAILED: native model revision must be pinned before acceptance")

    request_body = json.loads(args.request_json.read_text()) if args.request_json else None
    if request_body is not None and not isinstance(request_body, dict):
        parser.error("--request-json must contain an object")
    models = [entry["id"] for entry in http_json(f"{args.endpoint}/v1/models").get("data", [])]
    if not models:
        raise SystemExit("acceptance FAILED: the server reports no models")
    served = (request_body or {}).get("model")
    if served is None:
        # /v1/models advertises every model the server can serve; /v1/health names the loaded one.
        try:
            loaded = http_json(f"{args.endpoint}/v1/health").get("model_loaded")
        except Exception:
            loaded = None
        served = loaded if isinstance(loaded, str) and loaded else models[0]
    if served not in models:
        raise SystemExit(f"acceptance FAILED: requested model {served!r} is absent from /v1/models")
    if draft.get("kind") == "script" and served != native_instance.get("served_name"):
        raise SystemExit("acceptance FAILED: native endpoint served model does not match the pinned instance")
    print(f"server is healthy; serving model id: {served}")
    apis = probe_dialects(args.endpoint, served, args.gateway)
    if apis is not None:
        print(f"dialects through the gateway: {', '.join(apis) or 'none'}")
        if "chat" not in apis:
            raise SystemExit("acceptance FAILED: the gateway could not complete a chat request against the engine")
    try:
        runs = measure(args.endpoint, served, request_body=request_body, raw_output=args.raw_output)
    except (OSError, ValueError, RuntimeError) as exc:
        raise SystemExit(f"acceptance FAILED: {exc}") from None
    if len({run["prompt_tokens"] for run in runs}) != 1 or len({run["decode_method"] for run in runs}) != 1:
        raise SystemExit("acceptance FAILED: samples disagree on prompt token count or decode measurement method")
    decode = sorted(run["decode_tok_s"] for run in runs)[len(runs) // 2]
    ttft = sorted(run["ttft_ms"] for run in runs)[len(runs) // 2]
    completion_tokens = sorted(run["tokens"] for run in runs)[len(runs) // 2]
    prefill_runs = [run["server_prefill_tok_s"] for run in runs if run["server_prefill_tok_s"] is not None]
    prefill = sorted(prefill_runs)[len(prefill_runs) // 2] if len(prefill_runs) == len(runs) else None
    print(f"acceptance measurements: decode {decode:.1f} tok/s ({runs[0]['decode_method']}), ttft {ttft:.0f} ms over {len(runs)} samples")
    if decode < args.min_decode:
        raise SystemExit(f"acceptance FAILED: decode {decode:.1f} tok/s is below the {args.min_decode} tok/s floor")

    instance_path = ROOT / "model-instance" / f"{recipe['model_instance_id']}.json"
    instance = json.loads(instance_path.read_text())
    if not (isinstance(instance.get("revision"), str) and re.fullmatch(r"[0-9a-f]{40}", instance["revision"] or "")):
        instance["revision"] = pinned_revision(instance["repository"])
        instance_path.write_text(json.dumps(instance, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
        print(f"pinned model revision {instance['revision'][:12]}")

    serving = recipe.setdefault("serving", {})
    if serving.get("max_context_tokens") is None:
        serving["max_context_tokens"] = server_context_limit({
            "engineFlags": {"commandSnippet": shlex.join(draft.get("arguments", []))},
        }, environment=draft.get("environment"))
    if serving.get("max_context_tokens") is None:
        raise SystemExit("acceptance FAILED to promote: serving.max_context_tokens unknown and not stated in the draft")

    now = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    sweep_id = f"{recipe['id']}-acceptance"
    row = {
        "concurrency": 1,
        "context_tokens": runs[0]["prompt_tokens"],
        "output_tokens": completion_tokens,
        "prefill_tok_s": round(prefill, 1) if prefill is not None else None,
        "decode_tok_s": round(decode, 1),
        "decode_tok_s_per_stream": round(decode, 1),
        "ttft_ms_p50": round(ttft, 1),
        "peak_vram_gb": None,
        "samples": len(runs),
        "status": "accepted",
        "decode_method": runs[0]["decode_method"],
        "measurements": [{key: value for key, value in run.items() if key not in ("content", "reasoning_content")} for run in runs],
    }
    sweep = {
        "schema_version": "local-ai-registry/v1",
        "id": sweep_id,
        "recipe_id": recipe["id"],
        "measured_at": runs[0]["started_at"],
        "accepted_at": now,
        "source": {"kind": "acceptance-run", "url": "https://github.com/0xSero/local-ai-registry", "repository": None, "commit": None, "paths": None},
        "metrics": derive_metrics([row], runs[0]["started_at"]),
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
    is_docker = launch.get("kind") == "docker"
    digest = "sha256:" + launch["image"].split("@sha256:")[1] if is_docker else None
    launch["container"] = {
        "state": "digest-pinned" if is_docker else "none",
        "runtime": "docker" if is_docker else None,
        "image": launch["image"] if is_docker else None,
        "digest": digest,
        "compose_file": None,
        "reason": "image-reference-in-launch" if is_docker else "commit-pinned-native-script",
        "captured_at": now,
        "source": [{"kind": "acceptance-run", "url": "https://github.com/0xSero/local-ai-registry", "captured_at": now}],
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
    acceptance = {"accepted_at": now, "served_model_id": served, "harness": args.harness}
    if apis is not None:
        acceptance["apis"] = apis
    recipe.setdefault("metadata", {})["acceptance"] = acceptance
    path.write_text(json.dumps(recipe, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    print(f"PROMOTED {recipe['id']} to validated with evidence {sweep_id}")
    print("next: python3 scripts/curate_registry.py --index-only && python3 scripts/format_registry.py && make check, then commit and open a PR")
    return 0


if __name__ == "__main__":
    sys.exit(main())
