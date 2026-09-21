#!/usr/bin/env python3
"""Decode-under-deep-prefill benchmark.

C chat streams decode continuously (1024-token generations, looped); after --delay seconds one cold --deep-token
prompt (random token ids, /v1/completions, 8 output tokens) arrives. Reports, for the window in which the deep
prompt is prefilling: chat aggregate tok/s, per-stream tok/s, max and p95 inter-chunk gap on the chat streams,
and the deep prompt's TTFT. Also the same chat numbers for the 20 s before the deep prompt (baseline).
Usage: mixbench.py [--conc 4] [--deep 150000] [--delay 20]
"""
import argparse, json, random, statistics, threading, time, urllib.request

H = "http://10.10.10.12:8888"; M = "deepseek-v4.1-flash"
events = []; lock = threading.Lock(); stop = [False]


def chat(i):
    r = random.Random(i)
    while not stop[0]:
        body = {"model": M, "messages": [{"role": "user", "content": f"[{r.random():.6f}] Write a long, detailed tutorial on building a key-value store in Go, with code."}],
                "max_tokens": 1024, "temperature": 0.7, "stream": True, "stream_options": {"include_usage": True}}
        req = urllib.request.Request(H + "/v1/chat/completions", json.dumps(body).encode(), {"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=900) as resp:
                for raw in resp:
                    if stop[0]:
                        break
                    line = raw.decode(errors="replace").strip()
                    if not line.startswith("data: {"):
                        continue
                    j = json.loads(line[6:])
                    for c in j.get("choices") or []:
                        d = c.get("delta") or {}
                        txt = (d.get("content") or "") + (d.get("reasoning_content") or "")
                        if txt:
                            with lock:
                                events.append((time.time(), i, len(txt)))
        except Exception:
            time.sleep(1)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--conc", type=int, default=4); ap.add_argument("--deep", type=int, default=150000)
    ap.add_argument("--delay", type=float, default=20); a = ap.parse_args()
    ths = [threading.Thread(target=chat, args=(i,), daemon=True) for i in range(a.conc)]; [t.start() for t in ths]
    time.sleep(a.delay)
    r = random.Random(777)
    body = {"model": M, "prompt": [r.randrange(1000, 120000) for _ in range(a.deep)], "max_tokens": 8, "temperature": 0}
    t0 = time.time()
    out = json.loads(urllib.request.urlopen(urllib.request.Request(H + "/v1/completions", json.dumps(body).encode(), {"Content-Type": "application/json"}), timeout=3600).read())
    t1 = time.time(); stop[0] = True; time.sleep(2)
    # usage.completion_tokens is not streamed per chunk; count chunks (each SSE chunk ~ one scheduler step's tokens) and chars
    def window(lo, hi):
        ev = [e for e in events if lo <= e[0] < hi]
        per = {}
        for t, i, n in ev: per.setdefault(i, []).append(t)
        gaps = sorted(g for ts in per.values() for g in (b - a_ for a_, b in zip(ts, ts[1:])))
        # chars/4 ~ tokens for English/code; reported as est_tok_s
        chars = sum(n for _, _, n in ev)
        return dict(est_tok_s=round(chars / 4 / (hi - lo), 1), chunks=len(ev), max_gap_s=round(gaps[-1], 2) if gaps else None,
                    p95_gap_s=round(gaps[int(len(gaps) * 0.95)], 2) if gaps else None, streams=len(per))
    res = dict(conc=a.conc, deep_tokens=a.deep, deep_ttft_s=round(t1 - t0, 1), deep_prefill_tok_s=round(a.deep / (t1 - t0)),
               before=window(t0 - min(a.delay - 2, 20), t0), during=window(t0, t1), usage=out.get("usage"))
    print(json.dumps(res))


if __name__ == "__main__":
    main()
