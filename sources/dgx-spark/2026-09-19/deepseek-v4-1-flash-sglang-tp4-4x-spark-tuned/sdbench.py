#!/usr/bin/env python3
"""Python port of MiaAI-Lab/sparkDash DecodeBench (server/collectors/DecodeBench.js, src/shared/llmPrompts.js).

Protocol: temperature 0, top_p 1, thinking off (chat_template_kwargs enable_thinking/thinking false),
max_tokens = min_tokens = N (default 256, the knapcio README setting), ignore_eos, streaming with usage.
One 32-token warmup per prompt type. Per stream: decode tok/s = (completion_tokens - 1) / (last - first token).
Aggregate at C>1 = total decode tokens / (latest last token - earliest first token).
With C>1 each stream's prompt gets " (stream i/N)" appended, as in pickDecodeBenchPrompts.
Usage: sdbench.py [--host URL] [--types prose,code,structured] [--conc 1,8] [--reps 3] [--tokens 256]
"""
import argparse, json, statistics, threading, time, urllib.request

PROMPTS = {
    "structured": "Count from 1 to 200. Output only the numbers, separated by spaces. No other text.",
    "prose": "Write a detailed step-by-step explanation of how a hash map works, "
             "including collision handling, resizing, and time complexity. Be thorough.",
    "code": "Output only Python source code. No comments, no docstrings, no markdown fences. "
            "Write functions clamp_00 through clamp_49. Each function is exactly:\n"
            "def clamp_NN(x, lo=0, hi=1):\n"
            "    if x < lo:\n"
            "        return lo\n"
            "    if x > hi:\n"
            "        return hi\n"
            "    return x\n"
            "Change only the function name suffix (00, 01, … 49). One blank line between functions. No other text.",
}


def stream(host, model, prompt, n):
    body = {"model": model, "messages": [{"role": "user", "content": prompt}], "max_tokens": n, "min_tokens": n,
            "ignore_eos": True, "temperature": 0, "top_p": 1, "stream": True, "stream_options": {"include_usage": True},
            "chat_template_kwargs": {"enable_thinking": False, "thinking": False, "thinking_mode": "disabled"}}
    req = urllib.request.Request(host + "/v1/chat/completions", json.dumps(body).encode(), {"Content-Type": "application/json"})
    t0 = time.time(); first = last = None; usage = None
    with urllib.request.urlopen(req, timeout=360) as r:
        for raw in r:
            line = raw.decode().strip()
            if not line.startswith("data:") or line == "data: [DONE]":
                continue
            j = json.loads(line[5:])
            if j.get("usage"):
                usage = j["usage"]
            for c in j.get("choices") or []:
                d = c.get("delta") or {}
                if d.get("content") or d.get("reasoning_content") or d.get("reasoning"):
                    now = time.time(); first = first or now; last = now
    toks = (usage or {}).get("completion_tokens", 0)
    tps = (toks - 1) / (last - first) if first and last and last > first else 0.0
    return dict(tps=tps, tokens=toks, ttft_ms=(first - t0) * 1000 if first else None, first=first, last=last)


def wave(host, model, typ, c, n):
    base = PROMPTS[typ]
    prompts = [base] if c == 1 else [f"{base} (stream {i + 1}/{c})" for i in range(c)]
    res = [None] * c
    def run(i):
        try: res[i] = stream(host, model, prompts[i], n)
        except Exception as e: res[i] = dict(error=str(e))
    th = [threading.Thread(target=run, args=(i,)) for i in range(c)]
    [t.start() for t in th]; [t.join() for t in th]
    ok = [r for r in res if r and "error" not in r and r["first"]]
    agg = sum(r["tokens"] - 1 for r in ok) / (max(r["last"] for r in ok) - min(r["first"] for r in ok)) if ok else 0
    return dict(per=statistics.mean(r["tps"] for r in ok) if ok else 0, agg=agg, ttft=statistics.median(r["ttft_ms"] for r in ok) if ok else None,
                ok=len(ok), failed=c - len(ok))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="http://10.10.10.12:8888"); ap.add_argument("--model", default="deepseek-v4.1-flash")
    ap.add_argument("--types", default="prose,code,structured"); ap.add_argument("--conc", default="1,8")
    ap.add_argument("--reps", type=int, default=3); ap.add_argument("--tokens", type=int, default=256)
    a = ap.parse_args(); out = {}
    for typ in a.types.split(","):
        stream(a.host, a.model, PROMPTS[typ], 32)  # warmup
        for c in map(int, a.conc.split(",")):
            reps = [wave(a.host, a.model, typ, c, a.tokens) for _ in range(a.reps if c == 1 else 1)]
            best = sorted(reps, key=lambda r: r["agg"])[len(reps) // 2]  # median wave
            out[f"{typ}_c{c}"] = dict(best, runs=[round(r["agg"], 1) for r in reps])
            print(f"{typ} c{c} per {best['per']:.2f} agg {best['agg']:.2f} ttft {best['ttft']:.0f} ok {best['ok']} runs {[round(r['agg'],1) for r in reps]}", flush=True)
    print(json.dumps(out))


if __name__ == "__main__":
    main()
