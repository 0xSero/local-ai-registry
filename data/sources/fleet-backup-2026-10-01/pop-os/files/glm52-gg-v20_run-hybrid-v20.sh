#!/usr/bin/env bash
# GLM-5.2 NF3 hybrid on Gilded Gnosis v20 (rtx6kpro glm5.2_v20.md contract).
# Single container, helper-owned launch via serve-gilded-gnosis.sh.
# Pop-os adaptations vs the reference compose: model path ${MODEL_ROOT},
# PORT=8000 (controller owns :8080), served name GLM-5.2.
set -euo pipefail
IMG=voipmonitor/vllm:gilded-gnosis-v20-vllm3e731bc-si1a88b38-fi801d57a-cu132-20260722
exec docker run --rm --name local-studio-glm-5.2-nf3-hybrid \
  --entrypoint /usr/local/bin/serve-gilded-gnosis.sh \
  --network host --ipc host --shm-size 32g --init --gpus all \
  --ulimit memlock=-1 --ulimit stack=67108864 --ulimit nofile=1048576:1048576 \
  -e MODEL_FAMILY=glm52-hybrid \
  -e MODEL=/model \
  -e SERVED_MODEL_NAME=GLM-5.2 \
  -e GPUS=0,1,2,3 \
  -e PORT=8000 \
  -e TP=4 -e DCP=4 -e MTP=3 \
  -e DCP_BACKEND=a2a \
  -e DCP_A2A_MAX_TOKENS=16 \
  -e DCP_A2A_LARGE_BACKEND=ag_rs \
  -e DCP_CKV_GATHER=1 \
  -e VLLM_B12X_MLA_CKV_GATHER_MAX_TOKENS=480000 \
  -e KV_CACHE_DTYPE=nvfp4_ds_mla \
  -e MAX_MODEL_LEN=479744 \
  -e MAX_NUM_SEQS=8 \
  -e MAX_BATCHED_TOKENS=3072 \
  -e GRAPH=32 \
  -e GPU_MEMORY_UTILIZATION=0.978 \
  -e LOAD_FORMAT=fastsafetensors \
  -e INSTANTTENSOR_BACKEND=BUFFERED \
  -e F8_DMA=0 \
  -e PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
  -e VLLM_PCIE_ONESHOT_ALLREDUCE_MAX_SIZE=120KB \
  -e VLLM_PCIE_ONESHOT_FUSED_ADD_RMS_NORM_MAX_SIZE=84KB \
  ${DRY_RUN:+-e DRY_RUN=$DRY_RUN} \
  -v ${MODEL_ROOT}/GLM-5.2-MXFP8-NVFP4-NF3-Hybrid:/model:ro \
  -v ${HOME}/glm52-gg-v20/serve-glm52-v16.override.sh:/usr/local/bin/serve-glm52-v16.sh:ro \
  -v local-studio-jit-glm52-gg-v20:/cache \
  "$IMG"
