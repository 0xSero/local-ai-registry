# Qwen3.8-27B on Apple Silicon: reproducible native recipe

**The combined 200k smoke test passed on M3 Max 36 GiB.** [The archived run](evidence/combined-200k-fused/summary.json) processed **200,163 cold prompt tokens** and returned all three distant archive values and both image colors in a 26-token answer with native MTP active. [The independent verification receipt](evidence/combined-200k-fused/verification-receipt.json) confirms the answer and retention of the complete prompt in all 16 full-attention caches. [The M3 Max 36 GB recipe](../../registry/recipe/qwen38-27b-4bit-m3-max-36gb-mlx-vlm-mtp-200k.json) is now validated by a separate three-sample short acceptance run; the measured MTP/no-MTP comparison is recorded below.

The earlier 1024-token prefill attempt using the default attention path failed with Metal out-of-memory after the last logged progress of 113,664 / 200,163 tokens; [the failure evidence](evidence/failed-1024-prefill/summary.json) is preserved. The successful run used the bounded fused-attention wrapper below.

The available host is an **Apple M3 Max with 36 GiB unified memory**, running macOS 27.2; see [hardware.json](hardware.json). This is a native macOS/Metal launch with one request at a time. There is no 24 GB measurement, no exact 32 GB measurement, and no result for M1, M2, M4, M5, or M6. Reproducibility of this launch is not evidence that it is optimal on every M-series chip.

## What is pinned

| Component | Exact input |
| --- | --- |
| Python | 3.12.13, arm64 |
| MLX / MLX Metal | 0.32.2 |
| MLX-VLM | 0.7.3 from commit `573562df9fd9259047e3dc793e6b48be23389221` |
| Base weights | `mlx-community/Qwen3.8-27B-4bit` at `10c35caafbb80f7dc6a7a432cdd11af10a6d4818` |
| Native MTP head | `mlx-community/Qwen3.8-27B-MTP-bf16` at `9b1e8ab2bcfd157956a4d85927310de551fcdab1` |
| Full Python environment | [requirements-macos-arm64.txt](requirements-macos-arm64.txt) |
| Model file manifests | [base-manifest.json](base-manifest.json), [mtp-manifest.json](mtp-manifest.json) |

The text model uses affine **4-bit weights**; the vision encoder and separate native MTP head remain **BF16**, as verified in [the tensor-header inventory](weight-precision-inventory.json). Norms and quantization metadata also retain higher precision. The requested KV scheme is TurboQuant 4-bit; the runtime's quantization policy keeps the final full-attention layer's KV in **BF16**. Recurrent state is distinct from the quantized attention KV.

The two pinned model snapshots total **16,950,447,265 bytes (16.95 GB decimal)** according to their manifests, before the virtual environment and download metadata. Full downloads and checksum verification were completed locally. Download caches may avoid repeat weight transfers; remote metadata checks and the initial dependency/model downloads still need network access. Recorded checks are [base-verification.txt](base-verification.txt) and [mtp-verification.txt](mtp-verification.txt); their extra-file warnings concern local download bookkeeping rather than an assertion that every extra file belongs to the model.

## Install and fetch the exact snapshots

Run these commands from the repository root on macOS arm64 with `uv` installed. The requirements file pins the complete observed environment, including the MLX-VLM Git revision; it is not a wheel hash lockfile.

```sh
uv venv --python 3.12.13 runs/qwen38/venv
uv pip install --python runs/qwen38/venv/bin/python \
  -r sources/qwen38-apple-silicon/requirements-macos-arm64.txt

runs/qwen38/venv/bin/hf download mlx-community/Qwen3.8-27B-4bit \
  --revision 10c35caafbb80f7dc6a7a432cdd11af10a6d4818 \
  --local-dir runs/qwen38/models/Qwen3.8-27B-4bit
runs/qwen38/venv/bin/hf download mlx-community/Qwen3.8-27B-MTP-bf16 \
  --revision 9b1e8ab2bcfd157956a4d85927310de551fcdab1 \
  --local-dir runs/qwen38/models/Qwen3.8-27B-MTP-bf16

runs/qwen38/venv/bin/hf cache verify mlx-community/Qwen3.8-27B-4bit \
  --revision 10c35caafbb80f7dc6a7a432cdd11af10a6d4818 \
  --local-dir runs/qwen38/models/Qwen3.8-27B-4bit --fail-on-missing-files
runs/qwen38/venv/bin/hf cache verify mlx-community/Qwen3.8-27B-MTP-bf16 \
  --revision 9b1e8ab2bcfd157956a4d85927310de551fcdab1 \
  --local-dir runs/qwen38/models/Qwen3.8-27B-MTP-bf16 --fail-on-missing-files
```

