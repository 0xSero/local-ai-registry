#!/usr/bin/env bash
set -euo pipefail

die() {
  echo "ERROR: $*" >&2
  exit 2
}

MODEL="${MODEL:-lukealonso/GLM-5.2-NVFP4}"
MODEL_REVISION="${MODEL_REVISION:-8a1f4a13204acf2b7ac840375efaed64c231c522}"
SERVED_MODEL_NAME="${SERVED_MODEL_NAME:-GLM-5.2-NVFP4}"
PORT="${PORT:-8000}"
GPUS="${GPUS:-0,1,2,3,4,5,6,7}"
TP="${TP:-8}"
DCP="${DCP:-1}"
DCP_BACKEND="${DCP_BACKEND:-a2a}"
DCP_A2A_MAX_TOKENS="${DCP_A2A_MAX_TOKENS:-64}"
DCP_A2A_LARGE_BACKEND="${DCP_A2A_LARGE_BACKEND:-ag_rs}"
DCP_PREFILL_WORKSPACE="${DCP_PREFILL_WORKSPACE:-auto}"
MTP="${MTP:-0}"
MAX_NUM_SEQS="${MAX_NUM_SEQS:-64}"
GRAPH="${GRAPH:-$((MAX_NUM_SEQS * 4))}"
MAX_BATCHED_TOKENS="${MAX_BATCHED_TOKENS:-8192}"
if [[ "${TP}" == "6" ]]; then
  MAX_MODEL_LEN="${MAX_MODEL_LEN:-128000}"
  GPU_MEMORY_UTILIZATION="${GPU_MEMORY_UTILIZATION:-0.95}"
else
  MAX_MODEL_LEN="${MAX_MODEL_LEN:-262144}"
  GPU_MEMORY_UTILIZATION="${GPU_MEMORY_UTILIZATION:-0.96}"
fi
MOE_MODE="${MOE_MODE:-a4}"
MOE_BACKEND="${MOE_BACKEND:-b12x}"
LINEAR_BACKEND="${LINEAR_BACKEND:-auto}"
ONLINE_MXFP8="${ONLINE_MXFP8:-0}"
ONLINE_FP8="${ONLINE_FP8:-0}"
ONLINE_FP8_MXFP4="${ONLINE_FP8_MXFP4:-0}"
ONLINE_QUANT="${ONLINE_QUANT:-}"
NF3_GRID188="${NF3_GRID188:-1}"
F8_DMA="${F8_DMA:-0}"
B12X_PCIE_DMA="${B12X_PCIE_DMA:-1}"
LOAD_FORMAT="${LOAD_FORMAT:-instanttensor}"
INSTANTTENSOR_BACKEND="${INSTANTTENSOR_BACKEND:-BUFFERED}"
PYTORCH_CUDA_ALLOC_CONF="${PYTORCH_CUDA_ALLOC_CONF-expandable_segments:True}"
QUANTIZATION="${QUANTIZATION:-modelopt_fp4}"
QUANTIZATION_CONFIG_JSON="${QUANTIZATION_CONFIG_JSON:-}"
KV_CACHE_DTYPE="${KV_CACHE_DTYPE:-fp8}"
GLM52_INDEX_TOPK_PATTERN="${GLM52_INDEX_TOPK_PATTERN:-FFFSSSFSSSFSSSFSSSFSSSFSSSFSSSFSSSFSSSFSSSFSSSFSSSFSSSFSSSFSSSFSSSFSSSFSSSFSSS}"

case "${MOE_MODE}" in
  a4|native|default)
    B12X_MOE_FORCE_A8=0
    B12X_MOE_FORCE_A16=0
    ;;
  a16|force-a16)
    B12X_MOE_FORCE_A8=0
    B12X_MOE_FORCE_A16=1
    ;;
  force-a8-experimental|a8-experimental|a8)
    B12X_MOE_FORCE_A8=1
    B12X_MOE_FORCE_A16=0
    ;;
  *)
    die "MOE_MODE must be a4, a16, or force-a8-experimental"
    ;;
esac

case "${F8_DMA}" in
  0|ag|ring) ;;
  *) die "F8_DMA must be 0, ag, or ring" ;;
esac

case "${B12X_PCIE_DMA}" in
  0|1) ;;
  *) die "B12X_PCIE_DMA must be 0 or 1" ;;
esac

