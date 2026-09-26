#!/usr/bin/env python3
"""Independently check saved combined 200k retrieval, vision, MTP and KV evidence.

This is a stdlib-only verifier of captured files, not a model runner. A successful
exit prints a small JSON receipt with input hashes. Failure prints only an error
to stderr and exits nonzero. It does not infer total memory from cache byte sums.
"""

import argparse
import base64
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys


EXPECTED_VALUES = ["maple-7429", "harbor-6183", "violet-9052", "red", "blue"]
VISION_PNG_SHA256 = "1c8bed001809ffd620bec5e6907f12545a55322179f76e6129683de5b8598570"
# Bind the archive, distant key positions, image and question to the reviewed
# make_long_request.py --tokens 200000 --with-image fixture (1754 repeats per
# section). Derivation: SHA256(json.dumps(request["messages"], sort_keys=True,
# ensure_ascii=False, separators=(",", ":")).encode("utf-8")). The generator's
# original request file SHA256 is 745a772b15dcd912386c9cca78a2e19e544f417692d7c630e5f49a902e586a20
# in workload-200k-image.json. Hashing messages alone permits HTTP serialization,
# model-path and request-control differences without accepting another workload.
COMBINED_MESSAGES_SHA256 = "6e86af767b630388aa9dce853ca18306a1dcd3206022981b321c70652e0cb533"
# Only these controls accompany the reviewed workload. Other server inputs can
# add template text or constrain the answer without changing request.messages.
SAFE_REQUEST_KEYS = frozenset({
    "model", "messages", "temperature", "max_tokens", "enable_thinking",
    "chat_template_kwargs", "stream", "stream_options",
})
ATTENTION_LAYERS = list(range(3, 64, 4))
EXPECTED_CLASSES = {"ArraysCache": 48, "BatchTurboQuantKVCache": 15, "BatchKVCache": 1}


class VerificationError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise VerificationError(message)


def reject_constant(value):
    raise VerificationError("non-finite JSON constant: " + value)


def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate JSON object key: " + key)
        result[key] = value
    return result


def read_object(data, label):
    try:
        result = json.loads(data, parse_constant=reject_constant, object_pairs_hook=unique_pairs)
    except (ValueError, UnicodeDecodeError) as error:
        raise VerificationError(label + ": invalid JSON: " + str(error)) from error
    require(isinstance(result, dict), label + " must be a JSON object")
    return result


def count(value, minimum=0):
    return type(value) is int and value >= minimum


