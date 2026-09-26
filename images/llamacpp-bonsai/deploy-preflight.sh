#!/bin/sh
# Deploy entrypoint. Canonical interface (Main-approved): env OMP_SSH_FIRST + /opt/omp-acquire.
#  OMP_SSH_FIRST=1 : exec "$@" immediately (the runner's CONTAINER_STARTUP sshd bootstrap) so
#                    diagnostic SSH is reachable WITHOUT waiting on any model fetch.
#  unset (default) : blocking pinned acquisition (/opt/omp-acquire, fail-closed) THEN exec serve.
set -e
if [ "${OMP_SSH_FIRST:-0}" = "1" ]; then
  [ "$#" -ge 1 ] || { echo "[deploy-preflight] OMP_SSH_FIRST=1 requires a command (\$@ is empty)" >&2; exit 2; }
  echo "[deploy-preflight] OMP_SSH_FIRST=1: exec bootstrap now; run /opt/omp-acquire over SSH before serving"
  exec "$@"
fi
/opt/omp-acquire
exec /opt/llama/entrypoint.sh "$@"
