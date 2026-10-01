#!/usr/bin/env bash
# Corrected DFlash2 candidate: current GLM-5.3 branch plus SM120 NVFP4 target.
set -eu

candidate_name=glm-5.3-flash-dflash2-sm120
candidate_log=${HOME}/glm53-dflash2-build-v3/engine.log

docker rm -f "$candidate_name" >/dev/null 2>&1 || true

exec docker run --rm >> "$candidate_log" 2>&1 \
  --name "$candidate_name" \
  --gpus all \
  --ipc=host \
  --shm-size=32g \
  --security-opt label=disable \
  -p 8000:30000 \
  -e CUDA_DEVICE_ORDER=PCI_BUS_ID \
  -e TORCH_CUDA_ARCH_LIST=12.0a \
  -e FLASHINFER_CUDA_ARCH_LIST=12.0f \
  -v ${MODEL_ROOT}/GLM-5.3-Flash-NVFP4:/model:ro \
  -v ${MODEL_ROOT}/GLM-5.3-Flash-DFlash2:/draft:ro \
  -v ${HOME}/.cache/sglang-glm53-dflash2-v3:/root/.cache:rw \
  -v ${HOME}/glm53-flash-deploy/chat-template-mm.jinja:/chat-template.jinja:ro \
  glm53-flash-nvfp4-sglang:dflash2-glm53-current-sm120-v3 \
  -m sglang.launch_server \
  --model-path /model \
  --served-model-name glm-5.3-flash-dflash \
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
  --speculative-algorithm DFLASH \
  --speculative-num-steps 1 \
  --speculative-num-draft-tokens 8 \
  --speculative-draft-model-path /draft \
  --speculative-draft-model-quantization unquant \
  --speculative-draft-attention-backend fa4 \
  --media-url-max-file-size-mb 1024 \
  --enable-multimodal \
  --chat-template /chat-template.jinja \
  --reasoning-parser glm45 \
  --tool-call-parser glm47 \
  --enable-metrics \
  --enable-metrics-for-all-schedulers \
  --enable-cache-report \
  --enable-hierarchical-cache \
  --hicache-size 8 \
  --host 0.0.0.0 \
  --port 30000
