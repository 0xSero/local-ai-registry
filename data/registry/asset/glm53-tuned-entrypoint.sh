#!/bin/bash
# NCCL allreduce patch (GLM-5.2 winner) + optional extra sed hooks via WRAP_SED (;; separated sed exprs applied to v16)
set -e
D=/tmp/glm52-candidate; mkdir -p $D
cp /usr/local/bin/serve-glm52-v19.sh /usr/local/bin/serve-glm52-v16.sh /usr/local/bin/glm52-pcie-runtime-env.sh /usr/local/bin/glm52-dcp-prefill-policy.sh /usr/local/bin/glm52-pcie-calibration.py $D/
sed -i "s|exec /usr/local/bin/serve-glm52-v16.sh|exec $D/serve-glm52-v16.sh|" $D/serve-glm52-v19.sh
sed -i "s|/usr/local/bin/glm52-pcie-runtime-env.sh|$D/glm52-pcie-runtime-env.sh|g" $D/serve-glm52-v19.sh $D/serve-glm52-v16.sh
if [ "${PCIE_ALLREDUCE:-nccl}" = nccl ]; then sed -i "s/export VLLM_ENABLE_PCIE_ALLREDUCE=1/export VLLM_ENABLE_PCIE_ALLREDUCE=0/" $D/glm52-pcie-runtime-env.sh; fi
if [ -n "${WRAP_SED:-}" ]; then IFS=';;' read -ra EX <<< "$WRAP_SED"; for e in "${EX[@]}"; do [ -n "$e" ] && sed -i "$e" $D/serve-glm52-v16.sh; done; fi
echo "[glm-wrap] effective pcie env:"; grep -n "PCIE_ALLREDUCE" $D/glm52-pcie-runtime-env.sh | head -5
export GLM52_SERVER=$D/serve-glm52-v19.sh
exec /usr/local/bin/serve-gilded-gnosis.sh "$@"
