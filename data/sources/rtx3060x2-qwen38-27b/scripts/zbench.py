#!/usr/bin/env python3
"""zbench: benchmark any OpenAI-compatible endpoint on zver (LM Studio, llama-server, ...).

Measures generation speed, TTFT, long-prompt prefill speed, per-GPU peak VRAM/temp/power,
plus two opencode-relevant gates: a tool call and long-context recall.
Appends a markdown row to bench.md and a JSON line to bench.jsonl next to this script.

usage: zbench.py --url http://127.0.0.1:1234/v1 --model qwen3.8-27b --label "LMS Q4_K_M 32k q8 MTP" --ctx 32768
"""
import argparse, json, os, random, string, subprocess, threading, time, urllib.error, urllib.request
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))


class GpuSampler(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.peak, self.stop_flag = {}, False

    def run(self):
        while not self.stop_flag:
            out = subprocess.run(["nvidia-smi", "--query-gpu=index,memory.used,temperature.gpu,power.draw",
                                  "--format=csv,noheader,nounits"], capture_output=True, text=True).stdout
            for line in out.strip().splitlines():
                i, mem, temp, pw = [x.strip() for x in line.split(",")]
                p = self.peak.setdefault(int(i), [0, 0, 0])
                p[0], p[1], p[2] = max(p[0], float(mem)), max(p[1], float(temp)), max(p[2], float(pw))
            time.sleep(0.5)


def post(url, key, body, stream):
    req = urllib.request.Request(url + "/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
    try:
        return urllib.request.urlopen(req, timeout=1800) if stream else json.load(urllib.request.urlopen(req, timeout=1800))
    except urllib.error.HTTPError as e:
        raise SystemExit(f"HTTP {e.code} from server: {e.read().decode()[:800]}")


def stream_chat(a, messages, max_tokens, extra=None):
    """Returns (ttft_s, gen_s, completion_tokens, prompt_tokens, text)."""
    body = {"model": a.model, "messages": messages, "max_tokens": max_tokens, "temperature": 0, "stream": True,
            "stream_options": {"include_usage": True}, **(extra or {})}
    t0, t_first, text, usage = time.time(), None, "", {}
    with post(a.url, a.key, body, True) as r:
        for raw in r:
            line = raw.decode().strip()
            if not line.startswith("data:") or line.endswith("[DONE]"):
                continue
            d = json.loads(line[5:])
            if d.get("usage"):
                usage = d["usage"]
            for ch in d.get("choices", []):
                delta = ch.get("delta", {})
                piece = (delta.get("content") or "") + (delta.get("reasoning_content") or "")
                if piece and t_first is None:
                    t_first = time.time()
                text += delta.get("content") or ""
    t_end = time.time()
    t_first = t_first or t_end
    return t_first - t0, t_end - t_first, usage.get("completion_tokens", 0), usage.get("prompt_tokens", 0), text


def filler(n_words, seed):
    rnd = random.Random(seed)
    words = ["def", "return", "value", "config", "server", "token", "index", "buffer", "stream", "model", "cache",
             "thread", "window", "layer", "vector", "matrix", "schema", "record", "commit", "branch"]
    return " ".join(rnd.choice(words) for _ in range(n_words))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:1234/v1")
    ap.add_argument("--key", default=os.environ.get("ZBENCH_KEY", "none"))
    ap.add_argument("--model", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--ctx", type=int, required=True, help="loaded context length (recall gate plants at 85%%)")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--gen-tokens", type=int, default=256)
    ap.add_argument("--prefill-words", type=int, default=6000)
    ap.add_argument("--no-thinking", action="store_true", help="send chat_template_kwargs enable_thinking=false")
    ap.add_argument("--skip-recall", action="store_true")
    a = ap.parse_args()
    extra = {"chat_template_kwargs": {"enable_thinking": False}} if a.no_thinking else {}

    gpu = GpuSampler(); gpu.start()
    nonce = lambda: "".join(random.choices(string.ascii_lowercase, k=12))

    # warmup
    stream_chat(a, [{"role": "user", "content": "Say hi."}], 16, extra)

    # generation speed: coding prompt (what opencode does), greedy
    gens, ttfts = [], []
    for _ in range(a.runs):
        msg = f"[{nonce()}] Write a Python function that parses an nginx access log line into a dict, with a docstring and tests."
        ttft, gen_s, ct, _, _ = stream_chat(a, [{"role": "user", "content": msg}], a.gen_tokens, extra)
        gens.append(ct / gen_s if gen_s > 0 else 0); ttfts.append(ttft)
    gen_tps, ttft = sorted(gens)[len(gens) // 2], sorted(ttfts)[len(ttfts) // 2]

    # prefill speed on a long, cache-busted prompt
    long_prompt = f"[{nonce()}]\n" + filler(a.prefill_words, nonce()) + "\n\nSummarize the above in one word."
    p_ttft, _, _, p_tokens, _ = stream_chat(a, [{"role": "user", "content": long_prompt}], 1, extra)
    prefill_tps = p_tokens / p_ttft if p_ttft > 0 else 0

    # tool-call gate
    tools = [{"type": "function", "function": {"name": "get_weather", "description": "Get current weather for a city",
              "parameters": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]}}}]
    r = post(a.url, a.key, {"model": a.model, "temperature": 0, "max_tokens": 2048, "tools": tools, **extra,
                            "messages": [{"role": "user", "content": "What's the weather in Reykjavik right now? Use the tool."}]}, False)
    calls = r["choices"][0]["message"].get("tool_calls") or []
    tool_ok = bool(calls) and "reykjavik" in json.dumps(calls).lower()

    # long-context recall gate: plant a code at ~85% depth of the loaded window
    recall = "skipped"
    if not a.skip_recall:
        code = f"ZV-{random.randint(1000, 9999)}-{nonce()[:4].upper()}"
        n_words = int(a.ctx * 0.80)  # filler is ~1 token per word
        cut = int(n_words * 0.85)
        body = filler(cut, 1) + f"\nThe secret deploy code is {code}.\n" + filler(n_words - cut, 2)
        _, _, _, rp_tokens, text = stream_chat(a, [{"role": "user", "content": body + "\n\nWhat is the secret deploy code? Reply with only the code."}], 4096,
                                          {**extra, "temperature": 1.0, "top_p": 0.95, "top_k": 20, "min_p": 0.0})  # greedy can think-loop; see recall_check.py
        recall = f"{'pass' if code in text else 'FAIL'} @{rp_tokens // 1000}k"

    gpu.stop_flag = True; gpu.join()
    peaks = gpu.peak
    vram = " + ".join(f"{peaks[i][0] / 1024:.1f}" for i in sorted(peaks))
    temp = "/".join(f"{peaks[i][1]:.0f}" for i in sorted(peaks))
    power = "/".join(f"{peaks[i][2]:.0f}" for i in sorted(peaks))

    row = {"time": datetime.now().strftime("%Y-%m-%d %H:%M"), "label": a.label, "model": a.model, "ctx": a.ctx,
           "gen_tps": round(gen_tps, 1), "ttft_s": round(ttft, 2), "prefill_tps": round(prefill_tps, 0),
           "prefill_tokens": p_tokens, "vram_gb": vram, "temp_c": temp, "power_w": power,
           "tool_call": "pass" if tool_ok else "FAIL", "recall": recall, "thinking": not a.no_thinking}
    with open(os.path.join(HERE, "bench.jsonl"), "a") as f:
        f.write(json.dumps(row) + "\n")
    print(json.dumps(row, indent=1))


if __name__ == "__main__":
    main()
