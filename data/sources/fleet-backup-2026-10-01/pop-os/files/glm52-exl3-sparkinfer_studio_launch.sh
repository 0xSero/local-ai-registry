#!/usr/bin/env bash
# Local Studio foreground launcher for the validated text-only GLM-5.2 EXL3
# TR3 3.0bpw checkpoint with the quantized MTP-78 head.
set -Eeuo pipefail

readonly BASE_DIR=${HOME}/glm52-exl3-sparkinfer
readonly COMPOSE_FILE="$BASE_DIR/docker-compose.studio.yml"

export IMAGE="${IMAGE:-local/glm52-exl3-vision:v22-dcpstride}"
export MODEL_DIR="${MODEL_DIR:-${MODEL_ROOT}/GLM-5.2-EXL3-TR3-3.0bpw}"
export CACHE_DIR="${CACHE_DIR:-${MODEL_ROOT}/cache_glm52_exl3_text}"
export PORT="${PORT:-8000}"
export BIND_ADDRESS="${BIND_ADDRESS:-127.0.0.1}"
export CONTAINER_NAME="${CONTAINER_NAME:-glm52-exl3-sparkinfer}"
export SERVED_MODEL_NAME="${SERVED_MODEL_NAME:-GLM-5.2-EXL3}"
export COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-glm52-exl3-sparkinfer}"

# Validated 2026-07-26 winner: NCCL collectives outperform the B12X PCIe
# all-reduce on this host while remaining below the fixed 300 W/GPU limit.
export VLLM_ENABLE_PCIE_ALLREDUCE="${VLLM_ENABLE_PCIE_ALLREDUCE:-0}"
export VLLM_USE_B12X_DCP_A2A="${VLLM_USE_B12X_DCP_A2A:-0}"
export DCP_COMM_BACKEND="${DCP_COMM_BACKEND:-ag_rs}"
export KV_CACHE_DTYPE="${KV_CACHE_DTYPE:-fp8}"
export GPU_MEMORY_UTILIZATION="${GPU_MEMORY_UTILIZATION:-0.96}"
export MAX_MODEL_LEN="${MAX_MODEL_LEN:-400000}"
export MAX_NUM_BATCHED_TOKENS="${MAX_NUM_BATCHED_TOKENS:-2048}"
export ENABLE_ASYNC_SCHEDULING="${ENABLE_ASYNC_SCHEDULING:-1}"
export ENABLE_MTP="${ENABLE_MTP:-1}"
export MTP_TOKENS="${MTP_TOKENS:-3}"
export MTP_DRAFT_SAMPLE_METHOD="${MTP_DRAFT_SAMPLE_METHOD:-greedy}"
export VLLM_EXL3_TRELLIS_MIN_M="${VLLM_EXL3_TRELLIS_MIN_M:-1}"

# Preserve the publisher-tested physical rank order 3,1,2,0.
export CUDA_DEVICE_ORDER=PCI_BUS_ID
export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-GPU-<uuid>,GPU-<uuid>,GPU-<uuid>,GPU-<uuid>}"
export NVIDIA_VISIBLE_DEVICES="$CUDA_VISIBLE_DEVICES"

command -v docker >/dev/null 2>&1
docker compose version >/dev/null 2>&1
test -f "$COMPOSE_FILE"
test -f "$MODEL_DIR/config.json"
test -f "$MODEL_DIR/model.safetensors.index.json"
mkdir -p "$CACHE_DIR"

docker image inspect "$IMAGE" >/dev/null
docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true

echo "[glm52-exl3-text] launch: image=$IMAGE model=$MODEL_DIR served=$SERVED_MODEL_NAME context=$MAX_MODEL_LEN tp=4 dcp=4"
exec docker compose -f "$COMPOSE_FILE" --project-name "$COMPOSE_PROJECT_NAME" up --force-recreate
