#!/bin/zsh
# Qwen3.8-27B on a 24 GB M-series Mac: UD-IQ3_XXS weights, 204,800-token window (q4_0 KV), vision (mmproj), MTP.
# With no overrides, the argv is the recipe's launch.arguments.
#
# Before you start:  sudo sysctl iogpu.wired_limit_mb=20480        (not persistent across reboot)
# LLAMA_SERVER  llama-server from llama-b11182-bin-macos-arm64.tar.gz (default: llama-server on PATH)
# LLAMA_CACHE   model download directory (default: llama.cpp's own cache). Keep it outside any git checkout.
# Tuning overrides used for the evidence: QUANT, SPEC, DRAFT_N, DRAFT_KV, CTX, CTXCP, PORT.
set -euo pipefail
LLAMA_SERVER=${LLAMA_SERVER:-llama-server}
QUANT=${QUANT:-UD-IQ3_XXS}
CTX=${CTX:-204800}
PORT=${PORT:-8080}

exec "$LLAMA_SERVER" \
  -hf "unsloth/Qwen3.8-27B-GGUF:$QUANT" \
  --spec-type ${SPEC:-draft-mtp} --spec-draft-n-max ${DRAFT_N:-1} \
  -c "$CTX" -np 1 -fit off \
  -fa on -ctk q4_0 -ctv q4_0 -ctkd ${DRAFT_KV:-q4_0} -ctvd ${DRAFT_KV:-q4_0} \
  -ngl 99 \
  -ctxcp ${CTXCP:-4} -cram 0 \
  --image-min-tokens 1024 \
  --jinja --alias qwen3.8-27b \
  --host 127.0.0.1 --port "$PORT" \
  "$@"
