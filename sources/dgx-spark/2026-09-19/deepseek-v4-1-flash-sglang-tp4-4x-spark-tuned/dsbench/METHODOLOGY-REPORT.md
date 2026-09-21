# DeepSeek-V4.1-Flash on four DGX Sparks: a decode-speed methodology and requirement

Date: 2026-09-19
Scope: native DeepSeek-V4.1-Flash, SGLang TP4/EP2 over RoCE, DSpark maximum block size 5, vision enabled, 1M configured context. This report is an offline analysis of the supplied files. No server or GPU was contacted.

## Executive conclusion

The statement “C1 is about 100 tok/s” is true only for a narrow class of highly predictable, greedy outputs. The sparkDash code prompt asks for 50 copies of the same small function. It lets the draft model approach the six-token verify-step ceiling and produces 107–113 tok/s on several four-Spark systems. It is not evidence that an agentic coding session, prose response, thinking response, or a response at 400k context will decode at 100 tok/s.

The invariant is:

\[
\text{output tok/s} = \text{effective committed tokens per target verify step}
                       \times \text{target verify steps/s}.
\]

On the current fleet a C1 step is about 53 ms, or 18.9 steps/s. The measured effective acceptance is about 4.4 tokens/step for ordinary code and 2.2 for prose. Those imply about 83 and 42 tok/s respectively, matching `realbench.py`. A 100 tok/s result requires 5.3 committed tokens/step at 53 ms, nearly the maximum possible with k=5. Alternatively, ordinary code at 4.4 tokens/step would require a 44 ms step. Prose at 2.2 would require a physically implausible 22 ms step on this hardware and native checkpoint.

The proposed real-use requirement is therefore not a single prompt peak. It is a versioned, cold-prefix, mixed-workload panel at C1/C4/C8 and 0/32k/128k/~400k context, with thinking-on and thinking-off results shown separately. Its context-balanced headline targets are:

| concurrency | median per-stream decode | aggregate decode | interpretation |
|---:|---:|---:|---|
| C1 | **63 tok/s** | **63 tok/s** | mixed real-use panel, not sparkDash |
| C4 | **35 tok/s** | **140 tok/s** | four distinct requests; no shared long prefix |
| C8 | **22.5 tok/s** | **180 tok/s** | eight distinct requests; no shared long prefix |

These are proposed requirements, not measured facts. They are plausible without changing model numerics, but C4/C8 must be established by the new harness. Each context has a guardrail in §4; a fast code category cannot conceal a slow prose or thinking category. The 95% bootstrap lower confidence bound must be at least 95% of the target, and there may be no correctness, loop, or request-failure regression.

## 1. What the published numbers measure

### 1.1 The common metric mismatch

Three incompatible quantities are currently all called “tok/s”:

1. **Per-request post-first-token decode:** `(completion_tokens - 1)/(last token time - first token time)`. sparkDash and our `sdbench.py` intend this quantity.
2. **Concurrent wave aggregate:** sum of decoded tokens divided by the interval from the earliest first token to the latest last token. This is sparkDash's C>1 headline. It is neither the sum of separately measured stream rates nor request wall-clock throughput.
3. **Fixed-window sustained aggregate:** output-token counter delta divided by a steady measurement window. LIL v0.6.2 uses continuous OpenAI usage counters when available. With `--respect-eos`, streams that finish restart and may perform additional prefills inside the window.

End-to-end output rate, which includes prefill/TTFT, is a fourth quantity. It must not be compared with any of the three above.

### 1.2 sparkDash DecodeBench

**Observed protocol.** The supplied source fixes temperature 0, top_p 1 and thinking off; performs one 32-token warmup; forces `min_tokens=max_tokens`, `ignore_eos=true`, and no stops; and defines per-stream decode as `(completion_tokens-1)/(last-first)` (`sources/sparkDash/server/collectors/DecodeBench.js:1-13,48-59,106-117,278-283`). At C>1 it sums decode tokens over the earliest-first to latest-last content window (`DecodeBench.js:351-369`). Current source defaults to 400 output tokens, but the historical knapcio/Mia measurements explicitly used 256.

The three key prompts are (`sources/sparkDash/src/shared/llmPrompts.js:49-68`):

- structured: count from 1 to 200;
- prose: explain hash maps;
- code: write `clamp_00` through `clamp_49`, changing only the suffix.

Concurrent prompts append a suffix only at the end (`llmPrompts.js:180-195`). The assertion there that this avoids a shared prefix-cache block is not generally safe: almost the entire prompt remains identical, and the actual cache block size and tokenizer determine whether any shared blocks remain.

**Bias.** `ignore_eos` measures a forced steady decode, not user-observed completion behavior. The count and repeated-clamp prompts have exceptionally high DSpark acceptance. The short 256/400-token run understates slow drift, thermal variation and long-output loop risk. One warmup does not cover every batch/context graph. Unless the caller repeats cells, the source does not itself establish a sample distribution.

### 1.3 knapcio's SGLang numbers

**Protocol.** The README states four Sparks, TP4/EP2, temperature 0, thinking off, 256 new tokens, idle fleet, and engine-log contamination checks (`sources/knapcio-DeepSeek-V4.1-Flash-4x-DGX-Spark-TP4/repo/README.md:63-65`). `docs/window-20260916.md:3-5` confirms the same protocol. Because it invokes sparkDash, top_p is 1, EOS is ignored, there is a 32-token warmup, and the metric is the sparkDash first-to-last content window. The first two post-boot points were known to be low and were discarded; any `#running-req` above the requested concurrency invalidated the cell (`README.md:285-291`). The production C1 prose value is the median of 61.0/61.2/61.0, but most production cells were only one measured wave after two warmups. Same-configuration C1 variation between boots was reported as about ±2%.

**Published decode.** Aggregate tok/s, with the README's reported per-stream number in parentheses:

