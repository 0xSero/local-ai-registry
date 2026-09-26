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

    def test_llama_unified_kv_uses_full_context_and_last_flag_wins(self):
        for flags, expected in (("--kv-unified", 8192), ("-kvu", 8192),
                                ("-kvu --no-kv-unified", 2048), ("--kv-unified -no-kvu", 2048),
                                ("--no-kv-unified -kvu", 8192), ("-no-kvu --kv-unified", 8192),
                                ("--kv_unified", 8192), ("--kv_unified --no_kv_unified", 2048)):
            with self.subTest(flags=flags):
                self.assertEqual(server_context_limit(row(f"llama-server -c 8192 --parallel 4 {flags}")), expected)
        self.assertEqual(server_context_limit(row("llama-server -c 100000 -np 3 -kvu")), 100000)
        self.assertEqual(server_context_limit(row("--ctx_size 8192 --parallel 4 --kv_unified")), 8192)

    def test_llama_kv_environment_precedence_and_unknown_slot_counts(self):
        command = "llama-server -c 8192 --parallel 4"
        for value in ("on", "enabled", "true", "1"):
            env = {"LLAMA_ARG_KV_UNIFIED": value}
            self.assertEqual(server_context_limit(row(command), env), 8192)
            self.assertEqual(server_context_limit(row(command + " --no_kv_unified"), env), 2048)
            env["LLAMA_ARG_NO_KV_UNIFIED"] = ""
            self.assertEqual(server_context_limit(row(command), env), 2048)
            self.assertEqual(server_context_limit(row(command + " -kvu"), env), 8192)
        for value in ("off", "disabled", "false", "0"):
            self.assertEqual(server_context_limit(row(command), {"LLAMA_ARG_KV_UNIFIED": value}), 2048)
        self.assertIsNone(server_context_limit(row(command), {"LLAMA_ARG_KV_UNIFIED": "TRUE"}))
        self.assertIsNone(server_context_limit(row("-c 8192"), {"LLAMA_ARG_N_PARALLEL": "4"}))
        self.assertIsNone(server_context_limit(row(""), {"LLAMA_ARG_CTX_SIZE": "8192"}))
        for flags in ("--parallel 4 --parallel 2", "--parallel 4 --parallel -1", "--parallel 0", "-c 0", "--ctx_size 4096"):
            self.assertIsNone(server_context_limit(row("-c 8192 " + flags)))

    def test_llama_conflicting_direct_mix_rejects(self):
        self.assertIsNone(
            server_context_limit(row("llama-server -c 8192 --max-model-len 4096"))
        )


if __name__ == "__main__":
    unittest.main()
