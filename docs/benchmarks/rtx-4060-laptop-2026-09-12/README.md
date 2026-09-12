# RTX 4060 Laptop GPU: five text-generation acceptance runs

All five selected artifacts completed on one NVIDIA GeForce RTX 4060 Laptop GPU. The selection covers the current generations verified for this campaign: LFM2.5, Gemma 4 and Qwen3.8. This contribution adds a distinct laptop hardware record, five measured recipes and the missing LFM2.5-2.6B QAD artifact. It does not treat the desktop RTX 4060 as the same device.

Runs took place on 2026-09-12 in Asia/Kolkata; the preserved UTC timestamps are on 2026-09-11. Registry baseline: `4016d3036ebc57f61747214e22caa445fbb48bb1`.

| Model / quantization | Actual input tokens | Median decode, tok/s | Median first token, ms | Peak GPU memory, GiB | Configured context |
|---|---:|---:|---:|---:|---:|
| [LFM2.5-2.6B QAD Q4_0](../../../registry/recipe/lfm25-26b-qad-q4-0-rtx4060-laptop-llamacpp-tp1.json) | 1010 / 4076 | 124.5 / 119.7 | 234 / 914 | 1.78 | 8,192 |
| [Gemma 4 E4B QAT Q4_0](../../../registry/recipe/gemma4-e4b-qat-q4-0-rtx4060-laptop-llamacpp-tp1.json) | 1013 / 4093 | 62.7 / 61.2 | 456 / 1767 | 3.03 | 8,192 |
| [LFM2.5-8B-A1B Q4_K_M](../../../registry/recipe/lfm25-8b-a1b-q4-k-m-rtx4060-laptop-llamacpp-tp1.json) | 1009 / 4096 | 158.9 / 151.6 | 494 / 1751 | 5.10 | 8,192 |
| [Gemma 4 12B QAT Q4_0](../../../registry/recipe/gemma4-12b-qat-q4-0-rtx4060-laptop-llamacpp-tp1.json) | 247 / 511 | 30.5 / 30.0 | 395 / 754 | 7.08 | 2,048 |
| [Qwen3.8-27B UD-IQ2_XXS](../../../registry/recipe/qwen38-27b-ud-iq2-xxs-rtx4060-laptop-llamacpp-tp1.json) | 247 / 511 | 17.6 / 17.1 | 925 / 1753 | 7.04 | 2,048 |

Each slash separates the two measured prompt lengths, in order. Values are medians of three sequential requests after one warmup per point. The first three rows generated 256 tokens per request; Gemma 12B and Qwen generated 128. Their shorter prompts and output caps mean these are observations at different workloads, not an equal-workload ranking. Configured context is server capacity, not a claim that its full length was benchmarked.

## Hardware and runtime

- GPU: NVIDIA GeForce RTX 4060 Laptop GPU, 8,188 MiB reported total, compute capability 8.9, driver 610.57.04.
- Host: AMD Ryzen 9 8945HS, 16,007,725,056 bytes of system RAM, CachyOS, kernel 7.2.2-1-cachyos. AC was connected and the platform profile was `balanced` at each launch.
- Observed device power peaked at 57.03 W and temperature at 85 C during measured requests. The reported default/max power limits were 55/90 W; the actual enforced limit was unavailable. These measurements describe this laptop's operating conditions.
- Runtime: llama.cpp b10481, commit `25ae3a9b331fffea50ff8d07a5cad34c33f1276f`, CUDA 12.8.1 in Ubuntu 24.04. Docker 29.7.2 and NVIDIA Container Toolkit 1.20.0.
- Image: `ghcr.io/ggml-org/llama.cpp@sha256:87c812ce5a8955364c665229d0848e07a2cf38fbd387d83530bc4575a22ffaa1`. Both image identity and model file size/SHA-256 were checked before inference.

The table's GPU memory is the highest whole-device sample overlapping a measured request, polled every 200 ms; it includes other GPU processes and can miss peaks between polls. The device was using 44 MiB before the campaign. Registry `peak_vram_gb` uses decimal GB, while this table uses GiB. Host RAM and swap observations in the evidence are system totals, not per-model requirements; other applications remained running. Task-owned model downloads and the image pull had completed before these selected measurements.

