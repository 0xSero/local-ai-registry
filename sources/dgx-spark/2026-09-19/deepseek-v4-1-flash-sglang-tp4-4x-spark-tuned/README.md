# DeepSeek-V4.1-Flash on four DGX Sparks, SGLang TP4/EP2 — tuned profile

Submitter evidence for `deepseek-v4-1-flash-native-dgxspark-sglang-tp4-tuned`. Everything here was measured on the
submitter's own four-Spark fleet (spark-2384 head, 2822, de5c, 557f) on 2026-09-19/20.

## What this recipe is

knapcio's TP4 profile at [`a544a0f1`](https://github.com/knapcio/DeepSeek-V4.1-Flash-4x-DGX-Spark-TP4/tree/a544a0f1d00fc46d595e8a52766fec0dbefee5f8)
(canary-roce image: b12x RoCEnante all-reduce on both rails, Engram prefetch, EP2) plus:

- **adaptive DSpark verify** (`SGLANG_RAGGED_VERIFY_MODE=compact`) with a profiled SPS cost table and a six-file patch
  (`adaptive-verify/adaptive-verify.patch`): sglang#39257 capture slots, sglang#31016 planner gamma, and compact ragged
  Engram/indexer maps driven from the backend's replay-refreshed buffers;
- **48 request slots** and a **6,000,000-token KV pool** — see "memory" below for why the pool is 6M and not 8M;
- **`--prefill-decode-interval 4`**, a fairness control for mixed traffic (see "interference");
- **no server-side output cap**: knapcio's adapter defaults to `DSV41_MAX_NEW_TOKENS=32768`, which fills in and clamps
  every request, including clients that send no limit. This profile sets it to `0`.

Local deltas from upstream are in `start.sh.local-patch.diff` and `env.tp4.diff`: per-node ssh users, ssh by host name,
local checkpoint copies instead of the NFS exporter, and an `EXTRA_DOCKER_ARGS` passthrough used to bind-mount the
adaptive-verify files.

## Speed: two protocols, deliberately reported separately

**1. Local Inference Lab protocol** (`ssweep.sh`, llm-inference-bench v0.6.2 @ `ccd9ad8`), median of three 30 s cells,
temperature 1, EOS respected, cold unique prompts. This is `*-sweep.json`. Cold prefill 3.4k tok/s from 8k to 128k;
decode 49.3 tok/s at one stream and 350.8 aggregate at 48.

**2. sparkDash DecodeBench** (`sparkdash.log`, ported as `sdbench.py`), the protocol behind the public knapcio/MiaAI
tables: 256 forced tokens, temperature 0, top_p 1, thinking off, `ignore_eos`. Code 109.5, structured 121.2, prose 59.1
at one stream.

**These two disagree by 2x on the same server, and that is the point.** With speculative decoding,
`tok/s = committed tokens per verify step x verify steps per second`. sparkDash's "code" prompt asks for fifty copies of
the same `clamp_NN` function, which the DSpark drafter predicts almost perfectly. It measures a best case, not a
workload. Numbers from the two protocols must never be compared with each other.

## Real-use panel (dsbench)

Because neither protocol above resembles agentic use, the submitter commissioned an independent methodology review and
built a real-use harness from it. Both are included:

- `dsbench/METHODOLOGY-REPORT.md` — how every published DS4.1-on-Spark number was produced (knapcio, MiaAI, sparkDash,
  LIL, LocalMaxxing and the Discord census), why they disagree, a critique of the submitter's own earlier benchmarks,
  and a protocol and requirement for C1/C4/C8.
- `dsbench/harness/` — the harness (stdlib only): 16 fixed conversations across agentic-with-tools, code editing, prose
  and structured output; distinct cold contexts per stream built from a 108 MB source corpus and verified through
  `/tokenize`; contamination and four-node memory gates; Prometheus counter snapshots; bootstrap statistics.
- `dsbench/cells.jsonl`, `analysis.md`, `concurrent-window.txt` — one gate block on this recipe, 13 cells, all valid.

Measured with the client profile that matters here (thinking on, temperature 1, tools present — what the submitter's
agent CLI actually sends):

Ranges below are the min–max over **three runs of the identical configuration**, not single
measurements. See "why these are ranges" beneath the table — at C4/C8 the spread is real and large.

| context | 1 stream | 4 streams | 8 streams |
|---|---|---|---|
| none | 83.8–88.1 | 32.7–38.4 per stream / 77.5–97.7 aggregate | 21.1–26.6 per stream / 101.2–133.0 aggregate |
| 32k | 71.1–91.3 | 24.6–26.1 per stream / 62.6–67.5 aggregate | 15.0–16.3 per stream / 70.3–72.7 aggregate |
| 128k | 78.9 (one run) | — | — |

The stable, workload-independent way to state the same measurement is the engine's own step time at a
matched running count, which reproduces to 1–2% across those three runs (S1-omp, no injected context):

| concurrently decoding requests | 1 | 2 | 3 | 5 | 7 | 8 |
|---|---|---|---|---|---|---|
| step time (ms) | 54.5 | 75.5 | 86.5 | 127.7 | 133.6 | 132.8 |
| accept length | 3.3–4.9 | 2.8–3.5 | 2.8–3.0 | 2.7–3.3 | 2.7 | 2.7 |

`tok/s = accept_length × running / step_time` closes to within ~1% (r=3: 2.90×3/0.0874 = 99.5 vs 99.1
measured; r=8: 2.70×8/0.1328 = 162.7 vs 160.3).