| profile | prose C1 | prose C4 | prose C8 | code C1 | code C8 | structured C1 |
|---|---:|---:|---:|---:|---:|---:|
| upstream/Mia reference | 45.4 | 103.1 (26.7) | 114.1 (23.2) | — | — | — |
| base | 51.6 | 109.3 (28.5) | 160.9 (20.8) | 96.7 | 446.7 | 104.5 |
| canary | 55.4 | 118.9 (30.7) | 178.2 (24.0) | 100.4 | 513.3 | 108.0 |
| production | **61.0** | **125.2 (33.2)** | **178.9 (24.3)** | **113.3** | **548.3** | **124.1** |

Source: `README.md:67-82`. The parentheses are not consistently aggregate divided by concurrency (for example, 125.2/4 is 31.3, not 33.2), so the two columns likely use different internal windows/statistics. They must be retained as separately reported metrics rather than algebraically reconciled.

The switchless-ring document used 400 output tokens, one engine and no other load, but otherwise the sparkDash panel (`docs/switchless-ring.md:415-419,449-465`): prose aggregate C1/C4/C8 60.5/116.4/186.1 and code 107.5/326.4/521.6. It does not give repeat counts. These are directly comparable to other sparkDash cells only after matching output length, engine build, warm state and topology.

**Real-text control.** On the same family of stack, a 700-token English Krakow essay at temperature 0, warm row cache and idle engine decoded at 44–46 tok/s; Polish was 36–40, versus about 57 for sparkDash prose. A foreign request reduced the result by 20–40% (`docs/upstream-watch.md:55-59`). This is the most important control: even sparkDash “prose” is not a general prose rate.

### 1.4 MiaAI numbers

The upstream TP4 README table preserved by knapcio reports sparkDash prose, 256 tokens: aggregate C1/C2/C4/C8/C16 = 45.4/72.9/103.1/114.1/134.2, with TTFT 212/232/270/2700/12450 ms (`sources/knapcio-DeepSeek-V4.1-Flash-4x-DGX-Spark-TP4/repo/docs/README-upstream.md:147-178`, the same values are quoted in `README.md:69-74`). The version and repeat count are not stated. The C8 TTFT is anomalous relative to an independent ring reproduction and should not be used as a latency target.

Mia issue 20 supplies two better controlled experiments:

- One code/LRU prompt, C1, temperature 0, 1024 maximum tokens, thinking off, decode over tokens 129–641, three repetitions: k5 medians 64.57 and 66.81 versus k3 59.84 (`sources/miaai-DS4.1/m-20.md:13-35`). This is not sparkDash and its interior token window excludes startup and tail.
- A second fleet used exact sparkDash semantics: 256 tokens, T=0, top_p=1, thinking off, aggregate wave window (`m-20.md:54-70`). At k5, prose C1/C4/C8 = 48.6/105.4/133.2, structured C1/C8 = 97.3/246.1, and code C1/C8 = 90.3/367.3. k3 improved concurrent prose but reduced high-acceptance structured/code by 16–26%. The measured k5 acceptance was 5.85 tokens/step on counting and about 5 on code.

Issue 12 reports C1 95.0 counting, 71.3 code and 63.4 reasoning, plus aggregate C8 132.9 and C12 176.8, on four Sparks with five-run spread 0.3–3.2% (`sources/miaai-DS4.1/m-12.md:90-103`). The excerpt does not define the prompts, output length, sampling, timing window, per-cell repetitions, or idle gate. Those values are useful corroboration of prompt sensitivity, not acceptance thresholds.

An FP8 `wo_a` A/B used sparkDash C1 with n=8 per arm, first post-boot run discarded: code 95.91→97.41 and prose 51.58→49.00 (`sources/miaai-DS4.1/m-13.md:47-54`). Its matched A/B is credible for the delta, not a universal absolute rate.

### 1.5 LIL v0.6.2 and our LIL figures

There is no directly usable, published Local Inference Lab DS4.1-on-Spark result in the supplied catalog. The catalog recipe requires `sm_120a`, while the Spark fixture is `sm_121a`; the RTX PRO R36–R38 numbers are different hardware. `sources/spark-recipes-research.md:68-79` records this boundary.

The LIL harness we ran is nevertheless well specified:

- prompt: a request for an exhaustive history of mathematics (`sources/lil-llm_decode_bench-v0.6.2.py:116-122`);
- context filler: a deterministic cycle of 20 architecture sentences, not random text (`:93-114,4927-4937`);
- exact context mode: a random run prefix followed by binary search through `/tokenize` (`:14266-14363`);
- duration mode: continuously running streams, `continuous_usage_stats`, maximum 8192 tokens by default (`:10135-10177,16819-16829,16862-16867`);
- primary aggregate: usage-token delta divided by the measurement interval; stream chunks and then Prometheus are fallbacks (`:11349-11388`);
- “per-request” is aggregate/concurrency, not the median of independently timed streams (`:11405-11406`);
- warmup: all streams active and queue stable for three seconds after at least two seconds, plus our 15-second hidden C1 warmup (`:10979-11015,16915-16918`);
- our flags: T=1, respect EOS, exact targeting, duration 30 s. The harness sends no top_p or thinking flag, so effective top_p/thinking are server defaults unless captured separately. `--respect-eos` omits `ignore_eos` (`:10166-10177,17102-17105`).

Our JSON confirms version 0.6.2, temperature 1, `ignore_eos:false`, 30 seconds and `metrics_available:false` (`ours/runs/20260919T203121-kv6m/lil.json`, `metadata`). Therefore the runs do not contain authoritative engine step, acceptance, queue, or foreign-traffic counters. At respect-EOS, a stream can finish and restart, so the fixed window may include extra prefills. The deterministic filler and shared context within a cell can also exaggerate cache and expert-route reuse. These numbers are comparable to one another only when all flags, harness version, server defaults, context and warm state match. They are not directly comparable to sparkDash.

### 1.6 LocalMaxxing

