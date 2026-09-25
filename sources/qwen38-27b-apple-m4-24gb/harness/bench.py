#!/usr/bin/env python3
"""Short decode/prefill bench against a running llama-server. Prints one JSON line per prompt."""
import json, sys, urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8080"
LABEL = sys.argv[2] if len(sys.argv) > 2 else ""

PROMPTS = {
    "code": ("Write a Python function that returns the first n primes, with a docstring and type hints.", 200),
    "prose": ("Explain in plain prose, in about 200 words, why the sky is blue.", 200),
    "prefill4k": (" ".join(f"Line {i}: the quick brown fox jumps over the lazy dog." for i in range(330)) + "\nWhat number is the last line?", 16),
}

for name, (content, n) in PROMPTS.items():
    body = {"model": "qwen3.8-27b", "messages": [{"role": "user", "content": content}], "temperature": 0,
            "max_tokens": n, "chat_template_kwargs": {"enable_thinking": False}}
    req = urllib.request.Request(BASE + "/v1/chat/completions", json.dumps(body).encode(), {"Content-Type": "application/json"})
    t = json.load(urllib.request.urlopen(req, timeout=1800))["timings"]
    out = {"label": LABEL, "prompt": name, "prompt_n": t["prompt_n"], "pp_tps": round(t["prompt_per_second"], 1),
           "gen_n": t["predicted_n"], "tg_tps": round(t["predicted_per_second"], 2)}
    if "draft_n" in t:
        out["accept"] = f'{t["draft_n_accepted"]}/{t["draft_n"]}'
    print(json.dumps(out), flush=True)
