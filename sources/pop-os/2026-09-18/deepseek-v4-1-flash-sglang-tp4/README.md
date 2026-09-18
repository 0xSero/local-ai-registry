# DeepSeek-V4.1-Flash, SGLang TP4/EP4, 4x RTX PRO 6000 Blackwell 96 GB (2026-09-18)

Evidence for recipe `deepseek-v4-1-flash-fp8-rtxpro6000-sglang-tp4`. Captured from the Local Studio controller
recipe `deepseek-v4.1-flash` on a 4-GPU workstation: 125 GiB DDR5, Threadripper PRO 9965WX, Samsung 990 PRO 4TB for
the Engram tables, driver 595.84, GPUs power-capped at 275 W (stock clocks, no offsets).

## Files

- `controller-recipe.json`: the recipe as stored by the controller (no secrets).
- `launch.json`: the argv the boot script passed to `sglang.launch_server`.
- `prefill.json`: llm-inference-bench standalone cold prefill, 30 s windows, contexts 8k/32k/64k/128k.
- `decode-pass1-partial.json`: checkpoint of the first decode pass. Six of eight cells completed before the run was
  stopped by the operator; C4 and C8 at 32k context are missing.
- `row_store_v2.cpp`, `row_store_v2_parity_test.py`: the Engram row store used by this recipe and its byte-exact
  parity test against the image's original library and the raw checkpoint file.

## Method

Harness: [llm-inference-bench v0.6.2](https://github.com/local-inference-lab/llm-inference-bench/blob/ccd9ad8ced7e387794391bfb0ac6d99b1f66ba6f/llm_decode_bench.py),
SHA-256 `053989edff8c9c93e2b96e61342b2ffbd9851e03deba17e6d3fc96fcd6694c1e`, run against the engine port directly
(not through the controller proxy), with the flags Local Inference Lab uses in
`rtx6kpro/benchmarks/prepared-b12x-serving/ds41`:

```
--display-mode plain --no-hw-monitor --no-resume --respect-eos --temperature 1 --token-targeting exact
--max-tokens 8192 --decode-warmup-seconds 15 --kv-budget 4199936
prefill: --prefill-only --prefill-contexts 8k,32k,64k,128k --prefill-duration 30 --prefill-metric client
decode:  --skip-prefill --concurrency 1,2,4,8 --contexts 0,32k --duration 30
```

Prefill is uncached input tokens divided by client TTFT. Decode cells are sustained 30 s windows after a 15 s warmup.

## Limits of this evidence

- Decode is ONE pass. The protocol reports the median of three; passes two and three were not run.
- The C8 context-0 cell reports a 31 s median TTFT with near-empty prompts. Every request in that cell queued for a
  running-request slot (`--max-running-requests 8` plus one background 256-token keepalive client). The throughput
  of that cell is kept; its TTFT is recorded as null in the registry sweep.
- The server ran without `--enable-metrics`, so the harness could not validate effective concurrency or read DSpark
  acceptance from Prometheus. Server logs on the same day showed accept length 4.5 to 5.0 on real traffic at
  temperature 0; temperature 1 on padding text accepts fewer draft tokens, so decode here is lower than the
  operator's 2026-09-10 temperature-0 sweep of the same stack (C1 196 to 232 tok/s, C8 705 to 748 tok/s).
- The serving image is a local build and is not published, so this recipe is a controller-backed candidate.