case "${KV_CACHE_DTYPE}" in
  fp8|fp8_ds_mla|nvfp4_ds_mla) ;;
  *) die "KV_CACHE_DTYPE must be fp8, fp8_ds_mla, or nvfp4_ds_mla" ;;
esac

case "${DCP_A2A_LARGE_BACKEND}" in
  ag_rs|a2a) ;;
  *) die "DCP_A2A_LARGE_BACKEND must be ag_rs or a2a" ;;
esac

case "${DCP_PREFILL_WORKSPACE}" in
  auto|0|1) ;;
  *) die "DCP_PREFILL_WORKSPACE must be auto, 0, or 1" ;;
esac

case "${MOE_BACKEND}" in
  auto|triton|deep_gemm|deep_gemm_mega_moe|b12x|cutlass|flashinfer_trtllm|flashinfer_cutlass|flashinfer_cutedsl|flashinfer_b12x|marlin|humming|triton_unfused|aiter|flydsl|emulation) ;;
  *) die "MOE_BACKEND is not a supported vLLM MoE backend: ${MOE_BACKEND}" ;;
esac

case "${LINEAR_BACKEND}" in
  auto|b12x|cutlass|flashinfer_cutlass|flashinfer_cutedsl|flashinfer_trtllm|flashinfer_cudnn|flashinfer_b12x|marlin|triton|deep_gemm|torch|aiter|machete|fbgemm|conch|exllama|emulation) ;;
  *) die "LINEAR_BACKEND is not a supported vLLM linear backend: ${LINEAR_BACKEND}" ;;
esac

[[ "${ONLINE_MXFP8}" =~ ^(0|1)$ ]] || die "ONLINE_MXFP8 must be 0 or 1"
[[ "${ONLINE_FP8}" =~ ^(0|1)$ ]] || die "ONLINE_FP8 must be 0 or 1"
[[ "${ONLINE_FP8_MXFP4}" =~ ^(0|1)$ ]] || die "ONLINE_FP8_MXFP4 must be 0 or 1"
[[ "${NF3_GRID188}" =~ ^(0|1)$ ]] || die "NF3_GRID188 must be 0 or 1"
[[ "${MTP}" =~ ^[0-9]+$ ]] || die "MTP must be an integer token count"
[[ "${DCP_A2A_MAX_TOKENS}" =~ ^[0-9]+$ ]] || die "DCP_A2A_MAX_TOKENS must be an integer token count"
[[ "${MAX_NUM_SEQS}" =~ ^[0-9]+$ ]] || die "MAX_NUM_SEQS must be an integer"
[[ "${GRAPH}" =~ ^[0-9]+$ ]] || die "GRAPH must be an integer"
[[ "${#GLM52_INDEX_TOPK_PATTERN}" -eq 78 ]] || die "GLM52_INDEX_TOPK_PATTERN must be exactly 78 characters, got ${#GLM52_INDEX_TOPK_PATTERN}"

if [[ "${DCP_PREFILL_WORKSPACE}" == "auto" ]]; then
  case "${TP}:${DCP}" in
    4:4|6:2|6:3|6:6|8:2|8:4|8:8) DCP_PREFILL_WORKSPACE=1 ;;
    *) DCP_PREFILL_WORKSPACE=0 ;;
  esac
fi

DCP_PROJECT_MIN_PREFILL_TOKENS=1024
if ((GRAPH > DCP_PROJECT_MIN_PREFILL_TOKENS)); then
  DCP_PROJECT_MIN_PREFILL_TOKENS="${GRAPH}"
fi

if [[ -z "${ONLINE_QUANT}" ]]; then
  enabled_quant_aliases=0
  [[ "${ONLINE_MXFP8}" == "1" ]] && enabled_quant_aliases=$((enabled_quant_aliases + 1))
  [[ "${ONLINE_FP8}" == "1" ]] && enabled_quant_aliases=$((enabled_quant_aliases + 1))
  [[ "${ONLINE_FP8_MXFP4}" == "1" ]] && enabled_quant_aliases=$((enabled_quant_aliases + 1))
  if ((enabled_quant_aliases > 1)); then
    die "ONLINE_MXFP8, ONLINE_FP8, and ONLINE_FP8_MXFP4 are mutually exclusive"
  elif [[ "${ONLINE_MXFP8}" == "1" ]]; then
    ONLINE_QUANT=mxfp8
  elif [[ "${ONLINE_FP8}" == "1" || "${ONLINE_FP8_MXFP4}" == "1" ]]; then
    ONLINE_QUANT=fp8
  else
    ONLINE_QUANT=none
  fi
