#!/usr/bin/env bash
# Safe 4x Spark GLM-5.3-Flash NVFP4 (TP4/EP4, 128K, online FP8).
# DFLASH spec with incoai/GLM-5.3-Flash-DFlash2. Thinking on, CUDA graphs on.
# 128K is the validated admission ceiling; larger requests must fail closed.
# Do not set NUM_CONTINUOUS_DECODE_STEPS.
# Start ranks 3→2→1→0.
set -euo pipefail
BUNDLE=${HOME}/glm-5.3-flash-sglang-sm121
killall() { ssh -o BatchMode=yes -o ConnectTimeout=8 "$1" "docker rm -f glm53-flash-spark-tp4-rank0 glm53-flash-spark-tp4-rank1 glm53-flash-spark-tp4-rank2 glm53-flash-spark-tp4-rank3 glm53-flash-spark-tp2-rank0 glm53-flash-spark-tp2-rank1 >/dev/null 2>&1 || true"; }
docker rm -f glm53-flash-spark-tp4-rank0 glm53-flash-spark-tp2-rank0 >/dev/null 2>&1 || true
killall <user>@<fabric-ip>
killall <user>@<fabric-ip>
killall <user>@<fabric-ip>
sleep 2
ssh -o BatchMode=yes -o ConnectTimeout=8 <user>@<fabric-ip> "cd ${HOME}/glm-5.3-flash-sglang-sm121 && docker compose --env-file profiles/tp4.rank3.env up -d"
sleep 12
ssh -o BatchMode=yes -o ConnectTimeout=8 <user>@<fabric-ip> "cd ${HOME}/glm-5.3-flash-sglang-sm121 && docker compose --env-file profiles/tp4.rank2.env up -d"
sleep 12
ssh -o BatchMode=yes -o ConnectTimeout=8 <user>@<fabric-ip> "cd ${HOME}/glm-5.3-flash-sglang-sm121 && docker compose --env-file profiles/tp4.rank1.env up -d"
sleep 12
cd "$BUNDLE" && docker compose --env-file profiles/tp4.env up -d
echo "tp4 launched; API http://127.0.0.1:8000"
