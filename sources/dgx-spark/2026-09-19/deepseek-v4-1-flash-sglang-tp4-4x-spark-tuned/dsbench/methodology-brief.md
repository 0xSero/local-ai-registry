# Brief: a scientific decode-speed methodology and requirement for DeepSeek-V4.1-Flash on 4x DGX Spark

You are working offline on the files in this directory. Do not contact any server, do not run GPU work, and do not modify
anything outside this directory. Write your results to `REPORT.md` (and optional helper files under `out/`).

## Background
We are tuning DeepSeek-V4.1-Flash (SGLang, TP4 over RoCE, DSpark speculative decoding with block size 5, vision on,
1M context) on four DGX Sparks. The owner's goal: **maximise decode speed at concurrency 1, 4 and 8** (C1, C4, C8) for real use
(agentic coding sessions, chat, long contexts of up to ~400k tokens).

The previous tuning loop claimed "~100 tok/s at C1 reached" by porting the sparkDash benchmark (MiaAI-Lab), whose code prompt asks
the model to write 50 identical `clamp_NN` functions. That prompt is almost perfectly predictable by the drafter, so it inflates
speculative-decoding throughput. The owner called this plainly wrong. Our own benchmarks give different answers for the same
server: realbench.py code ~80 tok/s and prose ~40, LIL C1 43-58 (random filler, temperature 1), sparkDash code 110 / prose 59.
With speculative decoding, tok/s = (accepted tokens per verify step) x (steps per second), so the prompt and sampling settings
dominate the result. We need a methodology that is defensible and a requirement that is actually meaningful.

## Material
- `sources/discord-dump-20260918/`, `sources/discord-dump-20260919/`: the RTX PRO 6000 / Local Inference Lab Discord server dump
  (channels, attachments, launch rows). The DS4.1 / DGX Spark discussion is where the recipes and their published numbers come from.
- `sources/knapcio-DeepSeek-V4.1-Flash-4x-DGX-Spark-TP4/repo/`: the recipe we run (README "Measured" section, docs/window-20260916.md,
  docs/results/). Their numbers use sparkDash (256 tokens, temperature 0, thinking off).
- `sources/miaai-DS4.1/`: MiaAI-Lab's DS4.1 TP4 recipe and README speed tables.
- `sources/sparkDash/`: the sparkDash DecodeBench code (server/collectors/DecodeBench.js) and prompts (src/shared/llmPrompts.js).
- `sources/lil-llm_decode_bench-v0.6.2.py`: Local Inference Lab benchmark (commit ccd9ad8) we use for sweeps.
- `sources/localmaxxing/`: localmaxxing.com leaderboard data (public best 4x Spark DS4.1 = 71.98 tok/s bs1 temp 0; same setup 46.16 on another prompt).
- `sources/dsv41-step-anatomy.md`, `sources/b12x-rtx6000-to-gb10.md`: our step-time profile and kernel research.
- `ours/LEDGER.md`: every configuration we tried (rows 0-12), with results and reasoning.
- `ours/scripts/`: our benchmarks: realbench.py (idle-gated real prompts, 1024 tokens), quickbench.sh, sdbench.py (sparkDash port),
  mixbench.py (decode under a concurrent cold 150k prefill), lilc1.sh, ssweep11.sh.
- `ours/runs/`: raw outputs of every run (summary.json, real.json, lil.json, sd.log, mix.json, sweep decode-*.json, prefill.json, stress.json).

## What to produce (REPORT.md)
1. **How every published number was produced.** For knapcio, MiaAI, sparkDash, LIL, localmaxxing and any other DS4.1/Spark numbers
   in the Discord dump: prompt(s), output length, temperature/top_p, thinking on/off, ignore_eos, warmup, metric definition
   (per-stream vs aggregate, first-to-last token vs wall clock), number of samples, idle control. Quote file paths / message ids.
   Say which numbers are comparable to which, and why they disagree (with the acceptance-length x step-rate decomposition).
2. **Critique of our current methods** (realbench, quickbench, sdbench, LIL usage, mixbench): biases, variance, contamination risks,
   sample sizes, what each actually measures. Use our raw run data to estimate run-to-run variance per metric.
3. **A scientific protocol for C1, C4, C8 decode speed** that reflects real use of this model: a fixed, versioned prompt set that is
   representative (agentic coding with tool calls, code editing, prose/chat, structured output; thinking on and off as the owner's
   clients use it; realistic temperatures), short and long context (0, 32k, 128k, ~400k), output lengths, warmup, exact metric
   definitions (per-stream decode tok/s and aggregate, TTFT, inter-token gap percentiles), sample sizes chosen from the measured
   variance to detect a 3-5% change, statistics (median + bootstrap CI, paired comparisons between configs), idle gating and
   contamination rules, acceptance-length reporting, and how to report results so they are comparable with the public numbers.
   Include ready-to-run pseudo-code or a script spec for the benchmark (we will implement and run it; you must not run it).
4. **The requirement.** Propose concrete, justified target numbers for C1, C4 and C8 (per-stream and aggregate) under that protocol,
   derived from first principles (memory bandwidth, measured step time ~53 ms at C1, acceptance lengths per workload) and from the
   best credible published numbers. State what is realistically reachable on this hardware without numerics changes, and what would
   need numerics changes or root (driver/clock) changes. Be explicit about which claim "100 tok/s at C1" can and cannot mean.
5. **Where the remaining speed is**, ranked, for C1/C4/C8 specifically, with expected gain and evidence (from the Discord material,
   our profile and ledger). Note anything in the Discord material we have not tried.

Be precise, cite sources, and separate facts from estimates. No marketing language.
