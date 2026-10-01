# Locked DeepSeek-V4-Flash-0731 SparkInfer runtime for 4x RTX PRO 6000 Blackwell.
# Model weights remain an external read-only mount; they are never baked into the image.
FROM voipmonitor/vllm:eldritch-enlightenment-ds4dspark-v9-ve72ad00-b12x57422ad-cu132-20260703@sha256:937db99d072fe089be6d9d88c356e5e2540243389bc7669ecf57a102f637c15e

LABEL org.opencontainers.image.title="DeepSeek V4 Flash 0731 exact SparkInfer runtime" \
      org.opencontainers.image.base.digest="sha256:937db99d072fe089be6d9d88c356e5e2540243389bc7669ecf57a102f637c15e" \
      org.opencontainers.image.model="deepseek-ai/DeepSeek-V4-Flash-0731" \
      org.opencontainers.image.model.revision="7872f01b1d1fe23eabc4c98b48bffcef5a386062" \
      org.opencontainers.image.recipe.context="1048576" \
      org.opencontainers.image.recipe.model_id="DeepSeek-V4-Flash-0731"

ENV CUDA_VISIBLE_DEVICES="0,1,2,3" \
    CUTE_DSL_ARCH="sm_120a" \
    VLLM_USE_V2_MODEL_RUNNER="1" \
    VLLM_USE_B12X_MOE="1" \
    VLLM_USE_B12X_SPARSE_INDEXER="1" \
    VLLM_USE_B12X_FP8_GEMM="0" \
    B12X_DENSE_SPLITK_TURBO="1" \
    B12X_MLA_SM120_PREFILL_F16_ROPE="1" \
    NCCL_P2P_DISABLE="1" \
    NCCL_IB_DISABLE="1" \
    NCCL_P2P_LEVEL="SYS" \
    NCCL_PROTO="LL,LL128,Simple" \
    VLLM_ENABLE_PCIE_ALLREDUCE="0" \
    VLLM_CACHE_ROOT="/cache" \
    HF_HUB_OFFLINE="1" \
    TRANSFORMERS_OFFLINE="1"

ENTRYPOINT ["/opt/venv/bin/vllm"]

CMD ["serve", "/model", "--served-model-name", "DeepSeek-V4-Flash-0731", "--host", "0.0.0.0", "--port", "8000", "--trust-remote-code", "--tensor-parallel-size", "4", "--decode-context-parallel-size", "1", "--kv-cache-dtype", "fp8_ds_mla", "--moe-backend", "b12x", "--load-format", "safetensors", "-cc.pass_config.fuse_allreduce_rms=True", "--gpu-memory-utilization", "0.90", "--max-model-len", "1048576", "--max-num-seqs", "8", "--max-num-batched-tokens", "8192", "--block-size", "256", "--max-cudagraph-capture-size", "48", "--async-scheduling", "--enable-chunked-prefill", "--enable-auto-tool-choice", "--tokenizer-mode", "deepseek_v4", "--tool-call-parser", "deepseek_v4", "--reasoning-parser", "deepseek_v4", "--speculative-config", "{\"method\":\"dspark\",\"num_speculative_tokens\":5,\"moe_backend\":\"b12x\",\"draft_sample_method\":\"probabilistic\"}"]
