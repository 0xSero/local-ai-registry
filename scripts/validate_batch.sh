#!/usr/bin/env bash
# Validate several candidate recipes on RunPod, one pod each, and summarize.
#   scripts/validate_batch.sh <recipe-id>...            sequential
#   PARALLEL=3 scripts/validate_batch.sh <recipe-id>... up to 3 pods at once
# Logs land in runs/<recipe-id>.log next to the registry checkout. A failed
# recipe stays a candidate; the batch continues.
set -uo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
RUNS=${RUNS_DIR:-$ROOT/../runs}
mkdir -p "$RUNS"
[[ $# -gt 0 ]] || { echo "usage: $0 <recipe-id>..." >&2; exit 2; }

one() {
  local id=$1 log="$RUNS/$1.log" rc
  printf '%s start %s\n' "$(date -u +%H:%M:%S)" "$id" >&2
  python3 "$ROOT/scripts/validate_rented.py" "$id" --provider "${PROVIDER:-vast}" --recommend >>"$log" 2>&1; rc=$?
  if (( rc == 0 )); then printf '%s PROMOTED %s\n' "$(date -u +%H:%M:%S)" "$id"
  else printf '%s FAILED %s (rc=%s): %s\n' "$(date -u +%H:%M:%S)" "$id" "$rc" "$(grep -E 'acceptance FAILED|failed|giving up|did not|EXITED|TERMINATED' "$log" | tail -1)"; fi
}
export -f one; export ROOT RUNS

if [[ ${PARALLEL:-1} -gt 1 ]]; then
  printf '%s\n' "$@" | xargs -P "$PARALLEL" -I{} bash -c 'one "$@"' _ {}
else
  for id in "$@"; do one "$id"; done
fi | tee -a "$RUNS/batch-summary.log"
