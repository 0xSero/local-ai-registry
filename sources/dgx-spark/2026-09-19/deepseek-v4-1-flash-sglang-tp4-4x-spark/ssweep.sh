#!/bin/bash
# LIL protocol (llm-inference-bench v0.6.2 @ ccd9ad8) against MiaAI DS4.1 TP4 on 4x DGX Spark, head API
cd ~/bench-dsv41-4xspark-20260919 || exit 1
echo "sha256 $(sha256sum llm_decode_bench.py | cut -c1-64)"
KEYF=~/NewModels/DS4.1/state-tp4/api-key; KEYARG=(); [ -s $KEYF ] && KEYARG=(--api-key "$(cat $KEYF)")
COMMON=(--host http://10.10.10.12:8888 "${KEYARG[@]}" --model deepseek-v4.1-flash --display-mode plain --no-hw-monitor --no-resume
        --respect-eos --temperature 1 --token-targeting exact --max-tokens 8192 --decode-warmup-seconds 15 --kv-budget 8000000)
echo "=== STRESS $(date +%T)"; python3 sstress.py | tee stress.json
echo "=== DEEP $(date +%T)"; python3 sdeep.py 500000 777 | tee deep.txt
echo "=== PREFILL $(date +%T)"
python3 llm_decode_bench.py "${COMMON[@]}" --prefill-only --prefill-contexts 8k,32k,64k,128k --prefill-duration 30 --prefill-metric client --output prefill.json
for i in 1 2 3; do
  echo "=== DECODE $i $(date +%T)"
  python3 llm_decode_bench.py "${COMMON[@]}" --skip-prefill --concurrency 1,2,4,8 --contexts 0,32k --duration 30 --output decode-$i.json
done
echo "=== DONE $(date +%T)"
