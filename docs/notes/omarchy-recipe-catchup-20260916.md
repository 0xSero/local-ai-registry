# Omarchy recipe catch-up — 2026-09-16

The GitHub registry has 2,696 recipes, including 300 TP2 entries. Five TP2 entries are marked validated with Docker launch definitions. A TP2 label alone does not imply a runnable, tested plugin recipe: many records are reference-only candidates.

The plugin exporter filtered out every multi-GPU recipe before collecting alternatives. GPU counts configured through environment variables were also lost. The corrected exporter retains compatible validated alternatives, exports the registry hardware count and KV pool, and ships 67 recipes across 34 hardware types (six multi-GPU recipes). Existing manually installed vLLM TP2/TP4 launch definitions have been reconciled into the registry with private IPC and portable cache mounts.

## Freshly exercised hardware

| Recipe | Per-request context | Actual prompt | Image | Video API | Tools |
| --- | ---: | ---: | --- | --- | --- |
| Qwen3.8 AWQ, vLLM, 2× RTX 3090 | 262,144 | 261,482 | pass | pass | pass |
| Qwen3.8 Q4_K_M, llama.cpp, 2× Arc Pro B70 | 262,144 | 261,504 | pass | rejected (`video_url`, HTTP 400) | pass |

Both long requests returned `CONTEXT_256K_OK` with eight completion tokens and natural stops. NVIDIA used FP8 KV, full/piecewise CUDA graphs, and 456,835 allocated KV tokens. B70 used one slot, vision enabled, MTP disabled; its build has SYCL command graphs disabled. The prior B70 four-slot configuration divided a 262,144-token pool into 65,536 tokens per request.

[Machine-readable evidence](qwen38-tp2-256k-20260916.json) includes immutable image identities, launch arguments, API metadata, usage and measured elapsed times. `scripts/validate_tp2_context.py PORT vllm|llama OUTPUT` reproduces the direct-engine probes on an already-running localhost endpoint (Python standard library plus ffmpeg). These are capability and capacity checks, not retrieval-quality or throughput benchmarks. The other TP2/TP4 recipes were exported/reconciled, not newly benchmarked on unavailable four-card hardware.

## Source repositories and remaining reconciliation

- [qwen38-b70](https://github.com/0xSero/qwen38-b70): the attested image now backs the one-slot 256K vision-enabled TP2 definition. The API video limitation applies to this server, not the model family.
- [qwen38-3090-sglang](https://github.com/0xSero/qwen38-3090-sglang/tree/7cfb2601f3421a696ba9167e92478635c4abbb35): TP2 image/video evidence exists in `benchmarks/tp2-mm.json`; its published TP2 preset is 64K, not fresh 256K evidence. The registry currently contains the TP4 variant. Porting its sidecar downloads and mounts and validating a TP2 launch is separate work.
- [qwen36-b70](https://github.com/0xSero/qwen36-b70): the registry SGLang TP2 definition still requires host IPC. It remains excluded until a private-IPC launch is validated.
- Other exporter refusals currently include host-network TabbyAPI recipes, the Qwen3.8 SGLang TP4 definition, and GLM5.2 vLLM TP4 with host IPC. Two validated Spark recipes lack a recommended primary for their hardware group. `python3 scripts/export_plugin_recipes.py` prints the exact outstanding reasons.

CI now asserts that every compatible validated alternative for an exported hardware group survives export, including environment-configured GPU counts and both 256K Qwen TP2 recipes. The plugin separately checks context and advertised image/video inputs through its keyed gateway before showing ready. Unknown capabilities are preserved, and agent context settings follow the selected recipe.
