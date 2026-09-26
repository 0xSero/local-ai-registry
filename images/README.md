# images

The container images recipes run that we build ourselves. One directory, one Dockerfile, one image. Build and publish one with the `images` workflow (Actions → images → Run, give the directory and a tag). It prints the digest, which a profile in `registry/engines/` then pins; every image carries provenance, an SBOM and a build attestation:

    gh attestation verify oci://ghcr.io/0xsero/<image>@sha256:<digest> -o 0xSero

| Image | What it is |
|---|---|
| `gateway` | The one endpoint in front of every engine: OpenAI Chat passes through; Anthropic Messages and OpenAI Responses are translated, streaming and tool calls included. `python3 gateway/test.py` tests it against a fake engine. |
| `tabbyapi-exl3` | TabbyAPI (ExLlamaV3) plus the Python headers Triton needs to compile the Qwen3.5/3.8 kernels. |
| `llamacpp-prism` | Prism ML's llama.cpp fork, the only one that loads Ternary Bonsai's ternary packings. |
| `llamacpp-bonsai` | `llamacpp-prism` with Ternary Bonsai 2 27B baked in, for the RTX 2000 Ada. |

Other engines recipes use are pinned upstream images (`ggml-org/llama.cpp`, `lmsysorg/sglang-rocm`) or come from their own source trees (`sglang-exl3`, `exl3xpu`).
