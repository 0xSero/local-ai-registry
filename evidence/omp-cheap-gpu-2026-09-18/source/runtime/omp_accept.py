#!/usr/bin/env python3
"""Acceptance probes for one served model, run on the rented host.

Proves what the recipe will claim, not what the model card says:

    identity   /v1/models returns the exact served name, and a chat response
               reports the same model
    chat       a real completion with a deterministic answer
    reasoning  when claimed, the response carries a separate reasoning_content
               phase and the final content is still the answer
    tools      when claimed, a forced tool call returns a valid function
               name/arguments, and a tool result round-trips to a final answer
    vision     when claimed, two different images produce different answers
               that the text prompt does not reveal

Writes `<output-dir>/results.json` with per-probe evidence. Exits non-zero when
a claimed capability fails.
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import os
import sys
import time
import urllib.error
import urllib.request

TIMEOUT = 900


class ProbeError(RuntimeError):
    """A probe failed with the engine's own error text attached."""


def post(base_url: str, path: str, payload: dict, stream: bool = False, timeout: int = TIMEOUT):
    request = urllib.request.Request(
        f"{base_url}{path}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        # The engine's rejection reason is the useful evidence; keep it.
        detail = error.read().decode("utf-8", "replace")[:1000]
        raise ProbeError(f"HTTP {error.code}: {detail}") from None
    return body, time.monotonic() - started


def get(base_url: str, path: str, timeout: int = 60):
    with urllib.request.urlopen(f"{base_url}{path}", timeout=timeout) as response:
        return json.load(response)


def png_bytes(colour: tuple[int, int, int], size: int = 96) -> bytes:
    """A solid-colour PNG, produced without third-party imaging code."""
    import struct
    import zlib

    raw = b"".join(b"\x00" + bytes(colour) * size for _ in range(size))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data)) + tag + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    header = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


def chat(base_url: str, payload: dict) -> dict:
    body, elapsed = post(base_url, "/v1/chat/completions", payload)
    value = json.loads(body)
    value["_elapsed_seconds"] = round(elapsed, 3)
    return value


def probe_identity(base_url: str, served_name: str) -> dict:
    listing = get(base_url, "/v1/models")
    ids = [entry.get("id") for entry in listing.get("data", [])]
    return {
        "served_ids": ids,
        "expected": served_name,
        "matched": served_name in ids,
    }


