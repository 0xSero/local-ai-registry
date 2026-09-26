#!/usr/bin/env python3
"""Long-context coherence ladder against a running llama-server (stdlib only).

For each target level, the script builds a prose haystack from the llama.cpp docs (code blocks removed).
It puts three needle sentences at 10%, 50% and 90% depth and a 1280x800 document image
(ticket-1280.png) at the start. At the end it asks five questions: the three needles, the ticket
number in the image, and the number of crates drawn in the image. The request is cold
(cache_prompt=false), non-streaming, temperature 0, thinking off. The script writes one receipt
JSON per level into OUTDIR and prints one summary line per level.

If the corpus is shorter than a level needs, build() repeats the corpus. At the 202000 level,
about the last third of the haystack is a repeat of the corpus start, and the 90% needle is in that repeat.

usage:
  git clone https://github.com/ggml-org/llama.cpp && git -C llama.cpp checkout a25c9865fe03c954c93fd755b5d79ae86ba99750
  HAYSTACK_SRC=llama.cpp python3 ladder.py OUTDIR 4096 32768 202000     (the levels in the evidence)
env: BASE (server URL), HAYSTACK_SRC, IMAGE, IMG_TOKENS,
     LADDER_TIMEOUT (seconds per request, default 14400; the 200,709-token rung took 9,425 s on a
     10-core-GPU M4, so set 43200 on slower chips).
"""
import base64, glob, json, os, re, struct, sys, threading, time, urllib.request, zlib, subprocess, hashlib

BASE = os.environ.get("BASE", "http://127.0.0.1:8080")
SRC = os.environ.get("HAYSTACK_SRC", "llama.cpp")          # checkout of ggml-org/llama.cpp; evidence used commit a25c986
NEEDLES = [("10%", 0.10, "The harbour pilot's call sign is AMBER-FALCON-4417."),
           ("50%", 0.50, "The vault combination written on the whiteboard is 83-19-62."),
           ("90%", 0.90, "The name of the ship's cat is Professor Wobblesworth.")]
IMAGE = os.environ.get("IMAGE", os.path.join(os.path.dirname(os.path.abspath(__file__)), "ticket-1280.png"))
QUESTION = ("Answer five questions using only the material above. "
            "1) What is the harbour pilot's call sign? 2) What is the vault combination? "
            "3) What is the name of the ship's cat? 4) What ticket number is printed in the image at the very start? "
            "5) How many crates are drawn in that image? Reply as five short numbered lines.")
IMG_TOKENS = int(os.environ.get("IMG_TOKENS", "1100"))       # 1280x800 at patch 16, merge 2 -> ~1000
CORPUS_SHA256 = "774c20209d5d619000db2843cd9d5c6bf9ba8d51b3092796c23a9fe955f9145d"  # 472,323 chars at a25c9865
EXPECT = ["AMBER-FALCON-4417", "83-19-62", "Wobblesworth", "7291", "5"]


