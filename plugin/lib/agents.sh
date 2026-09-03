#!/usr/bin/env bash
# Agents: launch-only. Sourced; do not run.
#
# The local model reaches an agent only when the agent is launched from the panel: the endpoint,
# key, and model travel in the launch command's environment and flags. Nothing on disk that the
# user owns is edited, so nothing has to be restored when the plugin stops. Agents whose API
# dialect failed acceptance are hidden; the rest are the agents Omarchy itself knows how to launch.

AGENTS=(pi omp opencode ori claude codex grok agy hermes copilot crush)
ENDPOINT="http://127.0.0.1:$PORT"

agent_dialect() { # which gateway dialect an agent speaks
  case $1 in
    claude) printf messages ;;
    codex) printf responses ;;
    *) printf chat ;;
  esac
}

agents_json() { # -> {"default":"pi","installed":["pi",...],"launchable":[...]} against the accepted dialects
  local a def="" installed='[]' launchable='[]' apis
  apis=$(lread | jq -c '.accepted.apis')
  for a in "${AGENTS[@]}"; do
    bin_of "$a" >/dev/null 2>&1 || continue
    installed=$(jq -c --arg a "$a" '.+[$a]' <<<"$installed")
    jq -e --arg d "$(agent_dialect "$a")" 'index($d)!=null' <<<"$apis" >/dev/null && launchable=$(jq -c --arg a "$a" '.+[$a]' <<<"$launchable")
  done
  command -v omarchy-default-agent >/dev/null 2>&1 && def=$(omarchy-default-agent 2>/dev/null || true)
  jq -nc --arg d "${def:-}" --argjson i "$installed" --argjson l "$launchable" '{default:$d,installed:$i,launchable:$l}'
}

