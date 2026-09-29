#!/usr/bin/env python3
"""Long-context recall check, 3 trials: plant a code at 85% depth of a prompt filling ~80% of the window.

Separates "model couldn't find it" from "model ran out of answer budget while thinking":
each trial records whether the code appears in the answer, in the reasoning, and whether generation hit max_tokens.
usage: recall_check.py --url http://127.0.0.1:8090/v1 --model bench --ctx 131072 --label "..."
"""
import argparse, json, os, random, string, time, urllib.request

WORDS = ["def", "return", "value", "config", "server", "token", "index", "buffer", "stream", "model", "cache",
         "thread", "window", "layer", "vector", "matrix", "schema", "record", "commit", "branch"]


def filler(n, seed):
    r = random.Random(seed)
    return " ".join(r.choice(WORDS) for _ in range(n))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8090/v1")
    ap.add_argument("--key", default="none")
    ap.add_argument("--model", default="bench")
    ap.add_argument("--ctx", type=int, required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--trials", type=int, default=3)
    ap.add_argument("--max-tokens", type=int, default=4096)
    ap.add_argument("--sampled", action="store_true", help="Qwen thinking-mode sampling (temp 1.0, top_p 0.95, top_k 20) instead of greedy")
    a = ap.parse_args()
    results = []
    for t in range(a.trials):
        code = f"ZV-{random.randint(1000, 9999)}-{''.join(random.choices(string.ascii_uppercase, k=4))}"
        n = int(a.ctx * 0.80); cut = int(n * 0.85)
        body = filler(cut, 100 + t) + f"\nThe secret deploy code is {code}.\n" + filler(n - cut, 200 + t)
        samp = {"temperature": 1.0, "top_p": 0.95, "top_k": 20, "min_p": 0.0} if a.sampled else {"temperature": 0}
        req = {"model": a.model, **samp, "max_tokens": a.max_tokens,
               "messages": [{"role": "user", "content": body + "\n\nWhat is the secret deploy code? Reply with only the code."}]}
        t0 = time.time()
        r = json.load(urllib.request.urlopen(urllib.request.Request(
            a.url + "/chat/completions", data=json.dumps(req).encode(),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {a.key}"}), timeout=3600))
        msg, ch = r["choices"][0]["message"], r["choices"][0]
        content, reasoning = msg.get("content") or "", msg.get("reasoning_content") or ""
        res = {"trial": t + 1, "found_in_answer": code in content, "found_in_reasoning": code in reasoning,
               "hit_max_tokens": ch.get("finish_reason") == "length", "completion_tokens": r["usage"]["completion_tokens"],
               "prompt_tokens": r["usage"]["prompt_tokens"], "seconds": round(time.time() - t0), "answer": content.strip()[:60]}
        results.append(res); print(json.dumps(res))
    summary = {"label": a.label, "ctx": a.ctx, "passed": f"{sum(x['found_in_answer'] for x in results)}/{a.trials}",
               "truncated": sum(x["hit_max_tokens"] for x in results), "max_tokens": a.max_tokens, "sampling": "qwen-thinking" if a.sampled else "greedy"}
    print(json.dumps(summary))
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "recall.jsonl"), "a") as f:
        f.write(json.dumps({**summary, "trials": results}) + "\n")


if __name__ == "__main__":
    main()
