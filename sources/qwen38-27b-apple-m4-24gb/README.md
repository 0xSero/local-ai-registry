# Qwen3.8-27B on a 24 GB Apple M4: evidence

This directory holds the evidence for the recipe
`qwen3-8-27b-ud-iq3-xxs-apple-m4-24gb-llama-cpp-metal-mtp1-vision-200k`.
All runs were on one Mac, on 2026-09-25.

| Item | Value |
|---|---|
| Mac | iMac (24-inch, 2024), Mac16,3 |
| Chip | Apple M4, 10-core CPU, 10-core GPU |
| Memory | 24 GB unified memory |
| macOS | 26.5 (25F71) |
| Engine | llama.cpp b11182 (e9f824d8c), official macOS arm64 release |
| Weights | `unsloth/Qwen3.8-27B-GGUF` at `4ca72078`, file `UD-IQ3_XXS` (3.20 bits per weight) |
| Vision | `mmproj-BF16.gguf` from the same revision |
| MTP | Built into the GGUF (`blk.64.nextn`), used with `--spec-type draft-mtp` |

## Files

| File | Contents |
|---|---|
| `environment.json` | Hardware, macOS, engine and weight hashes, the exact server argv, and the run timeline |
| `metal-working-set.txt` | The default and the raised Metal memory limit, and an idle baseline |
| `gguf-metadata.json` | MTP tensors and effective bits per weight, from the GGUF header |
| `smoke.json` | Raw responses for chat, decode, tool call, two vision probes and reasoning |
| `ladder/ladder-*.json` | One receipt for each coherence-ladder rung (4K, 32K, 200K) |
| `server-final.log` | The full server log for the smoke and ladder runs (only the work path is replaced with `<workdir>`) |
| `tuning/llamacpp-bench.jsonl` | Decode and prefill speed for each tuning configuration |
| `tuning/configs.json` | The settings, the protocol and the log for each tuning configuration |
| `tuning/logs/` | The server log for each tuning configuration |
| `mlx-comparison/mlx-vlm-bench.txt` | The MLX speed comparison |
| `perplexity/` | The full `llama-perplexity` logs for UD-IQ3_XXS and UD-Q3_K_XL |
| `fit-params-estimate.txt` | The llama.cpp memory estimate for the model and the 204,800-token context |
| `serve-24gb.sh` | The launch script |
| `harness/` | The scripts and the test image that produced the evidence |

## How to repeat the runs

1. Download the engine and check it:
   ```
   curl -LO https://github.com/ggml-org/llama.cpp/releases/download/b11182/llama-b11182-bin-macos-arm64.tar.gz
   shasum -a 256 llama-b11182-bin-macos-arm64.tar.gz
   # ca2000b4037c3a467ec0758538af7e6f2b4dc2904f593bbedf4b28a97b6c444a
   tar xzf llama-b11182-bin-macos-arm64.tar.gz
   ```
   If a browser downloaded the tarball, run `xattr -dr com.apple.quarantine llama-b11182` before you start the server.
2. Raise the GPU memory limit. This setting is lost when the Mac restarts.
   ```
   sudo sysctl iogpu.wired_limit_mb=20480
   ```
3. Start the server. The first start downloads about 11.9 GB.
   ```
   LLAMA_SERVER=./llama-b11182/llama-server LLAMA_CACHE=~/models ./serve-24gb.sh
   ```
   `-hf` uses the `main` branch of the model repository. The evidence used `main` at `4ca72078`. For a pinned run, download `Qwen3.8-27B-UD-IQ3_XXS.gguf` and `mmproj-BF16.gguf` at that revision, check the sha256 values in `environment.json`, and use `-m` and `--mmproj`.
4. Run the smoke probes:
   ```
   python3 harness/smoke.py http://127.0.0.1:8080 smoke.json
   ```
5. Run the coherence ladder. It needs a llama.cpp checkout for the haystack text.
   ```
   git clone https://github.com/ggml-org/llama.cpp
   git -C llama.cpp checkout a25c9865fe03c954c93fd755b5d79ae86ba99750
   HAYSTACK_SRC=llama.cpp python3 harness/ladder.py ladder 4096 32768 202000
   ```
   The 200K rung took 2 h 37 min on this Mac. On a slower chip, set `LADDER_TIMEOUT=43200`.

## Notes

- The tuning runs used the same argv as the recipe, with two differences: `--image-min-tokens 1024` was not present yet, and each run changed `QUANT`, `SPEC` or `DRAFT_N` (see `tuning/configs.json`).
- `server-final.log` also shows three earlier ladder requests (tasks 156, 183 and 210). A sizing bug in the first version of `ladder.py` made those prompts too short, so I stopped that run and did not keep its receipts. The three rungs in `ladder/` ran after the fix.
- The `W find_slot: non-consecutive token position` lines in the logs occur on every image request. They are normal for image tokens in llama.cpp.
- `peak_wired_gb` in the ladder receipts is system-wide `vm_stat` wired memory, not memory for one process.
