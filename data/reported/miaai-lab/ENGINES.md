# MiaAI-Lab engine repos: facts for the recipe registry

Collected 2026-09-26 from shallow clones in `scratchpad/mia/src/`. Upstream comparisons use `turboderp-org/exllamav3` at tag `v1.4.2` (`src/up142`) and at main `6b84a21b6f1e5da3f291b9e1019061f0de788279` (2026-09-20, version 1.5.1, `src/upstream-exllamav3`).

---

## 1. MiaAI-Lab/exllamav3 (fork of turboderp-org/exllamav3)

| | |
|---|---|
| HEAD | `63b32f001d7b2cfed3b3e3aaf25f534ba53cc7ed` (2026-08-31) |
| GitHub fork flag | no (`isFork=false`); it is a re-uploaded copy, and `UPSTREAM_README.md` keeps the upstream README |
| Base | upstream **v1.4.2** (`exllamav3/version.py` = `1.4.2`). The file tree matches the v1.4.2 tag except for the fork additions below |
| License | MIT (`LICENSE`, "Copyright (c) 2025 Turboderp"). README: "Fork changes: MIT" |
| CI / wheels | none (no `.github/`). Upstream ships wheels built in CI; the fork does not |
| Dockerfile / published image | none |

### What is only in the fork (compared with upstream v1.4.2)
- `exllamav3/architecture/dflash2.py` and `modules/arch_specific/dflash2.py`: the DFlash2 draft model (z-lab/Qwen3.8-27B-DFlash2: grouped dynamic convs plus a top-16 candidate selector). **Upstream main now has its own `architecture/dflash2.py` and `exllamav3_ext/dflash2.cu`**, so DFlash2 is no longer fork-only on upstream main. It is fork-only only when compared with v1.4.2.
- `exllamav3/architecture/dspark.py`: the DSpark draft model (RadixArk/Qwen3.8-27B-DSpark: a DFlash backbone with Markov and confidence heads). **This is not in upstream main.** The env var `EXL3_DSPARK_CONF` sets the threshold that caps the confident-prefix draft window.
- `exllamav3/cache/nvfp4.py` (`CacheLayer_nvfp4`: E2M1 values with E4M3 block-16 scales, about 4.5 bits per element) and `exllamav3/cache/fp8.py` (`CacheLayer_fp8`: raw E4M3). Both are dequantized online in `modules/attention_fn/triton_paged.py`. `model_init.py` gains `-cq fp8` and `-cq nvfp4`, which apply to the target only; the draft cache stays fp16. **Neither is in upstream main**, which has `fp16`, `quant`, `mla`, `dsa`, `qsa` and `recurrent` caches.
- `generator/generator.py`: an optional lossless rejection-sampling verify for the DFlash stochastic walk at T>0, enabled with `EXL3_SPEC_RS=1`.
- aarch64 build: `exllamav3_ext/avx2_target.h` and `avx512_target.h` guard the AVX attributes with `#if defined(__x86_64__)…`, plus related edits in `cpu/moe_*.cpp/cu` and `parallel/all_reduce_cpu*.cpp`. Upstream main still has no `__x86_64__` guard in `avx2_target.h`, and its CI builds x86 only (Linux and Windows).
- `requirements.txt` adds `aiohttp` and `huggingface_hub`.
- `tools/`: `serve_openai.py` (the OpenAI server), `webconsole.py` plus `webconsole/` (a web UI over quantize, serve, eval and chat; `--host 127.0.0.1 --port 7861`), `webui.py` (Gradio), and the probes and benches `dflash2_*`, `dspark_*`, `decode_bench.py`, `accept_probe.py`, `longctx_passkey.py`, `nvfp4cache_test.py`, `fp8cache_test.py`, `gen_cal_trace.py` and others. The fork also adds `start.sh`, `stop.sh`, `.env.example`, `quantize.sh` and `eval/dflash2-fixtures/`.
- MTP drafting (`-mtp` in `model_init`) is **upstream**, and so is Hadamard int KV (`-cq 4`, `8`, `8,4`). The model card says: "the `qwen3_5` architecture … is supported upstream, including MTP speculative decoding".
- Upstream main has moved well past the fork (v1.5.1). It adds, among others, `glm5_next`, `glm_moe_dsa`, `kimi_linear`, `qwen4_exp`, `deepseek_v4_vision`, ngram drafting, DRY and PLE kernels. The fork has none of these.

