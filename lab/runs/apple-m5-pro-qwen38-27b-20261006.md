# Apple M5 Pro: Qwen3.8-27B at 200K, vision and MTP, 2026-10-06

One MacBook Pro (Mac17,9): Apple M5 Pro, 15-core CPU (5 super + 10 performance), **16-core GPU**, 48 GB unified memory at 307 GB/s, macOS 26.5. Host launches, no container. The machine was otherwise idle: no other model server running, and swap settled before each run. The gate runs used the launches exactly as `lab.py render` prints them (pinned packages in a fresh Python 3.12 venv, pinned weights, the same argv and environment).

## Lab runs (all six gates)

| Card | Recipe | Run | Decode (speed gate) | Prefill | Context gate |
|---|---|---|---|---|---|
| `apple-m5-pro-48gb` (new card) | `Youssofal/Qwen3.8-27B-MTPLX-Bare-Speed@b59d700`, `mtplx-qwen3.8-27b-4bit-mtp-200k@95e52b5404e3` | on the card | 22.3 tok/s (see token counting) | 179 tok/s | 166,625 tokens, recalled |
| `apple-m5-pro-24gb` | `leonsarmiento/Qwen3.8-27B-3bit-mlx@5fc234d`, `mlx-vlm-qwen3.8-27b-3bit-mtp-200k@ca64973a6aae` | proxy: same chip and bandwidth, 48 GB | 17.3 tok/s | 176 tok/s | 166,655 tokens, recalled; peak 17.72 GiB of the card's 20 GiB GPU budget |

Canonical runs: `apple-m5-pro-48gb.qwen3.8-27b.mtplx-qwen3.8-27b-4bit-mtp-200k.200k.20261006T030237.json` and `apple-m5-pro-24gb.qwen3.8-27b.mlx-vlm-qwen3.8-27b-3bit-mtp-200k.200k.20261006T032555.json`.

The M5 Pro 24 GB recipe had been proven only on an M5 Max (614 GB/s, 40-core GPU), and #110 estimated ~8–10 tok/s on a real M5 Pro. On the M5 Pro chip the speed gate measures 17.3 tok/s (two warm-up probes before it: 17.1 and 17.1), counted with the server's own tokenizer (`/v1/token/encode`). The proxy is the same SoC with the same memory bandwidth and the 16-core GPU, which is the lower M5 Pro GPU; only the memory size differs, and nothing caps it, so the proof records the measured peak against the card's budget, as `lab.py` does for every owner proxy run.

## Token counting on MTPLX

MTPLX 2.12.0 has no tokenize route (`/v1/token/encode`, `/tokenize` and `/v1/tokenize` answer 404), so `lab.py` falls back to `len(text) // 4` and the speed gate's 22.3 tok/s is an estimate. Three more runs of the same speed-gate prompt, counted with the model's own `tokenizer.json`, gave **20.5, 20.3 and 20.8 tok/s** (`apple-m5-pro-48gb.qwen3.8-27b.mtplx-tokenizer-and-vision.20261006.json`). Either way it clears 15 tok/s.

## Beyond the six gates

The gates do not check vision or the last 15% of the window. One request each, with a 448×448 PNG (a red circle and a blue square) followed by a ~199k-token haystack with a code planted at 40% depth (`long_probe.py` below):

| Build | Server | Prompt tokens | Answer | Peak |
|---|---|---|---|---|
| MTPLX 4-bit (48 GB) | fresh | 198,907 | `58213, red circle, blue square` (both right) | not reported by MTPLX; its cap is 36 GiB (`mx.set_memory_limit`), its plan 16.3 GB weights + 19,660 B/token q4 KV |
| mlx-vlm 3-bit (24 GB) | fresh | 198,937 | `58213; a red circle and a blue square.` (both right) | **18.46 GiB** (`mx.get_peak_memory`) of 20 GiB |
| mlx-vlm 3-bit (24 GB) | after the six gates (incl. the 166k context request) | 198,937 | the same, both right | **22.11 GiB**, over the 20 GiB budget |

MTPLX short-prompt vision: `The image contains a red circle and a blue square.` (225 prompt tokens, 5.1 s). Evidence, in row order: `apple-m5-pro-48gb.qwen3.8-27b.mtplx-199k-vision-fresh.20261006.json`, `apple-m5-pro-24gb.qwen3.8-27b.mlx-vlm-3bit-199k-vision-fresh.20261006.json`, `apple-m5-pro-24gb.qwen3.8-27b.mlx-vlm-3bit-199k-vision-after-gates.20261006.json`.

