#!/bin/bash
# deepmem.sh <tokens>: one cold deep prefill alone; sample MemAvailable on all nodes every 5 s; kill client below 2.5 GB.
N=${1:-420000}; D=~/dsv41-tune/runs/$(date +%Y%m%dT%H%M%S)-deepmem-$N; mkdir -p $D; echo $D > ~/dsv41-tune/runs/deepmem-latest
python3 ~/bench-dsv41-4xspark-20260919/sdeep.py $N 4242 > $D/deep.txt 2>&1 & P=$!
while kill -0 $P 2>/dev/null; do
  l="$(date +%T)"
  for h in local sero@100.83.190.2 valentine@10.10.10.14 valentine@10.10.10.13; do
    if [ $h = local ]; then a=$(awk "/MemAvailable/{print int(\$2/1024)}" /proc/meminfo); else a=$(ssh -o BatchMode=yes -o ConnectTimeout=5 $h "awk \"/MemAvailable/{print int(\\\$2/1024)}\" /proc/meminfo"); fi
    l="$l ${h#*@}=$a"; if [ -n "$a" ] && [ "$a" -lt 2500 ]; then echo "LOW $h $a -> kill" >> $D/mem.log; kill $P; fi
  done; echo "$l" >> $D/mem.log; sleep 5
done
cat $D/deep.txt; echo "=== DEEPMEM END"
