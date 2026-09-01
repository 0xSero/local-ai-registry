"""Focused tests for the server_capacity / server_context_limit launch-flag parsers."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from import_localmaxxing import server_capacity, server_context_limit


def row(command):
    return {"engineFlags": {"commandSnippet": command}}


class ServerCapacityTests(unittest.TestCase):
    def test_single_parallel_flag(self):
        self.assertEqual(server_capacity(row("vllm serve m --parallel 8")), 8)

    def test_single_np_flag(self):
        self.assertEqual(server_capacity(row("llama-server -np 4 --model g.gguf")), 4)

    def test_conflicting_repeated_flags_reject(self):
        self.assertIsNone(server_capacity(row("--parallel 8 --max-num-seqs 16")))
        self.assertIsNone(server_capacity(row("--parallel 4 --parallel 8")))

    def test_no_flag(self):
        self.assertIsNone(server_capacity(row("vllm serve model")))


class ServerContextLimitTests(unittest.TestCase):
    def test_single_direct_flag(self):
        self.assertEqual(server_context_limit(row("--max-model-len 32768")), 32768)

    def test_conflicting_direct_flags_reject(self):
        self.assertIsNone(
            server_context_limit(row("--max-model-len 32768 --context-length 8192"))
        )

    def test_llama_context_divided_by_parallel(self):
        self.assertEqual(server_context_limit(row("llama-server -c 131072 -np 4")), 32768)

    def test_llama_context_non_divisible_rejects(self):
        self.assertIsNone(server_context_limit(row("llama-server -c 100000 -np 3")))

    def test_llama_context_without_parallel_undivided(self):
        self.assertEqual(server_context_limit(row("llama-server -c 8192")), 8192)

    def test_llama_conflicting_direct_mix_rejects(self):
        self.assertIsNone(
            server_context_limit(row("llama-server -c 8192 --max-model-len 4096"))
        )


if __name__ == "__main__":
    unittest.main()
