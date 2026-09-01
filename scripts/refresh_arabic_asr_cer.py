"""Re-capture the Audar CER rows from the live Open Universal Arabic ASR board.

The registry's two Audar CER rows (Flash 13.43, Turbo 9.2) came from an
earlier snapshot of the board; the live board now reports Flash 13.65 /
Turbo 9.23 (Aug 20 2026 model update). WER rows already match live values.
This script rewrites only the two stale CER rows and records the live
board as the evidence source.
"""

import json
import re
import urllib.request
from pathlib import Path

BOARD = "https://huggingface.co/spaces/elmresearchcenter/open_universal_arabic_asr_leaderboard"
ROOT = Path("registry")


def live_scores():
    body = urllib.request.urlopen(
        urllib.request.Request(f"{BOARD}/raw/main/app.py", headers={"User-Agent": "Mozilla/5.0"}),
        timeout=30,
    ).read().decode(errors="replace")
    models = re.findall(r'"([^"]+)"', re.search(r'"Model": \[(.*?)\]', body, re.S).group(1))
    cer = [float(x) for x in re.findall(r"[0-9.]+", re.search(r'"Average CER[^"]*": \[(.*?)\]', body, re.S).group(1))]
    return dict(zip(models, cer))


def main():
    live = live_scores()
    print("live CER:", {k: v for k, v in live.items() if "Audar" in k})
    path = ROOT / "benchmark" / "cer.json"
    record = json.loads(path.read_text())
    changed = 0
    for row in record["rows"]:
        if row.get("variant") == "Audar-ASR-V1-Flash":
            row["score"] = live["audarai/Audar-ASR-V1-Flash"]
            changed += 1
        if row.get("variant") == "Audar-ASR-V1-Turbo":
            row["score"] = live["audarai/Audar-ASR-V1-Turbo"]
            changed += 1
    record["source"] = {
        "kind": "leaderboard-scrape",
        "url": BOARD,
        "paths": ["benchmarks/cer.html"],
    }
    path.write_text(json.dumps(record, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    print(f"rewrote {changed} Audar CER rows from the live board")


if __name__ == "__main__":
    main()
