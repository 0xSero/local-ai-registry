# DeepSeek-V4.1-Flash on 4x DGX Spark, SGLang TP4/EP4 (2026-09-19)

Evidence for recipe `deepseek-v4-1-flash-native-dgxspark-sglang-tp4`.

## Hardware

Four NVIDIA DGX Spark (GB10, 128 GB unified memory each, driver 580.159.03), one ConnectX-7 port per node on a
shared 10.10.10.0/24 RoCEv2 segment (active MTU 1024), 3.7 TB local NVMe per node. Head node holds the checkpoint;
each worker holds a local byte-identical copy (sizes verified, 53 files).

## Runtime

MiaAI-Lab [DeepSeek-v4.1-Flash-DGX-Sparks](https://github.com/miaai-lab/DeepSeek-v4.1-Flash-DGX-Sparks) at commit
`fba44707a12026a7bf92c85b234e5aa44923fc14`, TP4 profile (`start-tp4.sh`, `.env.tp4.example`). Base image
`lmsysorg/sglang@sha256:4a5d132a06a77c8331e15845f2e925adc788b00105097ad55409afa3f4fa4860`, overlay built by the
recipe (`image.txt`); SGLang `0.0.0.dev1+gda64c5cbb`, torch 2.13.0+cu130. Native checkpoint
`deepseek-ai/DeepSeek-V4.1-Flash@fb2764a5cf321eaa5070ca8f9e892818f477c16d` (MXFP4 experts, FP8 dense). Engram tables
packed per rank onto each node's NVMe (`./start-tp4.sh pack`), no host Engram cache.

Boot (`boot-lines.txt`): 8,000,000-token KV pool pinned, 1,048,576 context, 1024-token prefill chunks, 8 running
requests, DSpark block 3; the recipe's own smoke test and batch-of-8 warm-up passed.

## Local changes (`start.sh.local-patch.diff`, `env.tp4.diff`, `env.tp4`)

- Per-worker ssh users (`WORKER_USERS`) because the nodes use two different accounts.
- `pack` and `push_spec_tables` reach workers by ssh host name instead of fabric IP (one node's sshd does not listen
  on the fabric).
- `NFS_SHARE=0`: the recipe's NFS exporter container crash-looped on this head (the host already runs a kernel NFS
  server with other exports), so each worker got a local copy of the checkpoint bound to the same `dsv41-weights`
  volume name. Serving is unchanged by this.

## Files

- `stress.json`: four concurrent cold 150,000-token prompts (random token ids, 256 output tokens). 4 of 4 succeeded.
- `deep.txt`: one cold 500,000-token prompt. Succeeded.
- `prefill.json`, `decode-1.json`, `decode-2.json`, `decode-3.json`: llm-inference-bench v0.6.2 at commit `ccd9ad8`
  (SHA-256 `053989edff8c9c93e2b96e61342b2ffbd9851e03deba17e6d3fc96fcd6694c1e`) against the head API, flags in
  `ssweep.sh` (Local Inference Lab ds41 protocol: temperature 1, EOS respected, exact token targeting, 15 s warmup,
  30 s cells, three decode passes at concurrency 1/2/4/8 and context 0/32k).

## Limits

- Cold prefill here (about 2.0k tok/s) is about 40 percent below MiaAI-Lab's published 3.3k to 3.8k tok/s for the same
  profile. The active RoCE MTU on this fabric is 1024; not investigated further (changing it needs root on all nodes).
- Random-token stress prompts are the worst case for NVMe Engram reads (1.2k to 1.6k tok/s aggregate prefill).