`sources/localmaxxing/selected.json:1699-1977` contains three duplicate records for the same 71.98 submission and `:1978-2256` three duplicates for the same 46.16 submission. Duplicates are not independent samples.

| record | prompt | stated protocol | result and counters | missing/limiting evidence |
|---|---|---|---|---|
| `cmtwng2zt0ag3ps01plkq4m3k` | realistic Python `logtally` CLI task, 184 input, 600 output | four Sparks, vLLM TP4/RoCE, k5 greedy, T=0, thinking off, “after warmup,” configured context 420k | 71.98 tok/s, TTFT 470.6 ms; 575 drafted, 489 accepted | timing formula, top_p, ignore_eos, warmup count, repeat count, idle check absent |
| `cmtwng3gk0ag9ps01lirsaq3e` | multi-part robotics math/engineering/procedure prompt, 242 input, 600 output | same | 46.16 tok/s, TTFT 311.4 ms; 910 drafted, 418 accepted | same omissions |

The `contextLength:430080` field is a configured ceiling, not an actual 430k prompt: the recorded prompts contain only 184 and 242 tokens. These are short-context results. The site's verifier marks both unverified and claims impossible ceilings of 12.6/7.9 tok/s; that check is inconsistent with the supplied step-time evidence and appears to confuse target-pass accounting. It is not evidence that the submitted rates are physically impossible. The records remain unverified because their timing/sample receipts are incomplete, not because 72 tok/s violates the actual GB10 bandwidth bound.

The pair is still highly informative: on nominally the same stack, merely changing a credible short prompt changes C1 by 56%. It supports a mixed prompt panel and rejects a single-prompt requirement.

### 1.7 Other four-Spark DS4.1 numbers in the supplied research/Discord material

The following are a completeness ledger, not an apples-to-apples leaderboard. The local recipe census is `sources/spark-recipes-research.md:80-113`; its vLLM details are expanded in `sources/b12x-rtx6000-to-gb10.md:132-152`.

| source/setup | reported decode | protocol completeness and comparability |
|---|---|---|
| FujitsuPolycom/sparkring vLLM | C1 mixed aggregate 49.8 (code 77.3, prose 33.9); C6 159.9; 16-slot probes C8/C12/C16 164/229/285; acceptance 3.77 | T=0 and 300k configured context are stated; prompt suite/output timing details are external to the dump. Comparable only as a coarse mixed-workload bound. Six-hour C8 soak median 92.1 is a different sustained workload, not the short peak. |
| luxingcom LuZ SGLang | C1 code 83.59, json 76.20, structured 56.41, prose 45.84; peak aggregate code C16 537.5 | “SD-1” prompt definitions, sampling, output length, metric and n are not present in the supplied record. Do not merge with sparkDash despite similar labels. |
| run1999 SGLang | C1 52.9; C8 aggregate 169.8 | prompt/sampling/output/metric/n/idle state absent. |
| nacyot vLLM | sparkDash-like 256-token T=0 prose C1/C8 45.2/134.3; code 86.0/294.6; b12x-MoE code C8 377.3 | closest non-SGLang comparison; thinking, top_p, EOS and repeat count are not all preserved. About 1989 MHz clocks. Full-combo was not adopted due 2.66 GiB free headroom. |
| Richard0571 vLLM | C1 88.4 | one 256-token run; prompt type unstated. Not a baseline. |
| josephdrose vLLM | T=0.4 code 74.54, prose 38.59, mixed C8 159.56 | output length, metric, n and idle controls absent; temperature differs from greedy tables. |
| ZackO2o vLLM | C1 50.9, C6 125.1 (168.4 with KV pin) | protocol incomplete. |
| Aiden private 4-node recipe | no speed number | Discord message `1549866403144798373`, `sources/discord-dump-20260919/messages/ch-1517199740444475423.jsonl:571`, gives 393216 max context, 12 sequences and k5 only. |
| DS41RT AFD hybrid | 73–85 decode; later 74.1 vs 73.5 | **not four-Spark-only**: adds an RTX 5090 coordinator. No prompt, output length, sampling, metric, n, or idle gate. Discord messages `1548874246611271680` and `1548896031893233665`, same JSONL at lines 1166 and 1140. |

For completeness, the dump/research census also contains results that fail the native-four-Spark scope (`sources/spark-recipes-research.md:91-100`): drowzeys' ~3.22-bpw TR3 hybrid reports C1 math/code/prose 44.6/37.3/22.2 and C8 math 171.3; tonyd2wild's EXL3 abliterated checkpoint reports C1–C6 aggregate 58.27/96.00/128.29/152.44/171.11/189.97 at a 300k maximum; a vision-unqualified sparkring SGLang lane reports C1/C4/C8 35.2/77.6/104.0; a two-Spark Mia EXL3 recipe reports C1/C2 31.6/42.5; and a two-Spark sfxnz EXL3 result reports prose 21.2. Their prompts, sampling, output windows, repetition counts and idle controls are not preserved in the supplied census, so they are not requirement evidence. The table above uses “protocol incomplete” to mean that every requested field not explicitly named—prompt bytes, output length, temperature/top_p, thinking, EOS policy, warmup, metric, n and idle gate—is unknown.

RTX PRO 6000 R36–R38 results in the DS4.1 Discord channel are deliberately excluded from the four-Spark requirement. For example message `1548031191838490674` is a four-RTX matched A/B and explicitly reports end-to-end rate including prefill. It is both different hardware and a different metric. Eight-Spark, EXL3, abliterated-checkpoint, sub-400k-context, or vision-disabled results are likewise not native four-Spark comparators.

### 1.8 Why the numbers disagree

The differences are expected, not contradictory:

