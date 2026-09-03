#!/bin/bash
# pickup.sh "<step line>": re-record one chapter of story.sh at the current repo state, same mechanics
# as the take (real clicks, typed prompt). Marks are recorder time: <agent>, end, rec-start, rec-stop.
set -u
source <(sed -n '1,/^# fresh repo state/p' "$HOME/story.sh" | grep -v '^# fresh repo state')
OUT=/tmp/pickup-raw.mp4; MARKS=/tmp/pickup-marks.txt; : >"$MARKS"
[[ $(state) == ready ]] || { $CLI load >/dev/null; while [[ $(state) != ready ]]; do sleep 5; [[ $(state) == error ]] && exit 1; done; }
timeout 5 qs -p /usr/share/omarchy/shell ipc call notifications dismissAll >/dev/null 2>&1; ipc close
hypr "hl.dsp.window.close({ window = \"class:org.omarchy.agent\" })"; hypr "hl.dsp.cursor.move({ x = $CUR_X, y = $CUR_Y })"; sleep 1
gpu-screen-recorder -w HDMI-A-3 -f 30 -fm cfr -q high -cursor yes -o "$OUT" >/tmp/pickup-rec.log 2>&1 &
REC=$!; sleep 3; T0=$(date +%s); mark "rec-start"
eval "$1"
mark "end"; sleep 1; mark "rec-stop"; kill -INT $REC; wait $REC 2>/dev/null; echo "recorded $OUT"; cat "$MARKS"
