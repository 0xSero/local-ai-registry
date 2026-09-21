"""Workload-independent step-time / acceptance curve from dsbench receipts.

tok/s = committed_per_req_per_step * running / step_time, and `running` is set by how much the
sampled answers happen to overlap, not by the config. So compare configs on step_time and
committed-per-step AT A MATCHED running count, taken straight from the engine's decode-batch lines.
"""
import json, os, re, statistics, sys
from collections import defaultdict

RUN_RE = re.compile(r"#running-req:\s*(\d+)")
ACC_RE = re.compile(r"accept len:\s*([0-9.]+)")
TPS_RE = re.compile(r"gen throughput \(token/s\):\s*([0-9.]+)")
TS_RE = re.compile(r"^(\d{4}-\d\d-\d\d)T(\d\d:\d\d:\d\d\.\d+)Z")


def cell_curve(rel_lines):
    """-> {running: (n, median_step_s, median_accept, median_tps)}"""
    rows = []
    for line in rel_lines:
        if "Decode batch" not in line:
            continue
        m_run, m_acc, m_tps = RUN_RE.search(line), ACC_RE.search(line), TPS_RE.search(line)
        m_ts = TS_RE.match(line)
        if not (m_run and m_ts):
            continue
        import datetime as dt
        t = dt.datetime.fromisoformat(m_ts.group(1) + "T" + m_ts.group(2) + "+00:00").timestamp()
        rows.append((t, int(m_run.group(1)),
                     float(m_acc.group(1)) if m_acc else None,
                     float(m_tps.group(1)) if m_tps else None))
    out = defaultdict(lambda: {"gaps": [], "acc": [], "tps": []})
    for (t0, r0, a0, p0), (t1, r1, _, _) in zip(rows, rows[1:]):
        if r0 != r1:
            continue  # only intervals where the batch composition did not change
        gap = t1 - t0
        if 0 < gap < 10:
            out[r0]["gaps"].append(gap)
        if a0:
            out[r0]["acc"].append(a0)
        if p0:
            out[r0]["tps"].append(p0)
    res = {}
    for r, d in out.items():
        if len(d["gaps"]) < 3:
            continue
        res[r] = (len(d["gaps"]), statistics.median(d["gaps"]),
                  statistics.median(d["acc"]) if d["acc"] else None,
                  statistics.median(d["tps"]) if d["tps"] else None)
    return res


def load(run):
    out = {}
    for line in open(os.path.join(run, "cells.jsonl")):
        r = json.loads(line)
        cid = str(r.get("cell_id", ""))
        if cid.startswith("warmup") or not r.get("valid"):
            continue
        rel = (r.get("engine_log") or {}).get("relevant_lines") or []
        out[cid.split("-a")[0]] = cell_curve(rel)
    return out


runs = sys.argv[1:]
data = [load(r) for r in runs]
names = [os.path.basename(r).split("-")[1][:9] for r in runs]
keys = sorted(set().union(*[set(d) for d in data]))

print(f"{'cell':24s} {'run':>4s} " + "  ".join(f"{n:>26s}" for n in names))
print(f"{'':24s} {'':>4s} " + "  ".join(f"{'n   step_ms  acc   tok/s':>26s}" for _ in names))
for k in keys:
    runnings = sorted(set().union(*[set(d.get(k, {})) for d in data]))
    for rn in runnings:
        cells = []
        for d in data:
            v = d.get(k, {}).get(rn)
            if v:
                n, gap, acc, tps = v
                cells.append(f"{n:3d} {gap*1000/10:8.1f} {acc if acc else 0:5.2f} {tps if tps else 0:7.1f}")
            else:
                cells.append(f"{'-':>26s}")
        print(f"{k:24s} r={rn:<2d} " + "  ".join(cells))
    print()
