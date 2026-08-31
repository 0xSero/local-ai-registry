"""Resolve leaderboard rows to registry model ids.

A row joins a model only through evidence: an exact (case-insensitive)
match between the row's root Hugging Face repository and a model's
huggingface.repository, or an entry in the curated alias map beside this
script. Everything else stays model_id null — explicitly unmatched, never
guessed.
"""

import json
from pathlib import Path

ALIASES_PATH = Path(__file__).resolve().parent / "model_aliases.json"


def model_ids_by_repo(root):
    mapping = {}
    for path in sorted((root / "model").glob("*.json")):
        record = json.loads(path.read_text())
        repository = (record.get("huggingface") or {}).get("repository")
        if isinstance(repository, str) and repository:
            mapping[repository.lower()] = record["id"]
    for alias, model_id in json.loads(ALIASES_PATH.read_text()).items():
        mapping[alias.lower()] = model_id
    return mapping


def resolve_model_id(row, by_repo):
    root_repo = (row.get("root") or "").lower()
    return by_repo.get(root_repo)