Download the complete snapshots, including their processors, tokenizer, chat template, configuration, and vision weights. Do not replace either revision with `main` or substitute a similarly named quantization.

## Launch

[The pinned server wrapper](../../registry/asset/qwen38-mlx-vlm-serve.py) passes the following arguments to the pinned MLX-VLM server, sets an MLX allocation guideline, and emits runtime/cache audit JSON in the server log. Its default allocation guideline is the smaller of 27 GiB and the device's recommended working set, with a 256 MiB allocator cache. This guideline is **not a hard process-memory cap or a no-swap guarantee**. It supplies no evidence of a 24 GB fit.

The wrapper also selects MLX's public `force_fused=True` attention path for the measured BF16 text-prefill shape: one batch, 24 query heads, four KV heads, head dimension 256, more than eight query tokens, and at least 8192 KV tokens. It passes the mask unchanged and raises if the fused kernel is unavailable. In pinned MLX 0.32.2, [the default head-256 routing on pre-NAX GPUs](https://github.com/ml-explore/mlx/blob/1f8e74e3f12f31365464a6867c6579f0e9b29d85/mlx/backend/metal/scaled_dot_product_attention.cpp#L761) uses an unfused path whose score-buffer storage grows with query length times context length. That path caused the recorded M3 out-of-memory failure.

A [bounded synthetic attention comparison](sdpa-memory-comparison.json) on this Mac measured 1.816 GB peak MLX allocation for default attention versus 0.193 GB forced-fused at 1024 query / 32768 KV tokens. These are single attention operations, not full-model memory figures. The forced path was about 7% slower for that isolated operation but avoided the large score buffer. BF16 parity tests allow small floating-point differences from changed accumulation order; they do not assert identical logits or broad model quality. The wrapper records actual forced-call counts per prefill and allocation snapshots every 16384 processed columns.

Prefix caching is disabled in memory and on disk. The four-hour token-queue timeout allows the long cold prefill to complete without the default queue timeout interrupting it.

Keep the explicit KV and drafter environment variables as well as the CLI arguments. This pinned runtime reads configuration defaults during module import: CLI flags alone can announce TurboQuant while the cache path still uses a uniform quantizer. Setting the environment before Python starts supplies the configuration to those imported modules. The final-prefill audit records actual cache classes and bit widths so the configured scheme can be checked against the running cache.

```sh
env APC_ENABLED=0 APC_DISK_ENABLED=0 HF_HUB_OFFLINE=1 \
  KV_BITS=4 KV_GROUP_SIZE=64 KV_QUANT_SCHEME=turboquant QUANTIZED_KV_START=0 MAX_KV_SIZE=201024 \
  MLX_VLM_DRAFT_KIND=mtp \
  MLX_VLM_DRAFT_MODEL=runs/qwen38/models/Qwen3.8-27B-MTP-bf16 \
  MLX_VLM_VISION_CACHE_SIZE=1 \
  MLX_VLM_TOKEN_QUEUE_TIMEOUT=14400 TOKENIZERS_PARALLELISM=false \
  runs/qwen38/venv/bin/python registry/asset/qwen38-mlx-vlm-serve.py \
  --model runs/qwen38/models/Qwen3.8-27B-4bit \
  --draft-model runs/qwen38/models/Qwen3.8-27B-MTP-bf16 \
  --draft-kind mtp --draft-block-size 3 \
  --kv-bits 4 --kv-quant-scheme turboquant --quantized-kv-start 0 \
  --prefill-step-size 1024 --max-kv-size 201024 \
  --max-num-seqs 1 --vision-cache-size 1 \
  --host 127.0.0.1 --port 8766 --max-tokens 256 \
  > runs/qwen38/server.log 2>&1
```

