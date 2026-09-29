#!/usr/bin/env bash
# Stress-test both RTX 3060 12GB cards on zver, then restore qwen-coder.
# Output goes to ~/bench-results/dual3060-tests/. Render images with render_dual.py afterwards.
set -u
T=$(cd "$(dirname "$0")" && pwd); O=~/bench-results/dual3060-tests; mkdir -p "$O"; cd "$O"
export CUDA_DEVICE_ORDER=PCI_BUS_ID
Q="index,name,pci.bus_id,memory.total,memory.used,temperature.gpu,fan.speed,power.draw,power.limit,clocks.sm,clocks.mem,utilization.gpu,pcie.link.gen.current,pcie.link.width.current"

zver-ai unload >/dev/null; sleep 5
date '+%Y-%m-%d %H:%M:%S %Z' > started.txt
nvidia-smi > smi_idle.txt
nvidia-smi --query-gpu=index,name,pci.bus_id,vbios_version,driver_version,memory.total,pci.sub_device_id,pcie.link.gen.max,pcie.link.width.max,power.limit --format=csv > identity.csv

# VRAM tests: memtest_vulkan lists 1 = bus 65 (EVGA, display), 2 = bus 17 (ASUS). It reads the choice from a terminal, so use script(1) for a pty.
for dev in 1 2; do
  (sleep 1; printf '%s\n' "$dev"; sleep 420) | timeout 400 script -qfec "$T/memtest_vulkan" /dev/null 2>&1 \
    | sed 's/\x1b\[[0-9;?]*[A-Za-z]//g' | tr '\r' '\n' > "memtest_dev$dev.txt"
done

# Both cards at full load for 10 minutes, sampling both every 2 s.
( while true; do nvidia-smi --query-gpu=timestamp,$Q --format=csv,noheader,nounits >> burn_samples.csv; sleep 2; done ) &
SAMPLER=$!
(cd "$T/gpu-burn" && ./gpu_burn -m 90% 600) > burn.txt 2>&1
kill $SAMPLER
nvidia-smi > smi_after.txt
date '+%Y-%m-%d %H:%M:%S %Z' > finished.txt

zver-ai coder > reload.txt 2>&1
echo DONE
