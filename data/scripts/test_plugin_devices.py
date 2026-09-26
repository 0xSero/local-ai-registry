"""Launch declarations through the registry gate, export, and CLI; no Docker/GPU calls."""

import json
import os
import shlex
import subprocess
import tempfile
import unittest
from pathlib import Path

from check_plugin_gate import check_recipe
from export_plugin_recipes import entry

REPO = Path(__file__).resolve().parent.parent
UVM = "/dev/nvidia-uvm"


class PluginDeviceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        for collection in ("recipe", "model-instance", "model", "hardware", "index"):
            (self.root / collection).mkdir()
        self.model = {"id": "model"}
        self.instance = {"model_id": "model", "repository": "org/model", "revision": "b" * 40}
        self.hardware = {"accelerator_backend": "nvidia"}
        self.recipe = {
            "id": "test", "status": "validated", "hardware_id": "gpu", "model_instance_id": "instance",
            "launch": {
                "kind": "docker", "accelerator_backend": "nvidia",
                "image": "example@sha256:" + "a" * 64, "container_port": 8080,
                "devices": [UVM], "arguments": ["--device", "CUDA0"],
            },
        }
        (self.root / "model/model.json").write_text(json.dumps(self.model))
        (self.root / "model-instance/instance.json").write_text(json.dumps(self.instance))
        (self.root / "index/recipes.json").write_text("{}")
        self.env = os.environ | {
            "LOCAL_AI_REGISTRY_DIR": str(self.root),
        }

    def gate_errors(self):
        (self.root / "hardware/gpu.json").write_text(json.dumps(self.hardware))
        errors = []
        check_recipe(self.root, self.recipe, errors)
        return errors

    def exported(self):
        return entry(self.recipe, self.instance, self.model, self.hardware, {})

    def cli(self):
        (self.root / "recipe/test.json").write_text(json.dumps(self.recipe))
        return subprocess.run(
            ["bash", str(REPO / "bin/local-ai"), "command", "test"],
            env=self.env, capture_output=True, text=True, timeout=10,
        )

    def test_uvm_forwarded_before_image_and_engine_device_after(self):
        self.assertEqual(self.gate_errors(), [])
        self.assertEqual(self.exported()["launch"]["devices"], [UVM])
        cli = self.cli()
        self.assertEqual(cli.returncode, 0, cli.stderr)
        argv = shlex.split(cli.stdout)
        image = argv.index(self.recipe["launch"]["image"])
        self.assertEqual(argv[:image].count("--device"), 1)
        self.assertEqual(argv[argv.index("--device") + 1], UVM)
        self.assertEqual(argv[image + 1:], ["--device", "CUDA0"])

    def test_absent_null_and_empty_devices_add_no_host_access(self):
        for devices in ("absent", None, []):
            with self.subTest(devices=devices):
                self.recipe["launch"]["devices"] = devices
                if devices == "absent":
                    del self.recipe["launch"]["devices"]
                self.assertEqual(self.gate_errors(), [])
                cli = self.cli()
                self.assertEqual(cli.returncode, 0, cli.stderr)
                argv = shlex.split(cli.stdout)
                self.assertNotIn("--device", argv[:argv.index(self.recipe["launch"]["image"])])

    def test_cli_expands_required_mount_roots_as_literal_paths(self):
        self.recipe["launch"]["mounts"] = [
            {"source": "${MODEL_ROOT}/quant", "target": "/models", "read_only": True},
            {"source": "${CACHE_ROOT}/engine", "target": "/cache", "read_only": False},
        ]
        self.env["MODEL_ROOT"] = str(self.root / "models with spaces $(literal)")
        self.env["CACHE_ROOT"] = str(self.root / "cache with spaces")
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        argv = shlex.split(result.stdout)
        self.assertIn(self.env["MODEL_ROOT"] + "/quant:/models:ro", argv)
        self.assertIn(self.env["CACHE_ROOT"] + "/engine:/cache", argv)
        for variable in ("MODEL_ROOT", "CACHE_ROOT"):
            with self.subTest(variable=variable):
                value = self.env.pop(variable)
                result = self.cli()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("set " + variable, result.stderr)
                self.env[variable] = value

    def test_other_devices_and_malformed_types_rejected(self):
        for devices in (["/dev/nvidia0"], [UVM + "-tools"], [UVM + ":" + UVM],
                        [UVM + " "], ["/dev/../dev/nvidia-uvm"], [UVM, UVM],
                        [UVM, "/dev/sda"], UVM, False, 0, "", {}):
            with self.subTest(devices=devices):
                self.recipe["launch"]["devices"] = devices
                self.assertIn("devices", " ".join(self.gate_errors()))
                self.assertEqual(self.exported()["launch"]["devices"], devices)
                result = self.cli()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("devices", result.stderr)
                self.assertEqual(result.stdout, "")

    def test_uvm_requires_nvidia_launch_and_hardware(self):
        for backend in ("intel-xpu", "amd-rocm", "cpu"):
            with self.subTest(backend=backend):
                self.recipe["launch"]["accelerator_backend"] = backend
                self.hardware["accelerator_backend"] = backend
                self.assertIn("devices", " ".join(self.gate_errors()))
                self.assertNotEqual(self.cli().returncode, 0)
        self.recipe["launch"]["accelerator_backend"] = "nvidia"
        self.assertIn("devices", " ".join(self.gate_errors()))

    def test_legacy_intel_declaration_passes_gate_and_export(self):
        self.recipe["launch"].update(accelerator_backend="intel-xpu", devices=["/dev/dri"])
        self.hardware["accelerator_backend"] = "intel-xpu"
        self.assertEqual(self.gate_errors(), [])
        self.assertEqual(self.exported()["launch"]["devices"], ["/dev/dri"])


if __name__ == "__main__":
    unittest.main()
