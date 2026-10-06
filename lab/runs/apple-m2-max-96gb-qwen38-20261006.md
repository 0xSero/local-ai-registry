# Apple M2 Max 96GB — Qwen3.8-27B 4-bit, 200K, vision and MTP

## Hardware and runtime

- MacBook Pro `Mac14,6`
- Apple M2 Max, 38-core GPU, 96 GB unified memory, 400 GB/s
- macOS 26.6.2 (25G83), Metal 4
- Python 3.12.13
- `mlx-vlm==0.7.3`, `mlx==0.32.2`, `transformers==5.17.0`, `huggingface_hub==1.33.0`
- `mlx-community/Qwen3.8-27B-4bit@10c35caafbb80f7dc6a7a432cdd11af10a6d4818`
- `mlx-community/Qwen3.8-27B-MTP-4bit@b643c01b6d3b094e325edb6ebd832e16c486c575`
- `iogpu.wired_limit_mb=94208`, as rendered from the launch's 4 GiB reserve

No serial number, hardware UUID, provisioning identifier, username, home path or non-synthetic prompt is included.

## M2 long-prefill condition

The existing MTPLX and MLX-VLM Apple launches both hit the macOS Metal GPU watchdog during the canonical 166,667-token context gate:

- MTPLX 2.12.0, 4,096-token prefill chunks: `kIOGPUCommandBufferCallbackErrorImpactingInteractivity`.
- MTPLX with 2,048-token prefill chunks: the same error. Reducing the application prefill chunk does not split a single long-key SDPA dispatch.
- The registry's fused-attention MLX-VLM launcher: the same error after 105,728 of 166,667 prompt tokens.

This matches [MLX issue #3302](https://github.com/ml-explore/mlx/issues/3302): at long key lengths, one full-attention Metal dispatch exceeds the GPU watchdog interval. The unmerged chunked-SDPA implementation in [MLX PR #3307](https://github.com/ml-explore/mlx/pull/3307) is the upstream structural fix and was independently tested on M2 Ultra and M3 Ultra.

The passing launch sets `AGX_RELAX_CDM_CTXSTORE_TIMEOUT=1` only in the server process environment. This is the documented workaround while pinned MLX 0.32.2 lacks chunked full attention. It relaxes the GPU watchdog and can make the UI temporarily less responsive during a long prefill; it is therefore explicit in the frozen M2 launch rather than being a machine-global shell setting.

## Canonical lab run

Command, against the already-running host launch:

```bash
python3 lab/lab.py try \
  mlx-community/Qwen3.8-27B-4bit@10c35caafbb80f7dc6a7a432cdd11af10a6d4818 \
  --model qwen3.8-27b \
  --engine mlx-vlm-qwen3.8-27b-4bit-mtp-200k-m2-max \
  --card apple-m2-max-96gb \
  --on endpoint \
  --endpoint http://127.0.0.1:8080 \
  --gpu "Apple M2 Max 96GB (38-core GPU)"
```

All six unmodified gates passed:

- load, chat, separate reasoning, tools, context and speed
- context: correct recall at 166,667 prompt tokens
- context time: 3,212.6 seconds
- context peak: 20.79 GiB
- prefill: 52 tok/s
- first-30-second decode: 19.4 tok/s

Canonical evidence: `apple-m2-max-96gb.qwen3.8-27b.mlx-vlm-qwen3.8-27b-4bit-mtp-200k-m2-max.200k.20261006T084645.json`.

## Combined long-context vision and MTP probe

A fresh server received one request containing:

- a synthetic 196K-token archive with one six-digit code at 40% depth;
- a generated 512×256 image containing a red circle followed by a blue square;
- a request to return the code and identify both shapes in order.

Result:

- server prompt: 196,163 tokens, zero cached tokens
- answer: `731942, red circle, blue square`
- prefill: 46.91 tok/s
- elapsed: 4,217.5 seconds
- peak allocator memory: 23.057 GB decimal (21.47 GiB)
- MTP: 113 draft rounds, 113 drafted tokens, 95 accepted
- clean `stop`

The request used only generated text and an image created with Pillow. Its request and image hashes are recorded in `apple-m2-max-96gb.qwen3.8-27b.mlx-vlm-4bit-196k-vision-mtp.20261006.json`; the large request body and image are not committed.
