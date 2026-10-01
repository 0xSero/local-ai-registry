#!/usr/bin/env bash
set -euo pipefail

/usr/bin/systemctl --user stop gemma4-vl.service || true
/usr/bin/docker rm -f local-studio-llm >/dev/null 2>&1 || true
exec /usr/bin/docker run --rm --name local-studio-llm --gpus all --network host --ipc host --shm-size 16g -v ${HOME}/.cache/huggingface:/cache/huggingface -e PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True -e TORCH_CUDA_ARCH_LIST=12.1a -e FLASHINFER_CUDA_ARCH_LIST=12.1a -e HF_HOME=/cache/huggingface -e HF_HUB_OFFLINE=1 -e HF_HUB_DISABLE_XET=1 -e FLASHINFER_DISABLE_VERSION_CHECK=1 ghcr.io/anemll/dspark-vllm-gx10:0.1.1 coolthor/gemma-4-12B-it-NVFP4A16 --served-model-name gemma-4-12b-it --host 0.0.0.0 --port 8891 --trust-remote-code --max-model-len 8192 --gpu-memory-utilization 0.078 --kv-cache-memory-bytes 1400M --max-num-seqs 1 --limit-mm-per-prompt '{"image":2}' --generation-config vllm