# agent_command <name> <served-model> <key> -> prints the argv (NUL-separated) to run in a terminal.
# Each agent gets its own spelling of "use this endpoint"; the key doubles as the API key everywhere.
agent_command() {
  local name=$1 model=$2 key=$3 bin cfg
  bin=$(bin_of "$name") || { fail "$name is not installed"; return; }
  case $name in
    claude)
      printf '%s\0' env "ANTHROPIC_BASE_URL=$ENDPOINT" "ANTHROPIC_API_KEY=$key" "ANTHROPIC_MODEL=$model" \
        "ANTHROPIC_DEFAULT_SONNET_MODEL=$model" "ANTHROPIC_DEFAULT_OPUS_MODEL=$model" "ANTHROPIC_DEFAULT_HAIKU_MODEL=$model" \
        "$bin" --model "$model" ;;
    codex)
      printf '%s\0' env "LOCAL_AI_KEY=$key" "$bin" \
        -c "model_providers.local.name=Omarchy Local" -c "model_providers.local.base_url=$ENDPOINT/v1" \
        -c "model_providers.local.wire_api=responses" -c "model_providers.local.env_key=LOCAL_AI_KEY" \
        -c "model_provider=local" -c "model=$model" ;;
    opencode)
      cfg=$(jq -nc --arg u "$ENDPOINT/v1" --arg m "$model" --arg k "$key" \
        '{"$schema":"https://opencode.ai/config.json",provider:{"omarchy-local":{npm:"@ai-sdk/openai-compatible",name:"Omarchy Local",options:{baseURL:$u,apiKey:$k},models:{($m):{name:$m}}}}}')
      printf '%s\0' env "OPENCODE_CONFIG_CONTENT=$cfg" "$bin" --model "omarchy-local/$model" ;;
    pi|omp)
      # pi reads providers from its agent dir; a plugin-owned dir keeps the user's own untouched.
      # omp also wants a config.yml there, or it opens its first-run wizard.
      local dir="$STATE/agents/$name"; mkdir -p "$dir"
      jq -nc --arg u "$ENDPOINT/v1" --arg m "$model" --arg k "$key" \
        '{providers:{"omarchy-local":{baseUrl:$u,apiKey:$k,api:"openai-completions",models:[{id:$m,name:($m+" · local"),input:["text"],cost:{input:0,output:0,cacheRead:0,cacheWrite:0}}]}}}' \
        >"$dir/models.json"
      [[ $name == omp ]] && printf 'modelRoles:\n  default: omarchy-local/%s\nsetupVersion: 2\n' "$model" >"$dir/config.yml"
      printf '%s\0' env "PI_CODING_AGENT_DIR=$dir" "OMP_CODING_AGENT_DIR=$dir" "$bin" --provider omarchy-local --model "$model" ;;
    crush)
      # crush takes providers from XDG config only, not from OPENAI_BASE_URL, and its XDG data file pins the
      # last chosen model over the config: give it a plugin-owned config and data home
      local dir="$STATE/agents/crush/crush"; mkdir -p "$dir"
      # a mise shim would reinstall crush under the new data home: launch the real binary instead
      [[ $bin == */mise/shims/* ]] && command -v mise >/dev/null 2>&1 && bin=$(mise which crush 2>/dev/null || printf '%s' "$bin")
      jq -nc --arg u "$ENDPOINT/v1" --arg m "$model" --arg k "$key" \
        '{providers:{"omarchy-local":{type:"openai",name:"Omarchy Local",base_url:$u,api_key:$k,models:[{id:$m,name:$m,context_window:131072,default_max_tokens:8192}]}},models:{large:{provider:"omarchy-local",model:$m},small:{provider:"omarchy-local",model:$m}}}' \
        >"$dir/crush.json"
      printf '%s\0' env "XDG_CONFIG_HOME=$STATE/agents/crush" "XDG_DATA_HOME=$STATE/agents/crush" "OPENAI_API_KEY=$key" "$bin" ;;
    copilot)
      printf '%s\0' env "COPILOT_PROVIDER_BASE_URL=$ENDPOINT/v1" "COPILOT_PROVIDER_API_KEY=$key" "$bin" --model "$model" ;;
    grok)
      printf '%s\0' env "GROK_CLI_CHAT_PROXY_BASE_URL=$ENDPOINT/v1" "XAI_API_KEY=$key" "$bin" ;;
    *) # OpenAI-compatible by convention: hermes, ori, agy read the standard variables
      printf '%s\0' env "OPENAI_BASE_URL=$ENDPOINT/v1" "OPENAI_API_BASE=$ENDPOINT/v1" "OPENAI_API_KEY=$key" "OPENAI_MODEL=$model" "$bin" ;;
  esac
}

open_agent() { # open_agent [name]: default agent when omitted; refuses out loud when not ready
  local name=${1:-} snap model key
  snap=$(cat "$SNAPSHOT" 2>/dev/null || printf '{}')
  [[ $(jq -r '.state' <<<"$snap") == ready ]] || { fail "load a model first"; return; }
  [[ -n $name ]] || { name=$(jq -r '.agents.default // ""' <<<"$snap"); name=${name:-pi}; }
  jq -e --arg a "$name" '.agents.launchable|index($a)!=null' <<<"$snap" >/dev/null \
    || { fail "$name cannot use this model: its API dialect did not pass acceptance"; return; }
  model=$(jq -r '.model.servedName' <<<"$snap"); key=$(lread | jq -r '.share.key')
  local -a argv=(); while IFS= read -r -d '' v; do argv+=("$v"); done < <(agent_command "$name" "$model" "$key") || return 1
  log "open-agent $name"
  if [[ ${OMARCHY_AI_FOREGROUND:-0} == 1 ]]; then printf '%q ' "${argv[@]}"; echo; return 0; fi
  # the agent works where the person works: OMARCHY_AI_AGENT_DIR, else the directory recorded by
  # `omarchy-local-ai agent-dir <path>`, else wherever the shell was started (usually home)
  local dir=${OMARCHY_AI_AGENT_DIR:-$(cat "$STATE/agent-dir" 2>/dev/null)}
  [[ -n $dir && -d $dir ]] && cd "$dir"
  # the launcher's exit code is the terminal handshake (uwsm-app), not the agent: when it fails,
  # say what it said, so a stuck app daemon is not reported as a broken agent
  # omarchy-launch-tui blocks for the terminal's whole life and exits with the terminal's status, so
  # it is detached and its exit is not the launch result. It goes through uwsm's fast app daemon,
  # which can wedge ("Timed out waiting for pipes", ten seconds per call): a two-second ping decides,
  # and a wedged daemon gets the same terminal command through the plain uwsm client instead.
  if ! command -v uwsm-app >/dev/null 2>&1 || timeout 2 uwsm-app ping >/dev/null 2>&1; then
    setsid omarchy-launch-tui --app-id=org.omarchy.agent "${argv[@]}" >/dev/null 2>>"$LOGFILE" </dev/null & disown
  elif command -v uwsm >/dev/null 2>&1 && command -v xdg-terminal-exec >/dev/null 2>&1; then
    log "uwsm app daemon is not answering; opening $name through uwsm app"
    setsid uwsm app -- xdg-terminal-exec --app-id=org.omarchy.agent -e "${argv[@]}" >/dev/null 2>>"$LOGFILE" </dev/null & disown
  else fail "could not open a terminal for $name: the uwsm app daemon is not answering"; return 1; fi
  lwrite '.error=""'; snapshot_write   # a launch that worked retires an earlier refusal
}
