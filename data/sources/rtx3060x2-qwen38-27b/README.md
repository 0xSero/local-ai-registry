# zver local AI bench: Qwen3.8-27B on 2× RTX 3060 12GB

Measurements and scripts behind two [local-ai-registry](https://github.com/0xSero/local-ai-registry) recipes: llama.cpp `llama-server` (bare metal, no container) serving Qwen3.8-27B and Qwen3.6-35B-A3B on two RTX 3060 12GB cards with tensor split and MTP speculative decoding.

Visual report: https://claude.ai/artifact/BMrszv5mnpsfJGkpUEGvUd

## Headline (2026-09-29)

| Model (unsloth GGUF) | Context | Launch | Decode tok/s | Prefill tok/s (~6k prompt) | Tool call | Long-context recall |
|---|---|---|---|---|---|---|
| Qwen3.8-27B UD-Q4_K_XL | 131,072 | `-sm tensor -ts 1,1 -ctk q4_0 -ctv q4_0 --spec-type draft-mtp --spec-draft-n-max 3` | 48.8 | 662 | pass | 3/3 at 104,941 prompt tokens (recommended sampling) |
| Qwen3.6-35B-A3B MTP UD-Q4_K_XL | 131,072 | `-sm layer -ctk q8_0 -ctv q8_0 --load-mode none --spec-type draft-mtp --spec-draft-n-max 3` (auto-fit, no `-ngl`) | 88.2 | 1,080 | pass | pass at ~104k |

Decode = median of 3 greedy runs × 256 output tokens on a coding prompt, thinking on. Full matrix (9 configs), recall re-checks and the earlier 3060 + 3060 Ti results: `results/bench.md`.

## Hardware and software

- 2× RTX 3060 12GB: ASUS Dual (PCI subsystem `1043:881d`) and EVGA (`3842:3656`), PCIe Gen3 x16 each, 170 W power limit. The EVGA also drives a small monitor (~0.6 GB of its VRAM).
- Intel Core i9-9980XE, 64 GB DDR4 quad-channel, Arch Linux (Omarchy), kernel 7.2.5, NVIDIA driver 610.57.04, CUDA 13.3.1.
- llama.cpp `v0.5.0` (`7fe450e19305b828c199d602c23a8337aaa1f03b`), built with `-DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=86 -DGGML_CUDA_NCCL=OFF`. Environment: `CUDA_DEVICE_ORDER=PCI_BUS_ID`, `GGML_CUDA_ALLREDUCE=internal`. Hashes: `config/build.json`.
- Common flags: `-ngl 99 -fa on -np 1 --jinja`. Sampling for serving: `--temp 1.0 --top-p 0.95 --top-k 20 --min-p 0.0` (Qwen's thinking-mode recommendation). Live presets: `config/llama-server-presets.ini`.

## Method

- `scripts/zbench.py`: against any OpenAI-compatible endpoint: 3 greedy generations (median decode tok/s, TTFT), one ~6k-token cache-busted prompt for prefill, a tool-call gate (weather tool, city argument must be right), a long-context recall gate (a code planted at 85% depth of a prompt filling ~80% of the window), and per-GPU peak VRAM / temperature / power sampled every 0.5 s.
- `scripts/recall_check.py`: 3 recall trials with a 4,096-token cap, recording whether the model hit the cap. The single-trial recall "FAIL"s in `results/bench_dual.log` all hit an earlier 1,024-token cap while still thinking. With greedy decoding, 1 of 3 trials think-looped to the 4,096 cap for both IQ4_XS and Q4_K_XL; with the recommended sampling Q4_K_XL found the code 3/3.
- `scripts/run_llama.sh` / `scripts/bench_dual.sh`: start `llama-server` with each config, run zbench, stop it.
- Stress (`stress/`): memtest_vulkan v0.5.0 standard 5-minute test per card (both PASSed), then gpu-burn on both cards for 10 minutes at 90% memory: 0 errors, `GPU 0: OK`, `GPU 1: OK`; samples in `stress/burn_samples.csv`.

## Known limits

- One user, one request at a time (`-np 1`); no concurrency sweep.
- No quality benchmark beyond the tool-call and recall gates.
- The acceptance script in local-ai-registry (`scripts/accept_recipe.py`) promotes Docker launches only; these are bare-metal launches, so they stay `candidate` until a containerized run or a native acceptance path exists.
- llama.cpp master a week newer measured 50.0 tok/s on the Q4_K_XL config (within noise).
