import contextlib
import io
import json
import sys
import unittest
from unittest.mock import patch

import export_plugin_recipes as exporter


class PluginExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        output = io.StringIO()
        with patch.object(sys, 'argv', ['export_plugin_recipes.py']), contextlib.redirect_stdout(output), contextlib.redirect_stderr(io.StringIO()):
            exporter.main()
        cls.document = json.loads(output.getvalue())
        cls.recipes = {r['id']: r for hw in cls.document['hardware'].values()
                       for r in [hw['recipe']] + hw.get('recipes', [])}

    def test_environment_configured_tp2_claim(self):
        self.assertEqual(exporter.card_count({'hardware_count': 2, 'launch': {'environment': {'GPU_COUNT': '2'}}}), 2)

    def test_qwen_256k_alternates_survive_export(self):
        for name in ['qwen38-q4km-arcb70-llamacpp-tp2', 'qwen38-awq-int4-rtx3090-vllm-tp2']:
            with self.subTest(recipe=name):
                r = self.recipes[name]
                self.assertEqual(r['cards'], 2)
                self.assertEqual(r['serving']['ctxTokens'], 262144)

    def test_kv_pool_is_not_lost(self):
        self.assertEqual(self.recipes['qwen38-q4km-arcb70-llamacpp-tp2']['serving']['kvTokens'], 262144)

    def test_candidates_are_not_promoted(self):
        candidates = {r['id'] for r in exporter.load('recipe').values() if r.get('status') != 'validated'}
        self.assertFalse(candidates.intersection(self.recipes))

    def test_no_compatible_validated_alternative_is_dropped(self):
        instances = exporter.load('model-instance')
        for r in exporter.load('recipe').values():
            if (r.get('status') == 'validated' and r['launch'].get('kind') == 'docker'
                    and r['hardware_id'] in self.document['hardware']
                    and exporter.plugin_refusal(r, instances.get(r['model_instance_id'])) is None):
                self.assertIn(r['id'], self.recipes)


if __name__ == '__main__':
    unittest.main()
