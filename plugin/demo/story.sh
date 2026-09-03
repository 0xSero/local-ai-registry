#!/bin/bash
# story.sh: record "one job, eight hands" on the Arc Pro B70 through plugin v4, the way a person does it.
# The cursor clicks the bar icon, picks the agent in the popup, the agent opens on the local model, the
# prompt is typed live. Records HDMI-A-3 with the cursor; marks every chapter for cutting.
set -u
exec 2>>/tmp/story-trace.log
P=$HOME/.config/omarchy/plugins/sero.local-ai; CLI=$P/bin/omarchy-local-ai
export WAYLAND_DISPLAY=wayland-1 XDG_RUNTIME_DIR=/run/user/$(id -u) DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$(id -u)/bus
export HYPRLAND_INSTANCE_SIGNATURE=$(ls -t $XDG_RUNTIME_DIR/hypr | head -1)
REPO=$HOME/demo/ledger; OUT=/tmp/story-raw.mp4; MARKS=/tmp/story-marks.txt; T0=$(date +%s)
: >"$MARKS"; mark() { echo "$(( $(date +%s) - T0 )) $1" >>"$MARKS"; }
ipc() { timeout 5 qs -p /usr/share/omarchy/shell ipc call sero.local-ai "$@" >/dev/null 2>&1; }
hypr() { timeout 5 hyprctl dispatch "$1" >/dev/null 2>&1; }   # Hyprland 0.56 Lua dispatch form
state() { $CLI snapshot | jq -r .state; }
wait_state() { local want=$1 n=0; while [[ $(state) != "$want" && $n -lt 120 ]]; do sleep 2; n=$((n+1)); done; }

# --- the hand ---------------------------------------------------------------------------------
CUR_X=960; CUR_Y=540
glide() { # glide <x> <y>: move the cursor there in a curve of small steps, like a wrist would
  local x=$1 y=$2 i n=24 t
  for i in $(seq 1 $n); do
    t=$(python3 -c "import math; print((1-math.cos(math.pi*$i/$n))/2)")
    hypr "hl.dsp.cursor.move({ x = $(python3 -c "print(round($CUR_X+($x-$CUR_X)*$t))"), y = $(python3 -c "print(round($CUR_Y+($y-$CUR_Y)*$t))") })"
    sleep 0.018
  done
  CUR_X=$x; CUR_Y=$y
}
click() { glide "$1" "$2"; sleep 0.35; python3 "$HOME/click.py" left; sleep 0.6; }
type_text() { wtype -d 34 -- "$1"; sleep 0.5; wtype -k Return; }

# popup geometry on HDMI-A-3 (1920x1080): the bar icon, the Start/Stop row, the Open agent row,
# and the agent rows once the list is open (order = the snapshot's launchable list)
ICON="1766 1064"; START_OR_STOP="1700 1017"; OPEN_AGENT="1745 957"; AGENT_X=1700
agent_y() { case $1 in pi) echo 782;; omp) echo 807;; opencode) echo 832;; claude) echo 857;; codex) echo 882;; grok) echo 907;; copilot) echo 932;; crush) echo 957;; esac; }

# place_agent: the agent's window must sit fullscreen on workspace 1 of HDMI-A-3, the output the
# recorder captures. New windows open on whichever monitor has focus, so move it and verify.
place_agent() {
  local i where
  for i in 1 2 3 4 5 6 7 8; do
    sleep 1
    where=$(timeout 5 hyprctl clients -j 2>/dev/null | jq -r '.[] | select(.class=="org.omarchy.agent") | "\(.monitor) \(.workspace.id) \(.fullscreen)"' | head -1)
    [[ -z $where ]] && continue
    [[ $where == "0 1 2" ]] && return 0
    hypr "hl.dsp.window.move({ workspace = 1, window = \"class:org.omarchy.agent\" })"; sleep 0.4
    hypr "hl.dsp.window.fullscreen({ mode = \"fullscreen\", window = \"class:org.omarchy.agent\" })"
  done
  echo "agent window not placed: $where" >&2; return 1
}
close_agent() { hypr "hl.dsp.window.close({ window = \"class:org.omarchy.agent\" })"; sleep 1.5; }

