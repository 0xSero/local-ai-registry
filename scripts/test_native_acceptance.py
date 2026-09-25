"""Native acceptance binds a real local run to immutable runtime/model inputs."""

import copy
import hashlib
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

import accept_recipe
import trust


def fixture():
    recipe = {
        "id": "native-test", "status": "candidate", "model_instance_id": "model-test",
        "hardware_id": "apple-m4-24gb", "hardware_count": 1,
        "engine": {"name": "mlx-vlm", "version": "0.7.3", "graph_mode": None},
        "launch": {
            "kind": "native", "accelerator_backend": "metal", "host_port": 8080,
            "source_repository": "https://github.com/Blaizzy/mlx-vlm", "source_commit": "a" * 40,
            "arguments": ["python", "-m", "mlx_vlm.server", "--port", "8080"],
        },
        "serving": {"max_context_tokens": 200000},
        "capabilities": {"chat": None, "reasoning": None, "tools": None, "vision": None},
        "speed_sweep_ids": [], "metadata": {},
    }
    instance = {"id": "model-test", "repository": "owner/model", "served_name": "test-model", "revision": "b" * 40}
    hardware = {"id": "apple-m4-24gb", "vendor": "apple", "accelerator_backend": "metal"}
    return recipe, instance, hardware


def evidence(recipe, instance):
    return {
        "id": "native-test-acceptance", "recipe_id": recipe["id"], "accepted_at": "2026-09-25T00:00:00Z",
        "source": {"kind": "acceptance-run", "repository": recipe["launch"]["source_repository"],
                   "commit": recipe["launch"]["source_commit"], "hardware_id": recipe["hardware_id"],
                   "model_instance_id": recipe["model_instance_id"], "model_repository": instance["repository"],
                   "model_revision": instance["revision"], "served_model_id": instance["served_name"],
                   "launch_sha256": trust.native_launch_fingerprint(recipe)},
    }


