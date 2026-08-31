# GLM-5.3 Flash EXL3 Q4 on RTX PRO 6000 Blackwell

The public artifact is [`0xSero/GLM-5.3-Flash-EXL3-Q4`](https://huggingface.co/0xSero/GLM-5.3-Flash-EXL3-Q4), pinned here at revision `99cccdf0e8741715662c383828a9ea601990c125`. It stores routed experts in layers 3-44 at 4.0 bpw EXL3 and preserves the backbone in BF16.

## Accepted four-GPU runtime

The accepted runtime uses four RTX PRO 6000 Blackwell 96 GB GPUs, SGLang TP4/EP1, FP8 E4M3 KV, a 262,144-token configured context, and full CUDA graphs for decode and prefill. It passed model discovery, endpoint health, and generated-completion checks. GPU power limits were not changed.

The highest measured output-throughput profile used 256 concurrent requests, a warmed shared prefix, a measured input sequence length (ISL) of 131 tokens per request, and a requested output sequence length (OSL) of 1,024 tokens per request:

| Profile | Client output tok/s | Output tok/min | Total API tok/min | Median active decode/user | Median TTFT |
| --- | ---: | ---: | ---: | ---: | ---: |
| C32, cold, ISL 128, OSL 256 | 763.74 | 45,824 | 68,731 | 30.40 tok/s | 2.30 s |
| C64, warm, ISL 131, OSL 1,024 | 1,183.66 | 71,019 | 80,105 | 28.90 tok/s | 2.80 s |
| C128, warm, ISL 131, OSL 1,024 | 1,423.86 | 85,432 | 96,361 | 28.38 tok/s | 38.46 s |
| **C256, warm, ISL 131, OSL 1,024** | **1,710.16** | **102,610** | **115,737** | **31.61 tok/s** | **68.68 s** |

The C256 row is the maximum-throughput profile, not the lowest-latency profile. All 256 requests completed and returned 262,144 completion tokens in 153.29 seconds. Its p95 time to first token (TTFT) was 104.37 seconds. C32 or C64 is the more useful operating point when interactive latency matters.

The earlier approximately 900 tok/s observation is also reproduced and explained: at C32, the SGLang engine gauge reported 858.65 generation tok/s while the client observed 763.74 output tok/s over the complete batch. Engine gauges and client end-to-end throughput measure different boundaries.

## ISL, OSL, cache, prefill, decode, and TPM

- **ISL** is the measured input sequence length, including chat-template tokens.
- **OSL** is the requested output sequence length. Completed output tokens are taken from server-reported usage.
- **TTFT** is time to first generated token.
- **Client output tok/s** is all completed output tokens divided by batch wall time.
- **Output TPM** is client output tok/s multiplied by 60.
- **Total API TPM** includes prompt and output tokens. It is not a decode-only capacity number.
- **Active decode/user** measures a stream only while it is emitting tokens; it excludes that request's queueing and TTFT.

A cold ISL 1,024 / OSL 1 request measured 827.74 server prefill-compute tok/s. Repeating an approximately 1,022-token prefix produced a 93.75% instantaneous device-cache hit rate: 960 device-hit tokens and 64 newly computed tokens, with 466.78 ms TTFT. In the C256 run, cumulative SGLang counters recorded 32,768 device-hit tokens and 16,384 prefill-compute tokens, an effective 66.67% device-hit share. The instantaneous cache gauge returned to zero after the queue drained, so the counter-derived value is the meaningful batch result.

The reproducible runner is [`scripts/benchmark_openai_chat.py`](../scripts/benchmark_openai_chat.py). It uses OpenAI-compatible streaming requests, `/tokenize`, server-reported usage, and SGLang Prometheus counter deltas. It sends `max_completion_tokens` so the requested OSL is explicit.

## Concurrency sweep

The cold ISL 128 / OSL 256 client output sweep was:

| Concurrency | Output tok/s | Output tok/min | Median active decode/user | Median TTFT |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 73.62 | 4,417 | 79.03 tok/s | 0.24 s |
| 2 | 116.67 | 7,000 | 63.03 tok/s | 0.33 s |
| 4 | 214.05 | 12,843 | 62.26 tok/s | 0.67 s |
| 8 | 384.95 | 23,097 | 55.42 tok/s | 0.70 s |
| 16 | 496.98 | 29,819 | 38.20 tok/s | 1.54 s |
| 32 | 763.74 | 45,824 | 30.40 tok/s | 2.30 s |
| 64 | 812.03 | 48,722 | 20.91 tok/s | 3.73 s |
| 128 | 798.05 | 47,883 | 17.26 tok/s | 19.33 s |

Longer outputs amortize queueing and prefill overhead, which is why the sustained OSL 1,024 sweep reaches 100,000 output tokens/minute while the short OSL 256 sweep does not.

## Rejected candidates

- Virtual-slice EP4 reached 563.98 output tok/s at C64, versus 812.03 tok/s for TP4/EP1, and was rejected.
- NEXTN MTP5 reached 64.86 tok/s at C1 and regressed the non-speculative path.
- Single-batch overlap reached 792.01 tok/s at C64 and regressed the 812.03 tok/s baseline.
- Shared-expert fusion changes the expected expert geometry and was rejected by the loader.
- Two-batch overlap with data-parallel attention advanced through graph capture after a narrow state-vector patch, then failed because upstream SGLang does not implement the GLM-5 Next decoder-layer operation decomposition. No eager fallback was used.

## Accepted three-GPU pipeline runtime

The earlier capacity conclusion applied to **TP3**, not to pipeline parallelism. A TP1/PP3/EP1 overlay now assigns complete transformer layers to each of three GPUs and executes the checkpoint's four independently rotated logical slices inside every owned routed-expert layer. This preserves the sealed tensor semantics without putting two complete TP4 ranks on one card.

The measured prepared-weight allocation was 61.67 GB, 73.32 GB, and 74.49 GB across the three stages. With 64 mamba-state slots, FP8 E4M3 KV, and full decode CUDA graphs captured at batch sizes 1/2/4/8/16, the post-capture free-memory floor was 10.40 GB. Health, model discovery, and an explicit `READY` completion all passed.

| PP3 profile | Client output tok/s | Output tok/min | Total API tok/min | Cache state |
| --- | ---: | ---: | ---: | --- |
| C1, OSL 256 | 22.60 | 1,356 | — | cold |
| C8, OSL 256 | 117.37 | 7,042 | — | shared prefix |
| C16, OSL 256 | 120.74 | 7,244 | — | first shared-prefix screen |
| **C32, OSL 256** | **176.82** | **10,609** | **12,101** | unique prefixes, 0% cache hit |
| **C32, OSL 256** | **203.78** | **12,227** | **13,755** | warmed shared prefix |

PP3 is a capacity recipe, not a replacement for the four-GPU throughput profile. Pipeline stages serialize each token, and each stage runs four virtual EXL3 slices, so the accepted three-GPU ceiling is materially below TP4.

Prefill CUDA graphs were explicitly requested, but SGLang rejected them because GLM-5.3's hybrid KDA/DSA layers do not satisfy the Standard-GQA prefill graph contract. Decode remained fully graphed; no eager flag or CUDA-graph-disable flag was used.

## TP3, two GPUs, and stock ExLlamaV3

The original TP3 record remains correctly blocked: the artifact is four independently rotated tensor-parallel slices and cannot be reinterpreted as three ordinary TP ranks. The new working path is PP3, not TP3.

The current SGLang virtual-slice implementation prepares 209.48 GB across its three stages before cache, so its unchanged PP2 layout does not fit in two 96 GB cards. PP2 still needs lower-memory preparation, staged-payload release, or CPU offload before it can be claimed.

ExLlamaV3 supports layer splitting in general, but its stock architecture registry does not currently include GLM-5 Next, and this checkpoint uses a custom four-rank-sliced EXL3 contract. A native ExLlamaV3 two- or three-GPU path therefore requires both a GLM-5 Next architecture adapter and execution that preserves all four independent slice rotations; it is not a command-line switch for this artifact.

## Evidence boundary

The artifact card reports held-out BF16-to-Q4 forward KL divergence of 0.06579, 91.7% top-1 agreement, and a 2.38% perplexity delta. A new full-server aligned-logit KLD run has not been published. The recipe remains `candidate`, rather than `validated`, because the locally built runtime image has not been published by content digest and tool/vision execution has not been accepted.