fi

case "${ONLINE_QUANT}" in
  none|0|off)
    ONLINE_QUANT=none
    ;;
  mxfp8)
    # Quantize every eligible linear by default. Precision-sensitive layers
    # can be retained explicitly through QUANTIZATION_CONFIG_JSON.
    if [[ -z "${QUANTIZATION_CONFIG_JSON}" ]]; then
      QUANTIZATION_CONFIG_JSON='{"linear":{"weight":"mxfp8"}}'
    fi
    ;;
  nf3-mxfp8)
    # Exact dense/shared-expert overlay used by the published hybrid
    # checkpoint: 390 attention linears, 152 shared-expert projections, and
    # four dense-MLP projections. Layer 0, indexers/routers, eh_proj, and
    # lm_head remain in their checkpoint dtype (546 MXFP8 modules total).
    if [[ -z "${QUANTIZATION_CONFIG_JSON}" ]]; then
      QUANTIZATION_CONFIG_JSON='{"linear":{"weight":"mxfp8"},"shared_experts":{"weight":"mxfp8"},"ignore":["re:^model\\.layers\\.0\\.","re:.*\\.self_attn\\.indexer\\.","re:.*\\.mlp\\.gate$","model.layers.78.eh_proj","lm_head"]}'
    fi
    ;;
  fp8|fp8_block|fp8-block|fp8-mxfp4)
    ONLINE_QUANT=fp8
    if [[ -z "${QUANTIZATION_CONFIG_JSON}" ]]; then
      QUANTIZATION_CONFIG_JSON='{"linear":{"weight":"fp8_per_block_static"},"ignore":["lm_head","model.layers.78.eh_proj","re:.*kv_b_proj","re:.*\\.mlp\\.gate$","re:.*\\.self_attn\\.indexer\\.weights_proj$","re:.*\\.self_attn\\.indexers_proj$"]}'
    fi
    ;;
  custom)
    [[ -n "${QUANTIZATION_CONFIG_JSON}" ]] || die "ONLINE_QUANT=custom requires QUANTIZATION_CONFIG_JSON"
    ;;
  *)
    die "ONLINE_QUANT must be none, mxfp8, nf3-mxfp8, fp8, or custom"
    ;;
esac

unset NCCL_GRAPH_FILE NCCL_GRAPH_DUMP_FILE VLLM_B12X_MLA_EXTEND_MAX_CHUNKS

export CUDA_VISIBLE_DEVICES="${GPUS}"
export CUDA_DEVICE_ORDER=PCI_BUS_ID
export CUDA_DEVICE_MAX_CONNECTIONS=32
export CUTE_DSL_ARCH=sm_120a
export TORCH_CUDA_ARCH_LIST=12.0a
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-16}"
export PYTORCH_CUDA_ALLOC_CONF
export VLLM_WORKER_MULTIPROC_METHOD=spawn
export SAFETENSORS_FAST_GPU=1
export INSTANTTENSOR_BACKEND="${INSTANTTENSOR_BACKEND}"
export VLLM_USE_AOT_COMPILE=1
export VLLM_USE_BREAKABLE_CUDAGRAPH=0
export VLLM_USE_MEGA_AOT_ARTIFACT=1
export VLLM_MEMORY_PROFILE_INCLUDE_ATTN=1
export VLLM_MEMORY_PROFILER_ESTIMATE_CUDAGRAPHS=1
export VLLM_USE_FLASHINFER_SAMPLER=1
export VLLM_USE_B12X_WO_PROJECTION=1
export VLLM_USE_B12X_MHC=1
if [[ "${LINEAR_BACKEND}" == "auto" || "${LINEAR_BACKEND}" == "b12x" ]]; then
  export VLLM_USE_B12X_FP8_GEMM=1
else
  export VLLM_USE_B12X_FP8_GEMM=0
fi
if [[ "${MOE_BACKEND}" == "b12x" || "${MOE_BACKEND}" == "flashinfer_b12x" ]]; then
  export VLLM_USE_B12X_MOE=1
else
  export VLLM_USE_B12X_MOE=0
