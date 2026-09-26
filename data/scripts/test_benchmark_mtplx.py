import io
import json
import unittest
from unittest.mock import patch

import benchmark_mtplx


class BenchmarkEvidenceTests(unittest.TestCase):
    def request(self):
        return {"generation_mode": "mtp", "depth": 3, "temperature": 0.7,
                "top_p": 0.8, "top_k": 20, "max_tokens": 256,
                "enable_thinking": False, "messages": [{"role": "user", "content": "synthetic"}]}

    def stream(self, events):
        return io.BytesIO(b"".join(b"data: " + json.dumps(e).encode() + b"\n\n" for e in events)
                          + b"data: [DONE]\n\n")

    def test_evidence_excludes_unapproved_server_metadata(self):
        stream = self.stream([
            {"choices": [{"delta": {"content": "synthetic answer"}}]},
            {"usage": {"prompt_tokens": 200100, "completion_tokens": 9},
             "timings": {"draft_n": 6, "draft_n_accepted": 4},
             "mtplx_stats": {"peak_memory_bytes": 1234, "model_path": "/private/example",
                              "api_key": "not-for-publication", "drafted_tokens": 6}},
        ])
        with patch.object(benchmark_mtplx, "http", side_effect=[io.BytesIO(b"{}"), stream]):
            result = benchmark_mtplx.run("http://127.0.0.1:18198", self.request(), "test")
        self.assertEqual(result["usage"]["prompt_tokens"], 200100)
        self.assertEqual(result["timings"]["draft_n_accepted"], 4)
        self.assertEqual(result["stats"], {"peak_memory_bytes": 1234, "drafted_tokens": 6})
        self.assertNotIn("not-for-publication", json.dumps(result))
        self.assertNotIn("/private/example", json.dumps(result))

    def test_stream_error_cannot_be_accepted(self):
        with patch.object(benchmark_mtplx, "http", side_effect=[io.BytesIO(b"{}"), self.stream([
            {"error": {"message": "context rejected"}},
        ])]):
            with self.assertRaisesRegex(RuntimeError, "context rejected"):
                benchmark_mtplx.run("http://127.0.0.1:18198", self.request(), "test")

    def test_empty_completion_cannot_be_accepted(self):
        with patch.object(benchmark_mtplx, "http", side_effect=[io.BytesIO(b"{}"), self.stream([
            {"usage": {"prompt_tokens": 200100, "completion_tokens": 0}},
        ])]):
            with self.assertRaisesRegex(RuntimeError, "No measured completion"):
                benchmark_mtplx.run("http://127.0.0.1:18198", self.request(), "test")


if __name__ == "__main__":
    unittest.main()