Keep that process running. Use a second terminal in the same repository root for the probes. Check readiness with `curl --fail --silent --show-error http://127.0.0.1:8766/v1/models`. Preserve `runs/qwen38/server.log` alongside the probe evidence: it records the allocation settings and checks whether the full-attention layers retained the complete prompt. A configured `--max-kv-size` alone is not proof of retained 200k context.

Before a long run, start the optional system-swap watchdog in another terminal using the server PID (shown as `Started server process` in its log):

```sh
python3 -B sources/qwen38-apple-silicon/monitor_memory.py \
  --pid SERVER_PID --output runs/qwen38/memory-watch.jsonl
```

Replace `SERVER_PID` with that numeric PID and choose a new output filename for each run. The monitor samples every ten seconds and stops only that owned wrapper process if global swap grows more than 8192 MiB above its starting value. It checks PID, owner, start time, and command before sending SIGTERM, then SIGKILL after ten seconds if necessary. This is a recovery threshold, not proof of a memory fit: swap is system-wide and process RSS does not capture the complete unified GPU footprint. Preserve its JSONL observations with the run. When restarting a server, confirm its previous PID has exited; a graceful shutdown can keep an active prefill alive.

## Probe the running server

The stdlib-only [probe harness](../../scripts/probe_apple_qwen38.py) creates a unique subdirectory under the chosen output directory for each request. It writes the exact submitted `request.json`, its SHA256, every SSE line in `raw.jsonl`, and `summary.json`. Vision runs also save `vision.png`. The summary preserves token usage, server timings, draft counters, hardware metadata, and before/after `vm_stat` and swap observations, including for failed requests. Every probe requires the exact requested model identity in the response and valid measured prompt/completion token counts; missing identity or usage fails the probe.

Run a short answer check, then a longer decode sample that requires active native MTP:

```sh
runs/qwen38/venv/bin/python scripts/probe_apple_qwen38.py \
  --endpoint http://127.0.0.1:8766 --model runs/qwen38/models/Qwen3.8-27B-4bit \
  --kind text --expect 42 --timeout 14400 --output-dir runs/qwen38/evidence

runs/qwen38/venv/bin/python scripts/probe_apple_qwen38.py \
  --endpoint http://127.0.0.1:8766 --model runs/qwen38/models/Qwen3.8-27B-4bit \
  --kind text --max-tokens 256 --require-mtp \
  --prompt 'Write a Python function named fibonacci that returns the first n Fibonacci numbers, then explain how it works.' \
  --expect fibonacci --timeout 14400 --output-dir runs/qwen38/evidence
```

The vision fixture has a red left panel and a blue right panel. Its request asks for their order without naming either color:

![Submitted vision fixture](evidence/vision/vision.png)

```sh
runs/qwen38/venv/bin/python scripts/probe_apple_qwen38.py \
  --endpoint http://127.0.0.1:8766 --model runs/qwen38/models/Qwen3.8-27B-4bit \
  --kind vision --expect 'red, blue' --timeout 14400 \
  --output-dir runs/qwen38/evidence
```

Generate the long request with the pinned tokenizer, then submit the entire request. `--tokens 200000` produced **200,060 tokenizer-counted prompt tokens** in the saved [workload manifest](workload-200k.json). The server's measured `usage.prompt_tokens` is the acceptance authority.

```sh
runs/qwen38/venv/bin/python sources/qwen38-apple-silicon/make_long_request.py \
  --model runs/qwen38/models/Qwen3.8-27B-4bit --tokens 200000 \
  --output runs/qwen38/request-200k.json

runs/qwen38/venv/bin/python scripts/probe_apple_qwen38.py \
  --endpoint http://127.0.0.1:8766 --model runs/qwen38/models/Qwen3.8-27B-4bit \
  --kind request --request-json runs/qwen38/request-200k.json \
  --min-prompt-tokens 200000 --require-mtp \
  --expect 'maple-7429, harbor-6183, violet-9052' --timeout 14400 \
  --output-dir runs/qwen38/evidence
```

To exercise the long archive, vision, and native MTP together, generate the combined request with `--with-image`. Its saved [workload manifest](workload-200k-image.json) records **200,092 tokenizer-counted tokens before image-token expansion**. The completed [combined run](evidence/combined-200k-fused/summary.json) reports **200,163 prompt tokens** after image-token expansion, with both usage and timings reporting zero cached tokens.

