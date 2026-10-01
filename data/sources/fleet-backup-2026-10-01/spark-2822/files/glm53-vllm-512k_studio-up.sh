#!/usr/bin/env bash
set -euo pipefail

nodes=("<user>@<fabric-ip>" "<user>@<fabric-ip>" "<user>@<fabric-ip>")
for node in "${nodes[@]}"; do
  ssh -o BatchMode=yes -o ConnectTimeout=8 "$node" 'docker rm -f vllm_glm53_512k glm53-flash-spark-tp4-rank0 glm53-flash-spark-tp4-rank1 glm53-flash-spark-tp4-rank2 glm53-flash-spark-tp4-rank3 >/dev/null 2>&1 || true'
done
docker rm -f vllm_glm53_512k glm53-flash-spark-tp4-rank0 glm53-memory-flusher >/dev/null 2>&1 || true

for node in "${nodes[@]}"; do ssh "$node" '$HOME/glm53-vllm-512k/memory-flusher.sh'; done
"$HOME/glm53-vllm-512k/memory-flusher.sh"

ssh <user>@<fabric-ip> '$HOME/glm53-vllm-512k/launch-rank.sh 3'
sleep 10
ssh <user>@<fabric-ip> '$HOME/glm53-vllm-512k/launch-rank.sh 2'
sleep 10
ssh <user>@<fabric-ip> '$HOME/glm53-vllm-512k/launch-rank.sh 1'
sleep 10
"$HOME/glm53-vllm-512k/launch-rank.sh" 0
