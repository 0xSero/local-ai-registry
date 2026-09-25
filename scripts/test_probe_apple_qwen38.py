"""Native inference evidence gates must fail closed, and keep raw failures."""

import argparse
import base64
import hashlib
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parent))
import probe_apple_qwen38 as probe


def event(value):
    return "data: " + (value if isinstance(value, str) else json.dumps(value)) + "\n\n"


def complete_stream(prompt_tokens=200001, cache_n=0, mtp=True):
    timings = {"prompt_n": prompt_tokens, "cache_n": cache_n, "predicted_n": 16,
               "peak_memory": 18.75, "prompt_per_second": 1500, "predicted_per_second": 24.5}
    if mtp:
        timings.update(draft_kind="mtp", draft_rounds=6, draft_n=18, draft_n_accepted=8)
    return "".join([
        event({"model": "qwen-test", "choices": [{"index": 0, "delta": {"reasoning_content": "Thinking."}}]}),
        event({"choices": [{"index": 0, "delta": {"content": "red, blue"}}]}),
        event({"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}),
        event({"choices": [], "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": 16,
                                        "prompt_tokens_details": {"cached_tokens": cache_n}}, "timings": timings}),
        event("[DONE]"),
    ])


def parse_stream(text, **gates):
    capture = probe.StreamCapture()
    for index, line in enumerate(text.splitlines(keepends=True)):
        capture.feed(line, index * 10)
    return capture.finish(200, **gates)


class StreamGatesTests(unittest.TestCase):
    def test_completed_cold_long_context_and_mtp_are_measured(self):
        result = parse_stream(complete_stream(), min_prompt_tokens=200000,
                              require_mtp=True, expect="RED, BLUE")
        self.assertTrue(result["passed"], result["failures"])
        self.assertTrue(result["mtp_proven"])
        self.assertEqual(result["usage"]["prompt_tokens"], 200001)
        self.assertEqual(result["timings"]["peak_memory"], 18.75)
        self.assertEqual(result["content"], "red, blue")
        self.assertEqual(result["reasoning_content"], "Thinking.")
        self.assertLess(result["first_output_ms"], result["first_content_ms"])

    def test_nominal_context_and_cached_context_do_not_pass(self):
        for tokens, cached in ((100, 0), (200001, 200000), (None, 0), (True, 0)):
            with self.subTest(tokens=tokens, cached=cached):
                result = parse_stream(complete_stream(tokens, cached), min_prompt_tokens=200000)
                self.assertFalse(result["passed"])
        absent_cache = complete_stream().replace('"cache_n": 0, ', "")
        result = parse_stream(absent_cache, min_prompt_tokens=200000)
        self.assertFalse(result["passed"])
        self.assertIn("cold prefill requires explicit timings.cache_n=0", result["failures"])

    def test_mtp_configuration_alone_or_false_counters_are_not_proof(self):
        examples = [
            complete_stream(mtp=False),
            complete_stream().replace('"draft_kind": "mtp"', '"draft_kind": "draft_model"'),
            complete_stream().replace('"draft_n_accepted": 8', '"draft_n_accepted": 0'),
            complete_stream().replace('"draft_rounds": 6', '"draft_rounds": true'),
            complete_stream().replace('"draft_n": 18', '"draft_n": 3'),
        ]
        for response in examples:
            with self.subTest(response=response):
                result = parse_stream(response, require_mtp=True)
                self.assertFalse(result["passed"])
                self.assertFalse(result["mtp_proven"])

    def test_partial_empty_malformed_and_server_error_streams_fail(self):
        examples = [
            complete_stream().replace(event("[DONE]"), ""),
            complete_stream().replace('"finish_reason": "stop"', '"finish_reason": null'),
            complete_stream().replace('"content": "red, blue"', '"content": ""'),
            event("{broken-json") + complete_stream(),
            event('{"timings": {"peak_memory": NaN}}') + complete_stream(),
            event({"error": {"message": "OOM"}}) + complete_stream(),
            complete_stream() + event({"choices": []}),
        ]
        for response in examples:
            with self.subTest(response=response):
                self.assertFalse(parse_stream(response)["passed"])

    def test_expectation_checks_answer_not_reasoning(self):
        result = parse_stream(complete_stream(), expect="Thinking.")
        self.assertFalse(result["passed"])
        self.assertFalse(result["correctness_passed"])

    def test_missing_or_mixed_model_identities_fail(self):
        examples = [
            complete_stream().replace('"model": "qwen-test", ', ""),
            complete_stream().replace('"model": "qwen-test"', '"model": "other-model"'),
            event({"model": "other-model", "choices": []}) + complete_stream(),
        ]
        for response in examples:
            with self.subTest(response=response):
                self.assertFalse(parse_stream(response, expected_model="qwen-test")["passed"])
        self.assertTrue(parse_stream(complete_stream(), expected_model="qwen-test")["passed"])

    def test_short_probes_require_valid_measured_token_usage(self):
        examples = [
            complete_stream().replace('"usage":', '"unrelated_field":'),
            complete_stream().replace('"completion_tokens": 16', '"completion_tokens": 0'),
            complete_stream().replace('"completion_tokens": 16', '"completion_tokens": true'),
            complete_stream().replace('"completion_tokens": 16', '"completion_tokens": 1.5'),
            complete_stream().replace('"prompt_tokens": 200001', '"prompt_tokens": -1'),
            complete_stream().replace('"prompt_tokens": 200001', '"prompt_tokens": "200001"'),
        ]
        for response in examples:
            with self.subTest(response=response):
                self.assertFalse(parse_stream(response)["passed"])

    def test_length_without_expectation_does_not_claim_correctness(self):
        response = complete_stream().replace('"finish_reason": "stop"', '"finish_reason": "length"')
        result = parse_stream(response)
        self.assertTrue(result["passed"])
        self.assertIsNone(result["correctness_passed"])
        self.assertEqual(result["finish_reason"], "length")

    def test_multiline_sse_event_is_supported(self):
        response = complete_stream().replace('data: {"choices": [], "usage":',
                                             'data: {"choices": [],\ndata: "usage":')
        self.assertTrue(parse_stream(response, require_mtp=True)["passed"])


class EvidenceFilesTests(unittest.TestCase):
    def args(self, output, **overrides):
        values = dict(endpoint="http://127.0.0.1:8123/v1", model="qwen-test", kind="text",
                      output_dir=output, request_json=None, prompt=None, max_tokens=256,
                      min_prompt_tokens=200000, require_mtp=True, expect="red, blue",
                      timeout=7200, api_key_env="TEST_PROBE_KEY")
        return argparse.Namespace(**{**values, **overrides})

    def test_request_hash_raw_sse_and_summary_persist_without_auth_or_prompt_duplication(self):
        response = complete_stream().encode()
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(probe, "hardware_observation", return_value={"chip": "fixture"}), \
                patch.object(probe, "memory_observation", return_value={"swap": "fixture"}), \
                patch.dict(probe.os.environ, {"TEST_PROBE_KEY": "private-secret"}), \
                patch.object(probe.urllib.request, "urlopen", side_effect=lambda *a, **kw: io.BytesIO(response)) as opened:
            first = probe.run_probe(self.args(directory, prompt="The unique full prompt."))
            second = probe.run_probe(self.args(directory))
            output = Path(first["output_dir"])
            request_data = (output / "request.json").read_bytes()
            raw_text = (output / "raw.jsonl").read_text()
            events = [json.loads(line) for line in raw_text.splitlines()]
            self.assertTrue(first["passed"])
            self.assertNotEqual(first["output_dir"], second["output_dir"])
            self.assertEqual(first["request_sha256"], hashlib.sha256(request_data).hexdigest())
            self.assertEqual(events[0]["request_sha256"], first["request_sha256"])
            self.assertEqual("".join(item["line"] for item in events if item["event"] == "sse"), response.decode())
            self.assertNotIn("private-secret", raw_text + (output / "summary.json").read_text())
            self.assertNotIn("The unique full prompt.", raw_text)
            request = opened.call_args.args[0]
            self.assertEqual(request.get_header("Authorization"), "Bearer private-secret")
            self.assertEqual(opened.call_args.kwargs["timeout"], 7200)

    def test_http_failure_still_writes_failed_summary_and_raw_body(self):
        error = urllib.error.HTTPError("http://127.0.0.1:8123/v1/chat/completions", 500,
                                       "failed", {}, io.BytesIO(b'{"error":"OOM"}'))
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(probe, "hardware_observation", return_value={}), \
                patch.object(probe, "memory_observation", return_value={}), \
                patch.object(probe.urllib.request, "urlopen", side_effect=error):
            summary = probe.run_probe(self.args(directory))
            output = Path(summary["output_dir"])
            self.assertFalse(summary["passed"])
            self.assertTrue((output / "summary.json").is_file())
            events = [json.loads(line) for line in (output / "raw.jsonl").read_text().splitlines()]
            failure = next(item for item in events if item["event"] == "error")
            self.assertEqual(failure["error"]["response_body"], '{"error":"OOM"}')

    def test_supplied_request_is_preserved_except_stream_usage_controls(self):
        body = {"model": "qwen-test", "messages": [{"role": "user", "content": "Long actual prompt."}],
                "max_tokens": 300, "stream": False, "stream_options": {"include_usage": False},
                "temperature": 0.4, "enable_thinking": False}
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "prepared.json"
            source.write_text(json.dumps(body))
            args = self.args(directory, kind="request", request_json=str(source))
            actual = probe.build_request(args)
            self.assertEqual(actual, {**body, "stream": True, "stream_options": {"include_usage": True}})
            args.model = "wrong-model"
            with self.assertRaisesRegex(ValueError, "differs"):
                probe.build_request(args)

    def test_png_has_expected_pixels_and_prompt_does_not_reveal_colors(self):
        data = probe.vision_png(4, 2)
        self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
        offset, compressed = 8, b""
        while offset < len(data):
            length = struct.unpack(">I", data[offset:offset + 4])[0]
            kind = data[offset + 4:offset + 8]
            payload = data[offset + 8:offset + 8 + length]
            if kind == b"IDAT":
                compressed += payload
            offset += length + 12
        pixels = zlib.decompress(compressed)
        self.assertEqual(pixels, (b"\0" + b"\xff\0\0" * 2 + b"\0\0\xff" * 2) * 2)
        body = probe.build_request(self.args("unused", kind="vision"), data)
        content = body["messages"][0]["content"]
        self.assertNotIn("red", content[0]["text"].lower())
        self.assertNotIn("blue", content[0]["text"].lower())
        self.assertEqual(base64.b64decode(content[1]["image_url"]["url"].split(",")[1]), data)

    def test_endpoint_auth_is_not_logged_in_url(self):
        for endpoint in ("https://secret@example.com", "https://example.com?key=secret"):
            with self.assertRaises(ValueError):
                probe.chat_url(endpoint)
        for endpoint in ("http://localhost:8000", "http://localhost:8000/v1",
                         "http://localhost:8000/v1/chat/completions"):
            self.assertEqual(probe.chat_url(endpoint), "http://localhost:8000/v1/chat/completions")


if __name__ == "__main__":
    unittest.main()
