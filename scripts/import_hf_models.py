#!/usr/bin/env python3
"""Import leaderboard-referenced models from the Hugging Face API.

Benchmark rows join models only through a registered Hugging Face
repository. This importer registers the base repos that appear on the
scraped leaderboards but are missing from registry/model/, so their
scores can surface. Everything recorded comes from the HF API response:
parameter counts from safetensors metadata, download counts, and the
confirmed public identity. Fields the API does not report stay null
with unknown-state facts. Repos the API rejects are skipped, never
guessed.

Usage: python3 scripts/import_hf_models.py roots.json  (a JSON array of
"owner/repo" strings). Rerun stamp_benchmark_models.py and the index/
format/validate pipeline afterwards.
"""

import concurrent.futures
import datetime as dt
import json
import re
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path

API = "https://huggingface.co/api/models/{repo}?expand[]=safetensors&expand[]=config&expand[]=downloads&expand[]=downloadsAllTime"
REGISTRY = Path("registry/model")
CONTEXT = ssl.create_default_context()


def slug(value):
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9.]+", "-", value.lower())).strip("-").replace(".", "-")


def family_of(basename):
    match = re.match(r"[A-Za-z]+", basename)
    return match.group(0).lower() if match else "unknown"


def fetch(repo):
    request = urllib.request.Request(API.format(repo=repo), headers={"User-Agent": "local-ai-registry/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=25, context=CONTEXT) as response:
            return repo, json.load(response), None
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as error:
        return repo, None, str(error)


def provenance(kind, url, captured_at):
    return {"captured_at": captured_at, "sources": [{"kind": kind, "url": url, "captured_at": captured_at}]}


def unknown_fact(captured_at):
    return {
        "state": "unknown",
        "reason": "not-observed",
        "provenance": provenance("registry-enrichment", "https://github.com/0xSero/local-ai-registry", captured_at),
    }


def build_record(repo, payload, captured_at):
    total = (payload.get("safetensors") or {}).get("total")
    if not isinstance(total, int) or total <= 0:
        return None, "no safetensors parameter count"
    params = round(total / 1e9, 2) if total < 10e9 else round(total / 1e9)
    if params <= 0:
        params = round(total / 1e9, 3)
    basename = repo.split("/")[-1]
    api_url = f"https://huggingface.co/api/models/{repo}"
    return {
        "schema_version": "local-ai-registry/v1",
        "id": slug(basename),
        "name": basename,
        "family": family_of(basename),
        "params": params,
        "active_params": None,
        "architecture": None,
        "url": f"https://huggingface.co/{repo}",
        "huggingface": {
            "link_type": "repository",
            "repository": repo,
            "url": f"https://huggingface.co/{repo}",
            "status": "known",
            "reason": "hf-api-confirmed-public",
            "provenance": provenance("huggingface-api", api_url, captured_at),
        },
        "downloads": {
            "last_30d": payload.get("downloads"),
            "all_time": payload.get("downloadsAllTime"),
            "captured_at": captured_at,
            "source": "huggingface-api",
        },
        "facts": {
            "params": {
                "state": "known",
                "reason": "safetensors-parameter-metadata",
                "provenance": provenance("huggingface-api", api_url, captured_at),
            },
            "active_params": unknown_fact(captured_at),
            "architecture": unknown_fact(captured_at),
        },
        "provenance": provenance("huggingface-api", api_url, captured_at),
    }, None


def main() -> int:
    roots = json.loads(Path(sys.argv[1]).read_text())
    captured_at = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    existing_ids = {path.stem for path in REGISTRY.glob("*.json")}
    created = skipped = collided = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        for repo, payload, error in pool.map(fetch, sorted(set(roots))):
            if error:
                print(f"SKIP {repo}: {error}", file=sys.stderr)
                skipped += 1
                continue
            record, reason = build_record(repo, payload, captured_at)
            if record is None:
                print(f"SKIP {repo}: {reason}", file=sys.stderr)
                skipped += 1
                continue
            if record["id"] in existing_ids:
                print(f"COLLISION {repo}: id {record['id']} already exists — skipped", file=sys.stderr)
                collided += 1
                continue
            existing_ids.add(record["id"])
            (REGISTRY / f"{record['id']}.json").write_text(
                json.dumps(record, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
            )
            created += 1
    print(f"created {created} models; skipped {skipped}; id collisions {collided}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
