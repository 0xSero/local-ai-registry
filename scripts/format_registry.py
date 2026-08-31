#!/usr/bin/env python3
"""Canonical JSON formatting for everything under registry/.

Records: 2-space indent, sorted keys, raw UTF-8, trailing newline —
the same shape curate_registry.py writes, so a pipeline rerun on clean
data produces an empty diff.

Schema files keep their hand-authored key order (required before
properties reads better than alphabetical) but get the same indent,
encoding, and trailing newline.

Usage:
  python3 scripts/format_registry.py          # rewrite in place
  python3 scripts/format_registry.py --check  # exit 1 if anything would change
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "registry"


def canonical(path: Path) -> str:
    value = json.loads(path.read_text())
    sort = path.parent.name != "schema"
    return json.dumps(value, indent=2, sort_keys=sort, ensure_ascii=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="report files that would change; do not write")
    args = parser.parse_args()

    dirty = []
    for path in sorted(ROOT.rglob("*.json")):
        current = path.read_text()
        want = canonical(path)
        if current != want:
            dirty.append(path)
            if not args.check:
                path.write_text(want)

    if args.check and dirty:
        for path in dirty:
            print(f"needs formatting: {path.relative_to(ROOT.parent)}", file=sys.stderr)
        print(f"{len(dirty)} file(s) not in canonical format. Run: python3 scripts/format_registry.py", file=sys.stderr)
        return 1

    print(f"{'checked' if args.check else 'formatted'} {len(dirty)} changed file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