# step <agent> <boot seconds> <answer seconds> <prompt>
step() {
  local agent=$1 boot=$2 secs=$3 prompt=$4
  mark "$agent"
  click $ICON; sleep 0.8                      # popup
  ipc pick "$agent"; click $OPEN_AGENT; sleep 0.6   # list
  click $AGENT_X "$(agent_y "$agent")"        # the agent opens on the model
  if ! place_agent; then                      # a launch can drop on the first try; once more, on camera
    echo "retrying $agent" >&2; ipc close; sleep 1
    click $ICON; sleep 0.8; ipc pick "$agent"; click $OPEN_AGENT; sleep 0.6; click $AGENT_X "$(agent_y "$agent")"
    place_agent || return 1
  fi
  ipc close; sleep 0.5                        # the popup would keep the keyboard
  click 1200 700; sleep "$boot"               # into the terminal; let the TUI come up
  type_text "$prompt"
  sleep "$secs"
  close_agent
}

# fresh repo state for the take
git -C "$REPO" checkout -q -- . && git -C "$REPO" reset -q --hard HEAD
timeout 5 qs -p /usr/share/omarchy/shell ipc call notifications dismissAll >/dev/null 2>&1
ipc close; hypr "hl.dsp.window.close({ window = \"class:org.omarchy.agent\" })"
hypr "hl.dsp.cursor.move({ x = $CUR_X, y = $CUR_Y })"

gpu-screen-recorder -w HDMI-A-3 -f 30 -fm cfr -q high -cursor yes -o "$OUT" >/tmp/story-rec.log 2>&1 &
REC=$!; sleep 3; mark "rec-start"

# 0. the bar: from idle, click the circle, click Start, watch it come up
mark "panel-load"
[[ $(state) == ready ]] && { $CLI unload >/dev/null; wait_state idle; }
sleep 1; click $ICON; sleep 1.5; click $START_OR_STOP; sleep 6
[[ $(state) == idle ]] && { ipc open; sleep 1.5; click $START_OR_STOP; sleep 6; }
[[ $(state) == idle ]] && { echo "Start click did not take; loading directly" >&2; $CLI load >/dev/null; }
while [[ $(state) != ready ]]; do sleep 3; [[ $(state) == error ]] && { echo "load errored: $($CLI snapshot | jq -r .error)" >&2; break; }; done
echo "loaded: $(state)" >&2
sleep 5; ipc close; sleep 1

step pi       9  40 "Run lspci | grep -i arc and curl -s http://127.0.0.1:12434/v1/models. Then tell me in two lines what hardware and which model you are running on."
step opencode 12 50 "Run python3 -m unittest discover -s tests -t . and tell me which function has the bug and why. Do not fix it yet."
step codex    12 60 "Fix the off-by-one in ledger/core.py statement() so every entry is included. Change only that line."
step claude   10 95 "Review git diff and answer in one sentence: is the fix correct?"
step crush    12 40 "Run python3 -m unittest discover -s tests -t . and show me the result."
step omp      10 45 "Commit the change with a one-line message that names the bug."
step copilot  20 45 "Write a three-line pull request description for the last commit."
step grok     10 50 "Read git log -p -1 and summarize in three bullets: what was wrong, what changed, how it was verified."

# 9. stop: the circle, then Stop
mark "panel-stop"
click $ICON; sleep 1.5; click $START_OR_STOP; wait_state idle; sleep 3; ipc close
mark "end"; sleep 2; mark "rec-stop"
kill -INT $REC; wait $REC 2>/dev/null; echo "recorded $OUT"; cat "$MARKS"
