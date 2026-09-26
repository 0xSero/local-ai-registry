#!/bin/sh
# /opt/omp-acquire — pinned GGUF acquisition by COMMIT + sha256 fail-closed. Idempotent.
# Progress -> stdout+stderr and /opt/logs/deploy-preflight.log. ANY failure -> nonzero + NO marker.
set -e
N="Ternary-Bonsai-2-27B"; D="/opt/models/$N"; REPO="prism-ml/Ternary-Bonsai-2-27B-gguf"; REV="6ed5e12bf84b7a63069882c91dd9e9218647d17b"; LOG="/opt/logs/deploy-preflight.log"
mkdir -p /opt/logs "$D"
log() { echo "[omp-acquire] $*"; echo "[omp-acquire] $*" >>"$LOG" 2>/dev/null || true; }
g() { f="$1"; s="$2"
  if [ -f "$D/$f" ] && echo "$s  $D/$f" | sha256sum -c - >/dev/null 2>&1; then log "$f present + sha ok"; return 0; fi
  rm -f "$D/$f"; log "fetch $f @ $REV"
  if ! curl -fL --max-time "${OMP_ACQUIRE_TIMEOUT:-1800}" "${HF_ENDPOINT:-https://huggingface.co}/$REPO/resolve/$REV/$f" -o "$D/$f" >>"$LOG" 2>&1; then log "curl $f FAILED"; return 3; fi
  if ! echo "$s  $D/$f" | sha256sum -c - >>"$LOG" 2>&1; then log "sha256 MISMATCH $f"; rm -f "$D/$f"; return 3; fi
}
if [ -f "$D/.omp-ready" ] && [ "$(cat "$D/.omp-ready" 2>/dev/null)" = "$REV" ]; then log "already at $REV"; exit 0; fi
rm -f "$D/.omp-ready"
g Ternary-Bonsai-2-27B-PTQ1_0.gguf 53107f530aa52eb00912263ab1ee29bd199261c87cd7b4ad4ca1318c1fe33ee3 || exit 3
g Ternary-Bonsai-2-27B-mmproj-Q8_0.gguf 6807ede61d570bb86ba34b756a0fa109edc33668604de867c6ea6d8f1d631903 || exit 3
printf '%s' "$REV" > "$D/.omp-ready"; log "acquired pinned revision $REV; marker written"; exit 0
