#!/usr/bin/env python3
"""Add benchmark repository aliases from exact Hugging Face base-model metadata.

An unresolved leaderboard root is linked only when its public Hugging Face
metadata names one or more base repositories and every base repository already
maps to the same registry model. Ambiguous or absent lineage stays unresolved.
"""

from __future__ import annotations

import concurrent.futures
import json
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from benchmark_models import ALIASES_PATH, model_ids_by_repo, resolve_model_id

ROOT = Path(__file__).resolve().parents[1] / "registry"
CONTEXT = ssl.create_default_context()
API = (
    "https://huggingface.co/api/models/{repo}?"
    "expand%5B%5D=cardData&expand%5B%5D=tags&expand%5B%5D=sha"
)
BASE_TAG = re.compile(r"^base_model(?::[a-z0-9_-]+)*:(?P<repo>[^:]+/[^:]+)$", re.IGNORECASE)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def request_json(url: str, attempts: int = 5) -> dict[str, Any] | None:
    req = urllib.request.Request(url, headers={"User-Agent": "local-ai-registry/1.0"})
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(req, timeout=45, context=CONTEXT) as response:
                payload = json.load(response)
                return payload if isinstance(payload, dict) else None
        except urllib.error.HTTPError as error:
            if error.code in (401, 403, 404):
                return None
            if error.code != 429 or attempt == attempts - 1:
                raise
            delay = int(error.headers.get("Retry-After", "0") or 0) or 2**attempt
            time.sleep(min(delay, 60))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            if attempt == attempts - 1:
                raise
            time.sleep(2**attempt)
    return None


def repository_values(value: Any) -> set[str]:
    result: set[str] = set()
    if isinstance(value, str) and value.count("/") == 1:
        result.add(value)
    elif isinstance(value, list):
        for child in value:
            result.update(repository_values(child))
    elif isinstance(value, dict):
        for child in value.values():
            result.update(repository_values(child))
    return result


def base_repositories(payload: dict[str, Any]) -> set[str]:
    result = repository_values((payload.get("cardData") or {}).get("base_model"))
    for tag in payload.get("tags") or []:
        if not isinstance(tag, str):
            continue
        match = BASE_TAG.fullmatch(tag)
        if match:
            result.add(match.group("repo"))
    return result


def fetch(repo: str) -> tuple[str, dict[str, Any] | None, str | None]:
    try:
        url = API.format(repo=urllib.parse.quote(repo, safe="/"))
        payload = request_json(url)
        return repo, payload, None if payload is not None else "repository unavailable"
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        return repo, None, str(error)


def main() -> int:
    by_repo = model_ids_by_repo(ROOT)
    unresolved: set[str] = set()
    for path in (ROOT / "benchmark").glob("*.json"):
        for row in read_json(path).get("rows") or []:
            root = row.get("root")
            if (
                resolve_model_id(row, by_repo) is None
                and isinstance(root, str)
                and root.count("/") == 1
            ):
                unresolved.add(root)
    requested = {repo.lower() for repo in sys.argv[1:]}
    if requested:
        unresolved = {repo for repo in unresolved if repo.lower() in requested}

    derived: dict[str, str] = {}
    errors = ambiguous = no_lineage = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        for repo, payload, error in pool.map(fetch, sorted(unresolved)):
            if error is not None:
                errors += 1
                print(f"WARN {repo}: {error}", file=sys.stderr)
                continue
            bases = base_repositories(payload or {})
            if not bases or any(base.lower() not in by_repo for base in bases):
                no_lineage += 1
                continue
            model_ids = {by_repo[base.lower()] for base in bases}
            if len(model_ids) == 1:
                derived[repo.lower()] = model_ids.pop()
            else:
                ambiguous += 1

    aliases = read_json(ALIASES_PATH)
    updates = 0
    for repo, model_id in sorted(derived.items()):
        if aliases.get(repo) == model_id:
            continue
        if repo in aliases and aliases[repo] != model_id:
            ambiguous += 1
            continue
        aliases[repo] = model_id
        updates += 1
    if updates:
        ALIASES_PATH.write_text(json.dumps(aliases, indent=2, sort_keys=True) + "\n")

    print(
        f"unresolved repositories queried: {len(unresolved)}; aliases added: {updates}; "
        f"ambiguous: {ambiguous}; no mapped lineage: {no_lineage}; errors: {errors}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