fi
export VLLM_USE_B12X_SPARSE_INDEXER=1
export VLLM_USE_B12X_DCP_A2A=1
export VLLM_DCP_A2A_MAX_TOKENS="${DCP_A2A_MAX_TOKENS}"
export VLLM_DCP_A2A_LARGE_BACKEND="${DCP_A2A_LARGE_BACKEND}"
export VLLM_DCP_PROJECT_BEFORE_MERGE="${DCP_PREFILL_WORKSPACE}"
export VLLM_DCP_PROJECT_BEFORE_MERGE_MIN_PREFILL_TOKENS="${DCP_PROJECT_MIN_PREFILL_TOKENS}"
export VLLM_B12X_MLA_DCP_GATHER_IN_WORKSPACE="${DCP_PREFILL_WORKSPACE}"
export VLLM_USE_V2_MODEL_RUNNER=1
export VLLM_ENABLE_PCIE_ALLREDUCE=1
export VLLM_PCIE_ALLREDUCE_BACKEND=b12x
export VLLM_PCIE_ONESHOT_ALLREDUCE_MAX_SIZE="${VLLM_PCIE_ONESHOT_ALLREDUCE_MAX_SIZE:-64KB}"
export VLLM_PCIE_ONESHOT_FUSED_ADD_RMS_NORM_MAX_SIZE="${VLLM_PCIE_ONESHOT_FUSED_ADD_RMS_NORM_MAX_SIZE:-84KB}"
export VLLM_USE_B12X_PCIE_DMA="${B12X_PCIE_DMA}"
export VLLM_PCIE_DMA_FP8="${F8_DMA}"
export B12X_PCIE_DMA_FP8="${F8_DMA}"
export VLLM_DCP_GLOBAL_TOPK=1
export VLLM_DCP_SHARD_DRAFT=1
export VLLM_NF3_GRID188_DECODE="${NF3_GRID188}"
export B12X_MLA_SM120_UNIFIED=1
export B12X_DENSE_SPLITK_TURBO=1
export B12X_W4A16_TC_DECODE=1
export B12X_W4A8_TINY_DECODE=1
export B12X_MOE_FORCE_A8="${B12X_MOE_FORCE_A8}"
export B12X_MOE_FORCE_A16="${B12X_MOE_FORCE_A16}"
export NCCL_PROTO=LL,LL128,Simple
export NCCL_P2P_LEVEL=SYS
export NCCL_IB_DISABLE=1
export LD_PRELOAD=/opt/libnccl-local-inference.so.2.30.4
export VLLM_NCCL_SO_PATH=/opt/libnccl-local-inference.so.2.30.4
export TMPDIR="${TMPDIR:-/container-tmp}"
export XDG_CACHE_HOME="${XDG_CACHE_HOME:-/cache}"
export VLLM_CACHE_ROOT="${VLLM_CACHE_ROOT:-${VLLM_CACHE_DIR:-${XDG_CACHE_HOME}/vllm}}"
export VLLM_CACHE_DIR="${VLLM_CACHE_DIR:-${VLLM_CACHE_ROOT}}"
export TILELANG_CACHE_DIR="${TILELANG_CACHE_DIR:-${XDG_CACHE_HOME}/tilelang}"
export TILELANG_TMP_DIR="${TILELANG_TMP_DIR:-${TILELANG_CACHE_DIR}/tmp}"
export TVM_CACHE_DIR="${TVM_CACHE_DIR:-${XDG_CACHE_HOME}/tvm}"
export TVM_FFI_CACHE_DIR="${TVM_FFI_CACHE_DIR:-${XDG_CACHE_HOME}/tvm-ffi}"
export TRITON_CACHE_DIR="${TRITON_CACHE_DIR:-${XDG_CACHE_HOME}/triton}"
export TORCHINDUCTOR_CACHE_DIR="${TORCHINDUCTOR_CACHE_DIR:-${XDG_CACHE_HOME}/torchinductor}"
export TORCH_EXTENSIONS_DIR="${TORCH_EXTENSIONS_DIR:-${XDG_CACHE_HOME}/torch_extensions}"
export FLASHINFER_WORKSPACE_BASE="${FLASHINFER_WORKSPACE_BASE:-${XDG_CACHE_HOME}/flashinfer}"
export VLLM_FLASHINFER_AUTOTUNE_CACHE_DIR="${VLLM_FLASHINFER_AUTOTUNE_CACHE_DIR:-${XDG_CACHE_HOME}/flashinfer-autotune}"
export CUTE_DSL_CACHE_DIR="${CUTE_DSL_CACHE_DIR:-${XDG_CACHE_HOME}/cute-dsl}"
export B12X_CUTE_COMPILE_CACHE_DIR="${B12X_CUTE_COMPILE_CACHE_DIR:-${XDG_CACHE_HOME}/b12x-cute}"
export DG_JIT_CACHE_DIR="${DG_JIT_CACHE_DIR:-${XDG_CACHE_HOME}/deep-gemm}"
export MM_SPARSE_ATTN_AOT_CACHE="${MM_SPARSE_ATTN_AOT_CACHE:-${XDG_CACHE_HOME}/minfer/mm_sparse_attn}"
export MINFER_FMHA_CACHE_DIR="${MINFER_FMHA_CACHE_DIR:-${XDG_CACHE_HOME}/minfer/fmha_sm100}"
export CUDA_CACHE_PATH="${CUDA_CACHE_PATH:-${XDG_CACHE_HOME}/cuda}"
export CUPY_CACHE_DIR="${CUPY_CACHE_DIR:-${XDG_CACHE_HOME}/cupy}"
export NUMBA_CACHE_DIR="${NUMBA_CACHE_DIR:-${XDG_CACHE_HOME}/numba}"

