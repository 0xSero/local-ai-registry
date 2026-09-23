"""The Arc Pro B70 row must launch the EXL3 recipe, never the llama.cpp fallback.

The plugin runs `recipes[0]` of a card's entry, and `recipes[0]` is the recommended recipe. A recommendation
change (a re-run of recommend.py, a new recipe) that silently moved the B70 back to llama.cpp would make
"Run Qwen" start the slower engine. This pins the recommendation and the exported order.
"""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
B70 = "intel-arc-pro-b70-32gb"
EXL3 = "qwen38-27b-exl3-4bpw-arcb70-vllm-exl3xpu-tp1"


class B70RunsExl3(unittest.TestCase):
    def test_recommended_recipe_is_exl3(self):
        rec = [json.loads(p.read_text()) for p in (ROOT / "registry" / "recipe").glob("*.json")]
        picks = [r["id"] for r in rec if r.get("hardware_id") == B70 and r.get("recommended")]
        self.assertEqual(picks, [EXL3])

    def test_plugin_catalogs_put_exl3_first(self):
        v2 = json.loads((ROOT / "plugin" / "v2" / "recipes.json").read_text())
        self.assertEqual(v2["hardware"][B70]["recipes"][0]["id"], EXL3)
        v1 = json.loads((ROOT / "plugin" / "recipes.json").read_text())
        self.assertEqual(v1["hardware"][B70]["recipe"]["id"], EXL3)


if __name__ == "__main__":
    unittest.main()
