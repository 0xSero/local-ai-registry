#!/usr/bin/env python3
"""Fill MoE active-parameter counts from exact-revision Hugging Face model cards.

Only total/active pairs in the same short model-card passage are accepted. The
published total must agree with the registry's parameter count, and every
matching passage must agree on the active count; comparisons and ambiguous
cards are therefore skipped rather than guessed.
"""

from __future__ import annotations

import concurrent.futures
import datetime as dt
import html
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

REGISTRY = Path(__file__).resolve().parents[1] / "registry"
CONTEXT = ssl.create_default_context()
API = "https://huggingface.co/api/models/{repo}?expand%5B%5D=sha"
README = "https://huggingface.co/{repo}/resolve/{revision}/README.md"

PAIR_PATTERNS = (
    re.compile(
        r"(?:total\s+)?(?:params?|parameters?)\s*[:|]\s*"
        r"(?P<total>\d+(?:\.\d+)?)\s*(?P<total_unit>b|t|billion|trillion).{0,160}?"
        r"(?:active|activated)\s+(?:params?|parameters?)\s*[:|]\s*"
        r"(?P<active>\d+(?:\.\d+)?)\s*"
        r"(?P<active_unit>m|b|t|million|billion|trillion)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:total\s+)?(?:params?|parameters?)\s*\|\s*"
        r"(?:active|activated)\s+(?:params?|parameters?).{0,500}?"
        r"\|\s*(?P<total>\d+(?:\.\d+)?)\s*"
        r"(?P<total_unit>b|t|billion|trillion)\s*\|\s*"
        r"(?P<active>\d+(?:\.\d+)?)\s*"
        r"(?P<active_unit>m|b|t|million|billion|trillion)\s*\|",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?P<total>\d+(?:\.\d+)?)\s*(?P<total_unit>b|t|billion|trillion)"
        r"(?:[-\s]+parameters?)?.{0,160}?"
        r"(?P<active>\d+(?:\.\d+)?)\s*"
        r"(?P<active_unit>m|b|t|million|billion|trillion)\s+"
        r"(?:params?|parameters?\s+)?(?:active|activated)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?P<active>\d+(?:\.\d+)?)\s*"
        r"(?P<active_unit>m|b|t|million|billion|trillion)\s+"
        r"(?:params?|parameters?\s+)?(?:active|activated)\s+"
        r"(?:and|of|out\s+of)\s+"
        r"(?P<total>\d+(?:\.\d+)?)\s*(?P<total_unit>b|t|billion|trillion)\s+"
        r"(?:total\s+)?(?:params?|parameters?)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?P<total>\d+(?:\.\d+)?)\s*(?P<total_unit>b|t|billion|trillion)\s+"
        r"(?:parameters?\s+)?(?:in\s+)?total.{0,160}?"
        r"(?P<active>\d+(?:\.\d+)?)\s*(?P<active_unit>b|t|billion|trillion)\s+"
        r"(?:parameters?\s+)?(?:are\s+)?(?:active|activated)",
        re.IGNORECASE,
    ),
    re.compile(
        r"total\s+parameters?\s*[:|]\s*(?P<total>\d+(?:\.\d+)?)\s*"
        r"(?P<total_unit>b|t|billion|trillion).{0,160}?"
        r"active\s+parameters?\s*[:|]\s*(?P<active>\d+(?:\.\d+)?)\s*"
        r"(?P<active_unit>b|t|billion|trillion)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?P<total>\d+(?:\.\d+)?)\s*(?P<total_unit>b|t|billion|trillion)"
        r"(?:\s+parameters?)?\s*\(\s*(?P<active>\d+(?:\.\d+)?)\s*"
        r"(?P<active_unit>b|t|billion|trillion)"
        r"\s+(?:active|activated)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?P<total>\d+(?:\.\d+)?)\s*(?P<total_unit>b|t|billion|trillion)\s+"
        r"(?:total|overall)\s*[/,;|-]+\s*"
        r"(?P<active>\d+(?:\.\d+)?)\s*(?P<active_unit>b|t|billion|trillion)\s+"
        r"(?:active|activated)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:total\s+)?parameters?.{0,240}?"
        r"(?P<total>\d+(?:\.\d+)?)\s*(?P<total_unit>b|t|billion|trillion)"
        r".{0,360}?(?:active|activated)\s+parameters?.{0,240}?"
        r"(?P<active>\d+(?:\.\d+)?)\s*"
        r"(?P<active_unit>m|b|t|million|billion|trillion)",
        re.IGNORECASE,
    ),
)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n")


def request(url: str, attempts: int = 5) -> bytes | None:
    req = urllib.request.Request(url, headers={"User-Agent": "local-ai-registry/1.0"})
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(req, timeout=45, context=CONTEXT) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            if error.code in (401, 403, 404):
                return None
            if error.code != 429 or attempt == attempts - 1:
                raise
            delay = int(error.headers.get("Retry-After", "0") or 0) or 2**attempt
            time.sleep(min(delay, 60))
        except (urllib.error.URLError, TimeoutError):
            if attempt == attempts - 1:
                raise
            time.sleep(2**attempt)
    return None