mkdir -p \
  "${TMPDIR}" \
  "${VLLM_CACHE_DIR}" \
  "${TILELANG_CACHE_DIR}" \
  "${TILELANG_TMP_DIR}" \
  "${TVM_CACHE_DIR}" \
  "${TVM_FFI_CACHE_DIR}" \
  "${TRITON_CACHE_DIR}" \
  "${TORCHINDUCTOR_CACHE_DIR}" \
  "${TORCH_EXTENSIONS_DIR}" \
  "${FLASHINFER_WORKSPACE_BASE}" \
  "${VLLM_FLASHINFER_AUTOTUNE_CACHE_DIR}" \
  "${CUTE_DSL_CACHE_DIR}" \
  "${B12X_CUTE_COMPILE_CACHE_DIR}" \
  "${DG_JIT_CACHE_DIR}" \
  "${MM_SPARSE_ATTN_AOT_CACHE}" \
  "${MINFER_FMHA_CACHE_DIR}" \
  "${CUDA_CACHE_PATH}" \
  "${CUPY_CACHE_DIR}" \
  "${NUMBA_CACHE_DIR}"

spec_arg=()
if [[ "${MTP}" != "0" ]]; then
  spec_json="$(printf '{"model":"%s","method":"mtp","num_speculative_tokens":%s,"moe_backend":"%s","draft_sample_method":"probabilistic"}' "${MODEL}" "${MTP}" "${MOE_BACKEND}")"
  spec_arg=(--speculative-config "${spec_json}")
fi

