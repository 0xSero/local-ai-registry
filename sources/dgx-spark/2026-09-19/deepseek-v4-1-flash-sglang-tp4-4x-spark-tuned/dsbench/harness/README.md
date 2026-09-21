# dsbench

`dsbench` implements the real-use DeepSeek-V4.1-Flash protocol in `REPORT.md` §3 and the requirements in §4.1. It is Python 3.12 standard-library code. The main lane is not sparkDash: it uses diverse cold prefixes, EOS-respecting output, omp-like tool/thinking requests, exact tokenizer counts, and contamination-gated receipts.

No command in this README should be run until it is copied to `spark-2384`. The implementation was tested locally without contacting the configured server.

## Profiles and tiers

- `G0`: thinking off, temperature 0, top-p 1, fixed seed, 1,024-token benchmark cap.
- `S0`: thinking off, temperature 0.7, top-p 0.95, fixed seed, 1,024-token benchmark cap.
- `S1-omp`: thinking on, temperature 1, top-p 1, tools present, fixed seed, 2,048-token benchmark cap. It does not set a thinking budget; server-side reasoning effort remains 75.

The `max_tokens` fields exist only to bound benchmark duration. Production omp sends no output cap.

`gate` measures S1-omp and S0 at 0/32k with C1/C4/C8 plus S1-omp at 128k C1: seven rotating cells per block. Two discarded warmup waves per selected shape plus one measured wave normally take about 15–25 minutes for the first block and less for later blocks, based on the observed ~3,400-token/s C1 prefill rate and REPORT decode rates. It is intentionally under the 30-minute per-arm/per-block tuning budget.

`full` covers G0/S0/S1-omp × 0/32k/128k/400k × C1/C4/C8. Each block runs all 16 prompts at C1, four balanced C4 waves, and two balanced C8 waves. Expect roughly 7–10 hours per block on this hardware, dominated by distinct 400k prefills. A normal 15-block acceptance campaign is therefore about 105–150 GPU-hours per arm across at least three boots/days. A claimed 3% improvement needs 40 paired blocks and materially longer wall time.

## Build contexts

The builder talks only to `/tokenize`, falling back to `/v1/tokenize`. It sends messages, tools, and thinking template arguments, binary-searches the injected corpus, and refuses a nonzero target outside ±0.5%. The `0` variant means no injected long context; its actual base prompt token count is still recorded and checked against request usage.

Build one gate block:

```bash
python3 dsbench/build_contexts.py \
  --corpus "$HOME/dsv41-fixtures-src" \
  --output dsbench-contexts/gate-b1 \
  --tier gate \
  --profiles S1-omp,S0 \
  --contexts 0,32k,128k \
  --replicates 1 \
  --streams 8
```

For 15 paired blocks, use `--replicates 15`. Context objects are gzip-compressed and content-addressed; the JSONL index records the seed, early nonce, exact request hash, source order and hashes. Build the full profile/context set before a full run:

```bash
python3 dsbench/build_contexts.py \
  --corpus "$HOME/dsv41-fixtures-src" \
  --output dsbench-contexts/full-v1 \
  --tier full \
  --profiles G0,S0,S1-omp \
  --contexts 0,32k,128k,400k \
  --replicates 15 \
  --streams 8
```

By default the builder materializes the exact tier schedule, not the much larger Cartesian product. Keep global `--block-offset` equal to `--replicate-offset`; use `--all-assignments` only for custom schedules. It creates five unique variants for every scheduled request identity: two discarded warmup prefixes and three measured-attempt prefixes. This is required so an invalid retry cannot inherit its own earlier prefix cache. It also keys contexts by concurrency, preventing C1/C4/C8 cells from reusing bytes.

## Run one gate configuration

The identity arguments are mandatory. Obtain their values from the deployed checkpoint, tokenizer/chat-template files, engine checkout and image; do not use the placeholders below in a real receipt.

