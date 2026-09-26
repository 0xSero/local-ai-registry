# R10 ghcr.io/0xsero/deploy-llamacpp-bonsai-ptq1-rtx-2000-ada-16gb:v1
# Owned Prism llama.cpp deploy image: engine (digest-pinned) + fetch-by-COMMIT model preflight.
# llama-server -hf cannot pin a revision, so both GGUFs are curled by commit 6ed5e12bf84b and
# sha256-verified FAIL-CLOSED, then .omp-ready, then base /opt/llama/entrypoint.sh "$@". python3 (stdlib)
# baked so the sweep needs no runtime apt overlay. Build-status only; runtime untested here.
FROM ghcr.io/0xsero/llamacpp-prism@sha256:d9efaf72a177156667879c795217f5e98a6041930ddb29778399edc1ef57b33c
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends python3 && rm -rf /var/lib/apt/lists/*
LABEL org.opencontainers.image.source="https://github.com/0xSero/local-ai-images"
LABEL ai.omarchy.row="R10"
LABEL ai.omarchy.model.repo="prism-ml/Ternary-Bonsai-2-27B-gguf"
LABEL ai.omarchy.model.revision="6ed5e12bf84b7a63069882c91dd9e9218647d17b"
LABEL ai.omarchy.model.local_name="Ternary-Bonsai-2-27B"
LABEL ai.omarchy.model.mount="/opt/models/Ternary-Bonsai-2-27B"
LABEL ai.omarchy.model.quant="ptq1_0+mmproj-q8_0"
LABEL ai.omarchy.hardware="rtx-2000-ada-16gb"
LABEL ai.omarchy.target_context_tokens="131072"
LABEL ai.omarchy.engine_base_cuda_floor="12.8"
LABEL ai.omarchy.pinned_startup="/opt/llama/llama-server --model /opt/models/Ternary-Bonsai-2-27B/Ternary-Bonsai-2-27B-PTQ1_0.gguf --mmproj /opt/models/Ternary-Bonsai-2-27B/Ternary-Bonsai-2-27B-mmproj-Q8_0.gguf --alias Ternary-Bonsai-2-27B-PTQ1_0 --host 0.0.0.0 --port 8080 --ctx-size 131072 --cache-type-k q4_0 --cache-type-v q4_0 --n-gpu-layers 99 --jinja"
LABEL ai.omarchy.model.sha256.ptq1="53107f530aa52eb00912263ab1ee29bd199261c87cd7b4ad4ca1318c1fe33ee3"
LABEL ai.omarchy.model.sha256.mmproj="6807ede61d570bb86ba34b756a0fa109edc33668604de867c6ea6d8f1d631903"
COPY deploy-preflight.sh /opt/deploy-preflight.sh
COPY omp-acquire.sh /opt/omp-acquire
RUN chmod 0755 /opt/deploy-preflight.sh /opt/omp-acquire
ENTRYPOINT ["/opt/deploy-preflight.sh"]
CMD ["/opt/llama/llama-server", "--model", "/opt/models/Ternary-Bonsai-2-27B/Ternary-Bonsai-2-27B-PTQ1_0.gguf", "--mmproj", "/opt/models/Ternary-Bonsai-2-27B/Ternary-Bonsai-2-27B-mmproj-Q8_0.gguf", "--alias", "Ternary-Bonsai-2-27B-PTQ1_0", "--host", "0.0.0.0", "--port", "8080", "--ctx-size", "131072", "--cache-type-k", "q4_0", "--cache-type-v", "q4_0", "--n-gpu-layers", "99", "--jinja"]