### Install and build (exact)
From the fork checkout, or through the deployment kit, `start.sh` runs:
```bash
python3 -m venv .venv
.venv/bin/pip install --quiet --upgrade pip setuptools wheel typing_extensions packaging
.venv/bin/pip install torch --extra-index-url "${TORCH_INDEX_URL:-https://download.pytorch.org/whl/cu130}"
export TORCH_CUDA_ARCH_LIST="12.0;12.1"      # set automatically only when uname -m = aarch64; x86 auto-detects
export CUDA_HOME="${CUDA_HOME:-/usr/local/cuda}"
export MAX_JOBS=8   # 8 if nproc>=8 and RAM>=32 GB, else 4
.venv/bin/pip install --no-build-isolation .                                   # inside the engine repo
# or, from a kit:  .venv/bin/pip install --no-build-isolation git+https://github.com/MiaAI-Lab/exllamav3
.venv/bin/pip install --quiet aiohttp huggingface_hub
```
The CUDA compile takes 5 to 20 minutes. `EXL3_REPO` in `.env` overrides the source (a git URL or a local path). `quantize.sh -i <hf> -o <out> -b 3.5 [-w work] [-hq …]` pins `TORCH_CUDA_ARCH_LIST=12.0;12.1` and wraps `convert.py`.

### OpenAI server: `tools/serve_openai.py`
Launch as the kits do:
```bash
.venv/bin/python -u tools/serve_openai.py --model <dir> --host 0.0.0.0 --port 8888 \
  --cache_size 262144 --grid_size <GB> [--cache_quant nvfp4] --draft_model mtp|<draft dir>|none [--cpu_cache_size 0]
# short forms: -m -dm -gs -cs -cq -p -ccs ; also --max_body_mb 64
```
- **Flags:** `-m/--model`; `-dm/--draft_model` (`mtp` is the default and maps to `-mtp`, `none` disables drafting, a directory maps to `-dm <dir>`); `-gs/--grid_size`, an int GB memory budget with default 110; `-cs/--cache_size`, KV tokens with default 65536; `-cq/--cache_quant`; `--host` with default 0.0.0.0; `-p/--port` with default 8888; `-ccs/--cpu_cache_size`, accepted but documented as "not yet active"; `--max_body_mb`, default 64.
- **Endpoints:** `GET /v1/models` (`owned_by: "exl3"`), `GET /health` (returns `backend: "exl3"`, a busy flag, and cumulative prompt and completion token counters used by sparkDash), and `POST /v1/chat/completions` with and without streaming. There is no `/v1/completions` and no `/metrics`.
- **Tool calling:** the model's HF chat template renders `tools`. Output `<tool_call><function=…><parameter=…>` is parsed into OpenAI `tool_calls`, with arguments typed against the request's JSON schemas. `tool_choice` accepts auto, required or a named function; required and named are enforced by a system directive plus a retry. Generation stops at `</tool_call>` and returns `finish_reason: "tool_calls"`.
- **Reasoning:** thinking is always on. The kit README says `enable_thinking` is silently ignored. `split_reasoning()` splits at `</think>` and returns `reasoning_content`, both in full responses and in streamed deltas. Reasoning and content share `max_tokens`.
- **Concurrency:** batch 1, serialized by `gen_lock`. Concurrent requests queue. The kit measured 8 concurrent requests on DGX Spark at about 16.7 tok/s aggregate.
- **KV cache options** (`-cq`):

  | Value | Format | Bits per element | Source | Hardware |
  |---|---|---|---|---|
  | `none` | fp16 | 16 | upstream | all |
  | `8`, `8,4`, `4`, or `k,v` | Hadamard int | about 8.5 / 6.5 / 4.5 | upstream | all |
  | `fp8` | E4M3 | 8 | fork | cc ≥ 8.9 |
  | `nvfp4` | E2M1 with E4M3/16 scales | 4.5 | fork | cc ≥ 8.9 |

  The fp8 and nvfp4 lanes use Triton `tl.float8e4nv`. Ampere cards (sm_86, RTX 3090) cannot compile them and must use `4`.