**24 GB caveat.** A fresh server takes an image plus a 199k-token prompt in 18.46 GiB, close to #110's 18.79 GiB on the M5 Max. But the same request on a server that had already served the six gates peaked at 22.11 GiB. mlx-vlm reports `mx.get_peak_memory()` over the process lifetime; it read 17.72 GiB at the context gate, only the short speed-gate request followed, and APC (prefix caching) is off, so the extra memory was allocated during this request. Why a warm server needs more was not pinned down. On a real 24 GB Mac (wired limit 20480 MiB) a second near-full-window request may therefore run out of GPU memory. The recipe's acceptance (everything through the 166k context gate, 17.72 GiB) is inside the budget either way. Restarting the server between near-200k jobs avoids it. A launcher change (for example clearing MLX's buffer cache before each prefill) would re-pin every mlx-vlm recipe that shares the launcher, so it is not part of this change.

## Commands

```sh
# server (each launch exactly as `python3 lab/lab.py render <recipe>` prints it), then:
python3 lab/lab.py try Youssofal/Qwen3.8-27B-MTPLX-Bare-Speed@b59d7002368575f08a58ba0d26686b53a9c162d6 \
  --model qwen3.8-27b --engine mtplx-qwen3.8-27b-4bit-mtp-200k --card apple-m5-pro-48gb \
  --on endpoint --endpoint http://127.0.0.1:18198 --gpu "Apple M5 Pro 48GB (16-core GPU)"
python3 lab/lab.py try leonsarmiento/Qwen3.8-27B-3bit-mlx@5fc234d9e6080b8388a11286380e801b7c9f535c \
  --model qwen3.8-27b --engine mlx-vlm-qwen3.8-27b-3bit-mtp-200k --card apple-m5-pro-24gb \
  --on endpoint --endpoint http://127.0.0.1:8080 --gpu "Apple M5 Pro 48GB (16-core GPU)" \
  --proxy-gpu "Apple M5 Pro 48GB (16-core GPU, same chip and 307 GB/s as the card)"
```

`long_probe.py` (run with the engine's venv Python, which has Pillow; `lab.chat` sends temperature 0.6):

```python
"""One request: an image plus a ~199k-token prompt with a code planted at 40% depth. Usage: long_probe.py ENDPOINT OUT.json"""
import base64, io, json, sys
sys.path.insert(0, "lab")  # run from the repo root
import lab
from PIL import Image, ImageDraw

ep, out_path = sys.argv[1], sys.argv[2]
served = lab.call(ep, "/v1/models", timeout=30)[0]["data"][0]["id"]
img = Image.new("RGB", (448, 448), "white")
d = ImageDraw.Draw(img)
d.ellipse((60, 60, 220, 220), fill=(220, 20, 20))
d.rectangle((250, 250, 400, 400), fill=(20, 60, 220))
buf = io.BytesIO()
img.save(buf, "PNG")
lines = [f"Line {i}: the archive notes that shipment {i * 7 % 997} left dock {i % 13} on schedule." for i in range(8640)]
lines.insert(int(len(lines) * 0.4), "The access code for the vault is 58213.")
question = ("\n\nTwo questions. 1) What is the access code for the vault? 2) What two shapes are in the image above and what "
            "color is each? Answer in one line: code, then shapes.")
c, u, secs = lab.chat(ep, served, [{"role": "user", "content": [
    {"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()}},
    {"type": "text", "text": " ".join(lines) + question}]}], max_tokens=4096)
content = c["message"].get("content") or ""
res = {"served": served, "prompt_tokens": u.get("prompt_tokens"), "completion_tokens": u.get("completion_tokens"),
       "seconds": round(secs, 1), "finish": c.get("finish_reason"), "content": content[-300:],
       "code_ok": "58213" in content, "vision_ok": all(w in content.lower() for w in ("red", "blue", "circle", "square"))}
if u.get("peak_memory_gb"):
    res["peak_gib"] = round(u["peak_memory_gb"] * 1e9 / 2**30, 2)
print(json.dumps(res, indent=1))
json.dump(res, open(out_path, "w"), indent=1)
```
