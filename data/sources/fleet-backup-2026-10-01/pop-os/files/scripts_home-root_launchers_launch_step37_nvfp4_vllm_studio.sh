#!/usr/bin/env bash
set -euo pipefail
container=step37-flash-nvfp4-vllm
docker rm -f "$container" >/dev/null 2>&1 || true
exec docker run --rm \
  --name "$container" \
  --gpus '"device=0,1,2,3"' \
  --ipc=host \
  --shm-size=64g \
  --ulimit memlock=-1 \
  --ulimit stack=67108864 \
  --network host \
  -v ${MODEL_ROOT}/Step-3.7-Flash-NVFP4:/model:ro \
  -v ${MODEL_ROOT}/hf:/root/.cache/huggingface \
  -e CUDA_VISIBLE_DEVICES=0,1,2,3 \
  -e CUDA_DEVICE_ORDER=PCI_BUS_ID \
  -e HF_HOME=/root/.cache/huggingface \
  -e OMP_NUM_THREADS=8 \
  -e SAFETENSORS_FAST_GPU=1 \
  -e NCCL_P2P_DISABLE=1 \
  -e NCCL_IB_DISABLE=1 \
  -e NCCL_SOCKET_IFNAME=lo \
  -e GLOO_SOCKET_IFNAME=lo \
  -e NCCL_DEBUG=WARN \
  -e NCCL_CUMEM_HOST_ENABLE=0 \
  -e PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
  -e VLLM_LOGGING_LEVEL=INFO \
  vllm/vllm-openai:stepfun37 \
  --model /model \
    --host 0.0.0.0 \
    --port 8000 \
    --served-model-name step3p7-flash-nvfp4 \
    --tensor-parallel-size 4 \
    --enable-expert-parallel \
    --trust-remote-code \
    --quantization modelopt \
    --kv-cache-dtype fp8 \
    --max-model-len 8192 \
    --gpu-memory-utilization 0.90 \
    --reasoning-parser step3p5 \
    --enable-auto-tool-choice \
    --tool-call-parser step3p5 \
    --async-scheduling \
    --disable-custom-all-reduce