def post(path, body, timeout=float(os.environ.get("LADDER_TIMEOUT", "14400"))):
    req = urllib.request.Request(BASE + path, json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def png(w, h, rgb):
    raw = zlib.compress((b"\x00" + bytes(rgb) * w) * h)
    c = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    return b"\x89PNG\r\n\x1a\n" + c(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + c(b"IDAT", raw) + c(b"IEND", b"")


def corpus():
    files = sorted(glob.glob(f"{SRC}/docs/**/*.md", recursive=True) + glob.glob(f"{SRC}/tools/**/*.md", recursive=True)
                   + glob.glob(f"{SRC}/examples/**/*.md", recursive=True) + glob.glob(f"{SRC}/*.md"))
    if not files:
        sys.exit(f"no .md files under {os.path.abspath(SRC)}: set HAYSTACK_SRC to a ggml-org/llama.cpp checkout")
    text = "\n\n".join(open(f, errors="ignore").read() for f in files)
    text = re.sub(r"```.*?```", "", text, flags=re.S)          # prose only, no code blocks
    text = re.sub(r"\n{3,}", "\n\n", text)
    if hashlib.sha256(text.encode()).hexdigest() != CORPUS_SHA256:
        print("warning: corpus differs from the evidence corpus (llama.cpp a25c9865)", file=sys.stderr)
    return text


def ntok(s):
    return len(post("/tokenize", {"content": s})["tokens"])


def build(target, text, chars_per_tok):
    """Return haystack string with needles whose token count lands close to target."""
    budget = max(target - ntok(QUESTION) - IMG_TOKENS - 64, 256)  # template + image tokens headroom
    n_chars = int(budget * chars_per_tok)
    while len(text) < n_chars:
        text = text + "\n\n" + text
    hay = text[:n_chars]
    for _, frac, needle in sorted(NEEDLES, key=lambda x: -x[1]):
        cut = hay.rfind("\n\n", 0, int(len(hay) * frac)) + 2
        hay = hay[:cut] + needle + "\n\n" + hay[cut:]
    return hay


def grade(ans):
    """Check each expected value against its own numbered answer line (so '5)' numbering can't satisfy '5')."""
    lines = {}
    for line in ans.splitlines():
        m = re.match(r"^\s*\**\s*(\d+)\s*[.):]\s*(.*)$", line)
        if m:
            lines.setdefault(int(m.group(1)), m.group(2))
    out = {}
    for i, e in enumerate(EXPECT, 1):
        text = lines.get(i, "").lower()
        alts = [e.lower()] + (["five"] if e == "5" else [])
        out[e] = any(a in text for a in alts)
    return out


def wired_gb():
    out = subprocess.run(["vm_stat"], capture_output=True, text=True).stdout
    m = re.search(r"Pages wired down:\s+(\d+)", out)
    return int(m.group(1)) * 16384 / 1e9 if m else None


def main():
    outdir, levels = sys.argv[1], [int(x) for x in sys.argv[2:]]
    os.makedirs(outdir, exist_ok=True)
    text = corpus()
    sample = text[:20000]
    cpt = len(sample) / ntok(sample)
    img = "data:image/png;base64," + base64.b64encode(open(IMAGE, "rb").read()).decode()
    props = json.load(urllib.request.urlopen(BASE + "/props", timeout=30))
    for level in levels:
        lcpt = cpt                                              # per-level estimate; never leaks across levels
        hay = build(level, text, lcpt)
        for _ in range(5):                                      # correct chars/token estimate toward target
            got = ntok(hay) + ntok(QUESTION) + IMG_TOKENS + 64
            if abs(got - level) / level < 0.01:
                break
            lcpt *= level / got
            hay = build(level, text, lcpt)
        body = {"model": "qwen3.8-27b", "temperature": 0, "max_tokens": 96, "cache_prompt": False,
                "chat_template_kwargs": {"enable_thinking": False},
                "messages": [{"role": "user", "content": [
                    {"type": "image_url", "image_url": {"url": img}},
                    {"type": "text", "text": hay + "\n\n" + QUESTION}]}]}
        peak = [wired_gb() or 0]
        done = threading.Event()
        def sample_mem():
            while not done.wait(5):
                peak[0] = max(peak[0], wired_gb() or 0)
        threading.Thread(target=sample_mem, daemon=True).start()
        t0 = time.time()
        err = None
        try:
            r = post("/v1/chat/completions", body)
        except Exception as e:                                  # record failures as evidence too
            r, err = None, repr(e)
        wall = time.time() - t0
        done.set()
        rec = {"level": level, "wall_s": round(wall, 1), "peak_wired_gb": round(peak[0], 2), "error": err,
               "haystack_sha256": hashlib.sha256(hay.encode()).hexdigest(), "needles": [n[2] for n in NEEDLES],
               "server_props": {"n_ctx": props.get("default_generation_settings", {}).get("n_ctx"),
                                "build_info": props.get("build_info"), "modalities": props.get("modalities")}}
        if r:
            ans = r["choices"][0]["message"].get("content") or ""
            t = r.get("timings", {})
            rec.update({"answer": ans, "timings": t, "usage": r.get("usage"),
                        "checks": grade(ans)})
            rec["ok"] = all(rec["checks"].values())
        else:
            rec["ok"] = False
        path = f"{outdir}/ladder-{level:06d}.json"
        json.dump(rec, open(path, "w"), indent=1)
        t = rec.get("timings", {})
        print(json.dumps({"level": level, "ok": rec["ok"], "prompt_n": t.get("prompt_n"),
                          "pp_tps": round(t.get("prompt_per_second", 0), 1), "tg_tps": round(t.get("predicted_per_second", 0), 2),
                          "accept": f'{t.get("draft_n_accepted")}/{t.get("draft_n")}', "wall_s": rec["wall_s"],
                          "peak_wired_gb": rec["peak_wired_gb"], "checks": rec.get("checks"), "error": err}), flush=True)


if __name__ == "__main__":
    main()
