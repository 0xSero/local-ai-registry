#!/usr/bin/env bash
# Paths, the ledger, the lock, and logging. Sourced by omarchy-local-ai; do not run.
#
# Everything the plugin persists lives in $STATE:
#   ledger.json    the only authoritative state: current op, last error, last accepted recipe, share key
#   snapshot.json  the derived read model the panel watches (rewritten, never edited)
#   log            every worker step, for "refusal out loud" beyond the one-line error
#   op.lock        flock target; the fd is closed in every child so a killed worker cannot orphan it
#   assets/        config files the recipe mounts, written from recipes.json at launch
#   agents/        per-agent launch config generated at open-agent time

HOME_DIR="${OMARCHY_AI_USER_HOME:-$HOME}"
STATE="${OMARCHY_AI_STATE:-${XDG_STATE_HOME:-$HOME_DIR/.local/state}/omarchy/local-ai}"
MODEL_ROOT="${OMARCHY_AI_MODEL_ROOT:-$HOME_DIR/.cache/omarchy/local-ai/models}"
CACHE_ROOT="${OMARCHY_AI_CACHE_ROOT:-$HOME_DIR/.cache/omarchy/local-ai/cache}"
HF_HOME_DIR="${OMARCHY_AI_HF_HOME:-$HOME_DIR/.cache/huggingface}"
PORT="${OMARCHY_AI_PORT:-12434}"
POLL="${OMARCHY_AI_POLL:-2}"
TIMEOUT="${OMARCHY_AI_TIMEOUT:-3600}"
LABEL=io.omarchy.local-ai
NET="${OMARCHY_AI_NETWORK:-omarchy-local-ai}"
CTR="${OMARCHY_AI_CONTAINER:-omarchy-local-ai}"     # engine: $CTR-engine, gateway: $CTR-gateway
LEDGER="$STATE/ledger.json"
SNAPSHOT="$STATE/snapshot.json"
LOGFILE="$STATE/log"
LEDGER_EMPTY='{"schemaVersion":"omarchy-local-ai/ledger/1","op":{"name":"","recipeId":"","pid":0,"startedAt":"","detail":"","percent":0},"error":"","accepted":{"recipeId":"","servedModel":"","registry":"","apis":[]},"share":{"key":""}}'

fail() { printf 'local-ai: %s\n' "$*" >&2; return 1; }
now() { date -u +%Y-%m-%dT%H:%M:%SZ; }
log() { mkdir -p "$STATE"; printf '%s %s\n' "$(now)" "$*" >>"$LOGFILE"; }
bin_of() { [[ -x $HOME_DIR/.local/bin/$1 ]] && printf '%s\n' "$HOME_DIR/.local/bin/$1" || command -v "$1"; }
canon() { # canonicalize, resolving symlinks even for not-yet-existing leaf paths
  local p=$1 rest=""
  if realpath -m -- / >/dev/null 2>&1; then realpath -m -- "$p"; return; fi
  while [[ -n $p && ! -e $p ]]; do rest="/$(basename "$p")$rest"; p=$(dirname "$p"); done
  printf '%s%s\n' "$(realpath -- "${p:-/}" 2>/dev/null || printf '%s' "$p")" "$rest"
}

# ---------------------------------------------------------------- ledger
lread() { [[ -f $LEDGER ]] && cat "$LEDGER" || printf '%s\n' "$LEDGER_EMPTY"; }
HAVE_FLOCK=0; command -v flock >/dev/null 2>&1 && HAVE_FLOCK=1   # Omarchy has util-linux; the mkdir path is for tests elsewhere
lwrite() { # lwrite <jq-filter> [jq-args...]: atomic read-modify-write under a short file lock
  local f=$1; shift; mkdir -p "$STATE"
  if ((HAVE_FLOCK)); then
    { flock 9; jq -c "$@" "$f" <<<"$(lread)" >"$LEDGER.tmp.$$" && mv "$LEDGER.tmp.$$" "$LEDGER"; } 9>"$STATE/ledger.lock"
  else
    until mkdir "$STATE/ledger.lockd" 2>/dev/null; do sleep 0.02; done
    jq -c "$@" "$f" <<<"$(lread)" >"$LEDGER.tmp.$$" && mv "$LEDGER.tmp.$$" "$LEDGER"
    rmdir "$STATE/ledger.lockd" 2>/dev/null || true
  fi
}
op() { lwrite '.op={name:$n,recipeId:$r,pid:($p|tonumber),startedAt:(if .op.startedAt=="" or .op.name!=$n then $t else .op.startedAt end),detail:$d,percent:($c|tonumber)} | .error=""' \
  --arg n "$1" --arg r "$2" --arg p "$$" --arg t "$(now)" --arg d "${3:-}" --arg c "${4:-0}"; log "op $1 ${3:-}"; snapshot_write; }
op_done() { lwrite '.op={name:"",recipeId:"",pid:0,startedAt:"",detail:"",percent:0}'; snapshot_write; }
oops() { log "error: $1"; lwrite '.error=$e | .op={name:"",recipeId:"",pid:0,startedAt:"",detail:"",percent:0}' --arg e "$1"; snapshot_write; exit 1; }

# ---------------------------------------------------------------- op lock
# The worker holds fd 8 for its whole life. Children inherit nothing: every
# spawn below closes 8, so a worker killed mid-download does not leave `hf`
# holding the lock (the old plugin's orphaned-lock bug).
guard() {
  mkdir -p "$STATE"
  if ((HAVE_FLOCK)); then
    exec 8>"$STATE/op.lock"
    flock -n 8 || { fail "another operation is running"; return 1; }
  else # a lock directory that dies with the worker: stale when its pid is gone
    local d="$STATE/op.lockd"
    if ! mkdir "$d" 2>/dev/null; then
      local holder; holder=$(cat "$d/pid" 2>/dev/null || echo 0)
      kill -0 "$holder" 2>/dev/null && { fail "another operation is running"; return 1; }
      rm -rf "$d"; mkdir "$d" || { fail "another operation is running"; return 1; }
    fi
    printf '%s' "$$" >"$d/pid"; trap 'rm -rf "'"$d"'"' EXIT
  fi
}
run_child() { "$@" 8>&- 9>&-; }          # foreground child without the lock fds
spawn_child() { "$@" 8>&- 9>&- & }       # background child without the lock fds

busy_pid() { # pid of a live worker, or empty
  local p; p=$(lread | jq -r '.op.pid'); [[ $p -gt 0 ]] && kill -0 "$p" 2>/dev/null && printf '%s' "$p"; return 0
}