- **Acceptance:** supplied production quality records show median committed tokens/step around 5.47 code, 4.78 JSON, 3.48 reasoning, 3.17 format and 2.25 prose (`sources/dsv41-step-anatomy.md:357-365`). A nearly deterministic repeated function can exploit almost the whole k5 window; natural prose cannot.
- **Step rate:** T=1/top_p=.95 sampled decode was about 5% slower in steps/s than greedy even with folded sampling (`sources/knapcio-DeepSeek-V4.1-Flash-4x-DGX-Spark-TP4/repo/docs/window-20260916.md:38-41`). Engine build, clocks, RoCE path, EP placement and batch composition also change step time.
- **Concurrency composition:** repeated streams can route to similar experts and share prompt-cache blocks. Diverse agent requests grow the union of routed experts and read more MoE weights per step.
- **Window:** first-to-last decode excludes TTFT; fixed-window LIL can include request turnovers; end-to-end includes prefill.
- **Warm/cache state:** the first two post-boot knapcio points were low. Repeated filler can turn Engram/NVMe misses into cache hits. A “warm engine, cold unique prefix” condition must be explicit.
- **Short output:** 256 tokens has little power to expose thermal drift, loops, scheduler fairness or tail gaps.

Only results with the same prompt bytes/hash, chat template, tokenizer/model revision, sampling and thinking flags, output/EOS behavior, cache condition, context token count, concurrency composition, metric window, engine build, clocks and idle gate are directly comparable.

## 2. Critique of the current local methods

### 2.1 `realbench.py`

What it measures: C1 post-first-visible-content throughput on one ordinary Sieve implementation prompt and one transistor essay, max 1024 tokens, thinking off. It runs server-default sampling and then T=0, keeps three log-gated trials, and reports their median (`ours/scripts/realbench.py:1-48`). This is the best current indicator of ordinary C1 code/prose and correctly exposed the 80 versus 40 split.

Limitations:

- only two prompts and a fixed order; repeated runs can warm prefix/Engram state;
- no cache-bust nonce near the start of the request;
- the default-temperature arm does not record the effective server temperature/top_p;
- it timestamps stream closure as the last token, not the last content/reasoning event (`:21-30`), adding transport/final-usage tail;
- it detects only regex-visible batches in one engine log. `npre<=1` cannot prove that the sole prefill was its own, and it does not gate CPU, NVMe, RoCE or all four nodes;
- prose can end at 922/938 tokens while code hits the 1024 cap; this is real EOS behavior but changes precision across prompts;
- three runs are too few for 3–5% tuning decisions, and there is no C4/C8 or long-context arm.

Observed within-cell variation (sample standard deviation, n=3):

| run/config | metric | mean | SD | CV | range/mean |
|---|---|---:|---:|---:|---:|
| row 11 | code default | 79.47 | 2.45 | 3.08% | 6.17% |
| row 11 | prose default | 40.27 | 1.61 | 3.99% | 7.45% |
| row 11 | code T=0 | 84.90 | 1.15 | 1.36% | 2.59% |
| row 11 | prose T=0 | 42.37 | 0.35 | 0.83% | 1.65% |
| row 12 | code default | 81.10 | 2.31 | 2.84% | 5.43% |
| row 12 | prose default | 40.83 | 0.95 | 2.33% | 4.65% |
| row 12 | code T=0 | 83.03 | 2.66 | 3.21% | 6.26% |
| row 12 | prose T=0 | 42.47 | 1.27 | 2.98% | 5.89% |

Sources: `ours/runs/20260919T203121-kv6m/real.json` and `ours/runs/20260919T214436-pdi4/real.json`. With n=3 these CVs are themselves imprecise; they describe observed scatter, not a stable population parameter.

### 2.2 `quickbench.sh`

What it measures: a fixed sequence of realbench, one 30-second LIL pass, then sparkDash, while sampling clocks (`ours/scripts/quickbench.sh:1-27`). It is an efficient smoke/regression bundle.

Limitations: fixed order confounds cache/thermal history; only realbench performs an engine-log idle check; C8 sparkDash is one wave; LIL is one pass; clock collection is descriptive and does not invalidate a cell; `kill` may leave incomplete monitoring data on failure; the summary places incompatible metrics side by side without protocol labels. It should remain a smoke test, not the acceptance harness.

### 2.3 `sdbench.py`

What it measures: a faithful local port of sparkDash at 256 forced tokens, T=0/top_p=1/thinking off, one 32-token warmup, C1 median of three and C>1 one wave (`ours/scripts/sdbench.py:1-9,29-79`). It is valuable solely as a bridge to public sparkDash tables.

Limitations: artificial high-accept prompts, forced output/ignored EOS, no idle/foreign-request gate, no engine counters, no long context, and only one concurrent wave. The C>1 `per` number is an arithmetic mean of individually timed streams, whereas `agg` uses a common wave window; neither should be derived from the other (`:52-64`).

Row-11 C1 three-run CVs were approximately 0.4% prose, 2.3% code and 2.0% structured (`ours/runs/20260919T210207-sweep-row11/sparkdash.log`). That low scatter describes this short deterministic microbenchmark, not real workload variance. C8 has n=1.

### 2.4 Current LIL use

What it measures: a 30-second sustained output-token window under a single encyclopedic generation prompt, T=1, respect EOS, at chosen contexts and concurrency. It is useful for scheduler scaling and exposed the C1-to-C48 throughput shape.

Limitations: one output shape; repetitive deterministic context; shared prefix across streams; thinking and top_p not pinned; restarts under respect-EOS; aggregate/C masquerading as per-user speed; no server metrics in our artifacts; no foreign-traffic gate; most tuning iterations have one run.

Row-11 three-repeat aggregate variation was:

| context | C1 CV | C4 CV | C8 CV | means C1/C4/C8 |
|---|---:|---:|---:|---|
| 0 | 6.56% | 1.08% | 1.62% | 49.99 / 104.78 / 140.06 |
| 32k | 7.91% | 1.56% | 1.92% | 46.17 / 95.27 / 132.83 |

The full raw cells are `ours/runs/20260919T210207-sweep-row11/decode-{1,2,3}.json`. At C1, a claimed 3% change is smaller than ordinary observed scatter. At C4/C8, three waves look steadier, but three is still too few to characterize tails or boot-to-boot effects.

