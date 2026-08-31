#!/usr/bin/env python3
"""One-off backfill: derive metrics for speed-sweep records that lack them.

Historical imports (LocalMaxxing leaderboard rows and early snapshots)
carried only raw rows. The metrics block becomes required; this fills it
with honest aggregates of the rows and nothing else.
"""

import json
import sys
from pathlib import Path

from sweep_metrics import derive_metrics

ROOT = Path(__file__).resolve().parent.parent / "registry" / "speed-sweep"


def main() -> int:
    changed = 0
    for path in sorted(ROOT.glob("*.json")):
        record = json.loads(path.read_text())
        if record.get("metrics") is not None:
            continue
        record["metrics"] = derive_metrics(record["rows"], record.get("measured_at"))
        path.write_text(json.dumps(record, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
        changed += 1
    print(f"backfilled metrics on {changed} sweep(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
