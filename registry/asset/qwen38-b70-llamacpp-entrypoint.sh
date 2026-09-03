#!/usr/bin/env bash
set -e
source /opt/intel/oneapi/setvars.sh --force >/dev/null 2>&1

MODELS_DIR="${MODELS_DIR:-/models}"
GPU_COUNT="${GPU_COUNT:-2}"        # 1 or 2 Arc Pro B70s
CTX_SIZE="${CTX_SIZE:-262144}"     # default for 2 GPUs; 1 GPU defaults to 131072
PARALLEL="${PARALLEL:-1}"
BATCH="${BATCH:-8192}"
UBATCH="${UBATCH:-8192}"
PORT="${PORT:-8010}"
ENABLE_MTP="${ENABLE_MTP:-0}"
ENABLE_VISION="${ENABLE_VISION:-0}"

if [ "$GPU_COUNT" = "1" ]; then
    DEVICE_ARGS=(--device SYCL0)
    CTX_SIZE="${CTX_SIZE_OVERRIDE:-131072}"
else
    DEVICE_ARGS=(--device SYCL0,SYCL1 --split-mode tensor --tensor-split 1,1)
    CTX_SIZE="${CTX_SIZE_OVERRIDE:-$CTX_SIZE}"
fi

# Download + verify the pinned target model on first run
TARGET="$MODELS_DIR/$MODEL_FILE"
if [ ! -f "$TARGET" ]; then
    echo "[entrypoint] downloading $MODEL_REPO/$MODEL_FILE @$MODEL_REV ..."
    hf download "$MODEL_REPO" "$MODEL_FILE" --revision "$MODEL_REV" --local-dir "$MODELS_DIR"
fi
echo "$MODEL_SHA256  $TARGET" | sha256sum -c - || { echo "[entrypoint] SHA-256 mismatch!"; exit 1; }

# Optional MTP draft sidecar (speculative decoding)
DRAFT_ARGS=()
if [ "$ENABLE_MTP" = "1" ]; then
    if [ ! -f "$MODELS_DIR/$MTP_FILE" ]; then
        hf download "$MODEL_REPO" "$MTP_FILE" --revision "$MODEL_REV" --local-dir "$MODELS_DIR"
    fi
    DRAFT_ARGS=(--spec-type draft-mtp --model-draft "$MODELS_DIR/$MTP_FILE" --spec-draft-n-max "${SPEC_DRAFT_N_MAX:-8}" --spec-draft-threads "${DRAFT_THREADS:-16}" --spec-draft-poll 1 --spec-draft-ngl "${DRAFT_NGL:-0}" --spec-draft-device "${DRAFT_DEVICE:-SYCL0}")
fi

# Optional vision projector (image input; encoder on CPU — GPU offload hangs the xe driver)
MM_ARGS=()
if [ "$ENABLE_VISION" = "1" ]; then
    if [ ! -f "$MODELS_DIR/$MMPROJ_FILE" ]; then
        hf download "$MODEL_REPO" "$MMPROJ_FILE" --revision "$MODEL_REV" --local-dir "$MODELS_DIR"
    fi
    MM_ARGS=(--no-mmproj-offload --mmproj "$MODELS_DIR/$MMPROJ_FILE")
fi

# Lab runtime environment (b70-optimization-lab qwen38-27b-q4km-tp2 config.env)
export UR_L0_USE_IMMEDIATE_COMMANDLISTS=1
export UR_L0_V2_FORCE_DISABLE_COPY_OFFLOAD=1
export GGML_SYCL_COMM_SINGLE_KERNEL=1
export GGML_META_FUSE_ALLREDUCE_ADD=1
export GGML_META_FUSE_ALLREDUCE_ADD_RMS_MUL=1
export GGML_SYCL_COMM_FUSED_Q8=1
export GGML_SYCL_FUSED_SWIGLU_Q8=1
export GGML_SYCL_FUSED_ATTN_Q8=1
export GGML_SYCL_FUSED_GDN_Q8=1
export GGML_SYCL_FUSED_GDN_BETA_SIGMOID=1
export GGML_SYCL_FUSED_CONCAT_STATE=1
export GGML_SYCL_FUSED_GDN_STATE_IO=1
export GGML_SYCL_FUSED_CONV_STATE_IO=1
export GGML_SYCL_COMM_DIRECT_Q8=2
export GGML_SYCL_FUSED_ROPE_SET_ROWS=1
export GGML_SYCL_COMM_REDUCE_VEC4=1
export GGML_SYCL_FUSED_QK_NORM_ROPE=1
export GGML_SYCL_FUSED_CONV_SILU_L2=1
export GGML_SYCL_FUSE_EXT=31
# Quality guards (verified coherent on the JIT build):
# - FATTN_MMA=0: joint_matrix unavailable under oneAPI 2025.3 JIT
# - Q4K reorder-family OFF: expects the lab AOT build's reordered layout,
#   produces corrupted output on stock ggml-org weights under JIT
export GGML_SYCL_FATTN_MMA=0
export GGML_SYCL_MMQ_Q4K_REORDER=1
export GGML_SYCL_FUSED_MMVQ_SWIGLU_Q4K=1
export GGML_SYCL_FUSED_MMVQ_PAIR=0
export GGML_SYCL_FUSED_MMVQ_PAIR_GDN=0
export GGML_SYCL_FUSED_MMVQ_TRIPLE_ATTN=0
export GGML_SYCL_FUSED_MMVQ_TRIPLE_GDN=0
export GGML_SYCL_FUSED_MMVQ_QUAD_GDN=0

exec /build/llama.cpp/build-sycl/bin/llama-server \
    --model "$TARGET" \
    "${MM_ARGS[@]}" \
    "${DRAFT_ARGS[@]}" \
    --host 0.0.0.0 --port "$PORT" \
    "${DEVICE_ARGS[@]}" \
    --gpu-layers 99 \
    --flash-attn on \
    --batch-size "$BATCH" \
    --ubatch-size "$UBATCH" \
    --cache-type-k f16 \
    --cache-type-v f16 \
    --cache-ram 0 \
    --ctx-checkpoints 0 \
    --fit off \
    --reasoning off \
    --threads "${THREADS:-8}" \
    --poll 50 \
    --ctx-size "$CTX_SIZE" \
    --parallel "$PARALLEL" \
    --metrics
