#!/usr/bin/env python3
"""Capture native Apple inference evidence without changing registry status.

Only the Python standard library is required. Long-context requests must be
prepared with the model's real tokenizer and supplied with --request-json;
the gate uses the server's measured usage, never a character-count estimate.
Every run has its own directory, including failed and interrupted streams.
"""

import argparse
import base64
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import struct
import subprocess
import time
from datetime import datetime, timezone
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zlib


TIMING_FIELDS = {
    "cache_n", "prompt_n", "prompt_ms", "prompt_per_second", "predicted_n",
    "predicted_ms", "predicted_per_second", "peak_memory", "draft_kind",
    "draft_rounds", "draft_n", "draft_n_accepted", "draft_acceptance_rate",
}


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, allow_nan=False,
                       sort_keys=True, indent=2) + "\n").encode("utf-8")


def reject_json_constant(value):
    raise ValueError("invalid JSON numeric constant: " + value)


def chat_url(endpoint):
    parsed = urllib.parse.urlsplit(endpoint)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("--endpoint must be an HTTP(S) URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("endpoint credentials, query strings and fragments are not allowed")
    path = parsed.path.rstrip("/")
    if path.endswith("/chat/completions"):
        return endpoint.rstrip("/")
    if not path.endswith("/v1"):
        path += "/v1"
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc,
                                   path + "/chat/completions", "", ""))


def vision_png(width=256, height=128):
    """A red left panel and blue right panel, with no labels or metadata."""
    def chunk(kind, payload):
        checksum = zlib.crc32(kind + payload) & 0xFFFFFFFF
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", checksum)

    row = b"\x00" + b"\xff\x00\x00" * (width // 2) + b"\x00\x00\xff" * (width - width // 2)
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(row * height)) + chunk(b"IEND", b""))


def build_request(args, image_data=None):
    if args.kind == "request":
        if not args.request_json:
            raise ValueError("--kind request requires --request-json")
        body = json.loads(Path(args.request_json).read_text(), parse_constant=reject_json_constant)
        if not isinstance(body, dict):
            raise ValueError("request JSON must be an object")
        if body.get("model", args.model) != args.model:
            raise ValueError("request model differs from --model")
    else:
        if args.request_json:
            raise ValueError("--request-json requires --kind request")
        if args.kind == "vision":
            content = [
                {"type": "text", "text": args.prompt or
                 "Name the two solid colors in this image from left to right. "
                 "Reply with only the two color names, separated by a comma."},
                {"type": "image_url", "image_url": {
                    "url": "data:image/png;base64," + base64.b64encode(image_data).decode("ascii")}},
            ]
        else:
            content = args.prompt or "Compute 17 + 25. Reply with just the integer."
        body = {"messages": [{"role": "user", "content": content}],
                "temperature": 0, "max_tokens": args.max_tokens, "cache_prompt": False}
    if not isinstance(body.get("messages"), list) or not body["messages"]:
        raise ValueError("request must include a nonempty messages array")
    if body.get("n", 1) != 1:
        raise ValueError("this probe measures one completion; n must be 1")
    options = body.get("stream_options") or {}
    if not isinstance(options, dict):
        raise ValueError("stream_options must be an object")
    return {**body, "model": args.model, "stream": True,
            "stream_options": {**options, "include_usage": True}}


def command_observation(argv):
    try:
        result = subprocess.run(argv, capture_output=True, text=True, timeout=10, check=False)
        return {"command": argv, "returncode": result.returncode,
                "stdout": result.stdout.strip(), "stderr": result.stderr.strip()}
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"command": argv, "error": str(error)}


def hardware_observation():
    return {"platform": platform.system(), "machine": platform.machine(),
            "macos_version": platform.mac_ver()[0],
            "chip": command_observation(["sysctl", "-n", "machdep.cpu.brand_string"]),
            "memory_bytes": command_observation(["sysctl", "-n", "hw.memsize"])}


def memory_observation():
    return {"at": utc_now(), "vm_stat": command_observation(["vm_stat"]),
            "swap": command_observation(["sysctl", "vm.swapusage"])}


def finite_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def nonnegative_count(value):
    return finite_number(value) and value >= 0 and int(value) == value