class NativeTrustTests(unittest.TestCase):
    def test_native_assets_bind_manifest_hash_and_executable_filename(self):
        recipe, instance, hardware = fixture()
        recipe["launch"]["arguments"] = ["python", "registry/asset/serve.py"]
        recipe["launch"]["asset_ids"] = ["native-serve"]
        recipe["launch"]["asset_sha256"] = {"native-serve": "a" * 64}
        assets = {"native-serve": {"id": "native-serve", "file": "serve.py", "sha256": "a" * 64}}
        sweep = evidence(recipe, instance)
        self.assertEqual(trust.derive_status(recipe, instance, [sweep], hardware, assets), "validated")
        changed = copy.deepcopy(assets)
        changed["native-serve"]["sha256"] = "c" * 64
        self.assertEqual(trust.derive_status(recipe, instance, [sweep], hardware, changed), "candidate")
        changed = copy.deepcopy(assets)
        changed["native-serve"]["file"] = "another.py"
        self.assertEqual(trust.derive_status(recipe, instance, [sweep], hardware, changed), "candidate")
        changed["native-serve"]["file"] = "../serve.py"
        self.assertTrue(trust.native_asset_failures(recipe, changed))
        self.assertTrue(trust.native_asset_failures(recipe, {}))
        recipe["launch"]["asset_sha256"] = {}
        self.assertTrue(trust.native_asset_failures(recipe, assets))

    def test_native_requires_matching_runtime_model_hardware_and_launch_evidence(self):
        recipe, instance, hardware = fixture()
        sweep = evidence(recipe, instance)
        self.assertEqual(trust.derive_status(recipe, instance, [sweep], hardware), "validated")
        for field, value in (("commit", "c" * 40), ("repository", "https://github.com/other/runtime"),
                             ("hardware_id", "apple-m4-32gb"), ("model_revision", "d" * 40),
                             ("model_instance_id", "other-instance"), ("model_repository", "other/model"),
                             ("served_model_id", "other-model"),
                             ("launch_sha256", "e" * 64), ("kind", "imported")):
            with self.subTest(field=field):
                stale = copy.deepcopy(sweep)
                stale["source"][field] = value
                self.assertEqual(trust.derive_status(recipe, instance, [stale], hardware), "candidate")
        recipe["launch"]["arguments"].extend(["--kv-bits", "4"])
        self.assertEqual(trust.derive_status(recipe, instance, [sweep], hardware), "candidate")

    def test_reusing_a_model_commit_cannot_relabel_native_evidence(self):
        recipe, instance, hardware = fixture()
        sweep = evidence(recipe, instance)
        instance["repository"] = "fork/model"
        self.assertEqual(trust.derive_status(recipe, instance, [sweep], hardware), "candidate")
        recipe, instance, hardware = fixture()
        recipe["model_instance_id"] = instance["id"] = "another-quant-at-the-same-commit"
        self.assertEqual(trust.derive_status(recipe, instance, [sweep], hardware), "candidate")

    def test_native_contract_rejects_unpinned_and_nonmaterializable_launches(self):
        for field, value in (("source_repository", "file:///runtime"), ("source_commit", "main"),
                             ("source_commit", "a" * 40 + "\n"), ("arguments", []),
                             ("arguments", "python -m mlx_vlm.server"), ("arguments", 123),
                             ("arguments", ["--port", "8080"]),
                             ("arguments", ["sh", "-c", "serve && run"]), ("arguments", ["serve", "&&", "run"]),
                             ("host_port", True), ("host_port", 65536), ("accelerator_backend", "nvidia"),
                             ("environment", {"X": 2}), ("image", "example@sha256:" + "f" * 64)):
            with self.subTest(field=field, value=value):
                recipe, instance, hardware = fixture()
                recipe["launch"][field] = value
                self.assertTrue(trust.native_contract_failures(recipe, instance, hardware))
        recipe, instance, hardware = fixture()
        instance["revision"] = "main"
        self.assertTrue(trust.native_contract_failures(recipe, instance, hardware))

    def test_native_rejects_generic_hardware_missing_records_and_multiple_machines(self):
        recipe, instance, hardware = fixture()
        self.assertTrue(trust.native_contract_failures(recipe, instance, None))
        hardware["vendor"] = "nvidia"
        self.assertTrue(trust.native_contract_failures(recipe, instance, hardware))
        recipe, instance, hardware = fixture()
        recipe["hardware_id"] = hardware["id"] = "apple-max-24gb"
        self.assertTrue(trust.native_contract_failures(recipe, instance, hardware))
        recipe, instance, hardware = fixture()
        recipe["hardware_count"] = 2
        self.assertTrue(trust.native_contract_failures(recipe, instance, hardware))

    def test_native_is_not_plugin_recommendable_and_generic_acceptance_is_insufficient(self):
        recipe, instance, hardware = fixture()
        imported = {"accepted_at": "2026-09-25T00:00:00Z", "source": {"kind": "acceptance-run"}}
        self.assertEqual(trust.derive_status(recipe, instance, [imported], hardware), "candidate")
        recipe["status"] = "validated"
        self.assertIsNotNone(trust.recommendable(recipe))

    def test_docker_and_flm_boundaries_are_unchanged(self):
        recipe, instance, hardware = fixture()
        recipe["launch"] = {"kind": "docker", "image": "repo@sha256:" + "a" * 64,
                            "arguments": ["serve"], "host_port": 8080, "container_port": 8080,
                            "accelerator_backend": "nvidia"}
        generic = {"accepted_at": "2026-09-25T00:00:00Z", "source": {"kind": "acceptance-run"}}
        self.assertEqual(trust.derive_status(recipe, instance, [generic]), "validated")
        recipe["launch"]["image"] = "repo:latest"
        self.assertEqual(trust.derive_status(recipe, instance, [generic]), "candidate")
        recipe["launch"] = {"kind": "host", "container_port": 8080, "accelerator_backend": "amd-npu"}
        recipe["engine"]["name"] = "flm"
        self.assertEqual(trust.derive_status(recipe, instance, [generic]), "validated")
        recipe["engine"]["name"] = "mlx-vlm"
        self.assertEqual(trust.derive_status(recipe, instance, [generic]), "candidate")