### 2.5 `mixbench.py`

What it measures: scheduler responsiveness of four continuously looping chat streams while one cold 150k-token prefill runs (`ours/scripts/mixbench.py:1-8`). It correctly found that prefill/decode interval 4 replaced a 47.5-second freeze with a 2.15-second maximum chunk gap (`ours/runs/20260919T213444-mix-row11/mix.json`, `ours/runs/20260919T215556-mix-pdi4/mix.json`). This is an operational fairness test, not an idle decode-speed test.

Limitations:

- throughput is estimated as characters/4, not counted tokens (`mixbench.py:51-60`);
- gaps are SSE chunk gaps, not token-level inter-token gaps;
- `deep_ttft_s` is the wall time of a non-streaming request including eight output tokens, not literal TTFT (`:47-62`);
- thinking is not pinned;
- one trial per configuration, with different naturally generated chat output, provides no variance estimate.

The observed direction is large and operationally important—estimated during-prefill aggregate 1.6→21.7 tok/s and maximum gap 47.5→2.15 s—but no confidence interval can be assigned. The trade was deep-request wall time 49.5→68.4 s (+38%). Keep this as a separate interference/fairness requirement.

## 3. Scientific protocol for real-use C1/C4/C8

### 3.1 Immutable benchmark identity

Create a benchmark manifest and refuse to compare runs with different identities. The manifest must contain:

- model ID and exact checkpoint revision; tokenizer and chat-template hashes;
- engine repository commit, image digest and local patch-set hash;
- complete launch arguments/environment, including TP/EP, context, KV pool, DSpark block/adaptive table, vision limits and prefill scheduling;
- harness commit; prompt-set version and SHA-256 for every serialized request;
- sampling/thinking profile; output/EOS policy; context construction seed/hash;
- driver/kernel/NCCL/RoCEnante versions, node identities, clocks/power policy and fabric topology.

A change to any item creates a new result series. The primary condition is **warm engine, cold unique request prefix**. Warm-prefix replay is a separate reported condition.

### 3.2 Fixed prompt set

Use 16 immutable base conversations, four in each category:

1. **Agentic coding and tools (35% headline weight):** realistic repository issue plus compact synthetic file tree; requests must require inspection, a patch plan, and one or more JSON tool calls. Include multi-turn tool results but no real private data.
2. **Code editing/debugging (30%):** repair a failing implementation, write tests, refactor a module, and review a diff. Avoid templated repetition such as 50 identical functions.
3. **Prose/chat/reasoning (20%):** technical explanation, comparative recommendation, multilingual or narrative response, and a multi-part reasoning question.
4. **Structured output (15%):** heterogeneous JSON/tool arguments, a schema migration, SQL plus explanation, and a constrained YAML plan. Primary runs must not enable guided decoding unless the production client does; a guided-output panel is separate.

The weights are a proposed engineering definition, not observed client traffic. Replace them only from a privacy-preserving production request-class histogram and version the change. Always publish the four category medians as guardrails; never publish only the weighted score.

Every base conversation has four context variants: 0, 32,768, 131,072 and a tokenized 393,216–409,600-token variant. Contexts must be realistic, token-diverse local fixtures: source files, diffs, tool transcripts, documentation and dialogue. Do not cycle a small sentence list. Put a deterministic per-replicate cache-bust string near the beginning, and use distinct context/request bytes for every concurrent stream. Verify exact prompt token counts through `/tokenize` and store the serialized request hash.

### 3.3 Sampling and thinking panels

Run and report these panels independently:

| profile | use | required request fields |
|---|---|---|
| G0 | deterministic automation/public bridge | thinking off, T=0, top_p=1, fixed seed |
| S0 | sampled non-thinking chat/code | thinking off, T=0.7, top_p=0.95, fixed replicate seed |
| S1 | thinking client | thinking on with the actual production effort value, T=1.0, top_p=0.95, fixed replicate seed |

If the owner's clients send different values, substitute their exact request profiles before freezing v1.0. Do not leave fields to server defaults. Paired configuration A/B uses the same prompt, context, seed and stream assignment.

The headline “real-use” score is an equal-weight geometric mean of S0 and S1 until real client mix weights exist. G0 is reported but is not part of that headline. Thinking time and visible-answer time must also be split: first reasoning token, first visible answer token, reasoning tokens, answer tokens and total completion tokens.

### 3.4 Output policy

Primary runs respect EOS and stop strings. Set a 1024-token cap for G0/S0 and a 2048-token cap for S1. Prequalify prompts so the median output is at least 512 tokens for S0 and 768 total tokens for S1 and fewer than 20% of runs hit the cap. If a prompt fails this property, revise and version the fixture; do not discard short observations after seeing results.

Run a separate compatibility lane with exact sparkDash prompts and its forced 256-token semantics. That lane is only for comparison with public tables. It does not enter the requirement score.

### 3.5 Concurrency and timing

At C1, run each of the 16 prompts. At C4/C8, start four/eight **different** category-balanced requests behind a barrier. Rotate assignments so every prompt appears equally often in every concurrency and stream position. Do not duplicate a long prefix among streams.

Primary per-request metrics:

- `TTFT = first reasoning-or-content event - request sent`;
- `TTFA = first visible answer token - request sent` for thinking requests;
- `decode_tps_i = (completion_tokens_i - first_event_token_count_i)/(t_last_token_i - t_first_token_i)`;
- end-to-end output rate and total latency;
- per-stream p50/p95/p99/max inter-token gap.

Primary concurrent metrics:

- `aggregate_wave_tps = sum(decode_tokens_i)/(max(t_last_i)-min(t_first_i))`, only when all C streams succeed and their decode windows overlap at least 90%;
- `steady_server_tps = generation_token_counter_delta/fixed_server_window`, from server metrics;
- distribution of actual per-stream rates; report median and p10, not merely aggregate/C.

