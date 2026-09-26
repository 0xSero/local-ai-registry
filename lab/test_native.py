import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import lab
import native
import export_plugin


class NativeContractTests(unittest.TestCase):
    def setUp(self):
        self.p = json.loads((lab.ENGINES / "mtplx-qwen3.8-27b-4bit-200k.json").read_text())
        w = self.p["weights"]
        self.r = {"model": "qwen3.8-27b", "engine": self.p["id"] + "@" + native.digest(self.p)[:12],
                  "weights": w["repo"] + "@" + w["revision"], "set": {}}

    def test_every_native_profile_change_invalidates_recipe_pin(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(lab, "ENGINES", Path(tmp)):
            path = Path(tmp) / (self.p["id"] + ".json")
            path.write_text(json.dumps(self.p))
            lab.profile(self.r["engine"])
            self.p["env"]["HF_HUB_OFFLINE"] = "0"
            path.write_text(json.dumps(self.p))
            with self.assertRaisesRegex(SystemExit, "pin changed"):
                lab.profile(self.r["engine"])

    def test_refuses_mismatched_weights_and_unsupported_overrides(self):
        for change in ({"weights": "other/model@" + "a" * 40}, {"set": {"ctx": 4096}}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                native.render(self.p, {**self.r, **change})

    def test_refuses_unpinned_dependencies_or_inconsistent_context(self):
        for field, value in (("ctx", 4096), ("ctx", True), ("port", 0)):
            p = copy.deepcopy(self.p)
            p[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                native.validate(p)
        self.p["runtime"]["requirements"] = ["mtplx>=2.12.0"]
        with self.assertRaises(ValueError):
            native.validate(self.p)

    def test_native_launch_cannot_start_a_rental(self):
        with self.assertRaisesRegex(SystemExit, "no rental was started"):
            lab.rented({}, {"kind": "native"}, None)

    def test_native_card_is_not_exported_to_linux_plugin(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(export_plugin, "ROOT", Path(tmp)):
            root = Path(tmp)
            (root / "dist").mkdir()
            (root / "registry").mkdir()
            (root / "dist/catalog.json").write_text(json.dumps({"cards": {"apple": {"backend": "metal", "picks": ["mac"]}}}))
            (root / "registry/models.json").write_text("{}")
            self.assertEqual(json.loads(export_plugin.build())["hardware"], {})

    def test_exact_local_token_count_does_not_call_remote_endpoint(self):
        class Tokenizer:
            def encode(self, text, add_special_tokens):
                self_test.assertFalse(add_special_tokens)
                return [1, 2, 3]
        self_test = self
        with patch.object(lab, "call", side_effect=AssertionError("unexpected HTTP")):
            self.assertEqual(lab.count("http://unused", "text", Tokenizer()), (3, "local-tokenizer"))

    def test_wrong_served_alias_is_rejected_before_any_completion(self):
        launch = native.render(self.p, self.r)
        with patch.object(lab, "call", return_value=({"data": [{"id": "other-model"}]}, 0)) as call:
            with self.assertRaisesRegex(SystemExit, "does not match"):
                lab.gates("http://unused", launch)
            self.assertEqual(call.call_count, 1)

    def test_sdks_render_identical_native_steps_without_docker(self):
        sys.path.insert(0, str(lab.ROOT / "sdk/python"))
        import local_ai_registry as sdk
        r = {**self.r, "launch": native.render(self.p, self.r)}
        py = sdk.steps(r)
        js = subprocess.check_output(["node", "--input-type=module", "-e",
            'import {steps} from "./sdk/js/index.js"; console.log(JSON.stringify(steps(JSON.parse(process.argv[1]))));',
            json.dumps(r)], cwd=lab.ROOT, text=True)
        self.assertEqual(py, json.loads(js))
        self.assertNotIn("docker", json.dumps(py))
        self.assertIn("127.0.0.1", py[-1]["code"])
        self.assertIn("HF_HUB_DISABLE_IMPLICIT_TOKEN=1", py[1]["code"])


if __name__ == "__main__":
    unittest.main()
