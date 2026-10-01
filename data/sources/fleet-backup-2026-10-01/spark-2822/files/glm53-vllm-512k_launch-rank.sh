#!/usr/bin/env bash
set -euo pipefail

RANK="${1:?usage: launch-rank.sh <0|1|2|3>}"
IMAGE="ghcr.io/tonyd2wild/vllm-glm53-flash:sm121-v11-dflash2"
NAME="vllm_glm53_512k"
MODEL_HOST_PATH="$HOME/models/GLM-5.3-Flash-NVFP4"
DRAFT_HOST_PATH="$HOME/models/GLM-5.3-Flash-DFlash2"
CHAT_TEMPLATE="$HOME/glm-5.3-flash-sglang-sm121/chat-template-mm.jinja"
PATCH_FILE="$HOME/patches/sparse_attn_indexer_kpool.py"
CACHE_HOST_PATH="$HOME/.cache/glm53-vllm-512k"
HEAD_IP="<fabric-ip>"
MASTER_PORT="29521"
PORT="8000"

case "$RANK" in
  0) HOST_IP="<fabric-ip>"; HEADLESS=() ;;
  1) HOST_IP="<fabric-ip>"; HEADLESS=(--headless) ;;
  2) HOST_IP="<fabric-ip>"; HEADLESS=(--headless) ;;
  3) HOST_IP="<fabric-ip>"; HEADLESS=(--headless) ;;
  *) echo "rank must be 0..3" >&2; exit 2 ;;
esac

test -f "$MODEL_HOST_PATH/config.json" || { echo "missing model config" >&2; exit 3; }
test -f "$DRAFT_HOST_PATH/config.json" || { echo "missing DFlash2 config" >&2; exit 3; }
test -f "$CHAT_TEMPLATE" || { echo "missing multimodal chat template" >&2; exit 3; }
test -f "$PATCH_FILE" || { echo "missing SM121 sparse-indexer patch" >&2; exit 3; }
mkdir -p "$CACHE_HOST_PATH"

docker rm -f "$NAME" 2>/dev/null || true
docker run --gpus all -d \
  --name "$NAME" --restart no \
  --network host --ipc host --shm-size 32g --memory 112g --memory-swap 112g \
  --ulimit memlock=-1:-1 --cap-add IPC_LOCK \
  --device /dev/infiniband:/dev/infiniband \
  -v "$MODEL_HOST_PATH:/models/glm-5.3-flash-nvfp4:ro" \
  -v "$DRAFT_HOST_PATH:/models/dflash2-draft:ro" \
  -v "$CHAT_TEMPLATE:/models/chat-template-mm.jinja:ro" \
  -v "$PATCH_FILE:/usr/local/lib/python3.12/dist-packages/vllm/model_executor/layers/sparse_attn_indexer_kpool.py:ro" \
  -v "$CACHE_HOST_PATH:/cache" \
  -e VLLM_HOST_IP="$HOST_IP" \
  -e HF_HOME=/cache/huggingface \
  -e HF_HUB_OFFLINE=1 -e TRANSFORMERS_OFFLINE=1 \
  -e VLLM_ENGINE_READY_TIMEOUT_S=3600 \
  -e PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
  -e TORCH_CUDA_ARCH_LIST=12.1a -e FLASHINFER_CUDA_ARCH_LIST=12.1a \
  -e FLASHINFER_DISABLE_VERSION_CHECK=1 \
  -e NCCL_NET=IB -e NCCL_IB_DISABLE=0 \
  -e NCCL_IB_HCA=rocep1s0f1 -e NCCL_IB_GID_INDEX=3 \
  -e NCCL_IB_ROCE_VERSION_NUM=2 -e NCCL_IB_ADDR_FAMILY=AF_INET \
  -e NCCL_IB_ADDR_RANGE=<fabric-ip>/24 \
  -e NCCL_SOCKET_IFNAME=enp1s0f1np1 -e GLOO_SOCKET_IFNAME=enp1s0f1np1 \
  -e TP_SOCKET_IFNAME=enp1s0f1np1 -e MN_IF_NAME=enp1s0f1np1 \
  -e NCCL_NVLS_ENABLE=0 -e NCCL_CROSS_NIC=0 -e NCCL_IB_MERGE_NICS=0 \
  -e NCCL_CUMEM_ENABLE=0 -e NCCL_IGNORE_CPU_AFFINITY=1 -e NCCL_DEBUG=WARN \
  -e TORCH_NCCL_ASYNC_ERROR_HANDLING=1 \
  "$IMAGE" \
    /models/glm-5.3-flash-nvfp4 \
    --served-model-name glm-5.3-flash \
    --host 0.0.0.0 --port "$PORT" \
    --trust-remote-code \
    --tensor-parallel-size 4 \
    --gpu-memory-utilization 0.85 \
    --max-model-len 524288 \
    --max-num-seqs 1 --max-num-batched-tokens 2048 \
    --block-size 2304 --moe-backend marlin \
    --speculative-config '{"method":"dflash","model":"/models/dflash2-draft","num_speculative_tokens":7}' \
    --kv-cache-dtype fp8_e4m3 --kv-cache-memory 12884901888 \
    --tool-call-parser glm47 --enable-auto-tool-choice \
    --reasoning-parser glm45 --chat-template /models/chat-template-mm.jinja \
    --default-chat-template-kwargs '{"enable_thinking":true}' \
    --distributed-executor-backend mp \
    --nnodes 4 --node-rank "$RANK" \
    --master-addr "$HEAD_IP" --master-port "$MASTER_PORT" \
    "${HEADLESS[@]}"

echo "launched $NAME rank=$RANK host=$HOST_IP context=524288 kv=12GiB graphs=enabled"