## Workload and observations

Every recipe used one CUDA device, one request at a time, `--n-gpu-layers 999`, `--fit off`, flash attention, eight CPU threads, and text-only inference without a multimodal projector. LFM2.6, Gemma E4B and LFM8 used an 8,192-token context with batch/microbatch 512/128. Gemma 12B and Qwen used a 2,048-token context with batch/microbatch 128/64. Full argv is in each recipe and raw evidence bundle.

Prompts request a practical guide to reliable local model inference, using repeated reference notes to approach each target length. The server's `/v1/chat/completions/input_tokens` result and returned `usage.prompt_tokens` agree at every point. Requests set `temperature: 0`, `seed: 42`, `cache_prompt: false`, `reasoning_effort: none` and `chat_template_kwargs.enable_thinking: false`; the server uses `--reasoning-budget 0`. Every measured response reports `timings.cache_n: 0`.

Decode is the server's `timings.predicted_per_second`; prefill uses its prompt timing. First-token latency is measured by the client from request start to the first content/reasoning delta, excluding metadata-only chunks. Literal timestamped SSE, final usage, timings, requests, individual sample measurements and `[DONE]` are preserved. Each response completed the stream and generated the requested token cap. The helper's decode threshold establishes an acceptance floor, not proof of GPU execution; device telemetry and loader logs provide that evidence.

The loader reported 31/31 offloadable layers for LFM2.6, 43/43 for Gemma E4B, 25/25 for LFM8, 49/49 for Gemma 12B and 65/65 for Qwen. All five also reported a `CPU_Mapped` model buffer, so these are not claims that all weights reside in GPU memory. LFM2.6, Gemma E4B and Qwen placement observations came from separate startup checks with identical inference arguments plus `--verbosity 4`; their default logging had omitted loader details. Gemma 12B and LFM8 recorded these details during the selected benchmark run.

Arithmetic, JSON extraction and short Python-generation smoke requests are included as inspectable output examples, not a quality benchmark. All five eventually produced the correct arithmetic result and a suitable Python function. The extraction prompt asked for `name` and `count` from “Mira owns seven notebooks” without specifying whose name: E4B returned `notebook`, Gemma 12B returned `notebooks`, and the others returned `Mira`; all returned 7. That ambiguity prevents scoring these responses as a clean accuracy test. Several responses used code fences or extra prose despite strict-format instructions.

LFM8 is the fastest decoder in this campaign, but every measured 4,096-token response includes literal `<think></think>` in `content`. Its arithmetic example uses 508 output tokens, including reasoning-like prose, despite a zero reasoning budget. These tokens are included in throughput. Empty `reasoning_content` does not establish that reasoning is disabled. The initial LFM2.6 run lacked the server budget setting and was superseded; LFM8 was repeated with a larger smoke-only cap so its examples could finish. Both earlier runs remain in the bundles. Tools, vision and reasoning capabilities remain unvalidated.

## Container device requirement