```sh
runs/qwen38/venv/bin/python sources/qwen38-apple-silicon/make_long_request.py \
  --model runs/qwen38/models/Qwen3.8-27B-4bit --tokens 200000 --with-image \
  --output runs/qwen38/request-200k-image.json

runs/qwen38/venv/bin/python scripts/probe_apple_qwen38.py \
  --endpoint http://127.0.0.1:8766 --model runs/qwen38/models/Qwen3.8-27B-4bit \
  --kind request --request-json runs/qwen38/request-200k-image.json \
  --min-prompt-tokens 200000 --require-mtp \
  --expect 'maple-7429, harbor-6183, violet-9052, red, blue' --timeout 14400 \
  --output-dir runs/qwen38/evidence
```

The long-context gate requires a completed SSE response, nonempty answer text, at least 200,000 measured prompt tokens, explicit `timings.cache_n=0`, the expected retrieved values, and native MTP counters with positive draft rounds, drafted tokens, and accepted tokens. The combined request also requires both image colors in order in that same answer. Accepted draft tokens cannot exceed drafted tokens. A launch flag alone does not satisfy the MTP gate. Retention evidence must also come from the wrapper's final-prefill cache audit in the server log.

`--timeout` is the socket timeout plus an elapsed-time check when a line arrives; it is not a strict wall-clock kill timer during a blocked read. Monitor the server and client during long runs. A `length` finish reason records output truncation; it can complete a probe, but only an explicit `--expect` supplies the optional substring correctness check. Neither that check nor the three-key long-context fixture measures general language, reasoning, code, or vision quality. The synthetic retrieval test is a reproducible smoke test, not a broad quality benchmark.

The runtime's `timings.peak_memory` is its **process-lifetime MLX allocator peak in decimal GB**. It is not request-isolated RSS, total system RAM, or a no-swap guarantee. The cache audit separately records active/peak MLX bytes and per-layer cache storage; `cache_bytes_is_partial` must be checked before interpreting the aggregate. Native MTP acceptance counters can include verified draft tokens beyond the final stop token. They prove drafter activity, not an automatic speedup or the number of emitted output tokens.

The generator's workload manifest hashes its output file. The harness separately hashes the exact submitted request after setting streaming/usage controls and serializing it, so the two JSON byte hashes need not match. Keep both artifacts when auditing a run.

## Short acceptance and MTP comparison

The [short acceptance sweep](../../registry/speed-sweep/qwen38-27b-4bit-m3-max-36gb-mlx-vlm-mtp-200k-acceptance.json) and [MTP/no-MTP comparison](evidence/decode-comparison/comparison.json) are complete. They use the unchanged [decode request](decode-request.json): deterministic sampling, thinking disabled, and a 128-token output cap. Finalize the recipe's launch/serving fields before acceptance, which binds their fingerprint. To repeat acceptance for this now-validated recipe, start a fresh pinned MTP server with the launch command above, wait for readiness, then run one warmup followed by three measured samples:

```sh
runs/qwen38/venv/bin/python scripts/probe_apple_qwen38.py \
  --endpoint http://127.0.0.1:8766 --model runs/qwen38/models/Qwen3.8-27B-4bit \
  --kind request --request-json sources/qwen38-apple-silicon/decode-request.json \
  --require-mtp --timeout 14400 --output-dir runs/qwen38/mtp-comparison/mtp-warmup

runs/qwen38/venv/bin/python scripts/accept_recipe.py \
  qwen38-27b-4bit-m3-max-36gb-mlx-vlm-mtp-200k \
  --revalidate \
  --endpoint http://127.0.0.1:8766 --harness native-apple-short-acceptance \
  --request-json sources/qwen38-apple-silicon/decode-request.json \
  --raw-output runs/qwen38/acceptance-mtp.jsonl
```

Choose a new raw-output filename for each acceptance attempt; existing files are rejected. The harness promotes a passing candidate and records completion/decode evidence, but does not itself qualify vision, 200k context, or MTP. Check the measured samples' native draft counters separately. Use `--revalidate` only when deliberately refreshing an already validated recipe's acceptance.