```bash
python3 dsbench/run.py \
  --tier gate \
  --contexts-file dsbench-contexts/gate-b1/contexts.jsonl \
  --output dsbench-runs \
  --label baseline-r217 \
  --boot-id boot-20260920-a \
  --model-revision MODEL_COMMIT \
  --tokenizer-hash TOKENIZER_SHA256 \
  --chat-template-hash TEMPLATE_SHA256 \
  --engine-commit SGLANG_COMMIT \
  --image-id IMAGE_DIGEST \
  --harness-commit HARNESS_COMMIT \
  --git recipes=RECIPE_COMMIT \
  --pause-cmd "ompctl pause" \
  --resume-cmd "ompctl resume" \
  --blocks 1
```

Pause and resume hooks are passed as an executable plus arguments, not as a shell pipeline. They must be supplied together. The resume hook runs from `finally` after a successful pause, including on benchmark failure.

## Paired A/B across boots

Run A and B with the same context index, `pair-id`, `boot-id`, global block number and context replicate. Randomize AB versus BA independently for each block because selecting or launching an engine configuration is deployment-specific and intentionally outside this harness. A normal campaign uses five blocks on each of three boots/days. For global block 0, run these in the randomized order:

```bash
python3 dsbench/run.py --tier gate --contexts-file dsbench-contexts/gate-paired/contexts.jsonl \
  --output dsbench-runs --label config-A --arm A --pair-id adaptive-vs-base-v1 \
  --boot-id boot-1 --blocks 1 --block-offset 0 --replicate-offset 0 \
  --model-revision MODEL_COMMIT --tokenizer-hash TOKENIZER_SHA256 \
  --chat-template-hash TEMPLATE_SHA256 --engine-commit ENGINE_A_COMMIT --image-id IMAGE_A \
  --pause-cmd "ompctl pause" --resume-cmd "ompctl resume"

python3 dsbench/run.py --tier gate --contexts-file dsbench-contexts/gate-paired/contexts.jsonl \
  --output dsbench-runs --label config-B --arm B --pair-id adaptive-vs-base-v1 \
  --boot-id boot-1 --blocks 1 --block-offset 0 --replicate-offset 0 \
  --model-revision MODEL_COMMIT --tokenizer-hash TOKENIZER_SHA256 \
  --chat-template-hash TEMPLATE_SHA256 --engine-commit ENGINE_B_COMMIT --image-id IMAGE_B \
  --pause-cmd "ompctl pause" --resume-cmd "ompctl resume"
```

Repeat one A/B pair for global blocks 1–4 on `boot-1`, setting both offsets to the global block number. On `boot-2`, use blocks/replicates 5–9; on `boot-3`, use 10–14. Use the same offsets for A and B within each pair and independently randomize AB/BA. This keeps A/B bytes paired while giving every block/day a distinct prefix. Analyze all run directories together:

```bash
python3 dsbench/analyze.py dsbench-runs \
  --label config-B \
  --baseline-label config-A \
  --candidate-label config-B \
  --sparkdash sparkdash-compat.jsonl \
  --json-output comparison.json \
  --markdown-output comparison.md
```

## Full acceptance

```bash
python3 dsbench/run.py \
  --tier full \
  --contexts-file dsbench-contexts/full-v1/contexts.jsonl \
  --output dsbench-runs \
  --label accepted-candidate \
  --pair-id acceptance-v1 \
  --boot-id boot-1 \
  --blocks 5 \
  --block-offset 0 \
  --replicate-offset 0 \
  --model-revision MODEL_COMMIT \
  --tokenizer-hash TOKENIZER_SHA256 \
  --chat-template-hash TEMPLATE_SHA256 \
  --engine-commit SGLANG_COMMIT \
  --image-id IMAGE_DIGEST \
  --pause-cmd "ompctl pause" \
  --resume-cmd "ompctl resume"
```

Repeat on two more boots/days with both block and replicate offsets 5 and 10. Use `analyze.py` on all three output roots. A full requirement row passes only when the point median reaches target, the clustered 95% lower bound reaches 95% of target, p10 reaches 75% of the stream target, and there is no blocked cell. Invalid attempts remain in receipts but are excluded from accepted statistics.

