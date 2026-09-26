#!/usr/bin/env python3
"""Download the exact public Qwen3.8 MTPLX artifact and verify every file."""
import argparse
import hashlib
import json
import os
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    manifest = json.loads((Path(__file__).resolve().parent.parent / "sources" /
                           "qwen38-mtplx-m4-max-128gb" / "artifacts.json").read_text())
    if not args.verify_only:
        os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
        os.environ["HF_HUB_DISABLE_IMPLICIT_TOKEN"] = "1"
        from huggingface_hub import snapshot_download
        snapshot_download(manifest["repository"], revision=manifest["revision"],
                          local_dir=args.destination, token=False, max_workers=3,
                          allow_patterns=[item["file"] for item in manifest["files"]])
    for item in manifest["files"]:
        path = args.destination / item["file"]
        if not path.is_file() or path.stat().st_size != item["bytes"]:
            raise SystemExit(f"Missing or wrong size: {item['file']}")
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for block in iter(lambda: source.read(8 * 1024 * 1024), b""):
                digest.update(block)
        if digest.hexdigest() != item["sha256"]:
            raise SystemExit(f"SHA-256 mismatch: {item['file']}")
        print(f"Verified {item['file']}", flush=True)
    print(f"Verified revision {manifest['revision']}")


if __name__ == "__main__":
    main()
