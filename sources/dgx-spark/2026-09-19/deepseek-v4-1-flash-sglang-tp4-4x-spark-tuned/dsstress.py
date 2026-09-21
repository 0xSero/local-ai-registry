#!/usr/bin/env python3
"""Mixed stability stress for the DS4.1 4x Spark stack (row 9 config).

Runs for --minutes: 1x cold 420k-token prompt (once), 2x 150k-token prompts (once each), 12 short chat streams
looping 1024-token generations, 2 vision streams looping small image requests. Random token-id prompts avoid the
radix cache. Reports per-class successes, failures, TTFT and decode rates, and whether /health stayed up.
"""
import argparse, base64, json, random, struct, threading, time, urllib.request, zlib

H = "http://10.10.10.12:8888"; M = "deepseek-v4.1-flash"
lock = threading.Lock(); stats = {}; stop = time.time()


def rec(cls, **kw):
    with lock:
        stats.setdefault(cls, []).append(kw)


def post_stream(path, body, timeout=3600):
    req = urllib.request.Request(H + path, json.dumps(body).encode(), {"Content-Type": "application/json"})
    t0 = time.time(); first = last = None; usage = None
    with urllib.request.urlopen(req, timeout=timeout) as r:
        for raw in r:
            line = raw.decode(errors="replace").strip()
            if not line.startswith("data: {"):
                continue
            j = json.loads(line[6:])
            if j.get("usage"):
                usage = j["usage"]
            if j.get("choices"):
                now = time.time(); first = first or now; last = now
    toks = (usage or {}).get("completion_tokens", 0)
    return dict(ttft=round(first - t0, 2) if first else None, total=round(time.time() - t0, 1), tokens=toks,
                tps=round((toks - 1) / (last - first), 1) if first and last and last > first and toks > 1 else None,
                prompt=(usage or {}).get("prompt_tokens"))


def long_prompt(cls, ntok, seed):
    r = random.Random(seed)
    body = {"model": M, "prompt": [r.randrange(1000, 120000) for _ in range(ntok)], "max_tokens": 256, "temperature": 1.0,
            "stream": True, "stream_options": {"include_usage": True}}
    try: rec(cls, ok=True, **post_stream("/v1/completions", body))
    except Exception as e: rec(cls, ok=False, err=repr(e)[:200])


def chat_loop(i):
    r = random.Random(i)
    topics = ["a B-tree", "TCP congestion control", "the Rust borrow checker", "a ray tracer", "Raft consensus", "a bloom filter"]
    while time.time() < stop:
        body = {"model": M, "messages": [{"role": "user", "content": f"[{r.random():.6f}] Explain {r.choice(topics)} in depth with code."}],
                "max_tokens": 1024, "temperature": 0.7, "stream": True, "stream_options": {"include_usage": True}}
        try: rec("chat", ok=True, **post_stream("/v1/chat/completions", body, 900))
        except Exception as e: rec("chat", ok=False, err=repr(e)[:200]); time.sleep(5)


def png(seed):
    r = random.Random(seed); W, Hh = 128, 96; cols = [tuple(r.randrange(256) for _ in range(3)) for _ in range(2)]
    raw = b"".join(b"\x00" + bytes(c for x in range(W) for c in cols[x >= W // 2]) for y in range(Hh))
    ch = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    return b"\x89PNG\r\n\x1a\n" + ch(b"IHDR", struct.pack(">IIBBBBB", W, Hh, 8, 2, 0, 0, 0)) + ch(b"IDAT", zlib.compress(raw)) + ch(b"IEND", b"")


def vision_loop(i):
    k = 0
    while time.time() < stop:
        k += 1
        body = {"model": M, "temperature": 0, "stream": True, "stream_options": {"include_usage": True}, "max_tokens": 128,
                "messages": [{"role": "user", "content": [
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(png(i * 1000 + k)).decode()}},
                    {"type": "text", "text": "Describe the two colours in this image (left and right halves) in one sentence."}]}]}
        try: rec("vision", ok=True, **post_stream("/v1/chat/completions", body, 600))
        except Exception as e: rec("vision", ok=False, err=repr(e)[:200]); time.sleep(5)


def health_loop():
    while time.time() < stop + 60:
        try: urllib.request.urlopen(H + "/health", timeout=10); rec("health", ok=True)
        except Exception as e: rec("health", ok=False, err=repr(e)[:120], t=time.strftime("%T"))
        time.sleep(15)


def main():
    global stop
    ap = argparse.ArgumentParser(); ap.add_argument("--minutes", type=float, default=15); ap.add_argument("--chat", type=int, default=12)
    ap.add_argument("--vision", type=int, default=2); ap.add_argument("--huge", type=int, default=420000); a = ap.parse_args()
    stop = time.time() + a.minutes * 60; t0 = time.time()
    th = [threading.Thread(target=health_loop, daemon=True)]
    th += [threading.Thread(target=long_prompt, args=("huge_%dk" % (a.huge // 1000), a.huge, 42))]
    th += [threading.Thread(target=long_prompt, args=("long_150k", 150000, 100 + i)) for i in range(2)]
    th += [threading.Thread(target=chat_loop, args=(i,)) for i in range(a.chat)]
    th += [threading.Thread(target=vision_loop, args=(i,)) for i in range(a.vision)]
    [t.start() for t in th]; [t.join() for t in th[1:]]
    out = {"wall_s": round(time.time() - t0)}
    for cls, v in sorted(stats.items()):
        ok = [x for x in v if x.get("ok")]; bad = [x for x in v if not x.get("ok")]
        d = dict(n=len(v), ok=len(ok), failed=len(bad), errors=[x.get("err") for x in bad][:5])
        if cls != "health":
            d["ttft_s"] = sorted(x["ttft"] for x in ok if x.get("ttft") is not None)[:3] + (["..."] if len(ok) > 3 else [])
            tps = [x["tps"] for x in ok if x.get("tps")]
            if tps: d["median_tps"] = sorted(tps)[len(tps) // 2]
            d["tokens"] = sum(x.get("tokens", 0) for x in ok)
            if cls.startswith(("huge", "long")): d["detail"] = ok
        out[cls] = d
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
