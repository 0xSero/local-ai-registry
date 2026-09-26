#!/usr/bin/env python3
"""Acceptance probes for an OpenAI-compatible mlx-vlm server.

Gates: chat, tool call, vision (synthetic image with known answer), MTP
(draft acceptance reported by the server) and a long-context needle.
Writes one JSON report; exits non-zero when any requested gate fails.
"""

import argparse
import base64
import io
import json
import random
import sys
import time
import urllib.request

from PIL import Image, ImageDraw, ImageFont


def post(endpoint, body, timeout):
    request = urllib.request.Request(
        f"{endpoint}/v1/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    started = time.monotonic()
    with urllib.request.urlopen(request, timeout=timeout) as response:
        reply = json.load(response)
    reply["_wall_s"] = time.monotonic() - started
    return reply


def text_of(reply):
    return reply["choices"][0]["message"].get("content") or ""


def summary(reply):
    usage, timings = reply.get("usage") or {}, reply.get("timings") or {}
    return {
        "wall_s": round(reply["_wall_s"], 2),
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "prefill_tok_s": timings.get("prompt_per_second"),
        "decode_tok_s": timings.get("predicted_per_second"),
        "peak_memory_gb": timings.get("peak_memory"),
        "draft_kind": timings.get("draft_kind"),
        "draft_n": timings.get("draft_n"),
        "draft_n_accepted": timings.get("draft_n_accepted"),
    }


def chat(endpoint, model, **extra):
    body = {"model": model, "temperature": 0, "max_tokens": 512, **extra}
    return post(endpoint, body, timeout=600)


def gate_chat(endpoint, model):
    reply = chat(endpoint, model, messages=[{"role": "user", "content": "Reply with exactly: LOCAL_AI_READY"}])
    return "LOCAL_AI_READY" in text_of(reply), reply


def gate_tools(endpoint, model):
    tools = [{
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Current weather for a city",
            "parameters": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]},
        },
    }]
    reply = chat(endpoint, model, tools=tools,
                 messages=[{"role": "user", "content": "What is the weather in Lisbon? Use the tool."}])
    calls = reply["choices"][0]["message"].get("tool_calls") or []
    ok = any(c["function"]["name"] == "get_weather" and "lisbon" in c["function"]["arguments"].lower() for c in calls)
    return ok, reply


def gate_vision(endpoint, model):
    image = Image.new("RGB", (512, 512), "white")
    draw = ImageDraw.Draw(image)
    draw.ellipse((60, 60, 260, 260), fill=(220, 20, 20))
    draw.text((300, 330), "7394", fill="black", font=ImageFont.load_default(size=96))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    url = "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()
    reply = chat(endpoint, model, messages=[{"role": "user", "content": [
        {"type": "image_url", "image_url": {"url": url}},
        {"type": "text", "text": "What colour is the circle, and what number is written in the image? Answer in one short line."},
    ]}])
    answer = text_of(reply).lower()
    return "red" in answer and "7394" in answer, reply


def gate_mtp(endpoint, model):
    reply = chat(endpoint, model, max_tokens=384,
                 messages=[{"role": "user", "content": "Write a Python function that merges two sorted lists, with a docstring."}])
    timings = reply.get("timings") or {}
    ok = timings.get("draft_kind") == "mtp" and (timings.get("draft_n_accepted") or 0) > 0
    return ok, reply


def gate_reasoning(endpoint, model):
    reply = chat(endpoint, model, max_tokens=8192, chat_template_kwargs={"enable_thinking": True}, enable_thinking=True,
                 messages=[{"role": "user", "content": "A train leaves at 14:35 and arrives at 17:10. How many minutes is the trip? End with the number."}])
    message = reply["choices"][0]["message"]
    thought = message.get("reasoning_content") or message.get("reasoning") or ""
    return bool(thought.strip()) and "155" in (message.get("content") or ""), reply