For the no-MTP baseline, stop the server and confirm that its PID has exited before restarting. Use the same launch command and settings, removing the three option/value pairs `--draft-model`, `--draft-kind`, and `--draft-block-size`, and the two environment assignments `MLX_VLM_DRAFT_MODEL` and `MLX_VLM_DRAFT_KIND`. Also unset those two variables in the launching shell if inherited. Preserve a separate server log. After readiness, run one warmup and three measured requests; no MTP requirement is applied:

```sh
for sample in warmup 1 2 3; do
  runs/qwen38/venv/bin/python scripts/probe_apple_qwen38.py \
    --endpoint http://127.0.0.1:8766 --model runs/qwen38/models/Qwen3.8-27B-4bit \
    --kind request --request-json sources/qwen38-apple-silicon/decode-request.json \
    --timeout 14400 --output-dir "runs/qwen38/mtp-comparison/no-mtp-${sample}"
done
```

Exclude both warmups. Compare the median of each configuration's three server `timings.predicted_per_second` values; do not mix server rates with client SSE estimates. Check prompt counts, completion counts, answer text, finish reasons, and draft counters alongside the rates. Using the same request body does not guarantee identical outputs or token counts with speculative decoding; report any differences and do not label unequal outputs as identical token work. Positive MTP acceptance counters establish activity, not a speedup.

The [archived comparison](evidence/decode-comparison/comparison.json) used identical submitted request objects and 62 prompt tokens in all six measured requests. MTP produced 90 output tokens per request at a median **19.36455 tok/s**, with **38 draft rounds, 76 drafted tokens, and 52 accepted tokens** in each sample; [the acceptance stream](evidence/decode-comparison/mtp-acceptance.jsonl) preserves the answers and counters. Without MTP, each answer contained 73 tokens at a median **16.15422 tok/s**. All six requests finished with `stop`, but the answers differed between configurations. Median client elapsed time was **5,263 ms with MTP versus 5,023 ms without MTP**. The sequential MTP-first/no-MTP-second comparison was not randomized and does not establish a matched-output latency speedup, exact decoding parity, or a general MTP benefit.

## Optional runtime checks

[test_runtime.py](test_runtime.py) checks the wrapper's allocation settings and runtime pin, cache retention accounting, fused-attention routing and BF16 mask parity, and a tiny synthetic model's chunked native MTP path. It requires the pinned runtime and the additional test dependency `pytest==9.1.1`. These checks use Metal but do not load the 27B checkpoint or establish its context, quality, or hardware qualification. Run them with the serving process stopped so they do not compete with a measured inference run.

```sh
uv pip install --python runs/qwen38/venv/bin/python pytest==9.1.1
runs/qwen38/venv/bin/python -B -m pytest -q -p no:cacheprovider \
  sources/qwen38-apple-silicon/test_runtime.py
```

The test loads the wrapper with `compile`/`exec`, so it does not create `__pycache__` under `registry/asset`. The command also disables Python bytecode output and pytest's cache provider. The stdlib evidence-gate tests run separately with `python3 -m unittest discover -s scripts -p test_probe_apple_qwen38.py`; those tests do not need the model runtime or a GPU.

## Independently verify the combined evidence

After a successful combined request, copy the server log to a fixed snapshot and run:

```sh
python3 sources/qwen38-apple-silicon/verify_long_evidence.py \
  --probe-dir runs/qwen38/evidence/COMBINED_RUN_DIRECTORY \
  --server-log runs/qwen38/server-evidence.log \
  > runs/qwen38/long-evidence-receipt.json
```

Replace the probe directory with the actual unique directory printed by the harness. The verifier replays the captured SSE independently, compares it with the summary, checks the exact request hash and image fixture, and requires the complete five-value answer with a `stop` finish reason. A separate canonical message hash binds the archive text, distant key positions, and image question to this specific combined 200k workload; a different prompt needs a separately reviewed fixture. It also requires at least 200,000 cold prompt tokens, positive native MTP counters, and one matching final-prefill audit with all 16 full-attention caches retaining the full prompt. Fifteen caches must be TurboQuant 4-bit and one unquantized; the 48 recurrent states are checked separately. Its success receipt contains hashes of the files it checked. Keep those file bytes unchanged afterward.

