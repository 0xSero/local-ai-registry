"""Decode speed at long context: one ~N-token prompt, thinking off, 256 tokens out; prints server timings."""
import json, sys, time, urllib.request
N = int(sys.argv[1]); label = sys.argv[2]
line = "Line {i}: the archive notes that shipment {a} left dock {b} on schedule."
text = " ".join(line.format(i=i, a=i * 7 % 997, b=i % 13) for i in range(N // 24))
body = {"model": json.load(urllib.request.urlopen("http://127.0.0.1:8080/health"))["loaded_model"],
        "messages": [{"role": "user", "content": text + "\n\nSummarise the pattern of these records in about 150 words."}],
        "max_tokens": 256, "temperature": 0, "chat_template_kwargs": {"enable_thinking": False}}
t = time.monotonic()
req = urllib.request.Request("http://127.0.0.1:8080/v1/chat/completions", json.dumps(body).encode(), {"Content-Type": "application/json"})
out = json.load(urllib.request.urlopen(req, timeout=7200))
tm, u = out.get("timings", {}), out["usage"]
print(json.dumps({"label": label, "prompt_tokens": u["prompt_tokens"], "completion_tokens": u["completion_tokens"],
                  "decode_tok_s": round(tm.get("predicted_per_second", 0), 2), "prefill_tok_s": round(tm.get("prompt_per_second", 0), 1),
                  "draft": f"{tm.get('draft_n_accepted')}/{tm.get('draft_n')}", "peak_gib": round(tm.get("peak_memory", 0) * 1e9 / 2**30, 2),
                  "wall_s": round(time.monotonic() - t, 1)}))
