# images

These are retained historical build definitions. New images are built and published by [local-ai-images](https://github.com/sybil-solutions/local-ai-images) using its `release-image` workflow (Actions → release-image → Run, give the directory and a tag). All four definitions below are preserved there. The registry's duplicate `images` workflow is disabled; historical package digests and their signer identities remain unchanged. A reviewed profile in `registry/engines/` pins the resulting digest after its required acceptance gates. New builds carry provenance and a build attestation; enable an SBOM when it fits the attestation size limit:

    gh attestation verify oci://ghcr.io/sybil-solutions/<image>@sha256:<digest> --repo sybil-solutions/local-ai-images

| Image | What it is |
|---|---|
| `gateway` | The one endpoint in front of every engine: OpenAI Chat passes through; Anthropic Messages and OpenAI Responses are translated, streaming and tool calls included. `python3 gateway/test.py` tests it against a fake engine. |
| `tabbyapi-exl3` | TabbyAPI (ExLlamaV3) plus the Python headers Triton needs to compile the Qwen3.5/3.8 kernels. |
| `llamacpp-prism` | Prism ML's llama.cpp fork, the only one that loads Ternary Bonsai's ternary packings. |
| `llamacpp-bonsai` | `llamacpp-prism` with Ternary Bonsai 2 27B baked in, for the RTX 2000 Ada. |

Other recipes use pinned upstream images (`ggml-org/llama.cpp`, `lmsysorg/sglang-rocm`) or central images built from pinned source trees (`sglang-exl3`, `exl3xpu`). Image publication does not establish model serving or fidelity acceptance.
