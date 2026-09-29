#!/usr/bin/env bash
# Benchmark matrix for 2x RTX 3060 12GB (2026-09-29). Runs sequentially; a config that fails to load is logged and skipped.
cd "$(dirname "$0")"; export GGML_CUDA_ALLREDUCE=internal
Q=~/.lmstudio/models/unsloth/Qwen3.8-27B-GGUF; MOE=~/.lmstudio/models/unsloth/Qwen3.6-35B-A3B-MTP-GGUF/Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf
MTP="--spec-type draft-mtp --spec-draft-n-max 3"
run() { echo "=== $1"; ./run_llama.sh "$@" 2>&1 | grep -E '"gen_tps"|"prefill_tps"|"recall"|"tool_call"|"vram_gb"|died|acceptance' | tr '\n' ' '; echo; }
run "2x3060 · IQ4_XS · 64k · TENSOR 1:1 · q4_0 KV · MTP 3 (same as old best)" 65536 $Q/Qwen3.8-27B-UD-IQ4_XS.gguf -sm tensor -ts 1,1 -ctk q4_0 -ctv q4_0 $MTP
run "2x3060 · IQ4_XS · 128k · TENSOR 1:1 · q4_0 KV · MTP 3" 131072 $Q/Qwen3.8-27B-UD-IQ4_XS.gguf -sm tensor -ts 1,1 -ctk q4_0 -ctv q4_0 $MTP
run "2x3060 · Q4_K_XL · 64k · TENSOR 1:1 · q8_0 KV · MTP 3" 65536 $Q/Qwen3.8-27B-UD-Q4_K_XL.gguf -sm tensor -ts 1,1 -ctk q8_0 -ctv q8_0 $MTP
run "2x3060 · Q4_K_XL · 128k · TENSOR 1:1 · q4_0 KV · MTP 3" 131072 $Q/Qwen3.8-27B-UD-Q4_K_XL.gguf -sm tensor -ts 1,1 -ctk q4_0 -ctv q4_0 $MTP
run "2x3060 · Q5_K_S · 64k · TENSOR 1:1 · q4_0 KV · MTP 3" 65536 $Q/Qwen3.8-27B-UD-Q5_K_S.gguf -sm tensor -ts 1,1 -ctk q4_0 -ctv q4_0 $MTP
run "2x3060 · Q5_K_S · 96k · TENSOR 1:1 · q4_0 KV · MTP 3" 98304 $Q/Qwen3.8-27B-UD-Q5_K_S.gguf -sm tensor -ts 1,1 -ctk q4_0 -ctv q4_0 $MTP
run "2x3060 · IQ4_XS · 64k · layer 1:1 · q8_0 KV · MTP 3 (layer reference)" 65536 $Q/Qwen3.8-27B-UD-IQ4_XS.gguf -sm layer -ts 1,1 -ctk q8_0 -ctv q8_0 $MTP
run "2x3060 · Qwen3.6-35B-A3B MoE Q4_K_XL · 128k · layer 1:1 all-GPU · q8_0 KV · MTP 3" 131072 $MOE -sm layer -ts 1,1 -ctk q8_0 -ctv q8_0 $MTP
NGL_FLAG=" " run "2x3060 · Qwen3.6-35B-A3B MoE Q4_K_XL · 128k · auto-fit · q8_0 KV · MTP 3" 131072 $MOE -sm layer -ctk q8_0 -ctv q8_0 --load-mode none $MTP
echo MATRIX_DONE
