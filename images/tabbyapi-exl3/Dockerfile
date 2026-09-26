# TabbyAPI + ExLlamaV3 for the local-ai registry (Omarchy Local AI).
#
# Upstream image pinned by digest, unchanged except for one thing it lacks:
# the Python development headers. ExLlamaV3 runs its gated-delta-net kernels
# (Qwen3.5, Qwen3.8) through Triton, and Triton JIT-compiles a small CUDA
# utility module against Python.h at first use. Without the headers the model
# load dies with "fatal error: Python.h: No such file or directory". Gemma-4
# never touches that path, which is why only Gemma recipes validated upstream.
#
# Build: pushed by .github/workflows/release-image.yml with BuildKit provenance,
# an SBOM, and a GitHub build attestation on the digest.
# Base: upstream cu13 built 2026-09-22 from tabbyAPI f07131cd (OCI label
# org.opencontainers.image.revision), which requires ExLlamaV3 1.5.1 (its
# pyproject cu13 extra pins the v1.5.1+cu132.torch2.11.0 wheels). MTP drafting
# (`draft_model.draft_mode: mtp`) needs ExLlamaV3 >= 1.4.6; the previous base
# (cu13@ffa8388f, 2026-08-13) shipped 1.4.2. CUDA floor unchanged: cuda>=13.2.
FROM ghcr.io/theroyallab/tabbyapi:cu13@sha256:9d4696ef52592d65b857a6447a38fa11c263d727d97b7e1b250ff337bf25302c

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
    && apt-get install -y --no-install-recommends python3-dev build-essential \
    && rm -rf /var/lib/apt/lists/*

# Entrypoint, command, working directory, and venv PATH are inherited:
# ENTRYPOINT ["python3"]  CMD ["main.py", "--host", "0.0.0.0"]  WORKDIR /app
