#!/usr/bin/env bash
# Native Apple Silicon launch; install scripts/mtplx-requirements.txt first.
set -euo pipefail
if [[ $# != 1 || ! -d $1 ]]; then
  echo "usage: $0 /absolute/path/to/pinned-qwen38-mtplx-model" >&2
  exit 2
fi
MODEL_PATH=$(cd "$1" && pwd)
for file in config.json tokenizer.json model.safetensors.index.json mtp.safetensors model-vision.safetensors; do
  [[ -f "$MODEL_PATH/$file" ]] || { echo "Missing $file" >&2; exit 1; }
done
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1
export HF_HUB_DISABLE_IMPLICIT_TOKEN=1 TOKENIZERS_PARALLELISM=false
exec "${MTPLX_BIN:-mtplx}" serve \
  --model "$MODEL_PATH" \
  --model-id qwen38-27b-mtplx-4bit \
  --host 127.0.0.1 --port "${PORT:-18198}" --no-auth \
  --profile turbo --generation-mode mtp --depth 3 \
  --context-window 204800 --kv-quant q4 --prefill-chunk-tokens 512 \
  --fan-mode default --ssd-session-cache off --agent-rewrites off \
  --no-stats-footer --warmup-tokens 0 --stream-stall-deadline-s 1800