- **Draft flags:** DFlash2 uses `-dm <DFlash2 dir>` (bf16 or EXL3 draft; block_size 8, up to 7 draft tokens). DSpark uses `-dm <DSpark dir>`, detected by architecture (`DSparkDraftModel`), and is tuned with `EXL3_DSPARK_CONF`. MTP uses `-dm mtp`. Setting `EXL3_SPEC_RS=1` enables rejection-sampling verify at T>0.
- **Long context:** when `CONTEXT_SIZE` > 262144, `start.sh` copies `config.yarn-1m.json` over `config.json`.
- **GPUs and architectures:** the fork's own evidence covers DGX Spark GB10 (sm_121, aarch64, CUDA 13 cu130 torch). The 24 GB recipe targets RTX 3090 (sm_86) and 4090 (sm_89) but states "Not yet benchmarked on RTX". sm_120 is included in the aarch64 arch list. Upstream CI builds `8.0 8.6 8.9 9.0 10.0 12.0+PTX` on cu128 and cu132, x86 only. No aarch64 wheel exists anywhere, so GB10 must compile from source.

---

## 2. MiaAI-Lab/sparkring (fork of FujitsuPolycom/sparkring)

| | |
|---|---|
| HEAD | `b9cd552fdf8ea92edb5d4c0f83ac29bed8d1e6cf` (2026-08-30, "Update README with branch stability warning") |
| Divergence | GitHub compare: **0 commits ahead, 690 behind** `FujitsuPolycom/sparkring:main` (parent last pushed 2026-09-26). The MiaAI copy is a stale mirror with no fork-only changes |
| License | Apache-2.0 (`LICENSE`, `NOTICE`, `THIRD_PARTY_NOTICES.md`) |
| What it is | "Low-latency collective transport and vLLM-based inference-serving stack for switchless clusters of DGX Spark (GB10)". Two-node pairs use one direct 200 Gb/s cable; four-node rings use a `0-1-2-3-0` cable cycle. SIRCL provides custom RDMA collectives, patched NCCL covers the rest, and CUDA-graph command rings handle decode. README says "ALPHA SOFTWARE … Pin an immutable commit". |

- **Install** (`docs/BOOTSTRAP.md`), run on rank 0:
  ```bash
  curl -fLO https://raw.githubusercontent.com/FujitsuPolycom/sparkring/main/bootstrap.sh && bash bootstrap.sh
  export PATH="$HOME/.local/bin:$PATH"          # installs ~/.local/share/sparkring and ~/.local/bin/sparkring
  sparkring host check
  sparkring cluster init --size 4 [--fabric-supernet 10.77.0.0/21]
  sparkring cluster configure [--apply]
  sparkring doctor --verify
  ```
- **Serving:** each machine-readable recipe in `recipes/*.json` (schema `sparkring-recipe/v1`) pins the HF repo and revision, the engine fork commit, the base image digest, the image builder, the launcher and a smoke harness. For example, `recipes/qwen38-27b-exl3-k5k6-pair.json` specifies:

  | Field | Value |
  |---|---|
  | Model | `malaiwah/Qwen3.8-27B-EXL3-K5K6-hydrated@ab3a91a1…` |
  | Engine | `FujitsuPolycom/vllm` tag `qwen38-tested-20260817`, commit `229effc8…`, with exllamav3 commit `5f3c537c…` |
  | Image | built locally by `runtime/qwen38/build-image.sh` as `sparkring-qwen38:arm64-sm121`. Status: "no published image" |
  | Launcher | `scripts/qwen38_dgx2_serve.sh --check` then `--run` |
  | Topology | TP2, 1M-token static YaRN |
  | KV and scheduling | fp8 KV, 32 sequences |
  | Speculation and parsers | `qwen3_5_mtp` with 3 tokens; parsers `qwen3` / `qwen3_coder` |

  Other recipes cover DeepSeek-V4-Flash-0731 (TP2 and TP4), GLM-5.2 EXL3 3.5bpw (TP4/DCP4) and GLM-5.3-Flash NVFP4 with DFlash2 (TP4). `recipes/sparkcache/` holds the SparkCache variants. The README says the GLM-5.3 images "are published by immutable digest in the two quickstarts".
