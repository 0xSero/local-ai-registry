#!/usr/bin/env bash
# Start llama-server with the given flags, benchmark it with zbench, stop it.
# usage: run_llama.sh "<label>" <ctx> <gguf> [extra llama-server flags...]
# NGL_FLAG=" " to drop -ngl 99 and let llama.cpp --fit place layers/experts automatically
set -u
LABEL=$1 CTX=$2 GGUF=$3; shift 3
BIN=${LLAMA_BIN:-$HOME/src/llama.cpp/build/bin/llama-server}
LOG=$(dirname "$0")/logs/$(date +%H%M%S)-server.log; mkdir -p "$(dirname "$LOG")"
export CUDA_DEVICE_ORDER=PCI_BUS_ID   # since 2026-09-29: CUDA0 = ASUS 3060 12GB (bus 17), CUDA1 = EVGA 3060 12GB (bus 65, display). Before: CUDA1 was the 3060 Ti 8GB
"$BIN" -m "$GGUF" -c "$CTX" --host 127.0.0.1 --port 8090 ${NGL_FLAG:--ngl 99} -fa on -np 1 --jinja \
  --alias bench "$@" >"$LOG" 2>&1 &
PID=$!
trap 'kill $PID 2>/dev/null; wait $PID 2>/dev/null' EXIT
for _ in $(seq 240); do
  curl -sf http://127.0.0.1:8090/health >/dev/null && break
  kill -0 $PID 2>/dev/null || { echo "server died:"; grep -E ' E |error|failed' "$LOG" | tail -5; exit 1; }
  sleep 1
done
nvidia-smi --query-gpu=index,memory.used --format=csv,noheader | tr '\n' ' '; echo
python3 "$(dirname "$0")/zbench.py" --url http://127.0.0.1:8090/v1 --model bench --ctx "$CTX" --label "$LABEL" | tail -15
grep -E 'draft acceptance|accept' "$LOG" | tail -1
