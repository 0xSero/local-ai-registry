#!/usr/bin/env python3
"""cut.py raw.mp4 marks.txt out.mp4: tighten the raw take into the story cut.

Each chapter keeps its opening (the agent booting, the prompt) and its ending (the answer),
and drops the dead middle when it runs long. Panel chapters keep the whole thing, capped.
"""
import subprocess, sys

raw, marks, out = sys.argv[1:4]
pickups = list(zip(sys.argv[4::2], sys.argv[5::2]))  # optional (raw, marks) pairs whose chapters replace the take's

def read_marks(path):
    rows = [l.split(None, 1) for l in open(path) if l.strip()]
    return [(int(t), name.strip()) for t, name in rows]

marks = read_marks(marks)
override = {}
for praw, pmarks in pickups:
    pm = read_marks(pmarks)
    for (t, name), (t2, _) in zip(pm, pm[1:]):
        override[name] = (praw, t, t2 - t)
KEEP = {"panel-load": (0, 30), "panel-share": (0, 12), "panel-stop": (0, 8)}  # (head, cap)
HEAD, TAIL = 11, 10  # agent chapters: seconds kept at start and end when the chapter is long

inputs = [raw] + [praw for praw, _ in pickups]
segs = []  # (input index, start, duration)
for (t, name), (t2, _) in zip(marks, marks[1:]):
    src, dur = 0, t2 - t
    if name == "end":
        break
    if name in override:
        praw, t, dur = override[name]; src = inputs.index(praw); t2 = t + dur
    if name in KEEP:
        segs.append((src, t, min(dur, KEEP[name][1])))
    elif dur <= HEAD + TAIL + 4:
        segs.append((src, t, dur))
    else:
        segs.append((src, t, HEAD)); segs.append((src, t2 - TAIL, TAIL))

filt = "".join(f"[{src}:v]trim=start={s}:duration={d},setpts=PTS-STARTPTS,scale=1920:1080[v{i}];" for i, (src, s, d) in enumerate(segs))
filt += "".join(f"[v{i}]" for i in range(len(segs))) + f"concat=n={len(segs)}:v=1:a=0[v]"
cmd = ["ffmpeg", "-v", "error", "-y"]
for path in inputs:
    cmd += ["-i", path]
subprocess.run(cmd + ["-filter_complex", filt, "-map", "[v]",
                "-c:v", "libx264", "-preset", "slow", "-crf", "20", "-pix_fmt", "yuv420p", "-movflags", "+faststart", out], check=True)
print(f"{len(segs)} segments, {sum(d for _, _, d in segs)}s -> {out}")