An SSE event may contain multiple tokens. Client event gaps must therefore be labelled **inter-event gaps** unless continuous usage deltas or server traces establish per-token timestamps. Report engine step-gap percentiles separately. Use a monotonic clock and record client/server clock source.

### 3.6 Speculative-decoding decomposition

Snapshot monotonic engine counters at the exact measurement boundaries and report, by workload/context/concurrency:

- target verify steps and steps/s;
- generated/committed output tokens;
- effective committed tokens per target step = generated-token delta / step delta;
- proposed draft tokens, accepted draft tokens and accepted/proposed ratio;
- per-position acceptance when exported;
- chosen verify length/tier distribution under adaptive verification;
- average/maximum running and queued requests.

Then verify numerically that `steady_server_tps ≈ effective_tokens_per_step × steps_per_second`. A result without this decomposition may be a user-experience observation, but it is not sufficient to explain a tuning delta.

### 3.7 Warmup, idle gate and invalidation

After every boot/configuration:

1. verify model identity, vision and tool-call smoke tests;
2. exercise every graph shape C1/C4/C8, all three sampling/thinking profiles, and short/long context; run two full discarded waves after compilation;
3. wait until running=queued=0 for ten seconds and four-node GPU utilization, clocks, temperature, CPU load, free RAM, NVMe activity and RoCE counters are stable;
4. run the measured cold-prefix request with a new early nonce;
5. require engine logs/metrics to show exactly the benchmark streams and no unrelated prefill/decode.

Invalidate and repeat a block for: foreign request; error/retry/timeout; loop detector; queue after the barrier; missing metrics; effective concurrency below C; Xid/RoCE retry or rank health event; CPU/NVMe maintenance; any rank's sustained SM clock or power changing more than 2% between paired arms; temperature-throttle reason; prompt cache hit in the cold-prefix lane; output corruption; or fewer than C valid streams. After three invalid attempts, mark the cell blocked rather than selecting the best run.

The benchmark client must run off the head node. Pause all other clients. Record four-node telemetry continuously, but do not treat a sampled utilization chart as proof of idleness.

### 3.8 Samples and statistics

The row-11 LIL repetitions show C1 CV 6.6–7.9% and C4/C8 CV about 1–2%. For a paired comparison, an approximate two-sided 5% test with 80% power needs

\[
n \approx ((1.96+0.84)\,CV_{paired}/\delta)^2.
\]

Using a conservative paired CV of 6.5% gives about 14 independent pairs for a 5% change and 37 for a 3% change. Therefore:

- normal tuning gate: **15 paired AB/BA blocks per cell**, spread over at least three fresh boots or measurement days (five blocks each);
- a claimed 3% improvement: **40 paired blocks per cell**;
- randomize AB versus BA within each block; prompts/seeds/stream positions remain paired;
- the independent unit is the block/boot, not the eight streams inside a wave.

Report the median, 10th/90th percentiles and a 95% cluster bootstrap confidence interval (10,000 resamples, resampling boots then paired blocks). For A/B, report the median paired percent change and its cluster-bootstrap CI. Call an optimization faster only if the CI excludes zero, its lower bound exceeds the declared practical threshold (normally 3%), and correctness/latency guardrails pass. Do not choose the best of repeated waves.

### 3.9 Ready-to-implement harness specification

```text
load manifest.yaml and prompts-v1.jsonl
assert exact model/tokenizer/chat-template/engine identity
assert /metrics exposes request, generation-token, verify-step and spec counters

for config_pair in randomized_AB_or_BA_blocks:
  launch_or_select(config_pair.arm)
  run identity + vision + tool + correctness smoke
  warm every (C, context, profile) graph; discard >=2 complete waves

  for profile in [G0, S0, S1]:
    for context in randomized([0, 32768, 131072, 400000]):
      for C in randomized([1, 4, 8]):
        wait_for_idle(10s); assert_four_node_health()
        requests = balanced_distinct_requests(C, profile, context, paired_seed)
        insert_unique_early_nonce(requests); assert_exact_token_counts()
        pre = snapshot_engine_counters_and_telemetry()
        barrier_start_streams(requests)
        record every SSE event, cumulative usage delta, reasoning/content split
        post = snapshot_engine_counters_and_telemetry()
        validate_exact_concurrency_no_queue_no_foreign_cache_hit_no_errors(pre, post)
        if invalid: repeat up to 3; else write immutable JSONL receipt

derive per-request, wave and server-window metrics
derive steps/s, effective tokens/step, draft acceptance and verify-tier mix
cluster-bootstrap medians and paired deltas by boot/block
emit primary real-use tables plus exact sparkDash compatibility appendix
```

Each receipt should retain raw event timestamps and counter snapshots, not only summaries. A JSON schema should reject missing thinking/sampling fields, missing model revision, missing prompt hash, missing stream, or non-monotonic counters.

## 4. Requirement

### 4.1 Proposed numeric requirement

For the v1.0 real-use panel in §3, use the following aggregate and median-per-stream minima. Values are medians across the weighted workload categories and equal-weight S0/S1 panels. G0 is informational. Each category must also satisfy the regression guardrails below.

| actual prompt context | C1 per/aggregate | C4 aggregate | C4 median stream | C8 aggregate | C8 median stream |
|---:|---:|---:|---:|---:|---:|
| 0 | 68 | 150 | 37.5 | 190 | 23.75 |
| 32k | 65 | 145 | 36.25 | 185 | 23.1 |
| 128k | 62 | 138 | 34.5 | 175 | 21.9 |
| ~400k | 58 | 130 | 32.5 | 165 | 20.6 |
| equal-context geometric mean | **63** | **140** | **35** | **180** | **22.5** |

Pass rule: point median at or above target; 95% lower confidence bound at least 95% of target; p10 stream rate at least 75% of the corresponding median-stream target; error/loop/corruption rate zero in the measured sample. TTFT and gap SLOs must be reported but should be finalized only after the first valid baseline; the current artifacts do not support defensible 128k/400k tail thresholds.

