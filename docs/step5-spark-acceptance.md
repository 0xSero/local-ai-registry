# Step-5 on two DGX Sparks: pending acceptance

Status: experimental, not a catalog recipe. No validated launch or downloadable checkpoint is asserted. This document is a public, data-minimized release checklist; private calibration and evaluation data are not published.

## Target

- Exactly two DGX Sparks for serving; four may be used during research.
- C1 prose decode at least 50 tokens/s; C8 aggregate at least 200 tokens/s, with all eight per-stream rates reported separately.
- Cold, unique-prompt prefill at least 5,000 tokens/s.
- 262,144 tokens per request; at least 2,097,152 logical KV tokens across eight simultaneous slots, with a 4,194,304-token pool explored if it fits.
- Working text, reasoning, tools and vision; CUDA graphs preserved; MTP measured and validated.
- Fixed-panel full-vocabulary KL at most 0.028, disjoint confirmation, and an independent original sparse-attention fidelity gate.

No output caps, cache-hit credit, power/clock changes, context reduction or capability removal may be used to claim these targets. Run exactly four Terminal-Bench 2.1 tasks only after useful end-to-end speed is established; retain task durations and failure classifications.

## Evidence boundary

The current promising expert diagnostic quantizes only the later 44 expert layers to K4. It runs the full 92-layer model and measures mean KL 0.02088524 with top-1 agreement 0.96607971 on the development panel, while earlier experts and the body remain native. It is not a fully compressed two-Spark recipe and has no admitted two-Spark fit or disjoint-confirmation result. Uniform expert and body recipes tested so far fail the quality ceiling. The reference attention remains a hypothesis; original sparse semantics are not proven.

A separate two-Spark **four-layer** native runtime test measured median replay-and-rollback latency of 69.856885 ms serial versus 44.113548 ms batched at C8. C1 was 8.737757 versus 8.791227 ms. These fixed-order component samples are not independent repeated benchmarks, generated tokens/s, HTTP performance, or full-model throughput. Occupied histories during timing were 1,016–1,035 tokens. Only 17 of 255 nonempty slot combinations have batched graphs; other combinations use serial graphs.

A four-layer cache stress test committed 262,144 positions in each of eight slots with unchanged graphs. Full-attention storage retains the full history; sliding layers retain their bounded windows. This does not prove full-model memory fit or long-context recall. Native vision and HTTP component checks likewise do not establish a complete validated deployment.

Only aggregate metrics and test scope are disclosed here. Raw prompts, token arrays, calibration data, generated responses, images, machine addresses, credentials, local paths and private source bundles are excluded. No hash is offered as a substitute for publicly reproducible end-to-end acceptance.

## Container and promotion

The companion [runtime foundation](https://github.com/0xSero/local-ai-images/tree/feat/step5-spark-runtime/step5-spark-runtime) contains public dependencies and an integrity-checking launcher only. It requires a separately admitted runtime bundle and model assets; it does not ship a Step-5 server or checkpoint. Its build context is allowlisted. An image build is not model acceptance.

Before adding anything under `registry/recipes`:

1. Record the attested ARM64 image digest, runtime revision, permitted model revision and exact precision recipe. Validate the container on the target Sparks.
2. Prove full-model quality against the declared reference and on disjoint data. Resolve or explicitly retain the original sparse-fidelity blocker.
3. Read back the effective two-host configuration, graphs, MTP, eight physical slots and actual full-pool occupancy. Test long-context recall and vision with changed images.
4. Capture real HTTP text, reasoning and tool parsing in streaming and nonstreaming modes. Exercise natural EOS, irregular slot combinations, cancellation, refill, reuse and recovery.
5. Run C1/C2/C4/C8 cold unique-prompt sweeps, sustained windows and a mixed-load soak. Report every stream, aggregate decode, prefill, TTFT, memory, errors and exact token accounting. Do not extrapolate from components.
6. Run the registry's endpoint acceptance with the audited configuration. Generate the recipe through the lab tooling only after all required gates pass; then regenerate and check the catalog.

The existing catalog remains unchanged until these gates are met.

## Published dependency-image receipt

The ARM64 build succeeded in [workflow run 36937550729](https://github.com/0xSero/local-ai-images/actions/runs/36937550729) at source revision `d356084b1afb2f2f825986b28b07fa4b66df0a31`. GitHub build-attestation verification passed, and an anonymous manifest read returned the ARM64 image:

```text
ghcr.io/0xsero/step5-spark-runtime@sha256:09c8b6893af160588bf22c865e5acf03e7537322252162aa01d1a401737537cc
```

This digest pins the dependency foundation only. Target-device CUDA smoke is pending; no included serving bundle, full-model quality, vision-answer or speed acceptance is implied. The image is intentionally absent from validated engine/recipe entries.
