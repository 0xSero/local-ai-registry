#!/usr/bin/env python3
"""cut.py raw.mp4 marks.txt out.mp4 [pickup.mp4 pickup-marks.txt ...]

Nothing is cut out. Each chapter plays at 1x while the hand and the typing are on screen and while the
answer arrives, and the waiting in between runs as a time-lapse, so the viewer sees every action and
never a hard jump. Pickups replace same-named chapters.
"""
import subprocess, sys

raw, marks, out = sys.argv[1:4]
pickups = list(zip(sys.argv[4::2], sys.argv[5::2]))
HEAD, TAIL, FAST = 16, 14, 8          # seconds at 1x at the start and end of a chapter; speed of the middle
PANEL = {"panel-load": (12, 8), "panel-stop": (6, 4)}   # (head, tail) for the panel chapters

def read_marks(path, video=None):
    """Marks are wall-clock seconds from the take script. The recorder does not keep wall time exactly,
    so when the marks carry rec-start/rec-stop and the video is given, map them onto video time."""
    rows = [l.split(None, 1) for l in open(path) if l.strip()]
    marks = [(int(t), name.strip()) for t, name in rows]
    names = dict((n, t) for t, n in marks)
    if video and "rec-start" in names and "rec-stop" in names:
        dur = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", video]))
        wall = names["rec-stop"] - names["rec-start"]
        scale = dur / wall if wall > 0 else 1
        marks = [(int(round((t - names["rec-start"]) * scale)), n) for t, n in marks]
    return [(t, n) for t, n in marks if n not in ("rec-start", "rec-stop")]

chapters = []
wall_marks = read_marks(marks, raw)
for (t, name), (t2, _) in zip(wall_marks, wall_marks[1:]):
    if name != "end":
        chapters.append([0, t, t2 - t, name])
inputs = [raw]
for praw, pmarks in pickups:
    inputs.append(praw)
    pm = read_marks(pmarks, praw)
    for (t, name), (t2, _) in zip(pm, pm[1:]):
        for c in chapters:
            if c[3] == name:
                c[0], c[1], c[2] = len(inputs) - 1, t, t2 - t

parts, n = [], 0
def seg(src, start, dur, speed):
    global n
    f = f"[{src}:v]trim=start={start}:duration={dur},setpts=PTS-STARTPTS,scale=1920:1080"
    if speed != 1:
        f += f",setpts=PTS/{speed}"
    parts.append(f + f"[v{n}]"); n += 1

for src, t, dur, name in chapters:
    head, tail = PANEL.get(name, (HEAD, TAIL))
    if dur <= head + tail + 3:
        seg(src, t, dur, 1)
    else:
        seg(src, t, head, 1); seg(src, t + head, dur - head - tail, FAST); seg(src, t + dur - tail, tail, 1)

filt = ";".join(parts) + ";" + "".join(f"[v{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=0[v]"
cmd = ["ffmpeg", "-v", "error", "-y"]
for path in inputs:
    cmd += ["-i", path]
subprocess.run(cmd + ["-filter_complex", filt, "-map", "[v]", "-r", "30", "-c:v", "libx264", "-preset", "slow", "-crf", "20",
                      "-pix_fmt", "yuv420p", "-movflags", "+faststart", out], check=True)
total = sum(min(d, h + t) + max(0, d - h - t) / FAST for _, _, d, nm in chapters for h, t in [PANEL.get(nm, (HEAD, TAIL))])
print(f"{n} segments, about {int(total)}s -> {out}")
