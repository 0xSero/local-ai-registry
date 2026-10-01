#!/usr/bin/env bash
# GLM-5.2 MXFP8-NVFP4-NF3 Hybrid — TP4/DCP4 on yatesdr's stock v19 patched image.
# Source contract: user-supplied GLM-5.2-hybrid-TP4.yaml (gilded-gnosis-v19-int8-block-patched,
# digest-pinned). Direct `vllm serve` — no wrapper-script patches.
# Pop-os adaptations: ${MODEL_ROOT} model path, host network + port 8000 (litellm/webui/
# controller identity), served name GLM-5.2, i8 PCIe DMA (PCIe 5.0 box, per author's note),
# no autoheal sidecar (controller owns lifecycle), no restart policy (--rm, controller relaunches).
# DRAM KV offload tier KEPT: 64 GB warm tier in /dev/shm (252G free) extends prefix caching,
# which dominates this box's ~99% -prefill workload.
set -euo pipefail

IMG=ghcr.io/yatesdr/glm52-serve@sha256:ca8481687f7169adf177f02df83c06259af0941e9a1de8695b5a4e60d745463a

exec docker run --rm --name local-studio-glm-5.2-nf3-hybrid \
  --network host --ipc host --shm-size 32g --gpus all \
  --ulimit memlock=-1 --ulimit nofile=1048576 \
  --entrypoint /bin/sh \
  -e CUDA_VISIBLE_DEVICES=0,1,2,3 \
  -e CUDA_DEVICE_MAX_CONNECTIONS=32 \
  -e CUTE_DSL_ARCH=sm_120a \
  -e TORCH_CUDA_ARCH_LIST=12.0a \
  -e OMP_NUM_THREADS=16 \
  -e GLOO_SOCKET_IFNAME=lo \
  -e NCCL_SOCKET_IFNAME=lo \
  -e NCCL_IB_DISABLE=1 \
  -e NCCL_P2P_LEVEL=SYS \
  -e NCCL_PROTO=LL,LL128,Simple \
  -e VLLM_WORKER_MULTIPROC_METHOD=spawn \
  -e SAFETENSORS_FAST_GPU=1 \
  -e LD_PRELOAD=/opt/libnccl-local-inference.so.2.30.4 \
  -e VLLM_NCCL_SO_PATH=/opt/libnccl-local-inference.so.2.30.4 \
  -e XDG_CACHE_HOME=/cache/jit \
  -e TRITON_CACHE_DIR=/cache/jit/triton \
  -e PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
  -e KV_FP8_ROPE=1 \
  -e NF3_GRID188=1 \
  -e VLLM_NF3_GRID188_DECODE=1 \
  -e VLLM_USE_B12X_FP8_GEMM=1 \
  -e VLLM_USE_B12X_MOE=1 \
  -e VLLM_USE_B12X_SPARSE_INDEXER=1 \
  -e VLLM_USE_B12X_WO_PROJECTION=1 \
  -e VLLM_USE_B12X_MHC=1 \
  -e VLLM_USE_B12X_DCP_A2A=1 \
  -e VLLM_USE_B12X_PCIE_DMA=1 \
  -e VLLM_USE_V2_MODEL_RUNNER=1 \
  -e VLLM_USE_AOT_COMPILE=1 \
  -e VLLM_USE_MEGA_AOT_ARTIFACT=1 \
  -e VLLM_USE_FLASHINFER_SAMPLER=1 \
  -e VLLM_USE_BREAKABLE_CUDAGRAPH=0 \
  -e B12X_W4A16_TC_DECODE=1 \
  -e B12X_W4A8_TINY_DECODE=1 \
  -e B12X_MLA_SM120_UNIFIED=1 \
  -e B12X_DENSE_SPLITK_TURBO=1 \
  -e B12X_MOE_FORCE_A16=1 \
  -e B12X_MOE_FORCE_A8=0 \
  -e VLLM_DCP_GLOBAL_TOPK=1 \
  -e VLLM_DCP_SHARD_DRAFT=1 \
  -e VLLM_DCP_QUERY_SPLIT=0 \
  -e VLLM_DCP_A2A_MAX_TOKENS=64 \
  -e VLLM_DCP_A2A_LARGE_BACKEND=ag_rs \
  -e VLLM_DCP_PROJECT_BEFORE_MERGE=1 \
  -e VLLM_DCP_PROJECT_BEFORE_MERGE_MIN_PREFILL_TOKENS=1024 \
  -e VLLM_B12X_MLA_DCP_GATHER_IN_WORKSPACE=1 \
  -e VLLM_B12X_MLA_CKV_GATHER=1 \
  -e VLLM_ENABLE_PCIE_ALLREDUCE=1 \
  -e VLLM_PCIE_ALLREDUCE_BACKEND=b12x \
  -e VLLM_PCIE_ONESHOT_ALLREDUCE_MAX_SIZE=64KB \
  -e VLLM_PCIE_ONESHOT_FUSED_ADD_RMS_NORM_MAX_SIZE=84KB \
  -e VLLM_PCIE_DMA_FP8=i8 \
  -e B12X_PCIE_DMA_FP8=i8 \
  -e TORCH_EXTENSIONS_DIR=/cache/int8ext_baked_a826ef58 \
  -e VLLM_MEMORY_PROFILE_INCLUDE_ATTN=1 \
  -e VLLM_MEMORY_PROFILER_ESTIMATE_CUDAGRAPHS=1 \
  -e VLLM_DISABLED_KERNELS=MarlinFP8ScaledMMLinearKernel \
  -v ${MODEL_ROOT}/GLM-5.2-MXFP8-NVFP4-NF3-Hybrid:/model:ro \
  -v ${HOME}/glm52-prod/cache:/cache:rw \
  -v ${HOME}/glm52-prod/cache:/root/.cache:rw \
  "$IMG" \
  -c 'rm -f /dev/shm/vllm_offload_*.mmap 2>/dev/null || true; exec vllm serve "$@"' -- \
  /model \
  --served-model-name GLM-5.2 \
  --host=0.0.0.0 \
  --port 8000 \
  --trust-remote-code \
  --tensor-parallel-size=4 \
  --decode-context-parallel-size=4 \
  --dcp-comm-backend=ag_rs \
  --dcp-kv-cache-interleave-size=1 \
  --kv-cache-dtype=nvfp4_ds_mla \
  --attention-backend=B12X_MLA_SPARSE \
  --moe-backend=b12x \
  --quantization=nvfp4_nf3_hybrid \
  '--quantization-config={"linear":{"weight":"mxfp8"},"shared_experts":{"weight":"mxfp8"},"ignore":["re:^model\\.layers\\.0\\.","re:.*\\.self_attn\\.indexer\\.","re:.*\\.mlp\\.gate$","model.layers.78.eh_proj","lm_head"]}' \
  --load-format=safetensors \
  -cc.pass_config.fuse_allreduce_rms=True \
  --gpu-memory-utilization=0.970 \
  --max-model-len=480000 \
  --max-num-seqs=16 \
  --max-num-batched-tokens=3072 \
  --max-cudagraph-capture-size=64 \
  --async-scheduling \
  --enable-chunked-prefill \
  --enable-prefix-caching \
  --enable-flashinfer-autotune \
  --enable-auto-tool-choice \
  --tool-call-parser=glm47 \
  --reasoning-parser=glm45 \
  '--default-chat-template-kwargs={"reasoning_effort":"high"}' \
  --enable-prompt-tokens-details \
  --enable-force-include-usage \
  --enable-request-id-headers \
  '--hf-overrides={"use_index_cache":true,"index_topk_pattern":"FFFSSSFSSSFSSSFSSSFSSSFSSSFSSSFSSSFSSSFSSSFSSSFSSSFSSSFSSSFSSSFSSSFSSSFSSSFSSS"}' \
  '--speculative-config={"model":"/model","method":"mtp","num_speculative_tokens":5,"moe_backend":"b12x","draft_sample_method":"probabilistic"}'
