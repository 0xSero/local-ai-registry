#!/bin/bash
# story.sh: record "one job, eight hands" on the Arc Pro B70 through plugin v4.
# Records HDMI-A-3, walks each installed agent through one step of fixing ~/demo/ledger,
# and writes a mark file with the start time of every chapter for cutting.
set -u
P=$HOME/.config/omarchy/plugins/sero.local-ai; CLI=$P/bin/omarchy-local-ai
export WAYLAND_DISPLAY=wayland-1 XDG_RUNTIME_DIR=/run/user/$(id -u) DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$(id -u)/bus
export HYPRLAND_INSTANCE_SIGNATURE=$(ls -t $XDG_RUNTIME_DIR/hypr | head -1)
REPO=$HOME/demo/ledger; OUT=/tmp/story-raw.mp4; MARKS=/tmp/story-marks.txt; T0=$(date +%s)
: >"$MARKS"; mark() { echo "$(( $(date +%s) - T0 )) $1" >>"$MARKS"; }
panel() { timeout 5 qs -p /usr/share/omarchy/shell ipc call sero.local-ai "$1" >/dev/null 2>&1; }
hypr() { timeout 5 hyprctl dispatch "$1" >/dev/null 2>&1; }   # Hyprland 0.56 Lua dispatch form
state() { $CLI snapshot | jq -r .state; }
wait_state() { local want=$1 n=0; while [[ $(state) != "$want" && $n -lt 90 ]]; do sleep 2; n=$((n+1)); done; }
term() { tmux send-keys -t story "$@"; }
reset_pane() { tmux respawn-pane -k -t story -c "$REPO" "bash --noprofile --norc" 2>/dev/null; sleep 1; term "clear" Enter; }

# place_terminal: the story window must sit fullscreen on workspace 1 of HDMI-A-3, the output the recorder
# captures. New windows open on whichever monitor has focus, so move it and verify, retrying a few times.
place_terminal() {
  local i where
  for i in 1 2 3 4 5 6; do
    sleep 1.5
    where=$(timeout 5 hyprctl clients -j 2>/dev/null | jq -r '.[] | select(.class=="org.omarchy.agent") | "\(.monitor) \(.workspace.id) \(.fullscreen)"' | head -1)
    [[ -z $where ]] && continue
    [[ $where == "0 1 2" ]] && return 0
    hypr "hl.dsp.window.move({ workspace = 1, window = \"class:org.omarchy.agent\" })"; sleep 0.5
    hypr "hl.dsp.window.fullscreen({ mode = \"fullscreen\", window = \"class:org.omarchy.agent\" })"
  done
  echo "terminal not placed: $where" >&2; return 1
}

# step <agent> <mode> <extra flags> <seconds> <prompt>
#   arg:  the agent takes the prompt on its command line (no typing race)
#   type: the prompt is typed into the TUI after it has booted
step() {
  local agent=$1 mode=$2 extra=$3 secs=$4 prompt=$5 cmd
  mark "$agent"; panel close
  cmd=$(OMARCHY_AI_FOREGROUND=1 $CLI open-agent "$agent") || { echo "skip $agent"; return; }
  if [[ $mode == arg ]]; then
    term "clear; $cmd $extra $(printf '%q' "$prompt")" Enter
  else
    term "clear; $cmd $extra" Enter; sleep 14
    term -l "$prompt"; sleep 0.8; term Enter
  fi
  sleep "$secs"
  reset_pane
}

# fresh repo state for the take
git -C "$REPO" checkout -q -- . && git -C "$REPO" reset -q --hard HEAD

timeout 5 qs -p /usr/share/omarchy/shell ipc call notifications dismissAll >/dev/null 2>&1
gpu-screen-recorder -w HDMI-A-3 -f 30 -q high -o "$OUT" >/tmp/story-rec.log 2>&1 &
REC=$!; sleep 3

# 0. the bar: from idle, Start, watch it come up
mark "panel-load"
[[ $(state) == ready ]] && { $CLI unload >/dev/null; wait_state idle; }
panel open; sleep 3
$CLI load >/dev/null
while [[ $(state) != ready ]]; do panel open; sleep 4; [[ $(state) == error ]] && break; done
sleep 4; panel close; sleep 1

# the story terminal: it must live on workspace 1 of HDMI-A-3, the output the recorder captures
tmux kill-session -t story 2>/dev/null; systemctl --user stop story-term 2>/dev/null
systemd-run --user --collect --unit=story-term -E WAYLAND_DISPLAY=wayland-1 -E XDG_RUNTIME_DIR=$XDG_RUNTIME_DIR \
  foot -a org.omarchy.agent -e tmux new -s story -c "$REPO" >/dev/null 2>&1
place_terminal || exit 1
tmux set -t story status off 2>/dev/null; term "clear" Enter
panel close; sleep 1   # the popup must not sit over the terminal

step pi       arg  ""                                          45 "Run lspci | grep -i arc and curl -s http://127.0.0.1:12434/v1/models. Then tell me in two lines what hardware and which model you are running on."
step opencode type "--auto"                                    60 "Run python3 -m unittest discover -s tests -t . and tell me which function has the bug and why. Do not fix it yet."
step codex    arg  "--dangerously-bypass-approvals-and-sandbox" 75 "Fix the off-by-one in ledger/core.py statement() so every entry is included. Change only that line."
step claude   arg  "--permission-mode acceptEdits --allowedTools='Bash(git:*)'" 120 "Review git diff and answer in one sentence: is the fix correct?"
step crush    type "--yolo"                                    50 "Run python3 -m unittest discover -s tests -t . and show me the result."
step omp      arg  "--auto-approve"                            50 "Commit the change with a one-line message that names the bug."
step copilot  arg  "--allow-all -i"                            50 "Write a three-line pull request description for the last commit."
step grok     arg  "--always-approve"                          60 "Read git log -p -1 and summarize in three bullets: what was wrong, what changed, how it was verified."

tmux kill-session -t story 2>/dev/null; systemctl --user stop story-term 2>/dev/null; sleep 1

# 9. stop
mark "panel-stop"
$CLI unload >/dev/null; wait_state idle; panel open; sleep 4; panel close
mark "end"; sleep 2
kill -INT $REC; wait $REC 2>/dev/null; echo "recorded $OUT"; cat "$MARKS"
