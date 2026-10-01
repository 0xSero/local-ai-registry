#!/usr/bin/env bash
# Studio-managed launcher for GLM-5.3-Flash NVFP4 on 4x RTX PRO 6000 Blackwell (SM120).
# Runs the exact-docker image in FOREGROUND so Local Studio supervises this process.
set -eu

docker rm -f glm-5.3-flash-sglang-sm120 >/dev/null 2>&1 || true

exec docker run --rm >> ${HOME}/glm53-flash-deploy/engine.log 2>&1 \
  --name glm-5.3-flash-sglang-sm120 \
  --gpus all \
  --ipc=host \
  --shm-size=32g \
  --security-opt label=disable \
  -p 8000:30000 \
  -e CUDA_DEVICE_ORDER=PCI_BUS_ID \
  -e NVIDIA_VISIBLE_DEVICES=GPU-<uuid>,GPU-<uuid>,GPU-<uuid>,GPU-<uuid> \
  -v ${MODEL_ROOT}/GLM-5.3-Flash-NVFP4:/model:ro \
  -v ${HOME}/.cache/sglang-glm53:/root/.cache:rw \
  -v ${HOME}/glm53-flash-deploy/chat-template-mm.jinja:/chat-template.jinja:ro \
  glm53-flash-nvfp4-sglang:exact-20260826 \
  -m sglang.launch_server \
  --model-path /model \
  --served-model-name glm-5.3-flash \
  --tp-size 4 \
  --ep-size 4 \
  --context-length 1048576 \
  --quantization modelopt_fp4 \
  --attention-backend dsa \
  --dsa-prefill-backend flashinfer_sparse_mla \
  --dsa-decode-backend flashinfer_sparse_mla \
  --linear-attn-backend triton \
  --kv-cache-dtype fp8_e4m3 \
  --moe-runner-backend flashinfer_cutlass \
  --disable-shared-experts-fusion \
  --chunked-prefill-size 8192 \
  --max-prefill-tokens 8192 \
  --max-running-requests 8 \
  --mem-fraction-static 0.90 \
  --cuda-graph-max-bs-decode 8 \
  --speculative-algorithm NEXTN \
  --speculative-num-steps 5 \
  --speculative-eagle-topk 1 \
  --speculative-num-draft-tokens 6 \
  --speculative-adaptive \
  --media-url-max-file-size-mb 1024 \
  --enable-multimodal --chat-template /chat-template.jinja --reasoning-parser glm45 \
  --tool-call-parser glm47 \
  --enable-metrics \
  --enable-metrics-for-all-schedulers \
  --enable-cache-report \
  --enable-hierarchical-cache \
  --hicache-size 8 \
  --host 0.0.0.0 \
  --port 30000
