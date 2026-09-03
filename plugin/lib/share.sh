#!/usr/bin/env bash
# Tailscale share and the gateway key. Sourced; do not run.
#
# The key exists from the first Start: agents launched from the panel always send it, the gateway
# always checks it, and sharing adds nothing but the tailnet route. `share --key <value>` replaces
# it in place; the gateway reads the file on every request, so no restart.

KEY_FILE="$STATE/gateway.key"
ts_bin() { command -v tailscale 2>/dev/null; }

ensure_key() {
  [[ -s $KEY_FILE ]] && return 0
  mkdir -p "$STATE"; (umask 077; head -c 24 /dev/urandom | base64 | tr -d '/+=\n' | cut -c1-32 >"$KEY_FILE")
  lwrite '.share.key=$k' --arg k "$(cat "$KEY_FILE")"
}
set_key() {
  [[ ${#1} -ge 16 ]] || { fail "key must be at least 16 characters"; return; }
  mkdir -p "$STATE"; (umask 077; printf '%s\n' "$1" >"$KEY_FILE"); lwrite '.share.key=$k' --arg k "$1"; snapshot_write
}

share_state() { # -> {available,active,url,key}; read from tailscale each time, never cached
  local b active=false dns="" url=""
  b=$(ts_bin) || { jq -nc --arg k "$(cat "$KEY_FILE" 2>/dev/null)" '{available:false,active:false,url:"",key:$k}'; return; }
  "$b" serve status 2>/dev/null | grep -q "127\.0\.0\.1:$PORT" && active=true
  dns=$("$b" status --json 2>/dev/null | jq -r '(.Self.DNSName//"")|rtrimstr(".")')
  [[ -n $dns ]] && url="https://$dns"
  jq -nc --argjson a "$active" --arg u "$url" --arg k "$(cat "$KEY_FILE" 2>/dev/null)" '{available:true,active:$a,url:$u,key:$k}'
}
share_on() { ensure_key; "$(ts_bin)" serve --bg "http://127.0.0.1:$PORT" >/dev/null; }
share_off() { local b; b=$(ts_bin) || return 0; "$b" serve --bg "http://127.0.0.1:$PORT" off >/dev/null 2>&1 || "$b" serve reset >/dev/null 2>&1 || true; }

share_toggle() { # share [--key value]
  if [[ ${1:-} == --key ]]; then set_key "${2:-}"; return; fi
  jq -e '.available' >/dev/null <<<"$(share_state)" || { fail "tailscale is not installed"; return; }
  [[ $(jq -r .state "$SNAPSHOT" 2>/dev/null) == ready ]] || { fail "load a model first"; return; }
  if jq -e '.active' >/dev/null <<<"$(share_state)"; then share_off; log "share off"
  else share_on 2>"$STATE/share.err" || { fail "$(awk 'NF{l=$0} END{print (l==""?"tailscale serve failed":l)}' "$STATE/share.err")"; return; }; log "share on"; fi
  snapshot_write
}