Category guardrails relative to the accepted baseline: no category/profile/context median may regress by more than 3%; no p95 inter-event or engine-step gap may regress by more than 10%; no TTFT may regress by more than 10% unless the separately approved prefill-fairness trade explicitly permits it. Absolute short-context C1 floors are 72 tok/s for agentic/code-edit combined and 40 tok/s for prose/chat; 400k floors are 62 and 34 respectively.

### 4.2 Basis for the numbers

**Facts.** The current C1 verify step is about 53 ms, code acceptance about 4.4, and prose about 2.2 (`ours/LEDGER.md:36-45`). The per-rank step reads about 9.7–11.2 GB: 3.29 GB target dense, 0.83 GB draft and about 5.6–7.0 GB routed experts. At measured 216–235 GB/s plus 2.3–2.8 ms collectives, the central physical floor is about 42 ms; knapcio measured 49.49 ms and this fleet about 53 ms (`sources/dsv41-step-anatomy.md:31-57,177-212,289-319`). Context KV traffic through 400k is estimated below 0.5 ms/step; sparse-index selection may add another 1–2 ms (`dsv41-step-anatomy.md:214-242`).

**Derivation.** At 53 ms, a mixed effective acceptance of 3.3–3.7 commits/step gives 62–70 C1 tok/s. That range is consistent with ordinary code at 80–85, prose at 40–45, LocalMaxxing's realistic 72/46 pair, and Mia's 71.3 code/63.4 reasoning report. The 0-context C1 target 68 sits inside this range; the 400k target allows about 15% for context/indexer and route changes while requiring that decode remain mostly context-flat.

For C4/C8, direct extrapolation from C1 is invalid because diverse requests expand the expert union. The conservative anchors are our row-11 LIL 0-context aggregate 105/140, knapcio sparkDash prose 125/179, the ring's 116/186, and code-shaped public results far above those. A real-use mix should improve acceptance over the LIL encyclopedic filler but lose some repeated-prompt/cache/expert reuse versus sparkDash. Targets of 150/190 at short context and 130/165 at 400k are therefore deliberately between the prose and code public envelopes. This is an estimate to be tested, not a statement that the current system already passes.

### 4.3 Reachability boundary

**Realistically reachable without changing numerical formats:** the proposed 63/140/180 context-balanced targets, and approximately 68–75 C1 short-context for the mixed panel. The current stack already contains k5, EP2, RoCEnante, Engram prefetch, compact adaptive verification, 48 graphs, a safer 6M KV pin and prefill/decode interval 4. Equalizing the two slower drivers/clocks should recover an estimated 2–5%, but requires root and reboot. Kernel scheduling/fusion or a b12x MoE runner may add another single-digit C1 gain and 10–20% in some concurrent cells without changing stored weights, although different reduction order may not be bit-identical.

**Requires numerical-path changes or a different engine/draft to go materially beyond that:** FP8 `wo_a`/LM-head changes, alternative MoE arithmetic, non-bit-exact LuZ fusions, a different draft/block policy, or a vLLM/B12X K7 adaptive lane. Every such change needs the same quality panel; target verification preserves correctness probabilistically but does not make floating-point execution bit-identical.

**Not realistic on native weights/four GB10s:** a workload-independent 100 tok/s C1 requirement, especially for prose or thinking. At the measured 2.2 prose commits/step, even the central 42 ms hardware floor yields only about 52 tok/s; an optimistic 36 ms floor gives 61. Ordinary code at 4.4 and 44 ms can reach 100, but that needs near-floor execution and says nothing about prose.

Thus “100 tok/s at C1” may mean: sparkDash repeated-clamp/count output, greedy, thinking off, warm engine, short context, forced length, post-first-token only. It may also describe a specially favorable real code response. It cannot mean: every C1 request, a real-use median, prose/chat, thinking-on, 400k actual context, end-to-end latency, or sustained mixed-service performance.

## 5. Where the remaining speed is

Expected gains below are estimates and are not additive. All must be measured with the paired protocol.

### 5.1 Ranked for C1

| rank | change | expected C1 effect | evidence/status |
|---:|---|---:|---|
| 1 | Equalize the two 580.159.03 nodes with the faster fleet driver/clock behavior | **+2–5%** | Current slow pair runs ~2187 MHz versus ~2520 on the other pair; TP synchronizes to stragglers (`ours/LEDGER.md:36-39`). Root + reboot required. |
| 2 | Port/profile b12x routed-MoE runner against current FlashInfer CUTLASS | **+5–10% code; likely smaller prose** | nacyot vLLM reports about +7% C1 and larger batch-step wins, but baseline kernel differs (`sources/b12x-rtx6000-to-gb10.md:188-197`). Engineering/rebuild; numerics/reduction order must be quality-gated. |
| 3 | Fuse mHC/tiny kernels or port the LuZ ideas selectively | **0–5%** | About 3.6 ms mHC and 3.8 ms fusable-kernel budget exists, but LuZ's own full port gave code 100.3→99.8 and only +1% aggregate; prose 33.3→36.6, from a lower base (`sources/knapcio-DeepSeek-V4.1-Flash-4x-DGX-Spark-TP4/repo/docs/upstream-watch.md:61-69`). Not bit-exact. |
| 4 | Move remaining logits/Markov collectives to RoCE; prune Markov W2 | **2–3% ceiling** | W2 pruning can save at most 1–1.5 ms and changes draft distribution; collectives offer roughly 0.3–1 ms (`upstream-watch.md:51-53`; `dsv41-step-anatomy.md:244-287`). |
| 5 | FP8 `wo_a`, LM head or other dense byte cuts | **2–5% if made efficient** | Changes numerical path. Prior FP8 `wo_a` end-to-end was +1.6% code, −5% prose because extra kernels erased GEMM savings (`sources/miaai-DS4.1/m-13.md:35-56`). Do not adopt without panel success. |

