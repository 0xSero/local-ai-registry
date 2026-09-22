#!/usr/bin/env python3
"""Fail when the committed plugin catalog is not what the records export.

The catalog carries two provenance fields — `registryCommit` and `generatedAt` — that
are derived from the last commit that touched `registry/`. A squash merge (and a rebase)
rewrites that commit, so those two values legitimately differ between a pull-request
branch and the commit that lands it: the branch passes its own check and the push to main
then fails on nothing but its own stamp. That is not a stale catalog.

Everything else in the catalog IS a function of the records, so this regenerates the export
with the very same exporter the workflow runs and compares the whole document with those two
provenance fields removed. A genuinely stale catalog still fails, with the differing hardware
ids named.

    python3 scripts/check_plugin_catalog.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Two catalogs, two exporters: schema 1 is what plugin 5.x fetches, schema 2 what 6.x vendors.
CATALOGS = {
    "1": (ROOT / "plugin" / "recipes.json", ROOT / "scripts" / "export_plugin_recipes.py"),
    "2": (ROOT / "plugin" / "v2" / "recipes.json", ROOT / "scripts" / "export_plugin_v2.py"),
}
# Derived from the commit that last touched registry/, so a squash or rebase rewrites
# it. Compared nowhere: the values identify the build, not the exported content.
PROVENANCE = ("registryCommit", "generatedAt")


def compare(committed: dict, fresh: dict) -> list[str]:
    """Reasons the committed catalog disagrees with the export; empty when current.

    The provenance fields are dropped from both sides first: they are the build's own
    stamp, not the content, and a squash merge changes them without changing a single
    exported recipe.
    """
    left = {k: v for k, v in committed.items() if k not in PROVENANCE}
    right = {k: v for k, v in fresh.items() if k not in PROVENANCE}
    if left == right:
        return []

    reasons = []
    if left.get("schemaVersion") != right.get("schemaVersion"):
        reasons.append(f"schemaVersion: {left.get('schemaVersion')!r} -> "
                       f"{right.get('schemaVersion')!r}")
    if left.get("gateway") != right.get("gateway"):
        reasons.append("gateway: differs")
    if set(left.get("assets") or {}) != set(right.get("assets") or {}):
        reasons.append(f"assets: committed {sorted(left.get('assets') or {})} vs "
                       f"exported {sorted(right.get('assets') or {})}")
    left_hardware, right_hardware = left.get("hardware") or {}, right.get("hardware") or {}
    for hardware_id in sorted(set(left_hardware) | set(right_hardware)):
        if left_hardware.get(hardware_id) != right_hardware.get(hardware_id):
            if hardware_id not in left_hardware:
                reasons.append(f"{hardware_id}: missing from the committed catalog")
            elif hardware_id not in right_hardware:
                reasons.append(f"{hardware_id}: no longer exported by the records")
            else:
                reasons.append(f"{hardware_id}: entry differs")
    return reasons or ["the documents differ outside the known fields"]


def main() -> int:
    schema = sys.argv[1] if len(sys.argv) > 1 else "1"
    CATALOG, EXPORTER = CATALOGS[schema]
    if not CATALOG.exists():
        print(f"error: {CATALOG} does not exist", file=sys.stderr)
        return 1
    committed = json.loads(CATALOG.read_text())
    with tempfile.TemporaryDirectory() as scratch:
        fresh_path = Path(scratch) / "recipes.json"
        result = subprocess.run(
            [sys.executable, str(EXPORTER), "--out", str(fresh_path)],
            cwd=ROOT, capture_output=True, text=True,
        )
        if result.returncode != 0 or not fresh_path.exists():
            print("error: the exporter failed:", file=sys.stderr)
            print((result.stderr or result.stdout).strip()[-2000:], file=sys.stderr)
            return 1
        fresh = json.loads(fresh_path.read_text())

    reasons = compare(committed, fresh)
    if not reasons:
        print(f"{CATALOG.relative_to(ROOT)} is current: "
              f"{len(committed.get('hardware') or {})} hardware ids "
              f"(provenance stamp excluded: {', '.join(PROVENANCE)})")
        return 0
    print(f"{CATALOG.relative_to(ROOT)} is stale against the records.", file=sys.stderr)
    for reason in reasons:
        print(f"  {reason}", file=sys.stderr)
    print(f"  run: python3 {EXPORTER.relative_to(ROOT)} --out {CATALOG.relative_to(ROOT)}",
          file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
