#!/bin/zsh
# Restart serve-24gb.sh with env overrides (QUANT, CTX, SPEC, DRAFT_N, DRAFT_KV, EXTRA) and wait until it listens or dies.
# The tuning runs used this script, one cold server for each config. usage: restart.sh LOGNAME
HERE=${0:A:h}
export LLAMA_SERVER=${LLAMA_SERVER:-$HERE/tools/llama-b11182/llama-server}
export LLAMA_CACHE=${LLAMA_CACHE:-$HERE/models}
pkill -f "llama-server .*--port ${PORT:-8080}" 2>/dev/null
while pgrep -f "llama-server .*--port ${PORT:-8080}" >/dev/null; do sleep 1; done
LOG=$HERE/server-${1:-run}.log
nohup "$HERE/serve-24gb.sh" ${=EXTRA:-} > "$LOG" 2>&1 &
PID=$!
until grep -q "listening on" "$LOG" 2>/dev/null; do
  kill -0 $PID 2>/dev/null || { echo "SERVER DIED"; tail -20 "$LOG"; exit 1; }
  sleep 1
done
echo "ready: $LOG (pid $PID)"
