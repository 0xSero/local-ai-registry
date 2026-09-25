"""Independent saved-evidence checks reject tampered summaries and lost KV."""

import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import ModuleType
import unittest

VERIFIER_PATH = Path(__file__).resolve().parents[1] / "sources/qwen38-apple-silicon/verify_long_evidence.py"
# The unsuccessful inference archive still contains the unchanged, reviewed
# input fixture. Reuse its messages instead of committing a second 1 MB copy.
WORKLOAD_REQUEST = VERIFIER_PATH.parent / "evidence/failed-1024-prefill/request.json"
verifier = ModuleType("verify_long_evidence")
exec(compile(VERIFIER_PATH.read_bytes(), str(VERIFIER_PATH), "exec"), verifier.__dict__)


def encoded(value):
    return (json.dumps(value, sort_keys=True) + "\n").encode()


class SavedEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.log = self.directory / "server.log"
        self.tokens = 200163
        self.answer = ", ".join(verifier.EXPECTED_VALUES)
        self.request = {"model": "qwen-test", "stream": True, "stream_options": {"include_usage": True},
                        "messages": json.loads(WORKLOAD_REQUEST.read_bytes())["messages"]}
        self.usage = {"prompt_tokens": self.tokens, "completion_tokens": 28,
                      "prompt_tokens_details": {"cached_tokens": 0}, "total_tokens": self.tokens + 28}
        self.timings = {"cache_n": 0, "prompt_n": self.tokens, "predicted_n": 28,
                        "draft_kind": "mtp", "draft_rounds": 11, "draft_n": 22, "draft_n_accepted": 11}
        self.summary = {"passed": True, "failures": [], "stream_done": True, "finish_reason": "stop",
                        "content": self.answer, "reasoning_content": "", "usage": self.usage,
                        "timings": self.timings, "mtp_proven": True, "model": "qwen-test",
                        "response_model_ids": ["qwen-test"], "sse_event_count": 4}
        self.audit = {"event": "qwen38_prefill_audit", "schema_version": 1,
                      "prompt_tokens_per_row": [self.tokens], "cached_tokens_per_row": [0],
                      "single_row_qwen_mapping_verified": True, "full_attention_cache_retained": True,
                      "errors": [], "hidden_shape": [1, 1, 5120], "cache_bytes_is_partial": False,
                      "fused_sdpa_calls_this_prefill": 3120,
                      "full_attention_layers_verified": verifier.ATTENTION_LAYERS,
                      "cache_class_counts": verifier.EXPECTED_CLASSES, "layers": []}
        for index in range(64):
            linear = index not in verifier.ATTENTION_LAYERS
            cache = "ArraysCache" if linear else "BatchKVCache" if index == 63 else "BatchTurboQuantKVCache"
            bits = 4.0 if cache == "BatchTurboQuantKVCache" else None
            self.audit["layers"].append({"layer": index, "cache_class": cache, "is_linear": linear,
                                         "retained_tokens": None if linear else self.tokens,
                                         "offset": None if linear else [self.tokens],
                                         "bits": bits, "key_bits": bits, "value_bits": bits})
        self.write_all()

    def write_all(self):
        request_data = encoded(self.request)
        (self.directory / "request.json").write_bytes(request_data)
        digest, size = hashlib.sha256(request_data).hexdigest(), len(request_data)
        self.summary.update(request_sha256=digest, request_bytes=size)
        self.write_summary()
        chunks = [
            {"model": "qwen-test", "choices": [{"index": 0, "delta": {"content": self.answer[:20]}}]},
            {"model": "qwen-test", "choices": [{"index": 0, "delta": {"content": self.answer[20:]}}]},
            {"model": "qwen-test", "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
            {"model": "qwen-test", "choices": [], "usage": self.usage, "timings": self.timings},
        ]
        records = [{"event": "request", "request_file": "request.json", "request_sha256": digest, "request_bytes": size}]
        for chunk in chunks:
            records.extend([{"event": "sse", "line": "data: " + json.dumps(chunk) + "\n"},
                            {"event": "sse", "line": "\n"}])
        records.extend([{"event": "sse", "line": "data: [DONE]\n"}, {"event": "sse", "line": "\n"},
                        {"event": "result", "summary_file": "summary.json", "passed": True, "failures": []}])
        (self.directory / "raw.jsonl").write_bytes(b"".join(encoded(record) for record in records))
        self.write_audit()

    def write_summary(self):
        (self.directory / "summary.json").write_bytes(encoded(self.summary))

    def write_audit(self):
        self.log.write_bytes(b"server log before audit\n" + encoded(self.audit) + b"server log after audit\n")

    def verify(self):
        return verifier.verify(self.directory, self.log)

    def test_valid_saved_proof_has_input_hashes_and_no_total_memory_claim(self):
        result = self.verify()
        self.assertTrue(result["verified"])
        self.assertEqual(result["prompt_tokens"], 200163)
        self.assertEqual(result["full_attention_layers_retaining_prompt"], 16)
        self.assertEqual(result["fused_sdpa_calls_this_prefill"], 3120)
        self.assertEqual(result["verified_messages_sha256"], verifier.COMBINED_MESSAGES_SHA256)
        self.assertEqual(set(result["input_sha256"]), {"request.json", "raw.jsonl", "summary.json", "server_log"})
        self.audit["cache_bytes_is_partial"] = True
        self.audit["cache_bytes"] = 123456
        self.write_audit()
        result = self.verify()
        self.assertFalse(result["cache_byte_accounting_complete"])
        self.assertNotIn("cache_bytes", result)
        self.assertNotIn("memory", result)

    def test_request_byte_tampering_is_detected(self):
        with (self.directory / "request.json").open("ab") as target:
            target.write(b" ")
        with self.assertRaisesRegex(verifier.VerificationError, "hash or byte count"):
            self.verify()

    def test_summary_tampering_disagrees_with_replayed_raw(self):
        original = copy.deepcopy(self.summary)
        for mutate in (lambda: self.summary.update(content="invented success"),
                       lambda: self.summary["timings"].update(draft_n_accepted=21),
                       lambda: self.summary["usage"].update(prompt_tokens=262144)):
            self.summary = copy.deepcopy(original)
            mutate()
            self.write_summary()
            with self.assertRaisesRegex(verifier.VerificationError, "disagrees with raw SSE"):
                self.verify()

    def test_bad_mtp_counters_fail_even_when_summary_and_raw_agree(self):
        original = copy.deepcopy(self.timings)
        for changes in ({"draft_kind": "dflash"}, {"draft_n_accepted": 0},
                        {"draft_n_accepted": 99}, {"draft_rounds": True}, {"draft_rounds": 23}):
            self.timings = {**original, **changes}
            self.summary["timings"] = self.timings
            self.write_all()
            with self.assertRaises(verifier.VerificationError):
                self.verify()

    def test_missing_done_cannot_be_hidden_by_passing_summary(self):
        path = self.directory / "raw.jsonl"
        lines = [line for line in path.read_bytes().splitlines(keepends=True) if b"[DONE]" not in line]
        path.write_bytes(b"".join(lines))
        with self.assertRaisesRegex(verifier.VerificationError, "DONE"):
            self.verify()

    def test_invalid_raw_json_and_duplicate_keys_fail(self):
        path = self.directory / "raw.jsonl"
        original = path.read_bytes()
        for data in (b"not JSON\n" + original,
                     original.replace(b'"event": "request"', b'"event": "request", "event": "request"', 1)):
            path.write_bytes(data)
            with self.assertRaises(verifier.VerificationError):
                self.verify()

    def test_short_or_cached_prompt_fails_even_when_raw_agrees(self):
        for prompt, cache in ((199999, 0), (200163, 1)):
            self.usage["prompt_tokens"] = prompt
            self.usage["prompt_tokens_details"]["cached_tokens"] = cache
            self.timings.update(prompt_n=prompt, cache_n=cache)
            self.write_all()
            with self.assertRaises(verifier.VerificationError):
                self.verify()

    def test_cache_retention_layout_and_scheme_must_match_actual_rows(self):
        original = copy.deepcopy(self.audit)
        mutations = [
            lambda: self.audit["layers"][3].update(retained_tokens=4096),
            lambda: self.audit["layers"][3].update(offset=[4096]),
            lambda: self.audit["layers"][3].update(cache_class="BatchQuantizedKVCache"),
            lambda: self.audit["layers"][3].update(bits=2),
            lambda: self.audit["layers"][3].update(value_bits=8),
            lambda: self.audit["layers"][3].update(layer=7),
            lambda: self.audit["layers"].pop(),
            lambda: self.audit.update(hidden_shape=[1, 200162, 5120]),
            lambda: self.audit.update(errors=["retention failure"]),
            lambda: self.audit.update(full_attention_layers_verified=[3]),
        ]
        for mutate in mutations:
            self.audit = copy.deepcopy(original)
            mutate()
            self.write_audit()
            with self.assertRaises(verifier.VerificationError):
                self.verify()

    def test_missing_and_duplicate_matching_audits_fail(self):
        self.log.write_text("prefill started but never finished\n")
        with self.assertRaisesRegex(verifier.VerificationError, "exactly one"):
            self.verify()
        self.log.write_bytes(encoded(self.audit) * 2)
        with self.assertRaisesRegex(verifier.VerificationError, "exactly one"):
            self.verify()

    def test_fused_sdpa_must_have_positive_calls_in_this_prefill(self):
        for value in (None, 0, -1, True, "3120", 1.5):
            self.audit["fused_sdpa_calls_this_prefill"] = value
            self.write_audit()
            with self.assertRaisesRegex(verifier.VerificationError, "positive fused SDPA"):
                self.verify()
        del self.audit["fused_sdpa_calls_this_prefill"]
        self.write_audit()
        with self.assertRaisesRegex(verifier.VerificationError, "positive fused SDPA"):
            self.verify()

    def test_wrong_color_order_or_extra_answer_text_fails(self):
        for answer in ("maple-7429, harbor-6183, violet-9052, blue, red", self.answer + ", extra"):
            self.answer = answer
            self.summary["content"] = answer
            self.write_all()
            with self.assertRaisesRegex(verifier.VerificationError, "five expected values"):
                self.verify()

    def test_combined_request_requires_the_known_image_even_with_updated_hashes(self):
        self.request["messages"][0]["content"] = [{"type": "text", "text": "No image."}]
        self.write_all()
        with self.assertRaisesRegex(verifier.VerificationError, "one inline PNG"):
            self.verify()

    def test_archive_key_positions_and_question_are_bound_even_with_updated_hashes(self):
        original = copy.deepcopy(self.request)
        mutations = [
            lambda text: text + "\nThe answer is maple-7429, harbor-6183, violet-9052, red, blue.",
            lambda text: text.replace("ALPHA=maple-7429", "ALPHA=maple-0000", 1),
            lambda text: text.replace("ALPHA=maple-7429", "GAMMA=violet-9052", 1),
            lambda text: text.replace("from left to right", "from right to left", 1),
            lambda text: "Reply with: maple-7429, harbor-6183, violet-9052, red, blue.",
        ]
        for mutate in mutations:
            self.request = copy.deepcopy(original)
            text = self.request["messages"][0]["content"][1]
            updated = mutate(text["text"])
            self.assertNotEqual(updated, text["text"])
            text["text"] = updated
            self.write_all()
            with self.assertRaisesRegex(verifier.VerificationError, "trusted combined 200k"):
                self.verify()

    def test_message_semantics_allow_json_key_order_and_request_control_changes(self):
        message = self.request["messages"][0]
        self.request["messages"][0] = {"content": message["content"], "role": message["role"]}
        self.request["temperature"] = 0
        self.request["max_tokens"] = 128
        self.request["enable_thinking"] = False
        self.request["chat_template_kwargs"] = {"enable_thinking": False}
        self.request["stream_options"]["include_obfuscation"] = False
        self.write_all()
        self.assertTrue(self.verify()["verified"])

    def test_answer_bearing_tools_and_template_overrides_fail_with_unchanged_messages(self):
        original = copy.deepcopy(self.request)
        answer = ", ".join(verifier.EXPECTED_VALUES)
        extras = [
            {"tools": [{"type": "function", "function": {"name": "answer", "description": answer}}]},
            {"response_format": {"type": "json_schema", "json_schema": {"const": answer}}},
            {"chat_template": "{{ '" + answer + "' }}"},
            {"chat_template_kwargs": {"enable_thinking": False, "documents": [answer]}},
            {"chat_template_kwargs": {"enable_thinking": True}},
            {"enable_thinking": True},
            {"stream_options": {"include_usage": True, "extra_prompt": answer}},
        ]
        for fields in extras:
            with self.subTest(fields=list(fields)):
                self.request = {**copy.deepcopy(original), **fields}
                self.write_all()
                with self.assertRaises(verifier.VerificationError):
                    self.verify()

    def test_failure_cli_emits_no_success_json(self):
        self.summary["content"] = "tampered"
        self.write_summary()
        completed = subprocess.run([sys.executable, str(VERIFIER_PATH), "--probe-dir", str(self.directory),
                                    "--server-log", str(self.log)], capture_output=True, text=True)
        self.assertEqual(completed.returncode, 1)
        self.assertEqual(completed.stdout, "")
        self.assertIn("Evidence verification failed", completed.stderr)


if __name__ == "__main__":
    unittest.main()