def int_list(value, expected):
    return isinstance(value, list) and all(type(item) is int for item in value) and value == expected


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def replay_raw(raw_data, request_sha, request_bytes):
    records = [read_object(line, "raw JSONL record") for line in raw_data.splitlines()]
    require(len(records) >= 3, "raw capture is incomplete")
    first, last = records[0], records[-1]
    require(first.get("event") == "request" and first.get("request_file") == "request.json",
            "raw capture must start with its request receipt")
    require(first.get("request_sha256") == request_sha and first.get("request_bytes") == request_bytes,
            "raw request receipt does not match request.json")
    require(last.get("event") == "result" and last.get("passed") is True
            and last.get("failures") == [] and last.get("summary_file") == "summary.json",
            "raw capture has no successful final result receipt")
    events, pending = [], []
    for record in records[1:-1]:
        require(record.get("event") == "sse" and isinstance(record.get("line"), str),
                "raw capture contains an error, non-SSE event, or undecodable line")
        line = record["line"]
        if not line.strip():
            if pending:
                events.append("\n".join(pending))
                pending.clear()
        elif line.startswith("data:"):
            pending.append(line[5:].lstrip(" ").rstrip("\r\n"))
        else:
            require(line.startswith((":", "event:", "id:", "retry:")), "unrecognized SSE line")
    if pending:
        events.append("\n".join(pending))
    require(events and events[-1] == "[DONE]" and events.count("[DONE]") == 1,
            "raw stream must end with exactly one [DONE]")
    content, reasoning, usage, timings, models = [], [], {}, {}, set()
    finish_reason = None
    for data in events[:-1]:
        chunk = read_object(data, "SSE data")
        require(chunk.get("error") is None, "SSE contains a server error")
        if "model" in chunk:
            require(isinstance(chunk["model"], str) and chunk["model"], "invalid response model")
            models.add(chunk["model"])
        for key, target in (("usage", usage), ("timings", timings)):
            if chunk.get(key) is not None:
                require(isinstance(chunk[key], dict), "invalid SSE " + key)
                target.update(chunk[key])
        choices = chunk.get("choices")
        require(isinstance(choices, list), "SSE choices must be an array")
        for choice in choices:
            require(isinstance(choice, dict) and type(choice.get("index")) is int
                    and choice["index"] == 0, "unexpected completion choice")
            delta = choice.get("delta")
            require(isinstance(delta, dict), "SSE delta must be an object")
            answer = delta.get("content")
            if answer is None:
                answer = ""
            thought = delta.get("reasoning_content")
            if thought is None:
                thought = delta.get("reasoning")
            if thought is None:
                thought = ""
            require(isinstance(answer, str) and isinstance(thought, str), "non-text SSE output")
            require(finish_reason is None or not (answer or thought), "output continued after finish")
            content.append(answer)
            reasoning.append(thought)
            if choice.get("finish_reason") is not None:
                require(finish_reason is None, "multiple completion finish reasons")
                finish_reason = choice["finish_reason"]
    require(finish_reason == "stop", "raw completion must finish with stop")
    return {"content": "".join(content), "reasoning_content": "".join(reasoning),
            "usage": usage, "timings": timings, "finish_reason": finish_reason,
            "response_model_ids": sorted(models), "sse_event_count": len(events) - 1}