On this host, `--gpus device=0` exposed the GPU to `nvidia-smi`, but CUDA initialization failed with error 999. A controlled repeat succeeded when adding only `--device /dev/nvidia-uvm`; adding only `/dev/nvidia0` or `/dev/nvidiactl` did not resolve it. Every measured launch includes the UVM device and llama.cpp's explicit `--device CUDA0`. No daemon, cgroup, kernel or power settings were changed. The exact underlying registration failure was not established. See [NVIDIA's device/cgroup troubleshooting guidance](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/troubleshooting.html#containers-losing-access-to-gpus-with-error-failed-to-initialize-nvml-unknown-error).

The exporter, plugin gate and launchers now preserve this explicit NVIDIA device declaration. Validation allows only `/dev/nvidia-uvm` for NVIDIA recipes rather than permitting arbitrary device passthrough.

## Replay one measured point

The Omarchy plugin needs the Hugging Face CLI (`hf`) on the host for this pinned runtime: its image contains Python but not `huggingface_hub`. The plugin checks that prerequisite before downloading. The manual replay below uses `curl`.

From the repository root, with the existing Docker/NVIDIA setup, download and verify the selected QAD artifact:

```bash
export MODEL_ROOT="$PWD/models"
mkdir -p "$MODEL_ROOT/lfm26-qad-q4"
curl -fL --retry 3 'https://huggingface.co/LiquidAI/LFM2.5-2.6B-GGUF/resolve/84022ce711b28455e8c4fc364ce68c00cf995875/LFM2.5-2.6B-QAD-Q4_0.gguf' \
  -o "$MODEL_ROOT/lfm26-qad-q4/LFM2.5-2.6B-QAD-Q4_0.gguf"
printf '%s  %s\n' 'a247afd6414918eac8e520a9e6137dc271235461ecbe1180462221d5b8d40b03' \
  "$MODEL_ROOT/lfm26-qad-q4/LFM2.5-2.6B-QAD-Q4_0.gguf" | sha256sum -c -
```

Start the server in that terminal:

```bash
docker run --rm --name local-ai-rtx4060-lfm26 \
  --gpus device=0 --device /dev/nvidia-uvm \
  --publish 127.0.0.1:18080:8080 \
  --mount "type=bind,source=$MODEL_ROOT/lfm26-qad-q4,target=/models,readonly" \
  --entrypoint /app/llama-server \
  ghcr.io/ggml-org/llama.cpp@sha256:87c812ce5a8955364c665229d0848e07a2cf38fbd387d83530bc4575a22ffaa1 \
  --device CUDA0 \
  --model /models/LFM2.5-2.6B-QAD-Q4_0.gguf \
  --alias LFM2.5-2.6B-QAD-Q4_0.gguf \
  --ctx-size 8192 \
  --parallel 1 \
  --n-gpu-layers 999 \
  --fit off \
  --flash-attn on \
  --no-mmproj \
  --jinja \
  --metrics \
  --perf \
  --threads 8 \
  --threads-batch 8 \
  --batch-size 512 \
  --ubatch-size 128 \
  --host 0.0.0.0 \
  --port 8080 \
  --reasoning-budget 0
```

In a second terminal at the repository root, after `/health` returns successfully, extract the exact measured request and perform one warmup using the helper's measurement function. The following CLI call then measures three samples. The endpoint is the server origin, without a `/v1` suffix.

```bash
python3 - <<'PY'
import gzip, json, sys
from pathlib import Path
sys.path.insert(0, 'scripts')
from accept_recipe import measure
bundle = json.loads(gzip.decompress(Path('docs/benchmarks/rtx-4060-laptop-2026-09-12/lfm26-qad-q4.json.gz').read_bytes()))
key = 'runs/' + bundle['selected_run'] + '/1024/request.json'
Path('request-1010.json').write_text(bundle['files'][key])
body = json.loads(bundle['files'][key])
measure('http://127.0.0.1:18080', body['model'], samples=1,
        request_body=body, raw_output=Path('replay-1010-warmup.jsonl'))
PY
python3 scripts/accept_recipe.py lfm25-26b-qad-q4-0-rtx4060-laptop-llamacpp-tp1 \
  --endpoint http://127.0.0.1:18080 --request-json request-1010.json \
  --raw-output replay-1010.jsonl --revalidate
```

Run this in a working copy: the helper refreshes that recipe's acceptance record with the replayed point. Choose fresh filenames for both the warmup JSONL and CLI `--raw-output` on each replay; both refuse to overwrite existing evidence. The `4096/request.json` entry supplies the second LFM2.6 point. For other artifacts, use their pinned file, recipe argv and corresponding bundle's selected-run requests (`1024`/`4096` or `256`/`512`). Their exact source requests, token-count responses and launch records are included; the original GPU telemetry belongs to the recorded campaign, not a later replay.

## Pinned artifacts and raw evidence

| Artifact | Pinned checkpoint | SHA-256 |
|---|---|---|
| LFM2.5-2.6B-QAD-Q4_0.gguf | [LiquidAI/LFM2.5-2.6B-GGUF @ 84022ce711b2](https://huggingface.co/LiquidAI/LFM2.5-2.6B-GGUF/resolve/84022ce711b28455e8c4fc364ce68c00cf995875/LFM2.5-2.6B-QAD-Q4_0.gguf) | `a247afd6414918eac8e520a9e6137dc271235461ecbe1180462221d5b8d40b03` |
| gemma-4-E4B_q4_0-it.gguf | [google/gemma-4-E4B-it-qat-q4_0-gguf @ 4b4a2c1d584b](https://huggingface.co/google/gemma-4-E4B-it-qat-q4_0-gguf/resolve/4b4a2c1d584be7264f87aac328a1bc739ce81b6c/gemma-4-E4B_q4_0-it.gguf) | `676c35070db6dbe52f93e9c864ee0fba4eddea94b9c875d9cb10daff453fbaee` |
| LFM2.5-8B-A1B-Q4_K_M.gguf | [LiquidAI/LFM2.5-8B-A1B-GGUF @ 49c148317070](https://huggingface.co/LiquidAI/LFM2.5-8B-A1B-GGUF/resolve/49c14831707011e64d70b2ebd8462ba08d608434/LFM2.5-8B-A1B-Q4_K_M.gguf) | `4923ec14f06b968b74d663e5949867d2d9c3bf13a20b8be1a9f9af39989b2bb0` |
| gemma-4-12b-it-qat-q4_0.gguf | [google/gemma-4-12B-it-qat-q4_0-gguf @ 29d097773436](https://huggingface.co/google/gemma-4-12B-it-qat-q4_0-gguf/resolve/29d097773436b69ff9feafd636ab4cf873786537/gemma-4-12b-it-qat-q4_0.gguf) | `93567e57a8fe10b23569b9d9ec38cd005deedf71e29477c421a4b83f418a538b` |
| Qwen3.8-27B-UD-IQ2_XXS.gguf | [unsloth/Qwen3.8-27B-GGUF @ 4ca720788d1e](https://huggingface.co/unsloth/Qwen3.8-27B-GGUF/resolve/4ca720788d1e01f1bff70c033e0d0028fd02e502/Qwen3.8-27B-UD-IQ2_XXS.gguf) | `e792d8fb3142fe6d9171876d6da0f71f05a71028718debc72dbec93ff645e67d` |

Each `<artifact-id>.json.gz` below is a deterministic gzip-compressed JSON object with its pin, download receipt, selected result, included run names and a `files` mapping containing the original text of each request, response stream, startup log and telemetry file. Known local directory prefixes were replaced with `${MODEL_ROOT}`, `${RUN_ROOT}`, `${REGISTRY_ROOT}` and `${WORKSPACE}`; other text, including SSE framing and unsuccessful/superseded attempts, is preserved. Runtime diagnostics include the initial failed CUDA check as well as the successful device probes.

- [LFM2.5-2.6B QAD Q4_0 raw evidence](lfm26-qad-q4.json.gz), selected run `lfm26-qad-q4-no-thinking`.
- [Gemma 4 E4B QAT Q4_0 raw evidence](gemma-e4b-qat-q4.json.gz), selected run `gemma-e4b-qat-q4-initial`.
- [LFM2.5-8B-A1B Q4_K_M raw evidence](lfm8-q4.json.gz), selected run `lfm8-q4-smoke512`.
- [Gemma 4 12B QAT Q4_0 raw evidence](gemma12-qat-q4.json.gz), selected run `gemma12-qat-q4-initial`.
- [Qwen3.8-27B UD-IQ2_XXS raw evidence](qwen38-27b-ud-iq2-xxs.json.gz), selected run `qwen38-27b-ud-iq2-xxs-initial`.

The registry's `make trust` derives all five validated statuses from their acceptance evidence; it does not certify output quality or untested context lengths. The recommendation is selected with `python3 scripts/recommend.py --only rtx-4060-laptop-8gb` using the existing hardware-tier policy.

Validation passed: `make check` (45 Node tests, 26 Python tests, schema validation, TypeScript type checking and generated type/index checks), plugin `make check` (58 shell assertions and recipe sanity checks), plus real export and plugin hardware/mount/device contract checks. Engine, gateway and host download commands were captured. Only the fallback import preflight executed in the cached pinned image, with network and GPU access disabled; it correctly required host `hf` before downloading.
