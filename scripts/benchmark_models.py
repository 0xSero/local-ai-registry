"""Resolve leaderboard rows to registry model ids.

A row joins a model only through evidence: an exact case-insensitive match
between the row's root Hugging Face repository and a model or unambiguous model
instance repository; an entry in the curated repository alias map; or an exact
curated (organisation, variant, root) tuple whose source card identifies the
evaluated derivative while the root remains a genuine parent model.
Everything else stays model_id null — explicitly unmatched, never guessed.
"""

import json
from pathlib import Path

ALIASES_PATH = Path(__file__).resolve().parent / "model_aliases.json"
CURATED_ROW_ALIASES = {
    (
        "google",
        "gemma-3-12b-pt",
        "google/gemma-3-12b",
    ): "gemma-3-12b-pt",
    (
        "google",
        "gemma-3-1b-it",
        "google/gemma-3-1b-pt",
    ): "gemma-3-1b-it",
    (
        "google",
        "gemma-3-4b-it",
        "google/gemma-3-4b-pt",
    ): "gemma-3-4b-it",
    (
        "google",
        "medgemma-4b-pt",
        "google/gemma-3-4b-pt",
    ): "medgemma-4b-pt",
    (
        "mungert",
        "medgemma-4b-pt-gguf",
        "google/gemma-3-4b-pt",
    ): "medgemma-4b-pt",
    (
        "mlabonne",
        "marcoro14-7b-slerp",
        "aidc-ai-business/marcoroni-7b-v3",
    ): "marcoro14-7b-slerp",
    (
        "qwen",
        "qwen2-vl-2b-instruct",
        "qwen/qwen2-vl-2b",
    ): "qwen2-vl-2b-instruct",
}


def normalized(value):
    return str(value or "").strip().casefold()




def model_ids_by_repo(root):
    mapping = {}
    for path in sorted((root / "model").glob("*.json")):
        record = json.loads(path.read_text())
        repository = (record.get("huggingface") or {}).get("repository")
        if isinstance(repository, str) and repository:
            mapping[repository.lower()] = record["id"]

    instance_models = {}
    for path in sorted((root / "model-instance").glob("*.json")):
        record = json.loads(path.read_text())
        repository = (record.get("huggingface") or {}).get("repository") or record.get("repository")
        if isinstance(repository, str) and repository:
            instance_models.setdefault(repository.lower(), set()).add(record["model_id"])
    for repository, model_ids in instance_models.items():
        if len(model_ids) == 1:
            mapping.setdefault(repository, next(iter(model_ids)))

    for alias, model_id in json.loads(ALIASES_PATH.read_text()).items():
        mapping[alias.lower()] = model_id
    return mapping


def resolve_model_id(row, by_repo):
    row_alias = CURATED_ROW_ALIASES.get(
        (
            normalized(row.get("org")),
            normalized(row.get("variant")),
            normalized(row.get("root")),
        )
    )
    if row_alias:
        return row_alias
    return by_repo.get(normalized(row.get("root")))
