#!/usr/bin/env python3
"""Refresh Hugging Face download counts on model records.

For every model with a known huggingface.repository, fetches the repo's
30-day and all-time download counts from the public HF API and stores them
at model.downloads. Models without a repository (or whose repo the API does
not know) get explicit nulls — never guesses. Run from the repository root;
finish with format + validate before committing.
"""

import concurrent.futures
import datetime as dt
import glob
import json
import ssl
import sys
import urllib.error
import urllib.request

API = "https://huggingface.co/api/models/{repo}?expand%5B%5D=downloads&expand%5B%5D=downloadsAllTime"
CONTEXT = ssl.create_default_context()


def fetch(repo):
    request = urllib.request.Request(API.format(repo=repo), headers={"User-Agent": "local-ai-registry/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=20, context=CONTEXT) as response:
            payload = json.load(response)
        return repo, payload.get("downloads"), payload.get("downloadsAllTime"), None
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as error:
        return repo, None, None, str(error)


def main() -> int:
    captured_at = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    paths = sorted(glob.glob("registry/model/*.json"))
    records = {p: json.load(open(p)) for p in paths}
    repos = {}
    for p, d in records.items():
        repo = (d.get("huggingface") or {}).get("repository")
        if isinstance(repo, str) and repo:
            repos.setdefault(repo, []).append(p)

    results = {}
    errors = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        for repo, d30, dall, error in pool.map(fetch, sorted(repos)):
            results[repo] = (d30, dall)
            if error:
                errors += 1
                print(f"WARN {repo}: {error}", file=sys.stderr)

    for p, d in records.items():
        repo = (d.get("huggingface") or {}).get("repository")
        d30, dall = results.get(repo, (None, None))
        previous = d.get("downloads") or {}
        if d30 is None and previous.get("last_30d") is not None:
            continue  # fetch failed or repo unqueried: keep the prior counts
        d["downloads"] = {
            "last_30d": d30,
            "all_time": dall,
            "captured_at": captured_at,
            "source": "huggingface-api",
        }
        open(p, "w").write(json.dumps(d, indent=2, sort_keys=True, ensure_ascii=False) + "\n")

    known = sum(1 for r in results.values() if r[0] is not None)
    print(f"models: {len(paths)}; repos queried: {len(repos)}; with 30d counts: {known}; fetch errors: {errors}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
