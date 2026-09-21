#!/usr/bin/env python3
"""One vision request against the live API. Exits non-zero if the model cannot see the image."""
import base64, json, sys, urllib.request

api, model = sys.argv[1], sys.argv[2]
# 8x8 solid red PNG
png = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAgAAAAICAYAAADED76LAAAAF0lEQVR42mP8z8BQz0AEYBxVSF+F"
    "AAB6qQb9zsB0mgAAAABJRU5ErkJggg==")
body = {
    "model": model, "stream": False,
    "messages": [{"role": "user", "content": [
        {"type": "text", "text": "What colour fills this image? Answer with one word."},
        {"type": "image_url", "image_url": {
            "url": "data:image/png;base64," + base64.b64encode(png).decode()}}]}],
}
req = urllib.request.Request(api.rstrip("/") + "/v1/chat/completions",
                             data=json.dumps(body).encode(),
                             headers={"Content-Type": "application/json"})
try:
    r = json.load(urllib.request.urlopen(req, timeout=180))
except Exception as e:
    sys.exit(f"vision request failed: {type(e).__name__}: {e}")
text = (r["choices"][0]["message"].get("content") or "").strip()
if not text:
    sys.exit("vision request returned empty content: the multimodal path is not working")
print(f"vision ok -> {text[:60]}")
