#!/bin/bash
# memguard.sh: during a bench, kill quickbench/LIL if any node MemAvailable < 2.5 GB. Logs min seen.
LOG=~/dsv41-tune/runs/memguard.log; echo "=== $(date +%T) memguard start" >> $LOG
while pgrep -f "quickbench.sh|llm_decode_bench|realbench.py|dsstress.py" >/dev/null || [ "${1:-}" = wait ]; do
  set -- ; m=""
  for h in local sero@100.83.190.2 valentine@10.10.10.14 valentine@10.10.10.13; do
    if [ $h = local ]; then a=$(awk "/MemAvailable/{print int(\$2/1024)}" /proc/meminfo); else a=$(ssh -o BatchMode=yes -o ConnectTimeout=5 $h "awk \"/MemAvailable/{print int(\\\$2/1024)}\" /proc/meminfo"); fi
    m="$m $h=$a"
    if [ -n "$a" ] && [ "$a" -lt 2500 ]; then echo "$(date +%T) LOW $h ${a}MB -> killing bench" >> $LOG; pkill -f llm_decode_bench; pkill -f realbench.py; pkill -f quickbench.sh; pkill -f dsstress.py; fi
  done
  echo "$(date +%T)$m" >> $LOG; sleep 10
done
echo "=== $(date +%T) memguard end" >> $LOG
