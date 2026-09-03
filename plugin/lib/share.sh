#!/usr/bin/env bash
# Tailscale share and the gateway key. Sourced; do not run.
#
# The key exists from the first Start: agents launched from the panel always send it, the gateway
# always checks it, and sharing adds nothing but the tailnet route. `share --key <value>` replaces
# it in place; the gateway reads the file on every request, so no restart.

KEY_FILE="$STATE/gateway.key"
# the tailnet route is a port of its own, never a path on someone else's 443: the plugin claims
# 8443 (Tailscale's other default-allowed serve port) and leaves every existing config untouched
SHARE_PORT=8443
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
  [[ -n $dns && $active == true ]] && url="https://$dns:$SHARE_PORT"
  jq -nc --argjson a "$active" --arg u "$url" --arg k "$(cat "$KEY_FILE" 2>/dev/null)" '{available:true,active:$a,url:$u,key:$k}'
}
# share_state is two tailscale CLI calls, and snapshot_write runs several times a minute; the
# status cannot change faster than a human notices. A five-second TTL keeps the hot path off the
# tailscaled socket. share_toggle reads fresh state and drops the cache after every toggle.
SHARE_CACHE="$STATE/share.cache"
share_state_cached() {
  local now t=0 c; now=$(date +%s)
  if [[ -f $SHARE_CACHE ]]; then
    t=$(jq -r '.cachedAt // 0' "$SHARE_CACHE" 2>/dev/null || printf 0)
    if (( now - t < 5 )); then jq -c 'del(.cachedAt)' "$SHARE_CACHE"; return; fi
  fi
  c=$(share_state)
  jq -nc --argjson c "$c" --arg t "$now" '$c + {cachedAt:($t|tonumber)}' >"$SHARE_CACHE.tmp.$$" && mv "$SHARE_CACHE.tmp.$$" "$SHARE_CACHE"
  printf '%s' "$c"
}
share_on() { ensure_key; "$(ts_bin)" serve --bg "--https=$SHARE_PORT" "http://127.0.0.1:$PORT" >/dev/null; }
share_off() { local b; b=$(ts_bin) || return 0; "$b" serve "--https=$SHARE_PORT" off >/dev/null 2>&1 || true; rm -f "$SHARE_CACHE"; } # only our port, never a full reset

share_toggle() { # share [--key value]
  if [[ ${1:-} == --key ]]; then set_key "${2:-}"; return; fi
  jq -e '.available' >/dev/null <<<"$(share_state)" || { refuse "tailscale is not installed"; exit 1; }
  [[ $(jq -r .state "$SNAPSHOT" 2>/dev/null) == ready ]] || { refuse "load a model first"; exit 1; }
  # an op, so the panel shows the toggle in progress instead of a dead button
  op share "" "sharing on Tailscale" 0
  if jq -e '.active' >/dev/null <<<"$(share_state)"; then share_off; log "share off"
  else share_on 2>"$STATE/share.err" || { rm -f "$SHARE_CACHE"; op_done; refuse "$(awk 'NF{l=$0} END{print (l==""?"tailscale serve failed":l)}' "$STATE/share.err")"; exit 1; }; log "share on"; fi
  rm -f "$SHARE_CACHE"   # the toggle changed reality; the next snapshot must not serve the cache
  op_done
}
