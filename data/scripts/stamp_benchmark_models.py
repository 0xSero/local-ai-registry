#!/usr/bin/env python3
"""Re-resolve model_id on every benchmark row against the current model set.

Idempotent pipeline step: run after importing models or growing the
alias map, then rebuild the index. Rows resolve by exact case-insensitive
HF-repository match, the curated repository alias map, or a curated exact
organisation/variant/root tuple; everything else stays explicitly null.
"""

import json
import sys
from pathlib import Path

from benchmark_models import model_ids_by_repo, resolve_model_id

ROOT = Path("registry")


def main() -> int:
    by_repo = model_ids_by_repo(ROOT)
    changed = matched = total = 0
    for path in sorted((ROOT / "benchmark").glob("*.json")):
        record = json.loads(path.read_text())
        dirty = False
        for row in record["rows"]:
            total += 1
            model_id = resolve_model_id(row, by_repo)
            if model_id:
                matched += 1
            if row.get("model_id") != model_id:
                row["model_id"] = model_id
                dirty = True
        if dirty:
            path.write_text(json.dumps(record, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
            changed += 1
    print(f"rows matched: {matched}/{total}; benchmark files rewritten: {changed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
