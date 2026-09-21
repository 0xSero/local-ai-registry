#!/bin/bash
# Registry sweep for row 11 (6M KV) (knapcio canary-roce, adaptive compact verify, 48 slots): LIL v0.6.2 @ ccd9ad8 + sparkDash protocol.
D=~/dsv41-tune/runs/$(date +%Y%m%dT%H%M%S)-sweep-row11; mkdir -p $D; echo $D > ~/dsv41-tune/runs/sweep-latest; cd ~/bench-dsv41-4xspark-20260919 || exit 1
exec > >(tee -a $D/sweep.log) 2>&1
echo "sha256 $(sha256sum llm_decode_bench.py | cut -c1-64)"
COMMON=(--host http://10.10.10.12:8888 --model deepseek-v4.1-flash --display-mode plain --no-hw-monitor --no-resume
        --respect-eos --temperature 1 --token-targeting exact --max-tokens 8192 --decode-warmup-seconds 15 --kv-budget ${KV_BUDGET:-6000000})
echo "=== PREFILL $(date +%T)"
python3 llm_decode_bench.py "${COMMON[@]}" --prefill-only --prefill-contexts 8k,32k,64k,128k --prefill-duration 30 --prefill-metric client --output $D/prefill.json
for i in 1 2 3; do
  echo "=== DECODE $i $(date +%T)"
  python3 llm_decode_bench.py "${COMMON[@]}" --skip-prefill --concurrency 1,2,4,8,16,32,48 --contexts 0,32k --duration 30 --output $D/decode-$i.json
done
echo "=== SPARKDASH $(date +%T)"; python3 ~/dsv41-tune/sdbench.py --conc 1,8 > $D/sparkdash.log 2>&1; grep -v "^{" $D/sparkdash.log
echo "=== SWEEP DONE $(date +%T)"