FILLER = [
    "The archive ledger lists shipments of copper wire, grain, and lamp oil for the harbour district.",
    "Inspectors noted that the northern warehouse roof leaked during the autumn storms.",
    "A clerk copied the tide tables twice because the first copy smudged in the damp air.",
    "Merchants argued over the price of salt while the ferry waited at the pier.",
    "The lighthouse keeper recorded wind speed, cloud cover, and the number of passing ships.",
]


def gate_long(endpoint, model, target_tokens):
    rng = random.Random(0)
    code = "".join(rng.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(8))
    # ~20 tokens per filler sentence for this tokenizer; the server reports the exact count.
    sentences = [rng.choice(FILLER) for _ in range(target_tokens // 20)]
    sentences.insert(len(sentences) // 10, f"IMPORTANT: the vault access code is {code}. Remember it.")
    prompt = " ".join(sentences) + "\n\nWhat is the vault access code mentioned in the text above? Reply with only the code."
    reply = post(endpoint, {"model": model, "temperature": 0, "max_tokens": 4096,
                            "messages": [{"role": "user", "content": prompt}]}, timeout=7200)
    return code in text_of(reply), reply


def gate_long_vision(endpoint, model, target_tokens):
    """Vision and long context in one request: the synthetic image plus a needle haystack."""
    rng = random.Random(1)
    code = "".join(rng.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(8))
    sentences = [rng.choice(FILLER) for _ in range(target_tokens // 20)]
    sentences.insert(len(sentences) // 2, f"IMPORTANT: the vault access code is {code}. Remember it.")
    image = Image.new("RGB", (512, 512), "white")
    draw = ImageDraw.Draw(image)
    draw.ellipse((60, 60, 260, 260), fill=(220, 20, 20))
    draw.text((300, 330), "7394", fill="black", font=ImageFont.load_default(size=96))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    url = "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()
    question = ("\n\nAnswer in one line: the vault access code from the text, the colour of the circle in the image, "
                "and the number written in the image.")
    reply = post(endpoint, {"model": model, "temperature": 0, "max_tokens": 4096, "messages": [{"role": "user", "content": [
        {"type": "image_url", "image_url": {"url": url}},
        {"type": "text", "text": " ".join(sentences) + question},
    ]}]}, timeout=7200)
    answer = text_of(reply).lower()
    return code.lower() in answer and "red" in answer and "7394" in answer, reply


GATES = {"chat": gate_chat, "reasoning": gate_reasoning, "tools": gate_tools, "vision": gate_vision, "mtp": gate_mtp, "long": gate_long, "long_vision": gate_long_vision}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--endpoint", default="http://127.0.0.1:8080")
    parser.add_argument("--gates", default="chat,reasoning,tools,vision,mtp,long")
    parser.add_argument("--long-tokens", type=int, default=200000)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    with urllib.request.urlopen(f"{args.endpoint}/v1/models", timeout=30) as response:
        models = [m["id"] for m in json.load(response)["data"]]
    with urllib.request.urlopen(f"{args.endpoint}/health", timeout=30) as response:
        model = json.load(response).get("loaded_model") or models[0]

    report = {"endpoint": args.endpoint, "model": model, "gates": {}}
    for name in args.gates.split(","):
        extra = (args.long_tokens,) if name in ("long", "long_vision") else ()
        try:
            ok, reply = GATES[name](args.endpoint, model, *extra)
            report["gates"][name] = {"pass": ok, **summary(reply), "answer": text_of(reply)[-400:],
                                     "tool_calls": reply["choices"][0]["message"].get("tool_calls")}
        except Exception as exc:
            report["gates"][name] = {"pass": False, "error": f"{type(exc).__name__}: {exc}"}
        print(name, json.dumps({k: v for k, v in report["gates"][name].items() if k != "answer"}), flush=True)
        with open(args.out, "w") as f:
            json.dump(report, f, indent=2)
    return 0 if all(g["pass"] for g in report["gates"].values()) else 1


if __name__ == "__main__":
    sys.exit(main())
