# Prism ML's llama.cpp fork, for the local-ai registry (Omarchy Local AI).
#
# Ternary-Bonsai-2-27B ships PTQ1_0 / PQ2_0: custom ternary-g128 packings with a
# folded blockwise Hadamard rotation. Stock llama.cpp defines TQ1_0/TQ2_0 but
# rejects these files as unknown types, so the artifact cannot run on any
# upstream build. Prism ML publishes prebuilt CUDA servers for their fork; the
# tag below is the one their own Bonsai demo pins.
#
# Base is the CUDA 12.8 runtime, not 13.x: the published tarball links CUDA 12.8
# and runs on every driver from 525.60.13 up, which is what the campaign's
# rented cards have.
#
# Build: pushed by .github/workflows/release-image.yml with BuildKit provenance,
# an SBOM, and a GitHub build attestation on the digest.
FROM nvidia/cuda:12.8.1-runtime-ubuntu24.04@sha256:828c4d878adcaa4265d80c95d8ec877149b49bb2419a4cf3bb6aa889bbb7ca2e

ENV DEBIAN_FRONTEND=noninteractive
# libgomp1 for the OpenMP runtime, libcurl4 for the built-in model fetcher, and
# openssh-server so the validation bootstrap does not have to install it before
# the first SSH check.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates curl libgomp1 libcurl4 openssh-server \
    && rm -rf /var/lib/apt/lists/*

# checksum= is the digest GitHub publishes for this exact release asset.
ARG LLAMA_URL=https://github.com/PrismML-Eng/llama.cpp/releases/download/prism-b10683-d8f26ee/llama-prism-b10683-d8f26ee-bin-linux-cuda-12.8-x64.tar.gz
ADD --checksum=sha256:1af989aaf959db957a641d74f87d5af4f0c0d96ab397d6ebbcc2d1c04e71e0a1 \
    ${LLAMA_URL} /tmp/llama.tar.gz
RUN mkdir -p /opt/llama \
    && tar -xzf /tmp/llama.tar.gz -C /opt/llama --strip-components=1 \
    && rm /tmp/llama.tar.gz

COPY entrypoint.sh /opt/llama/entrypoint.sh
RUN chmod 0755 /opt/llama/entrypoint.sh

ENV LD_LIBRARY_PATH=/opt/llama
ENV PATH=/opt/llama:$PATH
EXPOSE 8080

# The dispatcher exists so one image serves two callers with one argv contract:
# the registry recipe passes /opt/llama/llama-server and its flags as separate
# arguments, and the campaign's SSH bootstrap passes a single shell string.
ENTRYPOINT ["/opt/llama/entrypoint.sh"]