The successful run is preserved in [the combined 200k archive](evidence/combined-200k-fused/archive.json), with [its verification receipt](evidence/combined-200k-fused/verification-receipt.json) and [server log](evidence/combined-200k-fused/server.log). To replay verification against those fixed files, pass `--probe-dir sources/qwen38-apple-silicon/evidence/combined-200k-fused --server-log sources/qwen38-apple-silicon/evidence/combined-200k-fused/server.log` to the verifier.

## Results and scope

| Gate | Result | Evidence |
| --- | --- | --- |
| Pinned dependency installation | Completed | `requirements-macos-arm64.txt` |
| Pinned model download/checksums | Completed | `base-verification.txt`, `mtp-verification.txt`, both manifests |
| 8k cold retrieval completion | Passed: all three values | [8k receipt](evidence/retrieval-8k/summary.json): 8,198 input / 22 output tokens |
| Native MTP activity | Passed at short context | [8k receipt](evidence/retrieval-8k/summary.json): 11 accepted of 22 drafted tokens over 11 rounds |
| Image color-order check | Passed: `Red, Blue` | [Vision receipt](evidence/vision/summary.json), 112 input / 4 output tokens, native MTP active |
| At least 200k cold prompt tokens | Passed: 200,163, zero cached | [Combined run usage/timings](evidence/combined-200k-fused/summary.json) |
| Full-attention KV retention | Passed: all 16 layers retain 200,163 tokens | [Verified audit](evidence/combined-200k-fused/verification-receipt.json): 15 TurboQuant 4-bit + 1 BF16 cache; 48 separate recurrent states; 3,024 forced-fused calls |
| Long-context retrieval answer | Passed: all three values | [Verified answer](evidence/combined-200k-fused/verification-receipt.json): `maple-7429, harbor-6183, violet-9052, red, blue` |
| Combined 8k retrieval, vision, and MTP with fused fix | Passed: all five values, 32 forced-fused calls | [Combined 8k receipt](evidence/combined-8k-fused/summary.json), 8,301 input / 26 output tokens |
| Combined long-context retrieval, vision, and MTP | Passed: exact five-value answer, 26 output tokens, `stop` | [Combined 200k receipt](evidence/combined-200k-fused/verification-receipt.json): 12 MTP rounds, 24 drafted tokens, 14 accepted |
| Combined 200k performance | 55.24855 prompt tok/s; 2.86290 decode tok/s | [Server timings](evidence/combined-200k-fused/summary.json): 60.38 min prefill; 60.55 min total client elapsed |
| Peak runtime memory and swap observations | 27.94146 GB decimal MLX peak (26.02 GiB); maximum global swap growth 3.09 GiB | [Memory summary](evidence/combined-200k-fused/memory-summary.json) and [sample log](evidence/combined-200k-fused/memory.jsonl) |
| Short registry acceptance | Passed: three samples; median 19.36455 decode tok/s | [Acceptance sweep](../../registry/speed-sweep/qwen38-27b-4bit-m3-max-36gb-mlx-vlm-mtp-200k-acceptance.json): 62 input / 90 output tokens, `stop`, active native MTP in each sample |
| Short no-MTP comparison | Median 16.15422 decode tok/s; 62 input / 73 output tokens | [Comparison archive](evidence/decode-comparison/comparison.json): different answers across configurations; no matched-output speedup claim |

The MLX peak is process-lifetime allocator usage, not total system memory. The [watchdog observations](evidence/combined-200k-fused/memory-summary.json) began with **4.58 GiB of global swap already used** and measured a maximum additional **3,316,446,659 bytes (3.09 GiB)**. Global swap cannot be attributed entirely to this server; this is not a no-swap result. The watchdog did not trigger and observed the server exit. A [late-prefill power snapshot](power-observation-fused.json), taken after 182,272 processed tokens, records AC power and no recorded thermal/performance warning at that moment; it is not continuous telemetry.

The recipe passed short registry acceptance and is validated. The successful combined smoke test establishes this measured 36 GiB host and workload, not the bounty's 24 GB tier, exact 32 GB machines, other Apple generations, broad quality, or optimal settings across chips. Those require separate measured runs.
