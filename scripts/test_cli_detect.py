"""`local-ai detect` matches nvidia-smi output against the full hardware collection."""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


class DetectNvidiaTests(unittest.TestCase):
    def detect(self, smi_line):
        with tempfile.TemporaryDirectory() as tmp:
            smi = Path(tmp) / "nvidia-smi"
            smi.write_text(f"#!/bin/sh\necho '{smi_line}'\n")
            smi.chmod(0o755)
            env = {k: v for k, v in os.environ.items() if k != "LOCAL_AI_HARDWARE"}
            env["PATH"] = f"{tmp}:{env['PATH']}"
            return subprocess.run(["bash", str(REPO / "bin/local-ai"), "detect"],
                                  env=env, capture_output=True, text=True, timeout=30)

    def test_real_collection_is_not_passed_as_one_argument(self):
        # the hardware records are larger than Linux's 128 KiB single-argument limit
        size = sum(p.stat().st_size for p in (REPO / "registry/hardware").glob("*.json"))
        self.assertGreater(size, 128 * 1024)
        result = self.detect("NVIDIA GeForce RTX 5070, 12227")
        self.assertEqual((result.returncode, result.stdout.strip()), (0, "rtx-5070-12gb"), result.stderr)

    def test_laptop_gpu_is_distinct_from_desktop(self):
        result = self.detect("NVIDIA GeForce RTX 5070 Ti Laptop GPU, 12227")
        self.assertEqual((result.returncode, result.stdout.strip()), (0, "rtx-5070-ti-laptop-12gb"), result.stderr)
        result = self.detect("NVIDIA GeForce RTX 5070 Ti, 16303")
        self.assertEqual((result.returncode, result.stdout.strip()), (0, "rtx-5070-ti-16gb"), result.stderr)


if __name__ == "__main__":
    unittest.main()