revision_args=()
if [[ -n "${MODEL_REVISION}" && "${MODEL}" != /* ]]; then
  revision_args=(--revision "${MODEL_REVISION}")
fi

linear_args=()
if [[ "${LINEAR_BACKEND}" != "auto" ]]; then
  linear_args=(--linear-backend "${LINEAR_BACKEND}")
fi

quant_args=()
if [[ -n "${QUANTIZATION}" && "${QUANTIZATION}" != "auto" && "${QUANTIZATION}" != "none" ]]; then
  quant_args+=(--quantization "${QUANTIZATION}")
fi
if [[ "${ONLINE_QUANT}" != "none" ]]; then
  quant_args+=(--quantization-config "${QUANTIZATION_CONFIG_JSON}")
fi

dcp_args=(--decode-context-parallel-size "${DCP}")
if [[ "${DCP}" != "1" ]]; then
  dcp_args+=(--dcp-comm-backend "${DCP_BACKEND}" --dcp-kv-cache-interleave-size 1)
fi

hf_overrides="$(printf '{"use_index_cache":true,"index_topk_pattern":"%s"}' "${GLM52_INDEX_TOPK_PATTERN}")"

cmd=(vllm serve "${MODEL}" \
  "${revision_args[@]}" \
  --served-model-name "${SERVED_MODEL_NAME}" \
  --host 0.0.0.0 \
  --port "${PORT}" \
  --trust-remote-code \
  --tensor-parallel-size "${TP}" \
  "${dcp_args[@]}" \
  --kv-cache-dtype "${KV_CACHE_DTYPE}" \
  --attention-backend B12X_MLA_SPARSE \
  --moe-backend "${MOE_BACKEND}" \
  "${linear_args[@]}" \
  "${quant_args[@]}" \
  --load-format "${LOAD_FORMAT}" \
  -cc.pass_config.fuse_allreduce_rms=True \
  --gpu-memory-utilization "${GPU_MEMORY_UTILIZATION}" \
  --max-model-len "${MAX_MODEL_LEN}" \
  --max-num-seqs "${MAX_NUM_SEQS}" \
  --max-num-batched-tokens "${MAX_BATCHED_TOKENS}" \
  --max-cudagraph-capture-size "${GRAPH}" \
  --async-scheduling \
  --enable-chunked-prefill \
  --enable-prefix-caching \
  --enable-flashinfer-autotune \
  --enable-auto-tool-choice \
  --tool-call-parser glm47 \
  --reasoning-parser glm45 \
  --default-chat-template-kwargs '{"reasoning_effort":"high"}' \
  --enable-prompt-tokens-details \
  --enable-force-include-usage \
  --enable-request-id-headers \
  --hf-overrides "${hf_overrides}" \
  "${spec_arg[@]}")

# Keep the preset reproducible while allowing explicit vLLM diagnostics and
# newly added upstream flags without requiring a second copy of this launcher.
cmd+=("$@")

if [[ "${DRY_RUN:-0}" == "1" ]]; then
  printf 'CUDA_VISIBLE_DEVICES=%q\n' "${CUDA_VISIBLE_DEVICES}"
  printf 'B12X_MOE_FORCE_A8=%q\n' "${B12X_MOE_FORCE_A8}"
  printf 'B12X_MOE_FORCE_A16=%q\n' "${B12X_MOE_FORCE_A16}"
  printf 'VLLM_USE_B12X_PCIE_DMA=%q\n' "${VLLM_USE_B12X_PCIE_DMA}"
  printf 'VLLM_DCP_PROJECT_BEFORE_MERGE=%q\n' "${VLLM_DCP_PROJECT_BEFORE_MERGE}"
  printf 'VLLM_DCP_PROJECT_BEFORE_MERGE_MIN_PREFILL_TOKENS=%q\n' "${VLLM_DCP_PROJECT_BEFORE_MERGE_MIN_PREFILL_TOKENS}"
  printf 'VLLM_B12X_MLA_DCP_GATHER_IN_WORKSPACE=%q\n' "${VLLM_B12X_MLA_DCP_GATHER_IN_WORKSPACE}"
  printf 'INSTANTTENSOR_BACKEND=%q\n' "${INSTANTTENSOR_BACKEND}"
  printf 'PYTORCH_CUDA_ALLOC_CONF=%q\n' "${PYTORCH_CUDA_ALLOC_CONF}"
  printf 'LOCAL_INFERENCE_CACHE_FINGERPRINT=%q\n' "${LOCAL_INFERENCE_CACHE_FINGERPRINT:-unset}"
  printf 'XDG_CACHE_HOME=%q\n' "${XDG_CACHE_HOME}"
  printf 'VLLM_CACHE_ROOT=%q\n' "${VLLM_CACHE_ROOT}"
  printf 'TRITON_CACHE_DIR=%q\n' "${TRITON_CACHE_DIR}"
  printf 'TORCHINDUCTOR_CACHE_DIR=%q\n' "${TORCHINDUCTOR_CACHE_DIR}"
  printf 'B12X_CUTE_COMPILE_CACHE_DIR=%q\n' "${B12X_CUTE_COMPILE_CACHE_DIR}"
  printf 'KV_CACHE_DTYPE=%q\n' "${KV_CACHE_DTYPE}"
  printf 'QUANTIZATION=%q\n' "${QUANTIZATION}"
  printf 'ONLINE_QUANT=%q\n' "${ONLINE_QUANT}"
  printf 'QUANTIZATION_CONFIG_JSON=%q\n' "${QUANTIZATION_CONFIG_JSON}"
  printf 'VLLM_NF3_GRID188_DECODE=%q\n' "${VLLM_NF3_GRID188_DECODE}"
  printf 'Command:'
  printf ' %q' "${cmd[@]}"
  printf '\n'
  exit 0
fi

exec "${cmd[@]}"