- **Reported numbers** (README, 16K context): Qwen3.8-27B EXL3 K5/K6 on 2 Sparks reached C1 29.50, C8 142.20, prefill 1,367 tok/s. On 4 Sparks it reached C1 35.07, C8 191.02, prefill 1,964 tok/s.
- **Relevance:** multi-Spark (2 or 4 machine) recipes only. Nothing here targets a single machine or x86. When importing, use FujitsuPolycom/sparkring upstream rather than this mirror.

---

## 3. MiaAI-Lab/tool-eval-bench (fork of SeraphimSerapis/tool-eval-bench)

| | |
|---|---|
| HEAD | `8eca976167dfe925c125edd5a289433e78ee54e0` (2026-07-01), `pyproject` version **2.0.7** |
| Divergence | **0 ahead, 197 behind** upstream. Upstream's latest release is **v2.7.0** (2026-09-21). The MiaAI model cards cite "tool-eval-bench 2.5.1", so they ran a newer upstream build, not this fork |
| License | MIT |
| What it is | A tool-calling quality benchmark over OpenAI `/v1/chat/completions`. It runs 69 deterministic scenarios in categories A–O, plus 15 opt-in Hard Mode scenarios (P, TC-70..84), for 84 total. Mock tools return noisy payloads. Optional add-ons: throughput (`--perf` via llama-benchy, or `--perf-legacy-only`), spec-decode bench and live monitor, and GSM8K, MMLU and IFEval plugins |

- **Install:** `uv tool install git+https://github.com/SeraphimSerapis/tool-eval-bench.git`, or `pip install -e '.[dev,perf,hf]'`. Requires Python ≥ 3.11 and depends on httpx, python-dotenv, pyyaml and rich.
- **Run against an endpoint** (v2.0.7 CLI; upstream v2.7 moved to subcommands such as `tool-eval-bench run …` and `tool-eval-bench probe`):
  ```bash
  tool-eval-bench --probe --base-url http://HOST:8888            # exit 0 = ready
  tool-eval-bench --base-url http://HOST:8888 --model <id> --seed 42 [--hardmode] [--temperature 1.0] \
      --json-file result.json 2>progress.jsonl
  ```
  The URL can also come from `TOOL_EVAL_BASE_URL`, `TOOL_EVAL_MODEL` and `TOOL_EVAL_API_KEY`, or from auto-discovery on localhost ports 8000, 8080, 30000, 4000, 11434 and 5000. `--short` runs the core 15 scenarios, `--no-think` sets `enable_thinking=false`, `--trials N` adds Pass@k and Pass^k, and `--context-pressure 0.75` pre-fills context. The default temperature is 0.0, the timeout 60 s per request, and the limit 8 turns per scenario.
- **Output:**
  - JSON with fields `schema_version: "1"`, `tool_eval_bench_version`, `final_score` (0–100), `rating`, `safety_warnings`, `deployability` and `total_scenarios`, plus per-scenario detail.
  - JSONL progress on stderr, ending with `{"event":"benchmark_complete",…,"final_score":N}`.
  - A Markdown report with full traces at `runs/YYYY/MM/<run_id>.md`.
  - A SQLite record at `data/benchmarks.sqlite`.
  - A Python API: `tool_eval_bench.api.run_benchmark(...)`.