def verify_request(request, summary):
    unexpected = set(request) - SAFE_REQUEST_KEYS
    require(not unexpected, "unsupported request inputs: " + ", ".join(sorted(unexpected)))
    if "enable_thinking" in request:
        require(request["enable_thinking"] is False, "enable_thinking must be false")
    if "chat_template_kwargs" in request:
        template = request["chat_template_kwargs"]
        require(isinstance(template, dict) and set(template) == {"enable_thinking"}
                and template["enable_thinking"] is False,
                "chat_template_kwargs must contain only enable_thinking=false")
    if "temperature" in request:
        require(type(request["temperature"]) in (int, float) and request["temperature"] >= 0,
                "temperature must be a nonnegative number")
    if "max_tokens" in request:
        require(count(request["max_tokens"], 1), "max_tokens must be a positive integer")
    model = request.get("model")
    require(isinstance(model, str) and model and summary.get("model") == model,
            "request and summary model identities differ")
    require(summary.get("response_model_ids") == [model], "response model identity differs")
    require(request.get("stream") is True, "request did not enable streaming")
    options = request.get("stream_options")
    require(isinstance(options, dict) and options.get("include_usage") is True,
            "request did not include streaming usage")
    require(set(options) <= {"include_usage", "include_obfuscation"}
            and all(type(value) is bool for value in options.values()),
            "unsupported streaming controls")
    messages = request.get("messages")
    require(isinstance(messages, list) and messages, "request has no messages")
    images = []
    for message in messages:
        require(isinstance(message, dict), "invalid request message")
        content = message.get("content")
        if isinstance(content, list):
            for part in content:
                require(isinstance(part, dict), "invalid multimodal content")
                if part.get("type") == "image_url":
                    image = part.get("image_url")
                    require(isinstance(image, dict) and isinstance(image.get("url"), str),
                            "invalid image URL")
                    images.append(image["url"])
    require(len(images) == 1 and images[0].startswith("data:image/png;base64,"),
            "combined proof requires one inline PNG fixture")
    try:
        png = base64.b64decode(images[0].split(",", 1)[1], validate=True)
    except ValueError as error:
        raise VerificationError("invalid PNG base64") from error
    require(sha256(png) == VISION_PNG_SHA256, "image differs from the red-left/blue-right fixture")
    canonical_messages = json.dumps(
        messages, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    messages_sha = sha256(canonical_messages)
    require(messages_sha == COMBINED_MESSAGES_SHA256,
            "messages differ from the trusted combined 200k retrieval/image workload")
    return messages_sha


def verify_summary(summary):
    require(summary.get("passed") is True and summary.get("failures") == [], "probe did not pass")
    require(summary.get("stream_done") is True and summary.get("finish_reason") == "stop",
            "probe is incomplete or truncated")
    content = summary.get("content")
    require(isinstance(content, str) and content.strip(), "answer text is empty")
    require([value.strip().casefold() for value in content.strip().split(",")] == EXPECTED_VALUES,
            "answer must contain exactly the five expected values in order")
    usage, timings = summary.get("usage"), summary.get("timings")
    require(isinstance(usage, dict) and isinstance(timings, dict), "usage or timings missing")
    tokens = usage.get("prompt_tokens")
    require(count(tokens, 200000), "measured prompt is shorter than 200000 tokens")
    require(count(usage.get("completion_tokens"), 1), "completion token usage is invalid")
    details = usage.get("prompt_tokens_details")
    require(isinstance(details, dict) and count(details.get("cached_tokens"))
            and details["cached_tokens"] == 0, "usage must explicitly report zero cached tokens")
    require(count(timings.get("cache_n")) and timings["cache_n"] == 0,
            "timings must explicitly report cache_n=0")
    require(count(timings.get("prompt_n")) and timings["prompt_n"] == tokens,
            "timings.prompt_n disagrees with usage")
    require(count(timings.get("predicted_n"), 1)
            and timings["predicted_n"] == usage["completion_tokens"],
            "timings.predicted_n disagrees with usage")
    require(timings.get("draft_kind") == "mtp" and summary.get("mtp_proven") is True,
            "native MTP identity is absent")
    counters = {key: timings.get(key) for key in ("draft_rounds", "draft_n", "draft_n_accepted")}
    require(all(count(value, 1) for value in counters.values()), "MTP counters must be positive integers")
    require(counters["draft_n_accepted"] <= counters["draft_n"]
            and counters["draft_rounds"] <= counters["draft_n"], "inconsistent MTP counters")
    return tokens, counters


def verify_audit(server_data, tokens):
    matches = []
    for line in server_data.decode("utf-8").splitlines():
        if "qwen38_prefill_audit" not in line:
            continue
        audit = read_object(line, "prefill audit log line")
        require(audit.get("event") == "qwen38_prefill_audit", "unexpected audit event")
        if int_list(audit.get("prompt_tokens_per_row"), [tokens]):
            matches.append(audit)
    require(len(matches) == 1, "need exactly one final-prefill audit for the measured prompt length")
    audit = matches[0]
    require(audit.get("schema_version") == 1 and type(audit.get("schema_version")) is int,
            "unsupported prefill audit schema")
    require(int_list(audit.get("cached_tokens_per_row"), [0]), "prefill audit used cached tokens")
    require(audit.get("single_row_qwen_mapping_verified") is True
            and audit.get("full_attention_cache_retained") is True and audit.get("errors") == [],
            "prefill audit did not establish full cache retention")
    require(int_list(audit.get("hidden_shape"), [1, 1, 5120]), "unexpected final MTP hidden-state shape")
    require(count(audit.get("fused_sdpa_calls_this_prefill"), 1),
            "prefill audit must record positive fused SDPA calls for this prefill")
    require(int_list(audit.get("full_attention_layers_verified"), ATTENTION_LAYERS),
            "prefill audit did not verify all 16 expected attention layers")
    layers = audit.get("layers")
    require(isinstance(layers, list) and len(layers) == 64, "prefill audit must describe 64 layers")
    counts = Counter()
    for index, layer in enumerate(layers):
        require(isinstance(layer, dict) and type(layer.get("layer")) is int
                and layer["layer"] == index, "cache layer indices are missing, duplicated or out of order")
        expected = "ArraysCache" if index not in ATTENTION_LAYERS else (
            "BatchKVCache" if index == 63 else "BatchTurboQuantKVCache")
        require(layer.get("cache_class") == expected, f"layer {index}: unexpected cache class")
        counts[expected] += 1
        require(layer.get("is_linear") is (index not in ATTENTION_LAYERS),
                f"layer {index}: incorrect recurrent/attention mapping")
        if index in ATTENTION_LAYERS:
            require(count(layer.get("retained_tokens")) and layer["retained_tokens"] == tokens
                    and int_list(layer.get("offset"), [tokens]), f"layer {index}: full prompt KV was not retained")
        if expected == "BatchTurboQuantKVCache":
            require(all(type(layer.get(key)) in (int, float) and layer[key] == 4
                        for key in ("bits", "key_bits", "value_bits")),
                    f"layer {index}: TurboQuant key/value cache is not 4-bit")
        elif expected == "BatchKVCache":
            require(all(layer.get(key) is None for key in ("bits", "key_bits", "value_bits")),
                    "final attention cache unexpectedly reports quantization")
    reported_counts = audit.get("cache_class_counts")
    require(isinstance(reported_counts, dict) and all(type(value) is int for value in reported_counts.values())
            and dict(counts) == EXPECTED_CLASSES and reported_counts == EXPECTED_CLASSES,
            "cache class counts disagree")
    require(type(audit.get("cache_bytes_is_partial")) is bool,
            "cache byte accounting completeness is unspecified")
    return audit


def verify(probe_dir, server_log):
    probe_dir, server_log = Path(probe_dir), Path(server_log)
    inputs = {name: (probe_dir / name).read_bytes() for name in ("request.json", "raw.jsonl", "summary.json")}
    inputs["server_log"] = server_log.read_bytes()
    request = read_object(inputs["request.json"], "request.json")
    summary = read_object(inputs["summary.json"], "summary.json")
    request_sha, request_bytes = sha256(inputs["request.json"]), len(inputs["request.json"])
    require(summary.get("request_sha256") == request_sha and summary.get("request_bytes") == request_bytes,
            "summary request hash or byte count does not match request.json")
    replayed = replay_raw(inputs["raw.jsonl"], request_sha, request_bytes)
    for key, value in replayed.items():
        require(summary.get(key) == value, "summary disagrees with raw SSE: " + key)
    messages_sha = verify_request(request, summary)
    tokens, counters = verify_summary(summary)
    audit = verify_audit(inputs["server_log"], tokens)
    return {"verified": True, "model": request["model"], "request_bytes": request_bytes,
            "verified_messages_sha256": messages_sha,
            "prompt_tokens": tokens, "completion_tokens": summary["usage"]["completion_tokens"],
            "answer": summary["content"], "mtp": {"draft_kind": "mtp", **counters},
            "cache_class_counts": EXPECTED_CLASSES, "full_attention_layers_retaining_prompt": 16,
            "hidden_shape": audit["hidden_shape"],
            "fused_sdpa_calls_this_prefill": audit["fused_sdpa_calls_this_prefill"],
            "cache_byte_accounting_complete": not audit["cache_bytes_is_partial"],
            "input_sha256": {name: sha256(data) for name, data in inputs.items()}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe-dir", type=Path, required=True)
    parser.add_argument("--server-log", type=Path, required=True)
    args = parser.parse_args()
    try:
        receipt = verify(args.probe_dir, args.server_log)
    except (OSError, ValueError, UnicodeDecodeError) as error:
        print("Evidence verification failed: " + str(error), file=sys.stderr)
        return 1
    print(json.dumps(receipt, sort_keys=True, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