def normalized_card(markdown: str) -> str:
    text = html.unescape(markdown)
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.DOTALL)
    text = re.sub(r"[`*_#<>]", " ", text)
    return re.sub(r"\s+", " ", text)


def total_agrees(published_total: float, registry_total: float) -> bool:
    tolerance = max(0.5, registry_total * 0.05)
    return abs(published_total - registry_total) <= tolerance


def billions(value: str, unit: str) -> float:
    scale = {"m": 0.001, "million": 0.001, "t": 1_000, "trillion": 1_000}.get(
        unit.lower(), 1
    )
    return round(float(value) * scale, 12)


def exact_numeric_match(text: str, match: re.Match[str], group: str) -> bool:
    prefix = text[max(0, match.start(group) - 24) : match.start(group)].lower()
    suffix = text[match.end(group) : match.end(group) + 16]
    if re.search(r"(?:~|≈|[-–—])\s*$", prefix):
        return False
    if re.search(r"\b(?:about|roughly|approximately|approx\.?)\s*$", prefix):
        return False
    return re.match(r"\s*(?:-|–|—|~)\s*\d", suffix) is None




def parameter_pair_from_card(
    markdown: str, registry_total: float
) -> tuple[float | int, float | int] | None:
    text = normalized_card(markdown)
    pairs: set[tuple[float, float]] = set()
    for pattern in PAIR_PATTERNS:
        for match in pattern.finditer(text):
            if not (
                exact_numeric_match(text, match, "total")
                and exact_numeric_match(text, match, "active")
            ):
                continue
            total = billions(match.group("total"), match.group("total_unit"))
            active = billions(match.group("active"), match.group("active_unit"))
            if 0 < active < total:
                pairs.add((total, active))

    matching_active = {
        active for total, active in pairs if total_agrees(total, registry_total)
    }
    if len(matching_active) == 1:
        selected = (registry_total, matching_active.pop())
    elif not matching_active and len(pairs) == 1:
        selected = next(iter(pairs))
    else:
        return None
    return tuple(int(value) if value.is_integer() else value for value in selected)


def active_from_card(markdown: str, registry_total: float) -> float | int | None:
    pair = parameter_pair_from_card(markdown, registry_total)
    return None if pair is None else pair[1]


def fetch_card(
    item: tuple[Path, dict[str, Any]],
) -> tuple[Path, dict[str, Any], str | None, str | None, str | None]:
    path, row = item
    repo = row["huggingface"]["repository"]
    try:
        api_url = API.format(repo=urllib.parse.quote(repo, safe="/"))
        raw = request(api_url)
        if raw is None:
            return path, row, None, None, "repository unavailable"
        payload = json.loads(raw)
        revision = payload.get("sha")
        if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{40}", revision):
            return path, row, None, None, "repository revision unavailable"
        card_url = README.format(
            repo=urllib.parse.quote(repo, safe="/"),
            revision=revision,
        )
        card = request(card_url)
        return (
            path,
            row,
            None if card is None else card.decode(errors="replace"),
            revision,
            None,
        )
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        return path, row, None, None, str(error)


def main() -> int:
    captured_at = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    candidates: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted((REGISTRY / "model").glob("*.json")):
        row = read_json(path)
        repo = (row.get("huggingface") or {}).get("repository")
        if (
            row.get("active_params") is None
            and row.get("architecture") == "moe"
            and isinstance(row.get("params"), (int, float))
            and isinstance(repo, str)
            and repo.count("/") == 1
        ):
            candidates.append((path, row))

    updates = matched_cards = params_corrected = errors = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        for path, row, card, revision, error in pool.map(fetch_card, candidates):
            if error is not None:
                errors += 1
                print(f"WARN {row['id']}: {error}", file=sys.stderr)
                continue
            if card is None or revision is None:
                continue
            pair = parameter_pair_from_card(card, float(row["params"]))
            if pair is None:
                continue
            total, active = pair
            matched_cards += 1
            repo = row["huggingface"]["repository"]
            source_url = README.format(repo=repo, revision=revision)
            if total != row["params"]:
                row["params"] = total
                row.setdefault("facts", {})["params"] = {
                    "provenance": {
                        "captured_at": captured_at,
                        "sources": [
                            {
                                "captured_at": captured_at,
                                "kind": "huggingface-model-card",
                                "url": source_url,
                            }
                        ],
                    },
                    "reason": "explicit-logical-total-parameter-count",
                    "state": "known",
                }
                params_corrected += 1
            row["active_params"] = active
            row.setdefault("facts", {})["active_params"] = {
                "provenance": {
                    "captured_at": captured_at,
                    "sources": [
                        {
                            "captured_at": captured_at,
                            "kind": "huggingface-model-card",
                            "url": source_url,
                        }
                    ],
                },
                "reason": "explicit-total-and-active-parameter-pair",
                "state": "known",
            }
            write_json(path, row)
            updates += 1

    print(
        f"candidates: {len(candidates)}; cards matched: {matched_cards}; "
        f"active parameters updated: {updates}; params corrected: {params_corrected}; "
        f"errors: {errors}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
