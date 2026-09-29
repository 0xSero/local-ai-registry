
### 2026-09-28 18:37 — zver
GPU: NVIDIA GeForce RTX 3060 Ti, 8192 MiB, 610.57.04 · CPU: Intel(R) Core(TM) i9-9980XE CPU @ 3.00GHz · RAM: 62 GB · 3 runs, 256-token generations, greedy

| Model | Gen tok/s | TTFT (s) | Prompt tok/s | Peak VRAM (GB) | Peak temp (°C) | Peak power (W) |
|---|---|---|---|---|---|---|
| gemma-4-e4b-it | 42.6 | 0.1 | 32156.7 | 5.5 | 53 | 135 |

### 2026-09-28 18:38 — zver
GPU: NVIDIA GeForce RTX 3060 Ti, 8192 MiB, 610.57.04 · CPU: Intel(R) Core(TM) i9-9980XE CPU @ 3.00GHz · RAM: 62 GB · 3 runs, 256-token generations, greedy

| Model | Gen tok/s | TTFT (s) | Prompt tok/s | Peak VRAM (GB) | Peak temp (°C) | Peak power (W) |
|---|---|---|---|---|---|---|
| gemma-4-e4b-it | 42.7 | 0.2 | 1773.1 | 5.5 | 62 | 137 |

### 2026-09-28 21:25–22:00 — zver · runtime / split / context comparison (Claude Opus 5.5)
GPUs: RTX 3060 12GB (ASUS, CUDA0 by PCI order) + RTX 3060 Ti 8GB (ZOTAC, drives display, ~1.3 GB used by desktop) · LM Studio 0.4.25 (llama.cpp runtime 2.47.0) vs llama-server v0.5.0 built locally (CUDA 13.3, sm_86) · 3 runs × 256-token coding generations, greedy, thinking on · prefill = ~6k-token prompt · recall = secret planted at 85% depth of a prompt filling ~80% of the window · VRAM/temp/power listed 3060 / 3060 Ti

| Config | Context | Gen tok/s | TTFT (s) | Prefill tok/s | Peak VRAM (GB) | Peak temp (°C) | Peak power (W) | Tool call | Long-context recall |
|---|---|---|---|---|---|---|---|---|---|
| LMS · Q4_K_S · 32k · split 12GB:8GB=13:7 · q8_0 KV · no MTP | 32k | 19.4 | 0.41 | 604 | 10.9 + 7.1 | 76/72 | 170/156 | pass | pass @19k |
| LMS · IQ4_XS · 32k · 13:7 · q8_0 KV · MTP 3 · parallel 1 | 32k | 31.2 | 0.45 | 539 | 11.0 + 6.7 | 75/71 | 170/162 | pass | pass @26k |
| llama-server · IQ4_XS · 32k · layer 14:6 · q8_0 KV · MTP 3 | 32k | 37.7 | 0.4 | 619 | 10.1 + 7.6 | 75/69 | 171/127 | pass | pass @26k |
| llama-server · IQ4_XS · 64k · layer 15:5 · q8_0 KV · MTP 3 | 64k | 34.0 | 0.4 | 600 | 11.6 + 7.6 | 76/69 | 170/119 | pass | pass @52k |
| llama-server · Q4_K_S · 32k · layer 15:5 · q8_0 KV · ub256 · MTP 3 | 32k | 34.1 | 0.39 | 617 | 11.2 + 7.4 | 76/68 | 171/118 | pass | pass @26k |
| llama-server · IQ4_XS · 16k · TENSOR 13:7 · q8_0 KV · MTP 3 | 16k | 44.1 | 0.47 | 558 | 9.9 + 7.5 | 74/69 | 170/140 | pass | pass @13k |
| llama-server · IQ4_XS · 32k · TENSOR 13:7 · q4_0 KV · MTP 3 | 32k | 45.1 | 0.48 | 557 | 10.1 + 7.6 | 75/70 | 170/140 | pass | pass @26k |
| llama-server · IQ4_XS · 64k · TENSOR 14:6 · q4_0 KV · MTP 3 | 64k | 43.6 | 0.48 | 536 | 11.1 + 7.7 | 75/70 | 170/131 | pass | pass @52k |
| llama-server · Qwen3.6-35B-A3B MoE Q4_K_XL · 128k · auto-fit (experts→RAM) · q8_0 KV · MTP 3 | 128k | 68.1 | 0.75 | 585 | 10.7 + 6.4 | 67/66 | 94/94 | pass | pass @104k |

**Failed to load (out of VRAM):** LM Studio defaults with lmstudio-community Q4_K_M (vision projector OOMs on the 12GB card; intermittent) · LMS Q4_K_S + MTP 32k (OOM at first generation) · llama-server Q4_K_S 64k (any KV) · IQ4_XS layer 96k/128k · tensor mode ≥32k with q8_0 KV · MoE with fixed 12 CPU expert layers (auto-fit works).