- **Scoring:** pass = 2, partial = 1, fail = 0. The score is total points over maximum points, times 100. Safety gating caps the rating at 3 stars if category K scores below 50%. Hard Mode is excluded from the base score by default.
- **Runtime:** v2.0.7 does not document it. Upstream v2.7 says the `--short` run "takes a couple of minutes". A full run depends on model speed and reasoning length. It is sequential by default (`--parallel 1` is recommended for reliable scores), so on a batch-1 server such as serve_openai.py it runs serially. The upper bound is 84 scenarios × up to 8 turns × a 60 s timeout.
- **Use as a quality gate:** feasible and already used this way. The Qwen3.8-27B EXL3 model card reports "tool-eval-bench 2.5.1, hardmode, temperature 1.0, seed 42: 87–88 / 100". Mechanically, run with `--json-file` and threshold `final_score`, also checking `safety_warnings` is empty. There is no built-in `--min-score` or fail-under flag: non-zero exit codes cover only probe, detection and empty-model errors, so the gate must parse the JSON. Caveats: `--seed` controls sampling only and runs are not bit-reproducible; scores vary about ±1 between runs (87 vs 88 above); the scenarios test tool-call protocol and judgment, not general quality. Pin the version, since scenario counts changed (upstream now has 23 Hard Mode scenarios), and compare only runs from the same version with the same flags.

---

## 4. MiaAI-Lab/sparkDash

| | |
|---|---|
| HEAD | `754f40a7454fed1d26d47d1d68dd7bef930ce5ca` (2026-09-22, "Release 1.8.8: show SGLang tok/s from the live throughput gauge") |
| Origin | MiaAI-Lab's own project, not a fork |
| License | MIT |
| What it is | A multi-unit monitoring web dashboard (React/Vite front end, Node/Express plus WebSocket back end) for DGX Spark GB10 machines and SSH-reachable Linux hosts with an NVIDIA GPU. It collects GPU, CPU, unified memory, storage and network metrics. An LLM probe auto-detects llama.cpp, vLLM, SGLang, ds4-server, EXL3 (through `serve_openai.py` `/health` `backend:"exl3"` / `owned_by:"exl3"`, see `server/collectors/LlmProbe.js`) and q27. It also has a decode benchmark across concurrency levels, a prefill sweep from 1k to 300k tokens, inference health read from Prometheus `/metrics` (vLLM and q27), plus ComfyUI, Hermes Agent and tailnet probes, Wake-on-LAN and shutdown controls |

- **Run:** `git clone https://github.com/MiaAI-Lab/sparkDash && cd sparkDash && docker compose up --build -d`, then open http://127.0.0.1:5555. For development, run `npm install && npm run dev` (Vite serves on :5173).
  - `docker-compose.yml` builds `Dockerfile` for linux/arm64 from `public.ecr.aws/docker/library/node:22-bookworm-slim`.
  - The container runs with `network_mode: host`, `privileged: true` and `pid: host`, and mounts `/proc`, `/sys`, `/`, `nvidia-smi` and `libnvidia-ml.so.1` (aarch64 path).
  - Environment defaults: `BIND_HOST=127.0.0.1`, `PORT=5555`, `LLM_PORT=8888`. A LAN bind requires `SPARKDASH_TOKEN`.
  - No published image: it is built locally.
- **Relevance to the registry:** it is not an inference engine. It is useful as an operator dashboard and as a second opinion on tok/s. Its decode bench protocol is temperature 0 with thinking off.

---

## Cross-cutting notes
- All Qwen3.8-27B EXL3 kits serve on port 8888. The DFlash2 kit uses the fork; the 16 GB one-click kit deliberately uses **upstream exllamav3 v1.4.4** (git tag, or turboderp release wheels selected by `tools/wheels.py`) and its own extended `serve_openai.py`, which adds `--model_id`, `--vision`, `--image_max_pixels`, `--ui` and `--harness_port`. That kit supports only integer KV and MTP.
- None of the MiaAI EXL3 paths has a Dockerfile or container image. Every recipe is a venv bootstrap.
