# DeepSeek-V4.1-Flash, vLLM jovian-judgement r38 TP4, 4x RTX PRO 6000 Blackwell 96 GB (2026-09-18)

Evidence for recipe `deepseek-v4-1-flash-fp8-rtxpro6000-vllm-tp4`. Same workstation as the SGLang evidence next to
this directory: 125 GiB DDR5, Threadripper PRO 9965WX, checkpoint and Engram tables on a Samsung 990 PRO 4TB,
driver 595.84, GPUs power-capped at 275 W with stock clocks and no P2P driver override.

## Runtime

Image `localinferencelab/vllm@sha256:f41ca8bb10bb3a125a50340d70d39ad4b7f5605f3fcb661bc992ed0bc4701a00`
(Local Inference Lab jovian-judgement community r38, vLLM `0.26.1rc0+glm53.r38.vllm66c29357`, torch 2.13.0), started
with the image's own `/usr/local/bin/serve-ds41-jovian.sh`. `Dockerfile` only switches the entrypoint to that script
because the Local Studio controller cannot override entrypoints. `env.list` is the complete environment.
Engram tables are read from disk (`ENGRAM_TABLE_MEMORY=disk`), which uses io_uring with registered buffers: the
container needs `--ulimit memlock=-1` and a seccomp profile that allows io_uring. `seccomp-default-plus-io_uring.json`
is Docker's default profile plus `io_uring_setup`, `io_uring_enter`, `io_uring_register`; the upstream compose file
uses `seccomp=unconfined` instead. Boot log: `GPU KV cache size: 7,636,766 tokens, Maximum concurrency for 524,288
tokens per request: 14.57x`.

## Files

- `controller-recipe.json`, `env.list`, `Dockerfile`, `seccomp-default-plus-io_uring.json`: the launch.
- `stress.json`: eight concurrent cold 150,000-token prompts (random token ids, 256 output tokens each). 8 of 8 succeeded.
- `deep-prefill.json`: one cold 500,000-token prompt. GPU memory stayed flat; no allocator warnings.
- `prefill.json`, `decode-1.json`, `decode-2.json`, `decode-3.json`: llm-inference-bench v0.6.2 at commit `ccd9ad8`
  (SHA-256 `053989edff8c9c93e2b96e61342b2ffbd9851e03deba17e6d3fc96fcd6694c1e`), flags from
  `rtx6kpro/benchmarks/prepared-b12x-serving/ds41`, against the engine port:

```
--display-mode plain --no-hw-monitor --no-resume --respect-eos --temperature 1 --token-targeting exact
--max-tokens 8192 --decode-warmup-seconds 15 --kv-budget 7636766
prefill: --prefill-only --prefill-contexts 8k,32k,64k,128k --prefill-duration 30 --prefill-metric client
decode:  --skip-prefill --concurrency 1,2,4,8,16 --contexts 0,32k --duration 30   (three passes; registry rows are medians)
```

## Limits

- Decode is well below Local Inference Lab's published r38 numbers on the same GPU model (C1 about 259 tok/s). Their
  receipts record an NVIDIA P2P driver override and uncapped 600 W cards; this host has neither. Not investigated further.
- The 8k prefill point (5,026 tok/s) is lower than the 32k to 128k points and lower than SGLang on this host; not investigated.
- Random-token prompts in `stress.json` and `deep-prefill.json` are the worst case for disk Engram reads.
- Other clients may have sent a few small requests during the sweep; the harness reported no errors and no loops.