**Findings**
- MTP speculative decoding (built into the unsloth GGUFs) is the biggest win: 19 → 31–45 tok/s, draft acceptance 74–90%.
- Same model/settings: llama-server 37.7 tok/s vs LM Studio 31.2 (+21%), prefill 619 vs 539 (+15%).
- Tensor split mode (both GPUs compute every layer) + q4_0 KV: 43.6 tok/s at 64k — +28% over layer split at the same context. LM Studio can't do tensor mode.
- 64k is the context ceiling for Qwen3.8-27B with the desktop on the 3060 Ti. Headless would free ~1.3 GB.
- LM Studio numbers its GPUs fastest-first (3060 Ti = device 0); llama-server here uses CUDA_DEVICE_ORDER=PCI_BUS_ID.
- Qwen3.6-35B-A3B MoE with experts auto-offloaded to RAM: 68 tok/s at 128k, ~94 W/card — fast/long-context second model (weaker agentic coder than Qwen3.8-27B per public benchmarks).
- Scripts: zbench.py (benchmark any OpenAI endpoint), run_llama.sh (start llama-server + bench), lms_load.py (LM Studio load with split/KV/MTP). Raw data: bench.jsonl, server logs in logs/.

### 2026-09-29 — zver · 2× RTX 3060 12GB (ASUS + EVGA), XMP on (Claude Opus 5.5)
Same method as above (zbench.py: 3 greedy runs × 256 tokens, ~6k-token prefill, tool call, recall at ~80% of window). llama-server v0.5.0 (7fe450e). The 3060 Ti 8GB was removed. VRAM listed ASUS (GPU0) + EVGA (GPU1, display).

| Config | Gen tok/s | Prefill tok/s | Peak VRAM (GB) | Tool call | Recall (1 greedy trial, 1,024-token cap) | MTP acceptance |
|---|---|---|---|---|---|---|
| 2x3060 · IQ4_XS · 64k · TENSOR 1:1 · q4_0 KV · MTP 3 (same as old best) | 52.6 | 668.0 | 8.2 + 9.0 | pass | pass @52k | 0.75 |
| 2x3060 · IQ4_XS · 128k · TENSOR 1:1 · q4_0 KV · MTP 3 | 56.8 | 679.0 | 9.3 + 10.1 | pass | FAIL @104k | 0.95 |
| 2x3060 · Q4_K_XL · 64k · TENSOR 1:1 · q8_0 KV · MTP 3 | 51.3 | 662.0 | 10.2 + 11.0 | pass | FAIL @52k | 0.93 |
| 2x3060 · Q4_K_XL · 128k · TENSOR 1:1 · q4_0 KV · MTP 3 | 48.8 | 662.0 | 10.7 + 11.6 | pass | pass @104k | 0.84 |
| 2x3060 · Q5_K_S · 64k · TENSOR 1:1 · q4_0 KV · MTP 3 | 47.6 | 651.0 | 10.2 + 11.0 | pass | FAIL @52k | 0.91 |
| 2x3060 · Q5_K_S · 96k · TENSOR 1:1 · q4_0 KV · MTP 3 | 49.1 | 650.0 | 10.7 + 11.6 | pass | FAIL @78k | 0.88 |
| 2x3060 · IQ4_XS · 64k · layer 1:1 · q8_0 KV · MTP 3 (layer reference) | 33.2 | 641.0 | 7.8 + 10.8 | pass | pass @52k | 0.82 |
| 2x3060 · Qwen3.6-35B-A3B MoE Q4_K_XL · 128k · layer 1:1 all-GPU · q8_0 KV · MTP 3 | failed to load (OOM) | failed to load (OOM) | failed to load (OOM) | failed to load (OOM) | failed to load (OOM) | – |
| 2x3060 · Qwen3.6-35B-A3B MoE Q4_K_XL · 128k · auto-fit · q8_0 KV · MTP 3 | 88.2 | 1080.0 | 10.9 + 10.0 | pass | pass @104k | 0.83 |

**Recall re-check** (recall_check.py: 3 trials, 4,096-token cap). The single-trial FAILs above were the model thinking past the 1,024-token cap, not missing the code.

| Config | Sampling | Found | Think-loops (hit cap) |
|---|---|---|---|
| 2x3060 · IQ4_XS · 128k · tensor 1:1 · q4_0 KV · MTP 3 | greedy | 2/3 | 1 |
| 2x3060 · Q4_K_XL · 128k · tensor 1:1 · q4_0 KV · MTP 3 | greedy | 2/3 | 1 |
| 2x3060 · Q4_K_XL · 128k · tensor 1:1 · q4_0 KV · MTP 3 · sampled | qwen-thinking | 3/3 | 0 |

**llama.cpp master (b11261-era) A/B, Q4_K_XL 128k tensor:** 50.0 tok/s vs 48.8 on v0.5.0: within noise. Staying on v0.5.0.

**Findings**
- Old best config (IQ4_XS, 64k, tensor, q4_0) went 43.6 → **52.6 tok/s** (+21%), prefill 536 → 668 (+25%), with ~7 GB VRAM to spare.
- The extra VRAM buys quality and context instead: **Q4_K_XL at 128k: 48.8 tok/s**, recall 3/3 at 104k with Qwen's recommended sampling. New `qwen-coder`.
- Tensor split beats layer split by ~60% on identical cards (52.6 vs 33.2).
- `qwen-fast` (Qwen3.6-35B-A3B MoE, 128k, auto-fit): 68 → **88.2 tok/s**, prefill 585 → 1,080.
- Greedy decoding (temperature 0) can make Qwen3.8 think-loop on long prompts; the presets use temp 1.0 / top-p 0.95 / top-k 20, which fixed it in testing.
- Stress tests: memtest_vulkan passed on both cards; gpu-burn 10 min on both at once, 0 errors. EVGA runs hotter (avg 83 °C, max 85 °C, fans 91%) than the ASUS (72 °C); no thermal throttling on either. Images: ~/bench-results/dual3060-tests/images/.