Already exhausted or rejected for general C1: k7 static (hurt prose), k3 (hurt code), more Engram cache, 8192 prefill chunks, NVFP4 experts, Markov W2 unsharding, parallel Engram misses and NCCL channel/algorithm tuning (`knapcio README.md:258-268`; `ours/LEDGER.md:26-34`). EP1 failed because 576 is not divisible by the MXFP4 kernel's 128 requirement; padding to 640 adds 11% expert bytes (`ours/LEDGER.md:32`).

### 5.2 Ranked for C4

| rank | change | expected C4 effect | evidence/status |
|---:|---|---:|---|
| 1 | Improve adaptive verify cost model/graph tiers using the real workload distribution | **+5–15% from current adaptive stack** | The major adaptive port is already present and gave C8 +8%, C16 +25%, C32 +57% while C1 stayed flat (`ours/LEDGER.md:29`). Further gains need accurate SPS profiling, not a generic RTX percentage. |
| 2 | b12x MoE runner | **step −10–15%; throughput +8–18%** | nacyot measured C4 step −14.5% in a different vLLM baseline. Diversity and expert-union effects make this more valuable than at C1. |
| 3 | Equal clocks/drivers | **+2–5%** | Same synchronous-straggler mechanism as C1. |
| 4 | vLLM LIL/B12X K7-adaptive experimental lane | **+10–30%, high uncertainty** | RTX adaptive gains do not transfer quantitatively; no supplied LIL DS4.1 Spark throughput exists. Requires engine rebuild/swap and full correctness testing. |

`--prefill-decode-interval 4` is not an idle C4 speed lever. It is a fairness control: it vastly improves chat service during a cold prefill but increased the 150k request wall time 38%. Keep it in a separate mixed-load SLO.

### 5.3 Ranked for C8

| rank | change | expected C8 effect | evidence/status |
|---:|---|---:|---|
| 1 | Refit adaptive verify scheduling to diverse C8, including padded graph-tier pricing | **+10–25%** | The current port improved LIL C8 only 8%, much less than higher concurrency; the remaining headroom depends on accepted-length distribution and padded graph selection. |
| 2 | b12x MoE runner | **+10–25%** | nacyot code C8 294.6→377.3 (+28%) with other knobs; treat 10–25% as the isolated hypothesis, not the measured delta. |
| 3 | Experimental LIL vLLM/B12X lane with K7 adaptive and B12X attention | **+20–40% possible, unproven on Spark** | No four-Spark DS4.1 LIL receipt exists. This is the largest untried architectural lane and the highest risk (`sources/b12x-rtx6000-to-gb10.md:193-197`). |
| 4 | Equal clocks/drivers and small kernel/collective work | **+2–8% combined** | Useful but secondary once the batch reads much of the expert set. |

Raising `MAX_RUNNING_REQUESTS` to 32/48 helped C16–C48 but is not expected to improve a true C8 wave once C8 graph capacity already exists. It should not be credited to C8 without an A/B.

### 5.4 Untried items specifically visible in the supplied Discord/research material

- LuZ fused ratio-1/ratio-2 decode kernels: not tried locally; public gain small and non-bit-exact.
- nacyot/Richard/joseph b12x MoE paths: not ported to this SGLang stack.
- LIL JJ/KK arm64 vLLM with B12X attention, K7 and adaptive padded-graph pricing: no published Spark DS4.1 speed receipt and therefore an experimental lane, not a promised improvement.
- root-level driver/clock equalization and post-OTA ConnectX checks: identified but intentionally not performed.
- RoCE MTU 4096/switch changes: root/network change; expected small for latency-dominated small collectives and must be isolated.

The Discord Aiden recipe at message `1549866403144798373` uses a 393,216 configured maximum, which is suitable for the lower edge of the protocol's “~400k” bin, but it publishes no speed number or actual long-prompt receipt. The DS41RT numbers use an RTX 5090 coordinator and cannot establish the four-Spark requirement.

## 6. Reporting template

Every result release should contain, in this order:

1. **Identity:** model/tokenizer/template/engine/image/patch/driver/fabric hashes.
2. **Primary real-use table:** C1/C4/C8 aggregate, median stream and p10 stream at all four contexts, S0 and S1 separate.
3. **Latency:** TTFT, TTFA, end-to-end and p50/p95/p99/max inter-event plus engine-step gaps.
4. **Spec decomposition:** steps/s, committed tokens/step, draft acceptance and verify-tier mix.
5. **Statistics:** n independent paired blocks, boots/days, median and 95% cluster-bootstrap CI, invalidated/retried cells.
6. **Correctness/quality:** exact task panel and pass/failure/loop counts.
7. **Public bridge:** exact sparkDash 256-token T=0/thinking-off table, explicitly labelled forced, warm and prompt-specific; optional exact LIL v0.6.2 compatibility table.
8. **Interference panel:** chat decode and gap tails during 32k/128k/400k cold prefill, separate from idle decode.

Do not reduce this to “the server does X tok/s.” The shortest defensible claim is: “Under protocol/version V, at C, actual context N, workload/profile W, the median per-stream decode was X and aggregate was Y (95% CI …), with effective acceptance A tokens/step at S steps/s.”

## Source classification

- **Observed facts:** values read from supplied source, logs or JSON; described with their local path/message ID.
- **Derived facts:** arithmetic from observed values, such as 18.9 steps/s from 53 ms or required 5.3 tokens/step for 100 tok/s.
- **Estimates/proposals:** requirement thresholds and expected gains. These are explicitly labelled and require the new benchmark before acceptance.

The principal local evidence is `ours/LEDGER.md`, `ours/runs/`, `ours/scripts/`, `sources/dsv41-step-anatomy.md`, the knapcio/Mia/sparkDash/LIL source trees, `sources/localmaxxing/selected.json`, `sources/spark-recipes-research.md`, `sources/b12x-rtx6000-to-gb10.md`, and Discord messages named above.
