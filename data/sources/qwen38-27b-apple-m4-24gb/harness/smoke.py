#!/usr/bin/env python3
"""Smoke-test a llama-server endpoint: served id, chat, decode, tool call, vision, reasoning, MTP draft stats.
Stdlib only. usage: smoke.py [BASE_URL] [OUT_JSON]"""
import base64, json, os, struct, sys, time, urllib.request, zlib

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8080"
OUT = sys.argv[2] if len(sys.argv) > 2 else None
IMAGE = os.environ.get("IMAGE", os.path.join(os.path.dirname(os.path.abspath(__file__)), "ticket-1280.png"))


def post(path, body, timeout=900):
    req = urllib.request.Request(BASE + path, json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=30) as r:
        return json.load(r)


def png(w, h, rgb):
    row = b"\x00" + bytes(rgb) * w
    raw = zlib.compress(row * h)
    chunk = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + chunk(b"IDAT", raw) + chunk(b"IEND", b"")


results = []


def chat(name, messages, check, **kw):
    body = {"model": MODEL, "messages": messages, "temperature": 0, **kw}
    t = time.time()
    r = post("/v1/chat/completions", body)
    wall = time.time() - t
    msg = r["choices"][0]["message"]
    ok = check(msg)
    tim = r.get("timings", {})
    results.append({"probe": name, "ok": ok, "wall_s": round(wall, 2), "request": {k: v for k, v in body.items() if k != "messages"},
                    "response": r})
    print(f"--- {name} ({wall:.1f}s) ok={ok}")
    print("content:", (msg.get("content") or "")[:300].replace("\n", " "))
    if msg.get("reasoning_content"):
        print("reasoning:", msg["reasoning_content"][:160].replace("\n", " "), "...")
    if msg.get("tool_calls"):
        print("tool_calls:", json.dumps(msg["tool_calls"])[:300])
    keys = ["prompt_n", "prompt_per_second", "predicted_n", "predicted_per_second", "draft_n", "draft_n_accepted"]
    print("timings:", {k: round(tim[k], 2) if isinstance(tim.get(k), float) else tim.get(k) for k in keys if k in tim})


models = get("/v1/models")
MODEL = models["data"][0]["id"]
props = get("/props")
print("served:", [m["id"] for m in models["data"]])
print("n_ctx:", props.get("default_generation_settings", {}).get("n_ctx"), "| modalities:", props.get("modalities"))

nothink = {"chat_template_kwargs": {"enable_thinking": False}}
content = lambda m: (m.get("content") or "")
chat("chat", [{"role": "user", "content": "Reply with exactly: validation-ok"}],
     lambda m: content(m).strip() == "validation-ok", max_tokens=16, **nothink)
chat("decode", [{"role": "user", "content": "Write a Python function that returns the first n primes, with a docstring."}],
     lambda m: "def " in content(m), max_tokens=256, **nothink)

tools = [{"type": "function", "function": {"name": "get_weather", "description": "Get current weather for a city",
          "parameters": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]}}}]
chat("tool", [{"role": "user", "content": "What's the weather in Dublin right now?"}],
     lambda m: any(c["function"]["name"] == "get_weather" and json.loads(c["function"]["arguments"]).get("city") == "Dublin"
                   for c in m.get("tool_calls") or []), tools=tools, max_tokens=256, **nothink)

img = "data:image/png;base64," + base64.b64encode(png(64, 64, (220, 20, 20))).decode()
chat("vision-solid", [{"role": "user", "content": [
    {"type": "image_url", "image_url": {"url": img}},
    {"type": "text", "text": "What single colour fills this image? One word."}]}],
     lambda m: "red" in content(m).lower(), max_tokens=16, **nothink)

ticket = "data:image/png;base64," + base64.b64encode(open(IMAGE, "rb").read()).decode()
chat("vision-document", [{"role": "user", "content": [
    {"type": "image_url", "image_url": {"url": ticket}},
    {"type": "text", "text": "Read this image. Give the ticket number, the destination, and the number of crates drawn."}]}],
     lambda m: all(s in content(m) for s in ("7291", "Galway")) and ("5" in content(m) or "five" in content(m).lower()),
     max_tokens=120, **nothink)

chat("reasoning", [{"role": "user", "content": "A train leaves at 09:40 and arrives at 13:05. How many minutes is the journey? Answer with just the number."}],
     lambda m: bool(m.get("reasoning_content")) and "205" in content(m), max_tokens=2048)

summary = {"base": BASE, "served_model_ids": [m["id"] for m in models["data"]], "props": {
    "n_ctx": props.get("default_generation_settings", {}).get("n_ctx"), "build_info": props.get("build_info"),
    "modalities": props.get("modalities")}, "all_ok": all(r["ok"] for r in results), "probes": results}
print("ALL OK" if summary["all_ok"] else "SOME PROBES FAILED")
if OUT:
    json.dump(summary, open(OUT, "w"), indent=1)
