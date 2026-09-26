#!/usr/bin/env python3
"""Synthetic, local-only MTPLX acceptance evidence. No personal input is read.

Requires the pinned runtime's transformers and Pillow. Start a dedicated server
first: this harness clears its session cache before every measured request.
It records only synthetic answers and an allowlist of performance counters.
"""
import argparse
import base64
import datetime as dt
import hashlib
import io
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path


STATS = {
    "generation_mode", "mtp_depth", "speculative_depth", "requested_mtp_depth",
    "drafted_tokens", "accepted_drafts", "target_verify_cycles", "mtp_disabled_reason",
    "peak_memory_bytes", "active_memory_bytes", "cache_memory_bytes", "cached_tokens",
    "elapsed_s", "prompt_eval_time_s", "decode_tok_s", "prefill_tok_s",
    "kv_quantization", "paged_kv_quantization", "kv_quant_attention_calls",
    "paged_kv_quant", "paged_kv_quant_mode", "paged_kv_quant_kernel_calls",
    "paged_kv_quant_attention_calls", "paged_kv_quant_dequant_calls",
}


def http(endpoint, path, body=None):
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(endpoint + path, data=data,
                                     headers={"Content-Type": "application/json"})
    return urllib.request.urlopen(request, timeout=7200)


def picture():
    from PIL import Image, ImageDraw, ImageFont
    image = Image.new("RGB", (448, 256), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((15, 15, 150, 125), fill="red")
    draw.ellipse((260, 15, 385, 140), fill="blue")
    draw.text((35, 175), "ORBIT 7319", font=ImageFont.load_default(size=44), fill="black")
    output = io.BytesIO()
    image.save(output, format="PNG")
    data = output.getvalue()
    return "data:image/png;base64," + base64.b64encode(data).decode(), hashlib.sha256(data).hexdigest()


def long_prompt(model_path, minimum):
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True, trust_remote_code=False)
    # Deliberately synthetic filler; the three values only appear at distributed
    # positions in the body. No truncation or sliding-window success is accepted.
    filler = "The archive describes river surveys, mountain weather, library shelves, garden paths, and railway timetables.\n"
    unit = len(tokenizer.encode(filler, add_special_tokens=False))
    copies = minimum // unit + 20
    sections = [filler * (copies // 4) for _ in range(4)]
    body = (sections[0] + "\nALPHA secret: amber-falcon-4821\n" + sections[1]
            + "\nBETA secret: violet-otter-6953\n" + sections[2]
            + "\nGAMMA secret: silver-badger-1706\n" + sections[3])
    instruction = ("Find the ALPHA, BETA and GAMMA secrets in the archive below. "
                   "At the end, report all three exact values and the word and number visible in the attached image.\n")
    prompt = instruction + body + "\nNow return the three secrets and the image word and number."
    count = len(tokenizer.encode(prompt, add_special_tokens=False))
    if count < minimum:
        raise RuntimeError(f"Generated {count} tokens, below required {minimum}")
    return prompt, count


def run(endpoint, body, name):
    with http(endpoint, "/admin/cache/clear", {}) as response:
        json.load(response)
    started_at = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    start, first = time.perf_counter(), None
    text, reasoning, stats, usage, timings = [], [], {}, {}, {}
    with http(endpoint, "/v1/chat/completions", body) as response:
        for line in response:
            if not line.startswith(b"data: "):
                continue
            payload = line[6:].strip()
            if payload == b"[DONE]":
                break
            event = json.loads(payload)
            if event.get("error"):
                raise RuntimeError(str(event["error"]))
            usage.update(event.get("usage") or {})
            timings.update(event.get("timings") or {})
            stats.update({k: v for k, v in (event.get("mtplx_stats") or {}).items() if k in STATS})
            for choice in event.get("choices") or []:
                delta = choice.get("delta") or {}
                if delta.get("content") or delta.get("reasoning_content"):
                    if first is None:
                        first = time.perf_counter()
                    text.append(delta.get("content") or "")
                    reasoning.append(delta.get("reasoning_content") or "")
    end = time.perf_counter()
    completion = usage.get("completion_tokens", 0)
    result = {
        "name": name, "started_at": started_at, "elapsed_s": end - start,
        "ttft_ms": None if first is None else (first - start) * 1000,
        "client_post_first_token_estimate": None if first is None or end == first else max(0, completion - 1) / (end - first),
        "usage": usage, "timings": timings, "stats": stats,
        "response": "".join(text), "reasoning_tokens_present": bool("".join(reasoning)),
        "request": {k: body[k] for k in ("generation_mode", "depth", "temperature", "top_p", "top_k", "max_tokens", "enable_thinking")},
        "prompt_sha256": hashlib.sha256(json.dumps(body["messages"], sort_keys=True).encode()).hexdigest(),
    }
    if completion <= 0 or first is None:
        raise RuntimeError("No measured completion")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", default="http://127.0.0.1:18198")
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--model", default="qwen38-27b-mtplx-4bit")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--stage", choices=("short", "long"), required=True)
    parser.add_argument("--context-tokens", type=int, default=200000)
    args = parser.parse_args()
    if urllib.parse.urlparse(args.endpoint).hostname not in ("127.0.0.1", "localhost", "::1"):
        parser.error("This harness only permits a local dedicated endpoint")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    image, image_sha = picture()
    jobs = []
    if args.stage == "short":
        for mode, depth in (("ar", 0), ("mtp", 1), ("mtp", 2), ("mtp", 3)):
            for sample in range(3):
                jobs.append((f"speed-{mode}-d{depth}-{sample + 1}", mode, depth,
                             [{"role": "user", "content": f"Trial {sample + 1}: Write a detailed Python implementation of merge sort, with comments explaining each step and examples."}], []))
        jobs.append(("vision", "mtp", 3, [{"role": "user", "content": [
            {"type": "text", "text": "Read the word and number in this image and name the colors of the square and circle."},
            {"type": "image_url", "image_url": {"url": image}},
        ]}], ["orbit", "7319", "red", "blue"]))
    else:
        prompt, count = long_prompt(args.model_path, args.context_tokens)
        print(f"Synthetic text token count before template/image: {count}", flush=True)
        jobs.append(("context-200k-vision-mtp", "mtp", 3, [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": image}},
        ]}], ["amber-falcon-4821", "violet-otter-6953", "silver-badger-1706", "orbit", "7319"]))
    failed = False
    with args.output.open("x") as output:
        for name, mode, depth, messages, expected in jobs:
            print(f"Running {name}", flush=True)
            body = {"model": args.model, "messages": messages, "stream": True,
                    "stream_options": {"include_usage": True}, "max_tokens": 256,
                    "generation_mode": mode, "depth": depth, "enable_thinking": False,
                    "temperature": 0.7, "top_p": 0.8, "top_k": 20, "seed": 42,
                    "suppress_stats_footer": True}
            result = run(args.endpoint.rstrip("/"), body, name)
            result["image_sha256"] = image_sha if expected else None
            result["checks"] = {value: value in result["response"].lower() for value in expected}
            if args.stage == "long":
                result["checks"]["full_context"] = result["usage"].get("prompt_tokens", 0) >= args.context_tokens
                result["checks"]["cold_prefill"] = result["usage"].get("prompt_tokens_details", {}).get("cached_tokens", 0) == 0
            if mode == "mtp":
                result["checks"]["mtp_drafted"] = (result["timings"].get("draft_n", 0) or result["stats"].get("drafted_tokens", 0)) > 0
                result["checks"]["mtp_accepted"] = (result["timings"].get("draft_n_accepted", 0) or result["stats"].get("accepted_drafts", 0)) > 0
            failed |= not all(result["checks"].values())
            output.write(json.dumps(result, sort_keys=True) + "\n")
            output.flush()
            print(json.dumps({"name": name, "usage": result["usage"], "timings": result["timings"], "checks": result["checks"]}), flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
