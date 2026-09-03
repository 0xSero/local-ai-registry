#!/bin/bash
# pickup.sh "<step line>": re-record one chapter of story.sh at the current repo state. Marks: <agent>, end.
set -u
source <(sed -n '1,/^# fresh repo state/p' "$HOME/story.sh" | grep -v '^# fresh repo state')   # env and functions only
CLI=$HOME/.config/omarchy/plugins/sero.local-ai/bin/omarchy-local-ai
OUT=/tmp/pickup-raw.mp4; MARKS=/tmp/pickup-marks.txt; : >"$MARKS"
[[ $(state) == ready ]] || { $CLI load >/dev/null; while [[ $(state) != ready ]]; do sleep 5; [[ $(state) == error ]] && exit 1; done; }
timeout 5 qs -p /usr/share/omarchy/shell ipc call notifications dismissAll >/dev/null 2>&1; panel close
tmux kill-session -t story 2>/dev/null; systemctl --user stop story-term 2>/dev/null
systemd-run --user --collect --unit=story-term -E WAYLAND_DISPLAY=wayland-1 -E XDG_RUNTIME_DIR=$XDG_RUNTIME_DIR \
  foot -a org.omarchy.agent -e tmux new -s story -c "$REPO" >/dev/null 2>&1
place_terminal || exit 1
tmux set -t story status off 2>/dev/null; term "clear" Enter; panel close; sleep 1
gpu-screen-recorder -w HDMI-A-3 -f 30 -q high -o "$OUT" >/tmp/pickup-rec.log 2>&1 &
REC=$!; sleep 3; T0=$(date +%s)   # marks are recorder time
eval "$1"
tmux kill-session -t story 2>/dev/null; systemctl --user stop story-term 2>/dev/null
mark "end"; sleep 1; kill -INT $REC; wait $REC 2>/dev/null; echo "recorded $OUT"; cat "$MARKS"