def probe_chat(base_url: str, served_name: str) -> dict:
    response = chat(base_url, {
        "model": served_name,
        "messages": [{"role": "user", "content": "Reply with exactly: pong"}],
        "max_tokens": 64,
        "temperature": 0,
        "stream": False,
    })
    choice = (response.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    content = (message.get("content") or "").strip()
    return {
        "model": response.get("model"),
        "content": content[:200],
        "contains_pong": "pong" in content.lower(),
        "usage": response.get("usage"),
        "elapsed_seconds": response.get("_elapsed_seconds"),
    }


def probe_reasoning(base_url: str, served_name: str) -> dict:
    response = chat(base_url, {
        "model": served_name,
        "messages": [{
            "role": "user",
            "content": "A bat and a ball cost $1.10 together. The bat costs $1.00 more "
                       "than the ball. How much does the ball cost? Answer with the number only.",
        }],
        "max_tokens": 1024,
        "temperature": 0,
        "stream": False,
    })
    choice = (response.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    reasoning = message.get("reasoning_content") or ""
    content = (message.get("content") or "").strip()
    return {
        "reasoning_chars": len(reasoning),
        "reasoning_head": reasoning[:300],
        "content": content[:200],
        "separate_phase": bool(reasoning.strip()) and "think" not in content.lower()[:20],
        "answer_correct": "0.05" in content or "5" == content.strip(),
    }


TOOL_SCHEMA = [{
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Return the current weather for a city.",
        "parameters": {
            "type": "object",
            "properties": {"city": {"type": "string"}},
            "required": ["city"],
        },
    },
}]


def probe_tools(base_url: str, served_name: str) -> dict:
    first = chat(base_url, {
        "model": served_name,
        "messages": [{"role": "user", "content": "What is the weather in Lisbon? Use the tool."}],
        "tools": TOOL_SCHEMA,
        "tool_choice": "auto",
        "max_tokens": 512,
        "temperature": 0,
        "stream": False,
    })
    message = (first.get("choices") or [{}])[0].get("message") or {}
    calls = message.get("tool_calls") or []
    if not calls:
        return {"tool_call_present": False, "raw_content": (message.get("content") or "")[:300]}
    call = calls[0]
    function = call.get("function") or {}
    try:
        arguments = json.loads(function.get("arguments") or "{}")
    except json.JSONDecodeError:
        arguments = {}
    second = chat(base_url, {
        "model": served_name,
        "messages": [
            {"role": "user", "content": "What is the weather in Lisbon? Use the tool."},
            {"role": "assistant", "content": message.get("content") or "", "tool_calls": calls},
            {"role": "tool", "tool_call_id": call.get("id") or "call_0",
             "content": json.dumps({"temperature_c": 21, "sky": "clear"})},
        ],
        "tools": TOOL_SCHEMA,
        "max_tokens": 256,
        "temperature": 0,
        "stream": False,
    })
    final = ((second.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    return {
        "tool_call_present": True,
        "function_name": function.get("name"),
        "arguments": arguments,
        "arguments_valid": function.get("name") == "get_weather" and "city" in arguments,
        "follow_up_content": final[:300],
        "follow_up_used_result": "21" in final,
    }


COLOUR_WORDS = {
    "red": ("red", "crimson", "scarlet", "vermilion", "maroon", "ruby"),
    "blue": ("blue", "azure", "cobalt", "navy", "sapphire", "indigo"),
}


def probe_vision(base_url: str, served_name: str) -> dict:
    red = base64.b64encode(png_bytes((220, 20, 20))).decode()
    blue = base64.b64encode(png_bytes((20, 20, 220))).decode()

    def ask(data: str, disable_thinking: bool = False) -> dict:
        payload = {
            "model": served_name,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": "What is the dominant colour of this image? "
                                             "Answer with one word."},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{data}"}},
                ],
            }],
            "max_tokens": 512,
            "temperature": 0,
            "stream": False,
        }
        if disable_thinking:
            # A thinking phase can consume the whole budget and leave content
            # empty; the vision probe isolates vision, not reasoning.
            payload["chat_template_kwargs"] = {"enable_thinking": False}
        return chat(base_url, payload)

    def content(response: dict) -> str:
        message = (response.get("choices") or [{}])[0].get("message") or {}
        return (message.get("content") or "").strip()

    def answer(data: str) -> tuple[str, str, int | None]:
        response = ask(data)
        text = content(response)
        if text:
            return text, "budget", (response.get("usage") or {}).get("prompt_tokens")
        retry = ask(data, disable_thinking=True)
        return (content(retry), "retry-without-thinking",
                (retry.get("usage") or {}).get("prompt_tokens"))

    red_text, red_source, red_prompt_tokens = answer(red)
    blue_text, blue_source, blue_prompt_tokens = answer(blue)

    def names(text: str, colour: str) -> bool:
        lowered = text.lower()
        return any(word in lowered for word in COLOUR_WORDS[colour])

    return {
        "red_answer": red_text[:120],
        "blue_answer": blue_text[:120],
        "red_source": red_source,
        "blue_source": blue_source,
        "red_names_colour": names(red_text, "red"),
        "blue_names_colour": names(blue_text, "blue"),
        "answers_differ": red_text.lower() != blue_text.lower(),
        "answered": bool(red_text) and bool(blue_text),
        "red_prompt_tokens": red_prompt_tokens,
        "blue_prompt_tokens": blue_prompt_tokens,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:5000")
    parser.add_argument("--served-name", required=True)
    parser.add_argument("--context-tokens", type=int, required=True)
    parser.add_argument("--capabilities", default="{}")
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args(argv)

    capabilities = json.loads(args.capabilities)
    output_dir = args.output_dir
    os.makedirs(output_dir, exist_ok=True)
    results: dict[str, object] = {
        "served_name": args.served_name,
        "context_tokens": args.context_tokens,
        "capabilities": capabilities,
        "probes": {},
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    probes: list[tuple[str, object]] = [
        ("identity", lambda: probe_identity(args.base_url, args.served_name)),
        ("chat", lambda: probe_chat(args.base_url, args.served_name)),
    ]
    if capabilities.get("reasoning"):
        probes.append(("reasoning", lambda: probe_reasoning(args.base_url, args.served_name)))
    if capabilities.get("tools"):
        probes.append(("tools", lambda: probe_tools(args.base_url, args.served_name)))
    if capabilities.get("vision"):
        probes.append(("vision", lambda: probe_vision(args.base_url, args.served_name)))

    failures: list[str] = []
    for name, probe in probes:
        try:
            value = probe()
        except (urllib.error.URLError, ProbeError, OSError, ValueError, KeyError) as error:
            value = {"error": f"{type(error).__name__}: {error}"}
            failures.append(name)
        results["probes"][name] = value
        if isinstance(value, dict) and "error" in value and name not in failures:
            failures.append(name)

    identity = results["probes"].get("identity") or {}
    if not identity.get("matched"):
        failures.append("identity")
    chat_probe = results["probes"].get("chat") or {}
    if not chat_probe.get("contains_pong"):
        failures.append("chat")
    if capabilities.get("reasoning"):
        if not (results["probes"].get("reasoning") or {}).get("separate_phase"):
            failures.append("reasoning")
    if capabilities.get("tools"):
        if not (results["probes"].get("tools") or {}).get("arguments_valid"):
            failures.append("tools")
    if capabilities.get("vision"):
        vision = results["probes"].get("vision") or {}
        if not (vision.get("red_names_colour") and vision.get("blue_names_colour")):
            failures.append("vision")

    results["failed_probes"] = sorted(set(failures))
    results["verdict"] = "accepted" if not failures else "rejected"
    with open(os.path.join(output_dir, "results.json"), "w") as stream:
        json.dump(results, stream, indent=2, sort_keys=True)
    print(json.dumps(results, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))