class NativeHostTests(unittest.TestCase):
    def test_exact_chip_and_memory_are_required(self):
        recipe, _, _ = fixture()
        with patch.object(accept_recipe.platform, "system", return_value="Darwin"), \
                patch.object(accept_recipe.platform, "machine", return_value="arm64"), \
                patch.object(accept_recipe.platform, "mac_ver", return_value=("26.0", (), "")), \
                patch.object(accept_recipe.subprocess, "check_output", side_effect=["Apple M4\n", str(24 << 30)]):
            host = accept_recipe.native_host(recipe, "http://127.0.0.1:8080")
        self.assertEqual(host["hardware_id"], "apple-m4-24gb")
        self.assertEqual(host["memory_bytes"], 24 << 30)
        with patch.object(accept_recipe.platform, "system", return_value="Darwin"), \
                patch.object(accept_recipe.platform, "machine", return_value="arm64"), \
                patch.object(accept_recipe.subprocess, "check_output", side_effect=["Apple M4\n", str(32 << 30)]):
            with self.assertRaisesRegex(ValueError, "hardware mismatch"):
                accept_recipe.native_host(recipe, "http://127.0.0.1:8080")

    def test_remote_wrong_port_and_nonapple_hosts_are_rejected(self):
        recipe, _, _ = fixture()
        for endpoint in ("http://example.com:8080", "http://127.0.0.1:8081", "http://127.0.0.1:8080/v1"):
            with self.subTest(endpoint=endpoint), self.assertRaisesRegex(ValueError, "loopback"):
                accept_recipe.native_host(recipe, endpoint)
        with patch.object(accept_recipe.platform, "system", return_value="Linux"):
            with self.assertRaisesRegex(ValueError, "Apple Silicon"):
                accept_recipe.native_host(recipe, "http://127.0.0.1:8080")


class NativePromotionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.recipe, self.instance, self.hardware = fixture()
        for kind in ("recipe", "model-instance", "hardware", "speed-sweep"):
            (self.root / kind).mkdir()
        self.recipe_path = self.root / "recipe/native-test.json"
        self.instance_path = self.root / "model-instance/model-test.json"
        self.write_inputs()
        self.run = {"started_at": "2026-09-25T00:00:00Z", "prompt_tokens": 321, "tokens": 12,
                    "decode_tok_s": 44.0, "ttft_ms": 300.0, "server_prefill_tok_s": 1200.0,
                    "decode_method": "timings.predicted_per_second", "content": "The answer.",
                    "reasoning_content": "", "response_model_ids": ["test-model"]}

    def write_inputs(self):
        self.recipe_path.write_text(json.dumps(self.recipe))
        self.instance_path.write_text(json.dumps(self.instance))
        (self.root / "hardware/apple-m4-24gb.json").write_text(json.dumps(self.hardware))

    def invoke(self):
        argv = ["accept_recipe.py", "native-test", "--endpoint", "http://127.0.0.1:8080"]
        with patch.object(accept_recipe, "ROOT", self.root), patch.object(sys, "argv", argv), \
                patch.object(accept_recipe, "native_host", return_value={"hardware_id": "apple-m4-24gb"}), \
                patch.object(accept_recipe, "http_json", return_value={"data": [{"id": "test-model"}]}), \
                patch.object(accept_recipe, "measure", return_value=[copy.deepcopy(self.run) for _ in range(3)]), \
                redirect_stdout(io.StringIO()):
            return accept_recipe.main()

    def test_promotion_records_source_commit_and_only_measured_context(self):
        self.assertEqual(self.invoke(), 0)
        promoted = json.loads(self.recipe_path.read_text())
        sweep = json.loads((self.root / "speed-sweep/native-test-acceptance.json").read_text())
        self.assertEqual(promoted["status"], "validated")
        self.assertEqual(promoted["launch"]["container"]["state"], "none")
        self.assertIsNone(promoted["launch"]["container"]["image"])
        self.assertEqual(sweep["source"]["commit"], "a" * 40)
        self.assertEqual(sweep["source"]["model_revision"], "b" * 40)
        self.assertEqual(sweep["source"]["model_repository"], "owner/model")
        self.assertEqual(sweep["source"]["model_instance_id"], "model-test")
        self.assertEqual(sweep["source"]["served_model_id"], "test-model")
        self.assertEqual(sweep["source"]["hardware_id"], "apple-m4-24gb")
        self.assertEqual(sweep["rows"][0]["context_tokens"], 321)
        self.assertEqual(sweep["metrics"]["max_context_tokens"], 321)
        self.assertEqual(promoted["serving"]["max_context_tokens"], 200000)
        self.assertEqual(promoted["capabilities"], self.recipe["capabilities"])
        self.assertIn("no automatic vision", promoted["metadata"]["acceptance"]["scope"])
        self.assertEqual(trust.derive_status(promoted, self.instance, [sweep], self.hardware), "validated")

    def test_unpinned_model_is_rejected_before_any_network_or_mutation(self):
        self.instance["revision"] = None
        self.write_inputs()
        before = self.recipe_path.read_bytes(), self.instance_path.read_bytes()
        with patch.object(accept_recipe, "pinned_revision") as pin:
            with self.assertRaisesRegex(SystemExit, "pinned before acceptance"):
                self.invoke()
        pin.assert_not_called()
        self.assertEqual(before, (self.recipe_path.read_bytes(), self.instance_path.read_bytes()))
        self.assertEqual(list((self.root / "speed-sweep").iterdir()), [])

    def test_native_artifact_checks_reject_changed_or_missing_blobs_before_promotion(self):
        blob = b"print('native fixture')\n"
        digest = hashlib.sha256(blob).hexdigest()
        self.recipe["launch"].update({"arguments": ["python", "registry/asset/serve.py"],
                                     "asset_ids": ["native-serve"], "asset_sha256": {"native-serve": digest}})
        self.write_inputs()
        (self.root / "asset").mkdir()
        manifest = {"id": "native-serve", "file": "serve.py", "sha256": digest, "size_bytes": len(blob)}
        (self.root / "asset/native-serve.json").write_text(json.dumps(manifest))
        with self.assertRaisesRegex(SystemExit, "blob is missing"):
            self.invoke()
        (self.root / "asset/serve.py").write_bytes(blob + b"# changed\n")
        with self.assertRaisesRegex(SystemExit, "does not match"):
            self.invoke()
        self.assertEqual(json.loads(self.recipe_path.read_text())["status"], "candidate")
        self.assertEqual(list((self.root / "speed-sweep").iterdir()), [])
        (self.root / "asset/serve.py").write_bytes(blob)
        self.assertEqual(self.invoke(), 0)

    def test_unrelated_served_model_or_completion_cannot_promote(self):
        for mismatch in ("advertised", "response", "missing-response-model"):
            with self.subTest(mismatch=mismatch):
                if mismatch == "advertised":
                    self.instance["served_name"] = "other-model"
                    self.write_inputs()
                else:
                    self.instance["served_name"] = "test-model"
                    self.write_inputs()
                    self.run["response_model_ids"] = ["other-model"] if mismatch == "response" else []
                with self.assertRaisesRegex(SystemExit, "model"):
                    self.invoke()
                self.assertEqual(json.loads(self.recipe_path.read_text())["status"], "candidate")
                self.assertEqual(list((self.root / "speed-sweep").iterdir()), [])

    def test_reasoning_without_an_answer_cannot_promote_native_text(self):
        self.run["content"] = ""
        self.run["reasoning_content"] = "Let me think about this."
        with self.assertRaisesRegex(SystemExit, "no answer text"):
            self.invoke()
        self.assertEqual(json.loads(self.recipe_path.read_text())["status"], "candidate")
        self.assertEqual(list((self.root / "speed-sweep").iterdir()), [])


if __name__ == "__main__":
    unittest.main()