class StreamCapture:
    """Parse SSE while retaining incomplete output and explicit failure reasons."""

    def __init__(self):
        self.content = ""
        self.reasoning = ""
        self.usage = {}
        self.timings = {}
        self.models = set()
        self.finish_reason = None
        self.done = False
        self.first_output_ms = None
        self.first_content_ms = None
        self.last_output_ms = None
        self.errors = []
        self.pending = []
        self.event_count = 0

    def feed(self, line, elapsed_ms):
        if not line.strip():
            self.dispatch(elapsed_ms)
        elif line.startswith("data:"):
            self.pending.append(line[5:].lstrip(" ").rstrip("\r\n"))
        elif line.startswith((":", "event:", "id:", "retry:")):
            pass
        else:
            self.errors.append("unrecognized SSE line")

    def dispatch(self, elapsed_ms):
        if not self.pending:
            return
        data = "\n".join(self.pending)
        self.pending.clear()
        if self.done:
            self.errors.append("data received after [DONE]")
            return
        if data == "[DONE]":
            self.done = True
            return
        try:
            chunk = json.loads(data, parse_constant=reject_json_constant)
        except (ValueError, TypeError):
            self.errors.append("malformed SSE JSON")
            return
        if not isinstance(chunk, dict):
            self.errors.append("SSE payload is not an object")
            return
        self.event_count += 1
        if chunk.get("error") is not None:
            self.errors.append("server error: " + json.dumps(chunk["error"], ensure_ascii=False))
        if isinstance(chunk.get("model"), str):
            self.models.add(chunk["model"])
        if isinstance(chunk.get("usage"), dict):
            self.usage.update(chunk["usage"])
        for name in ("timings", "generation_timings"):
            if isinstance(chunk.get(name), dict):
                self.timings.update(chunk[name])
        self.timings.update({key: chunk[key] for key in TIMING_FIELDS if key in chunk})
        choices = chunk.get("choices", [])
        if not isinstance(choices, list):
            self.errors.append("choices is not an array")
            return
        for choice in choices:
            if not isinstance(choice, dict):
                self.errors.append("choice is not an object")
                continue
            if choice.get("index", 0) != 0:
                self.errors.append("unexpected completion index")
                continue
            delta = choice.get("delta", {})
            if not isinstance(delta, dict):
                self.errors.append("delta is not an object")
                continue
            content = delta.get("content") or ""
            reasoning = delta.get("reasoning_content") or delta.get("reasoning") or ""
            if not isinstance(content, str) or not isinstance(reasoning, str):
                self.errors.append("non-text content or reasoning delta")
                continue
            if content or reasoning:
                if self.first_output_ms is None:
                    self.first_output_ms = elapsed_ms
                self.last_output_ms = elapsed_ms
            if content and self.first_content_ms is None:
                self.first_content_ms = elapsed_ms
            self.content += content
            self.reasoning += reasoning
            if choice.get("finish_reason") is not None:
                self.finish_reason = choice["finish_reason"]

    def finish(self, elapsed_ms, min_prompt_tokens=0, require_mtp=False, expect=None,
               expected_model=None):
        self.dispatch(elapsed_ms)
        failures = list(self.errors)
        if not self.done:
            failures.append("stream has no [DONE] marker")
        if self.finish_reason not in ("stop", "length"):
            failures.append("stream has no successful completion finish_reason")
        if not self.content.strip():
            failures.append("completion contains no answer text")
        prompt_tokens = self.usage.get("prompt_tokens")
        completion_tokens = self.usage.get("completion_tokens")
        if not nonnegative_count(prompt_tokens):
            failures.append("usage.prompt_tokens must be a nonnegative integer")
        if not nonnegative_count(completion_tokens) or completion_tokens <= 0:
            failures.append("usage.completion_tokens must be a positive integer")
        if expected_model is not None and self.models != {expected_model}:
            failures.append("response must report only the exact requested model identity")
        if min_prompt_tokens:
            if not nonnegative_count(prompt_tokens) or prompt_tokens < min_prompt_tokens:
                failures.append("measured usage.prompt_tokens is below the required minimum or absent")
            if not nonnegative_count(self.timings.get("cache_n")) or self.timings["cache_n"] != 0:
                failures.append("cold prefill requires explicit timings.cache_n=0")
            details = self.usage.get("prompt_tokens_details")
            if isinstance(details, dict) and "cached_tokens" in details:
                cached = details["cached_tokens"]
                if not nonnegative_count(cached) or cached != 0:
                    failures.append("usage reports cached prompt tokens or an invalid cached-token count")
        kind = self.timings.get("draft_kind")
        counters = {key: self.timings.get(key)
                    for key in ("draft_rounds", "draft_n", "draft_n_accepted")}
        mtp_proven = (isinstance(kind, str) and kind.lower() == "mtp"
                      and all(nonnegative_count(value) and value > 0 for value in counters.values())
                      and counters["draft_n_accepted"] <= counters["draft_n"])
        if require_mtp and not mtp_proven:
            failures.append("MTP requires draft_kind=mtp and positive, consistent draft counters")
        correctness = None if expect is None else expect.casefold() in self.content.casefold()
        if correctness is False:
            failures.append("answer does not contain the expected substring")
        return {
            "passed": not failures, "failures": failures, "stream_done": self.done,
            "finish_reason": self.finish_reason, "content": self.content,
            "reasoning_content": self.reasoning, "usage": self.usage, "timings": self.timings,
            "response_model_ids": sorted(self.models), "sse_event_count": self.event_count,
            "elapsed_ms": elapsed_ms, "first_output_ms": self.first_output_ms,
            "first_content_ms": self.first_content_ms, "last_output_ms": self.last_output_ms,
            "mtp_proven": mtp_proven, "correctness_passed": correctness,
            "gates": {"min_prompt_tokens": min_prompt_tokens, "require_mtp": require_mtp,
                      "expected_substring": expect, "expected_model": expected_model},
        }