## Receipts and interpretation

Each run directory is created once and never reused:

- `manifest.json`: operator-supplied identity, selected engine log `server_args=`, filtered serving environment, image ID, passed git commits, prompt/index hashes, clocks and capability probes.
- `requests.jsonl`: serialized-request hash, exact verified prompt count, sampling/thinking fields, every SSE event with `monotonic_ns`, reasoning/content/tool split, cumulative usage and request metrics.
- `cells.jsonl`: idle evidence, counter/log snapshots, telemetry, overlap, invalidation reasons, per-wave and speculative-decode metrics.
- `blocked.jsonl`: cells still invalid after three attempts.

Prometheus counters are used when available. The engine log remains the authority for exact running requests, foreign prefills, queueing, cache hits and rank/fabric errors. If `/metrics` is absent, the log supplies verify steps, acceptance, verify-length mix and throughput. Missing log decomposition invalidates the cell. SSE gaps are labelled inter-event gaps because one event may contain multiple tokens.

For 128k and 400k cells the runner checks `MemAvailable` locally and on all three remote nodes before launch and every second during streaming. Any read failure or value below 3 GiB sets the cancellation flag, closes streams at the next SSE event, and invalidates the attempt.

The analyzer emits per-request, per-wave and server-window data in JSON; a compact Markdown requirement table; log/counter speculative decomposition; 10,000-sample hierarchical bootstrap intervals (boots, then blocks); paired percent deltas; and category/TTFT/gap guardrails. It uses the §3.2 category weights in a weighted geometric mean; for C4/C8 it scales the measured common-window aggregate by weighted-stream/unweighted-stream rate instead of pretending aggregate/C is a measured stream rate. Treat `faster >3%` as established only when the paired CI lower bound exceeds 3% and all guardrails pass.

## sparkDash compatibility lane

This is an exact semantic bridge to `ours/scripts/sdbench.py`: one 32-token warmup per prompt type, thinking off, temperature 0, top-p 1, forced 256 tokens, ignored EOS, three C1 repeats and one C>1 wave.

```bash
python3 dsbench/sparkdash_bridge.py --output sparkdash-compat.jsonl
```

It is explicitly labelled compatibility-only and never enters real-use requirements.

## Validation

Run the unit tests without a server:

```bash
python3 -m unittest discover -s dsbench/tests -v
```

`tests/mock_sglang.py` is a threaded standard-library mock with `/tokenize`, `/v1/models`, `/metrics`, OpenAI chat/SSE reasoning, content, tool-call and usage deltas, plus a fake engine log. It binds only to `127.0.0.1` when launched manually:

```bash
python3 dsbench/tests/mock_sglang.py --port 8765 --log /tmp/dsbench-mock-engine.log
```

The unit suite mocks the transport in-process so it also works in sandboxes that forbid even loopback sockets. `schema/receipt.schema.json` defines required request/cell/manifest fields. The runner additionally invalidates prompt-token mismatches and non-monotonic counter snapshots.

## Documented choices

- JSON is used for the manifest instead of YAML because Python's standard library has no YAML parser. It captures every identity item the operator/API/log can supply.
- The OpenAI API does not expose checkpoint, tokenizer or chat-template hashes. They are mandatory operator inputs and are frozen in the manifest; model ID is live-checked through `/v1/models`.
- Four-node clocks, power, temperature, NVMe and RoCE telemetry have no portable standard-library API. Engine-log health events and memory are enforced here; configuration-specific telemetry may be added as immutable manifest artifacts. Paired clock/power drift cannot be inferred from absent telemetry and must be reviewed externally rather than silently passed.
- Exact server cancellation is not part of the OpenAI API. The memory guard closes client streams as soon as the next event is received; the resulting error invalidates the entire cell.
- A full acceptance campaign is deliberately expensive. The gate exists for tuning; it is not promoted into a full-panel pass claim.
