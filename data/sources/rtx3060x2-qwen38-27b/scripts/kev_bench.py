#!/usr/bin/env python3
"""Smoke-test + latency bench for a TypeSafe-compatible /v1/systemone server (Kev locally, or hosted Jev).

usage: kev_bench.py [--url http://127.0.0.1:8009] [--key-file ~/.config/kev/api-key] [--model kev]
Prints each decision with its probabilities and wall-clock latency; appends a summary line to kev_bench.jsonl.
"""
import argparse, json, os, statistics, time, urllib.request
from datetime import datetime

STEER = {"type": "choice", "instructions": "A coding agent is mid-task. Should this new message change the current task (steer) or wait until it is done (follow-up)?",
         "criteria": {"steer": "adjusts or constrains the current task", "follow-up": "a separate task for afterwards"}}
ROUTE = {"type": "choice", "instructions": "Which model should handle this request?",
         "criteria": {"local": "local 27B coding model: routine edits, small bugs, tests, explanations",
                      "cloud": "frontier cloud model: large refactors, architecture, subtle multi-file debugging"}}
KEEP = {"type": "noul", "instructions": "Is this tool result still needed to finish the user's current task?"}
URGENT = {"type": "score", "instructions": "How urgent is this message?", "criteria": ["not urgent", "somewhat urgent", "very urgent"]}

CASES = [
    ("steer", "Actually, preserve the public API.", STEER, "steer"),
    ("steer", "Only change the validation helper, not the UI.", STEER, "steer"),
    ("steer", "After this, summarize yesterday's release notes.", STEER, "follow-up"),
    ("steer", "What is the weather in Lisbon?", STEER, "follow-up"),
    ("route", "Rename the variable `cnt` to `count` in utils.py.", ROUTE, "local"),
    ("route", "Add a pytest test for parse_date() covering leap years.", ROUTE, "local"),
    ("route", "Redesign the auth layer across the Rails app and the mobile client so sessions survive token rotation; keep backward compatibility.", ROUTE, "cloud"),
    ("route", "Intermittent deadlock between the job queue and the DB pool under load; logs attached from three services.", ROUTE, "cloud"),
    ("keep", {"task": "fix failing test test_calc.py::test_add", "tool_result": "$ python -m pytest -q\nF\ntest_calc.py:4: AssertionError: assert add(2, 3) == 5 (got -1)"}, KEEP, "yes"),
    ("keep", {"task": "fix failing test test_calc.py::test_add", "tool_result": "$ ls ~/Downloads\nIMG_2231.jpg  receipt.pdf  whimsy/"}, KEEP, "no"),
    ("urgent", "The production site is down and customers can't check out.", URGENT, "2"),
]


def call(url, key, model, state, q):
    body = {"model": model, "state": state, "questions": {"q": q}}
    req = urllib.request.Request(url + "/v1/systemone", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
    t = time.time()
    r = json.load(urllib.request.urlopen(req, timeout=300))
    return r["answers"]["q"], (time.time() - t) * 1000


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8009")
    ap.add_argument("--key-file", default=os.path.expanduser("~/.config/kev/api-key"))
    ap.add_argument("--model", default="kev")
    ap.add_argument("--label", default="Kev-4B CPU")
    a = ap.parse_args()
    key = open(a.key_file).readline().strip()

    call(a.url, key, a.model, "warmup", STEER)  # first call pays one-time setup
    lat, right = [], 0
    for kind, state, q, want in CASES:
        ans, ms = call(a.url, key, a.model, state, q)
        got = ans.get("choice") if ans["type"] == "choice" else (("yes" if ans["noul"] >= 0.5 else "no") if ans["type"] == "noul" else str(round(ans["score"])))
        ok = got == want; right += ok; lat.append(ms)
        detail = ans.get("probabilities") or {"p_yes": round(ans.get("noul", 0), 3)}
        print(f"{'✓' if ok else '✗'} {ms:7.0f} ms  {kind:6} want={want:9} got={got:9} {json.dumps({k: round(v, 3) for k, v in detail.items()})}  | {str(state)[:60]}")

    long_state = {"task": "fix failing test", "tool_result": "\n".join(f"line {i}: DEBUG worker heartbeat ok, queue depth {i % 7}" for i in range(400))}
    _, long_ms = call(a.url, key, a.model, long_state, KEEP)
    summary = {"time": datetime.now().strftime("%Y-%m-%d %H:%M"), "label": a.label, "correct": f"{right}/{len(CASES)}",
               "median_ms": round(statistics.median(lat)), "max_ms": round(max(lat)), "long_state_ms": round(long_ms)}
    print(json.dumps(summary))
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "kev_bench.jsonl"), "a") as f:
        f.write(json.dumps(summary) + "\n")


if __name__ == "__main__":
    main()