def run_probe(args):
    url = chat_url(args.endpoint)
    image_data = vision_png() if args.kind == "vision" else None
    body = build_request(args, image_data)
    request_data = json_bytes(body)
    request_sha = hashlib.sha256(request_data).hexdigest()
    run_name = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ") + "-" + args.kind + "-" + uuid.uuid4().hex[:8]
    output = Path(args.output_dir).expanduser().resolve() / run_name
    output.mkdir(parents=True, exist_ok=False)
    (output / "request.json").write_bytes(request_data)
    if image_data:
        (output / "vision.png").write_bytes(image_data)
    metadata = {"schema_version": 1, "started_at": utc_now(), "endpoint": url,
                "model": args.model, "kind": args.kind, "request_sha256": request_sha,
                "request_bytes": len(request_data), "timeout_seconds": args.timeout,
                "hardware": hardware_observation(), "memory_before": memory_observation(),
                "output_dir": str(output)}
    headers = {"Content-Type": "application/json", "Accept": "text/event-stream"}
    token = os.environ.get(args.api_key_env) if args.api_key_env else None
    if token:
        headers["Authorization"] = "Bearer " + token
    request = urllib.request.Request(url, data=request_data, headers=headers, method="POST")
    capture = StreamCapture()
    start = time.monotonic()
    with (output / "raw.jsonl").open("w", encoding="utf-8") as raw:
        def record(event, **fields):
            raw.write(json.dumps({"event": event, "at": utc_now(),
                                  "elapsed_ms": (time.monotonic() - start) * 1000,
                                  **fields}, ensure_ascii=False) + "\n")
            raw.flush()

        record("request", request_sha256=request_sha, request_file="request.json",
               endpoint=url, request_bytes=len(request_data))
        try:
            with urllib.request.urlopen(request, timeout=args.timeout) as response:
                for line_bytes in response:
                    elapsed = (time.monotonic() - start) * 1000
                    try:
                        line = line_bytes.decode("utf-8")
                    except UnicodeDecodeError:
                        record("sse", line=None, bytes_base64=base64.b64encode(line_bytes).decode("ascii"))
                        capture.errors.append("invalid UTF-8 in SSE stream")
                        continue
                    record("sse", line=line)
                    capture.feed(line, elapsed)
                    if elapsed > args.timeout * 1000:
                        raise TimeoutError("total probe timeout exceeded")
        except (Exception, KeyboardInterrupt) as error:
            error_data = {"type": type(error).__name__, "message": str(error)}
            if isinstance(error, urllib.error.HTTPError):
                error_data["response_body"] = error.read().decode("utf-8", errors="replace")
                error.close()
            capture.errors.append(error_data["type"] + ": " + error_data["message"])
            record("error", error=error_data)
        result = capture.finish((time.monotonic() - start) * 1000,
                                args.min_prompt_tokens, args.require_mtp, args.expect, args.model)
        summary = {**metadata, **result, "finished_at": utc_now(),
                   "memory_after": memory_observation()}
        (output / "summary.json").write_bytes(json_bytes(summary))
        record("result", summary_file="summary.json", passed=summary["passed"],
               failures=summary["failures"])
    return summary


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--endpoint", required=True, help="Server root, /v1 base, or chat-completions URL")
    result.add_argument("--model", required=True, help="Exact served model ID")
    result.add_argument("--kind", choices=("text", "vision", "request"), default="text")
    result.add_argument("--output-dir", required=True, help="Parent for a unique evidence directory")
    result.add_argument("--request-json", help="Prepared OpenAI request; required for kind=request")
    result.add_argument("--prompt", help="Override the built-in text or vision prompt")
    result.add_argument("--max-tokens", type=int, default=256, help="For built-in text and vision requests")
    result.add_argument("--min-prompt-tokens", type=int, default=0,
                        help="Measured usage minimum; also requires explicit cache_n=0")
    result.add_argument("--require-mtp", action="store_true")
    result.add_argument("--expect", help="Case-insensitive substring required in the final answer")
    result.add_argument("--timeout", type=float, default=7200, help="Request timeout in seconds (default: 7200)")
    result.add_argument("--api-key-env", default="OPENAI_API_KEY", help="Optional authentication env variable; its value is never recorded")
    return result


def main():
    cli = parser()
    args = cli.parse_args()
    if args.max_tokens <= 0 or args.min_prompt_tokens < 0 or not math.isfinite(args.timeout) or args.timeout <= 0:
        cli.error("token limits and timeout must be positive (minimum prompt tokens may be zero)")
    if args.kind == "request" and args.prompt:
        cli.error("--prompt is only supported for text and vision requests")
    try:
        summary = run_probe(args)
    except (OSError, ValueError) as error:
        cli.error(str(error))
    print(json.dumps({key: summary[key] for key in ("passed", "failures", "output_dir", "request_sha256")}, indent=2))
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
