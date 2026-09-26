"""Acceptance evidence must describe the request that actually ran."""

import io
import itertools
import json
import sys
import tempfile
import unittest
import urllib.error
from contextlib import nullcontext, redirect_stdout
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

import accept_recipe


def sse(chunk):
    return b"data: " + json.dumps(chunk).encode() + b"\n"


class AcceptanceTests(unittest.TestCase):
    def test_stream_preserves_actual_request_usage_timings_and_raw_lines(self):
        body = {
            "model": "test-model", "messages": [{"role": "user", "content": "A supplied prompt"}],
            "temperature": 0, "max_tokens": 128, "cache_prompt": False,
            "stream": False, "stream_options": {"include_usage": False},
        }
        usage = {"prompt_tokens": 321, "completion_tokens": 12, "total_tokens": 333,
                 "prompt_tokens_details": {"cached_tokens": 0}}
        timings = {"cache_n": 0, "prompt_n": 321, "predicted_n": 12,
                   "prompt_per_second": 1200.0, "predicted_per_second": 44.0}
        timeline = [
            (0.1, sse({"model": "test-model", "choices": [{"index": 0, "delta": {"role": "assistant"}}]})),
            (0.2, b"\n"),
            (0.3, sse({"choices": [{"delta": {"reasoning_content": "A thought."}}]})),
            (0.8, sse({"choices": [{"delta": {"content": "The answer."}}]})),
            (1.0, sse({"choices": [{"delta": {}, "finish_reason": "length"}]})),
            (1.1, sse({"choices": [], "usage": usage, "timings": timings})),
            (1.2, b"data: [DONE]\n"),
        ]
        with tempfile.TemporaryDirectory() as directory, patch.object(accept_recipe.time, "monotonic", return_value=100.0) as clock:
            def stream():
                for offset, line in timeline:
                    clock.return_value = 100.0 + offset
                    yield line

            path = Path(directory) / "raw.jsonl"
            with patch.object(accept_recipe.urllib.request, "urlopen", return_value=nullcontext(stream())) as open_url:
                run = accept_recipe.measure("http://localhost:9999", "test-model", samples=1,
                                            request_body=body, raw_output=path)[0]
            actual_body = json.loads(open_url.call_args.args[0].data)
            self.assertEqual(actual_body, {**body, "stream": True, "stream_options": {"include_usage": True}})
            self.assertFalse(body["stream"])
            self.assertFalse(body["stream_options"]["include_usage"])
            self.assertEqual(run["prompt_tokens"], 321)
            self.assertEqual(run["tokens"], 12)
            self.assertEqual(run["usage"], usage)
            self.assertEqual(run["timings"], timings)
            self.assertEqual(run["response_model_ids"], ["test-model"])
            self.assertEqual(run["finish_reason"], "length")
            self.assertEqual(run["content"], "The answer.")
            self.assertEqual(run["reasoning_content"], "A thought.")
            self.assertAlmostEqual(run["ttft_ms"], 300.0)
            self.assertAlmostEqual(run["client_decode_ms"], 500.0)
            self.assertAlmostEqual(run["client_decode_tok_s"], 22.0)
            self.assertEqual(run["decode_tok_s"], 44.0)
            self.assertEqual(run["decode_method"], "timings.predicted_per_second")
            events = [json.loads(line) for line in path.read_text().splitlines()]
            self.assertEqual(events[0]["body"], actual_body)
            self.assertEqual([event["line"] for event in events if event["event"] == "sse"],
                             [line.decode() for _, line in timeline])
            self.assertTrue(all("at" in event and "elapsed_ms" in event for event in events))
            self.assertEqual(events[-1]["result"], run)

    def test_default_request_keeps_client_measurement_without_server_timings(self):
        response = b"".join([
            sse({"choices": [{"delta": {"content": "First"}}]}),
            sse({"choices": [{"delta": {"content": " rest"}, "finish_reason": "stop"}]}),
            sse({"choices": [], "usage": {"prompt_tokens": 321, "completion_tokens": 10}}),
            b"data: [DONE]\n",
        ])
        with patch.object(accept_recipe.urllib.request, "urlopen", return_value=io.BytesIO(response)) as open_url, \
                patch.object(accept_recipe.time, "monotonic", side_effect=itertools.count(100.0, 1.0)):
            run = accept_recipe.measure("http://localhost:9999", "test-model", samples=1)[0]
        body = json.loads(open_url.call_args.args[0].data)
        self.assertEqual(body["messages"][0]["content"], "Summarize the history of computing. " * 32)
        self.assertNotIn("max_tokens", body)
        self.assertNotIn("cache_prompt", body)
        self.assertEqual(run["decode_method"], "client_post_first_token_estimate")
        self.assertEqual(run["decode_tok_s"], 9.0)  # Nine tokens after the first, over one second.
        self.assertIsNone(run["server_decode_tok_s"])

    def test_failed_streams_preserve_raw_evidence(self):
        cases = {
            "server-error": [sse({"error": {"message": "out of memory"}})],
            "empty": [sse({"choices": [{"delta": {}, "finish_reason": "stop"}],
                           "usage": {"prompt_tokens": 321, "completion_tokens": 0}}), b"data: [DONE]\n"],
            "truncated": [sse({"choices": [{"delta": {"content": "Partial output"}}],
                               "usage": {"prompt_tokens": 321, "completion_tokens": 12}})],
        }
        with tempfile.TemporaryDirectory() as directory:
            for name, lines in cases.items():
                with self.subTest(name=name):
                    path = Path(directory) / f"{name}.jsonl"
                    with patch.object(accept_recipe.urllib.request, "urlopen", return_value=io.BytesIO(b"".join(lines))):
                        with self.assertRaises(RuntimeError):
                            accept_recipe.measure("http://localhost:9999", "test-model", samples=1, raw_output=path)
                    events = [json.loads(line) for line in path.read_text().splitlines()]
                    self.assertEqual([event["line"] for event in events if event["event"] == "sse"],
                                     [line.decode() for line in lines])
                    self.assertEqual(events[-1]["event"], "error")
                    self.assertFalse(any(event["event"] == "result" for event in events))
            path = Path(directory) / "http-error.jsonl"
            error = urllib.error.HTTPError("http://localhost:9999", 500, "failed", {}, io.BytesIO(b'{"error":"OOM"}'))
            with patch.object(accept_recipe.urllib.request, "urlopen", side_effect=error), self.assertRaises(urllib.error.HTTPError):
                accept_recipe.measure("http://localhost:9999", "test-model", samples=1, raw_output=path)
            events = [json.loads(line) for line in path.read_text().splitlines()]
            self.assertEqual(events[-1]["error"]["response_body"], '{"error":"OOM"}')
            error.close()

    def test_tool_call_output_is_measured_after_metadata_only_delta(self):
        response = b"".join([
            sse({"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "call-1", "type": "function", "function": None}]}}]}),
            sse({"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"name": "weather"}}]}}]}),
            sse({"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": '{"city":"Oslo"}'}}]}}]}),
            sse({"choices": [{"delta": {}, "finish_reason": "tool_calls"}]}),
            sse({"choices": [], "usage": {"prompt_tokens": 321, "completion_tokens": 12}}),
            b"data: [DONE]\n",
        ])
        body = {"tools": [{"type": "function", "function": {"name": "weather", "parameters": {"type": "object"}}}],
                "tool_choice": "required", "messages": [{"role": "user", "content": "Weather in Oslo?"}]}
        with patch.object(accept_recipe.urllib.request, "urlopen", return_value=io.BytesIO(response)) as open_url, \
                patch.object(accept_recipe.time, "monotonic", side_effect=itertools.count(100.0, 1.0)):
            run = accept_recipe.measure("http://localhost:9999", "test-model", samples=1, request_body=body)[0]
        self.assertEqual(json.loads(open_url.call_args.args[0].data)["tools"], body["tools"])
        self.assertEqual(run["finish_reason"], "tool_calls")
        self.assertEqual(run["content"], "")
        self.assertEqual(run["ttft_ms"], 2000.0)
        self.assertEqual(run["decode_tok_s"], 11.0)

    def test_completed_samples_survive_a_later_failure(self):
        success = b"".join([
            sse({"choices": [{"delta": {"content": "First"}}]}),
            sse({"choices": [{"delta": {"content": " rest"}, "finish_reason": "stop"}]}),
            sse({"choices": [], "usage": {"prompt_tokens": 321, "completion_tokens": 10}}),
            b"data: [DONE]\n",
        ])
        failure = sse({"error": {"message": "out of memory"}})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "raw.jsonl"
            with patch.object(accept_recipe.urllib.request, "urlopen", side_effect=[io.BytesIO(success), io.BytesIO(failure)]), \
                    self.assertRaises(RuntimeError):
                accept_recipe.measure("http://localhost:9999", "test-model", samples=2, raw_output=path)
            events = [json.loads(line) for line in path.read_text().splitlines()]
            self.assertEqual([event["sample"] for event in events if event["event"] == "result"], [1])
            self.assertEqual(events[-1]["event"], "error")
            self.assertEqual(events[-1]["sample"], 2)

    def test_promotion_uses_actual_context_and_keeps_individual_samples(self):
        run = {
            "started_at": "2026-09-12T00:00:00+00:00", "prompt_tokens": 321, "tokens": 12,
            "decode_tok_s": 44.0, "ttft_ms": 300.0, "server_prefill_tok_s": 1200.0,
            "decode_method": "timings.predicted_per_second", "content": "The answer.",
            "reasoning_content": "A thought.", "response_model_ids": ["test-model"],
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for kind in ("recipe", "model-instance", "speed-sweep"):
                (root / kind).mkdir()
            recipe_path = root / "recipe/test.json"
            recipe_path.write_text(json.dumps({
                "id": "test", "status": "candidate", "model_instance_id": "test-instance",
                "launch": {"kind": "reference"}, "draft_launch": {
                    "kind": "docker", "image": "test@sha256:" + "a" * 64,
                    "arguments": ["--ctx-size", "8192", "--parallel", "4"],
                },
            }))
            (root / "model-instance/test-instance.json").write_text(json.dumps({"revision": "b" * 40}))
            request_path = root / "request.json"
            request_body = {"model": "test-model", "messages": [{"role": "user", "content": "A prompt"}], "cache_prompt": False}
            request_path.write_text(json.dumps(request_body))
            raw_path = root / "raw.jsonl"
            argv = ["accept_recipe.py", "test", "--endpoint", "http://localhost:9999",
                    "--request-json", str(request_path), "--raw-output", str(raw_path)]
            with patch.object(accept_recipe, "ROOT", root), patch.object(sys, "argv", argv), \
                    patch.object(accept_recipe, "http_json", return_value={"data": [{"id": "other-model"}, {"id": "test-model"}]}), \
                    patch.object(accept_recipe, "measure", return_value=[dict(run) for _ in range(3)]) as measure, \
                    redirect_stdout(io.StringIO()):
                self.assertEqual(accept_recipe.main(), 0)
            measure.assert_called_once_with("http://localhost:9999", "test-model", request_body=request_body, raw_output=raw_path)
            sweep = json.loads((root / "speed-sweep/test-acceptance.json").read_text())
            row = sweep["rows"][0]
            self.assertEqual(row["context_tokens"], 321)
            self.assertEqual(row["samples"], 3)
            self.assertEqual(len(row["measurements"]), 3)
            self.assertNotIn("content", row["measurements"][0])
            self.assertEqual(sweep["metrics"]["max_context_tokens"], 321)
            self.assertEqual(sweep["metrics"]["point_count"], 1)
            promoted = json.loads(recipe_path.read_text())
            self.assertEqual(promoted["serving"]["max_context_tokens"], 2048)
            self.assertEqual(promoted["status"], "validated")
            self.assertEqual(promoted["metadata"]["acceptance"]["served_model_id"], "test-model")
            self.assertTrue(promoted["launch"]["container"]["captured_at"].endswith("Z"))

            promoted["status"] = "candidate"
            promoted["serving"]["max_context_tokens"] = None
            promoted["launch"]["environment"] = {"LLAMA_ARG_KV_UNIFIED": "true"}
            recipe_path.write_text(json.dumps(promoted))
            with patch.object(accept_recipe, "ROOT", root), patch.object(sys, "argv", argv), \
                    patch.object(accept_recipe, "http_json", return_value={"data": [{"id": "test-model"}]}), \
                    patch.object(accept_recipe, "measure", return_value=[dict(run) for _ in range(3)]), \
                    redirect_stdout(io.StringIO()):
                self.assertEqual(accept_recipe.main(), 0)
            self.assertEqual(json.loads(recipe_path.read_text())["serving"]["max_context_tokens"], 8192)


if __name__ == "__main__":
    unittest.main()
