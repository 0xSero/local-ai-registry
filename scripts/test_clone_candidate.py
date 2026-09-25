"""clone_candidate.py writes a draft_launch the recipe schema accepts."""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import clone_candidate

REG = Path(__file__).resolve().parent.parent / "registry"
SOURCE = "qwen359b-exl3-4bpw-rtx5070-tabbyapi-tp1"  # validated docker launch with an asset mount


class CloneCandidateTests(unittest.TestCase):
    def clone(self, *extra):
        with tempfile.TemporaryDirectory() as tmp:
            reg = Path(tmp)
            (reg / "recipe").mkdir()
            shutil.copy(REG / "recipe" / f"{SOURCE}.json", reg / "recipe")
            shutil.copytree(REG / "hardware", reg / "hardware")
            shutil.copytree(REG / "model-instance", reg / "model-instance")
            argv = ["clone_candidate.py", SOURCE, "rtx-3090-24gb", "--id", "clone-test", *extra]
            with mock.patch.object(clone_candidate, "REG", reg), mock.patch.object(sys, "argv", argv), \
                    mock.patch("sys.stdout"):
                clone_candidate.main()
            return json.loads((reg / "recipe" / "clone-test.json").read_text())

    def test_another_instance_does_not_inherit_the_weights_subdir(self):
        clone = self.clone("--instance", "turboderp-qwen3-5-9b-exl3--4-bpw")
        self.assertNotIn("weights_subdir", clone["metadata"])

    def test_draft_launch_keys_are_allowed_by_schema(self):
        source = json.loads((REG / "recipe" / f"{SOURCE}.json").read_text())
        self.assertTrue(source["launch"]["asset_ids"])
        allowed = set(json.loads((REG / "schema" / "recipe.schema.json").read_text())
                      ["properties"]["draft_launch"]["properties"])
        clone = self.clone()
        draft = clone["draft_launch"]
        self.assertLessEqual(set(draft), allowed)
        self.assertNotIn("asset_ids", draft)
        # the asset mount stays; accept_recipe.py derives asset_ids from it at promotion
        self.assertIn("asset/", json.dumps(draft["mounts"]))
        # the plugin export mounts the weights from this subdir; without it the engine cannot find the model
        self.assertEqual(clone["metadata"]["weights_subdir"], source["metadata"]["weights_subdir"])


if __name__ == "__main__":
    unittest.main()