With thinking off (temperature 0.7) the same stack gives 41.8 at one stream. The difference is acceptance, not the
hardware: 4.55 committed tokens per step with thinking on versus 2.33 with it off (accept rate 0.70 vs 0.25). Reasoning
text is far more predictable for the drafter than sampled prose.

**A note on concurrent aggregates — corrected 2026-09-20.** An earlier revision of this table reported the C4/C8
columns as "38.2 per stream / 130.4 concurrent" and "22.2 / 172.4", computed by `concurrent_window.py`, which measures
only the window `[max(first_token_i), min(last_token_i)]` in which every stream is still decoding. The reasoning was
that a wave aggregate spanning the earliest first token to the latest last token is tail-dominated, because this panel
respects EOS and answers differ in length. That reasoning is sound but the estimator is not: with EOS respected those
common windows are only 2.1–5.5 s long, so edge jitter of a few hundred milliseconds moves the result by tens of
percent, and most generated tokens fall outside the window entirely.

**Why these are ranges.** A revision of this file published earlier on 2026-09-20 claimed that
`median_stream_tps` and `aggregate_wave_tps` reproduce to 0.3–1.0%. That claim was based on two runs
that happened to agree, and a third run of the same configuration falsified it. Over three identical
runs the spread is 17–27% on per-stream and 26–31% on the aggregate.

The cause is not instability in the server and not contamination — every cell was valid, `max_running`
never exceeded the target concurrency, and prefill token counts per cell were identical. It is that
`avg_running`, how much the streams actually overlap, is a property of the sampled answer lengths at
temperature 1, not of the configuration: C8 averaged 3.28 concurrently-decoding requests in one run
and 5.76 in another. Aggregate throughput rises with overlap while per-stream rate falls, which is why
the two columns move in opposite directions between runs. Any single-block A/B on these numbers can
therefore show whatever the sampling happened to do.

What does reproduce is step time at a matched running count (1–2%) and accept length (~3%), which is
why they are reported above. `concurrent_window.py`, used in the first revision of this table, is
worse still (10–19% over the same runs, and 53% against its own earlier published value); it is
retained in the evidence directory only for transparency. None of these aggregates are comparable
with sparkDash or LIL, which force equal-length outputs.

## Memory, long context and stability

- Cold 420,000-token prompt alone: completes in 199 s (2,108 tok/s), lowest `MemAvailable` on any node 4.7 GB
  (`deep.txt`, `deep-memavail.log`).
- 15.7-minute mixed stress — one 420k prompt, two cold 150k prompts, 12 looping chat streams, 2 looping vision streams:
  **zero failures** (72 chat, 440 vision, 58 health checks), lowest `MemAvailable` 4.46 GB (`stress.json`, `dsstress.py`).
- **Why the KV pool is 6M, not 8M**: with an 8M pool and 48 slots the fleet idles at 5–8 GB `MemAvailable` per node, and
  a single cold 420k prefill drove one node to 1.05 GB before the guard killed the client. At 6M the same node bottoms
  out at 4.7 GB. A deep prefill transient costs about 5 GB on this hardware; keep at least ~10 GB idle headroom.
  `memguard.sh` is the guard used during every stress run.
- Vision verified end to end on the serving path (`vision_test.py`): a 189-image-token request answered correctly.

## Interference: `--prefill-decode-interval 4`

While a cold 150k prompt prefills, chat streams starve without this flag. Measured with `mixbench.py`
(4 chat streams decoding, one cold 150k prompt arriving mid-run):

| | chat during the prefill | longest inter-event gap | 150k TTFT |
|---|---|---|---|
| without the flag | 1.6 tok/s total | 47.5 s | 49.5 s |
| with `--prefill-decode-interval 4` | 21.7 tok/s total | 2.15 s | 68.4 s |

It is a fairness trade, not a speed win: the deep request's first token arrives 38% later. Idle single-stream decode is
unaffected.

## Negative results worth recording

- **DSpark block size 7** (with adaptive verify): prose −7%, 32-stream throughput −8%. Rejected.
- **EP_SIZE=1**: cannot boot. `Mxfp4FlashinferCutlassMoEMethod` requires `intermediate_size_per_partition % 128 == 0`;
  2304/4 = 576. Padding to 640 would add ~11% MoE bytes on a memory-bound path.
- **Forcing the full verify budget at concurrency** (`dspark_force_budget_frac=1.0`, a runtime setting): the adaptive
  planner trims the verify cap from 6.0 at one stream to 3.5–4.4 at 3–8 streams. Forcing 6.0 raises committed tokens per
  step by 31% at C4 (3.36 → 4.41) and buys **no** throughput — longer verify blocks cost proportionally more step time.
  The planner's cost model is well calibrated; C4/C8 are step-time bound. Cells in `dsbench/budget-ab-*-cells.jsonl`.

## Fleet caveat

Two of the four Sparks (2384, 2822) run NVIDIA driver 580.159.03 and sit at ~2190 MHz SM clock; the other two
(580.142 and 580.173.02) run ~2520 MHz. Tensor parallelism is synchronous, so the slower pair sets the pace. This is a
driver difference, not an applied clock lock, and it was not changed for these measurements (it needs root and a reboot).
Expect a few percent more on a fleet with matched drivers.

## Reproducing

`ssweep.sh` (LIL sweep), `sdbench.py` (sparkDash bridge), `dsstress.py` (stress), `deepmem.sh` + `memguard.sh` (deep
prefill with the memory guard), `mixbench.py` (interference), `dsbench/harness/README.md` (real-use panel). Boot lines in
`boot-lines.txt`; image and upstream commit in `image.txt`; the exact serving environment in `env.tp4`.
