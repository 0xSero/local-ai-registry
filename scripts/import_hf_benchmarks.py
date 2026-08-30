#!/usr/bin/env python3
"""Import scraped Hugging Face model benchmark scores into registry/benchmarks/.

Source is the static "HF Model & Benchmark Matrix" scrape (120 leaderboard pages,
one per benchmark). Each page holds a ranked table of [rank, variant, root, org,
score, conf, context] rows. Scores are reported measurements from public
leaderboards, not locally verified runs, so they never attach to recipes or
affect launch validation.
"""

import argparse
import json
import re
from pathlib import Path


SCHEMA = "local-ai-registry/v1"
ROW_HEADER = ("rank", "variant", "root", "org", "score", "conf", "context")


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def load_benchmark_meta(matrix):
    meta = {}
    for name in ("benchmarks.data.json", "speech.data.json"):
        path = matrix / name
        if not path.exists():
            continue
        for entry in json.loads(path.read_text())["b"]:
            meta[entry["id"]] = {"name": entry["name"], "category": entry.get("cat")}
    return meta


def source_url(html):
    match = re.search(r"https://huggingface\.co/(?:spaces|datasets)/[A-Za-z0-9_.\-/]+", html)
    return match.group(0) if match else None


def parse_rows(html):
    tables = re.findall(r"<table[^>]*>(.*?)</table>", html, re.S)
    if not tables:
        return []
    rows = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", tables[0], re.S):
        cells = [re.sub(r"<[^>]+>", "", cell).strip() for cell in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S)]
        if len(cells) != len(ROW_HEADER) or cells[0] == "rank":
            continue
        score = cells[4].rstrip("*").strip()
        rows.append({
            "rank": int(cells[0]),
            "variant": cells[1] or None,
            "root": cells[2] or None,
            "org": cells[3] or None,
            "score": float(score) if re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", score) else None,
            "conf": cells[5] or None,
            "context": cells[6] or None,
        })
    return rows


def import_page(matrix, page, meta, root):
    benchmark_id = page.stem
    html = page.read_text()
    rows = parse_rows(html)
    if not rows:
        return 0
    info = meta.get(benchmark_id, {})
    write(root / "benchmarks" / f"{benchmark_id}.json", {
        "schema_version": SCHEMA,
        "id": benchmark_id,
        "name": info.get("name") or benchmark_id,
        "category": info.get("category"),
        "source": {
            "kind": "leaderboard-scrape",
            "url": source_url(html),
            "paths": [f"benchmarks/{page.name}"],
        },
        "rows": rows,
    })
    return len(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("matrix", nargs="?", default=str(Path.home() / "projects/hf-model-benchmarks"))
    parser.add_argument("--root", default="registry")
    args = parser.parse_args()
    matrix = Path(args.matrix)
    root = Path(args.root)
    meta = load_benchmark_meta(matrix)
    imported = 0
    total_rows = 0
    for page in sorted((matrix / "benchmarks").glob("*.html")):
        count = import_page(matrix, page, meta, root)
        imported += 1
        total_rows += count
    print(f"imported {imported} benchmarks with {total_rows} score rows")


if __name__ == "__main__":
    main()
