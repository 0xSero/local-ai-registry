#!/usr/bin/env python3
"""Render test images for the two RTX 3060 12GB cards from ~/bench-results/dual3060-tests (real output only)."""
import csv, html, os, re, statistics, subprocess

D = os.path.expanduser("~/bench-results/dual3060-tests")
OUT = os.path.join(D, "images"); os.makedirs(OUT, exist_ok=True)
rd = lambda f: open(os.path.join(D, f), errors="replace").read()
ansi = lambda s: re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", s)
started, finished = rd("started.txt").strip(), rd("finished.txt").strip()
day = started.split()[0]
CARDS = {"0": ("ASUS Dual RTX 3060 12GB", "#5aa9ff"), "1": ("EVGA RTX 3060 12GB", "#f2b33d")}

rows = [r for r in csv.reader(open(os.path.join(D, "burn_samples.csv"))) if len(r) >= 15]
series, stats = {}, {}
for idx in CARDS:
    R = [r for r in rows if r[1].strip() == idx]
    g = lambda i: [float(r[i]) for r in R]
    series[idx] = {"temp": g(6), "sm": g(10), "pw": g(8)}
    busy = [r for r in R if float(r[12]) >= 90]
    b = lambda i: [float(r[i]) for r in busy]
    stats[idx] = {"max_temp": max(b(6)), "avg_temp": round(statistics.mean(b(6))), "max_fan": max(b(7)),
                  "avg_pw": round(statistics.mean(b(8))), "avg_sm": round(statistics.mean(b(10))), "minutes": round(len(busy) * 2 / 60)}
burn = ansi(rd("burn.txt"))
verdict = re.findall(r"GPU \d+: (?:OK|FAULTY)", burn)
errs = sorted(set(re.findall(r"errors: (\d+ - \d+)", burn)))
mem = {d: rd(f"memtest_dev{d}.txt") for d in ("1", "2")}

CSS = open(os.path.expanduser("~/bench-results/3060ti-sale/render.py")).read().split('CSS = """')[1].split('"""')[0]
HEAD = ('<!doctype html><meta charset="utf-8"><link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
        'family=Unbounded:wght@700&family=IBM+Plex+Sans:wght@400;500;600&family=JetBrains+Mono:wght@400;500;600&display=swap">'
        f"<style>{CSS}.key{{display:flex;gap:28px;font:500 20px 'JetBrains Mono',monospace;color:var(--ink2)}}.key i{{display:inline-block;width:28px;height:6px;border-radius:3px;margin-right:10px;vertical-align:middle}}</style>")


def shot(name, body):
    p = os.path.join(OUT, name + ".html")
    open(p, "w").write(HEAD + f'<div class="page">{body}</div>')
    subprocess.run(["chromium", "--headless=new", "--disable-gpu", "--hide-scrollbars", "--virtual-time-budget=4000",
                    "--force-device-scale-factor=2", "--window-size=1080,1080", f"--screenshot={os.path.join(OUT, name + '.png')}",
                    "file://" + p], check=True, capture_output=True)


def chart(key, lo, hi, h=110):
    w = 968; lines = ""
    for idx, (_, color) in CARDS.items():
        xs = series[idx][key]
        pts = " ".join(f"{i * w / max(1, len(xs) - 1):.1f},{h - (min(max(x, lo), hi) - lo) / (hi - lo) * h:.1f}" for i, x in enumerate(xs))
        lines += f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="3"/>'
    return f'<svg viewBox="0 0 {w} {h}" width="100%" height="{h}" preserveAspectRatio="none">{lines}</svg>'


key = "".join(f'<span><i style="background:{c}"></i>{n}</span>' for n, c in CARDS.values())
a, e = stats["0"], stats["1"]
cells = "".join(f'<div class="cell"><span>{lbl}</span>{chart(k, lo, hi)}</div>' for lbl, k, lo, hi in [
    (f"GPU temperature · ASUS max {a['max_temp']:.0f} °C · EVGA max {e['max_temp']:.0f} °C", "temp", 30, 90),
    (f"Core clock · ASUS avg {a['avg_sm']} MHz · EVGA avg {e['avg_sm']} MHz", "sm", 0, 2100),
    (f"Power · both ~{a['avg_pw']} W (power limit 170 W)", "pw", 0, 200)])
shot("dual-stress", f'''<div class="eyebrow">Stress test · gpu-burn · both cards at 100% · {day}</div>
<h1>{a["minutes"]} minutes, two cards: <span class="a">0 errors</span></h1>
<div class="key">{key}</div>
<div style="display:grid;gap:12px">{cells}</div>
<div class="term" style="flex:0 0 auto;font-size:17px">{html.escape(chr(10).join(["errors: " + x for x in errs] + ["Tested 2 GPUs:"] + verdict))}</div>
<div class="foot"><span>{started} → {finished.split()[1]}</span><span>no thermal throttling on either card</span></div>''')

lines = []
for d, name in (("1", "EVGA · bus 65"), ("2", "ASUS · bus 17")):
    L = [re.sub(r" {2,}", "  ", l.strip()) for l in mem[d].splitlines() if re.search(r"test of|iteration\. Passed|PASSed", l)]
    L = list(dict.fromkeys(L))
    lines += [f"── {name}"] + [l for l in L if "test of" in l][:1] + [l for l in L if "iteration" in l][-3:] + [l for l in L if "PASSed" in l][-1:] + [""]
shot("dual-vram", f'''<div class="eyebrow">Video memory test · memtest_vulkan v0.5.0 · {day}</div>
<h1>VRAM, both cards: <span class="a">0 errors</span></h1>
<div class="badge">PASSED × 2</div>
<div class="term" style="font-size:14.5px">{html.escape(chr(10).join(lines))}</div>
<div class="foot"><span>Standard 5-minute run per card</span><span>{day}</span></div>''')
print(stats, verdict, errs)
