import contextlib
import io
import json
import re
import sys
import unittest
from unittest.mock import patch

import export_plugin_v2 as exporter

FORBIDDEN = {"ipc", "capAdd", "securityOpt", "networkMode", "devices", "mounts", "kind", "provenance", "validated", "speed"}


class PluginExportV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        output = io.StringIO()
        with patch.object(sys, 'argv', ['export_plugin_v2.py']), contextlib.redirect_stdout(output), contextlib.redirect_stderr(io.StringIO()):
            cls.rc = exporter.main()
        cls.text = output.getvalue()
        cls.document = json.loads(cls.text)
        cls.recipes = {r['id']: r for hw in cls.document['hardware'].values() for r in hw['recipes']}

    def test_exports_cleanly(self):
        self.assertEqual(self.rc, 0)
        self.assertEqual(self.document['schemaVersion'], 'omarchy-local-ai/recipes/2')
        self.assertTrue(self.document['gateway']['image'].startswith('ghcr.io/0xsero/gateway@sha256:'))

    def test_one_hardware_entry_per_line(self):
        lines = self.text.splitlines()
        for hardware_id in self.document['hardware']:
            matching = [l for l in lines if l.startswith(f'    "{hardware_id}": ')]
            self.assertEqual(len(matching), 1, hardware_id)

    def test_nothing_refusable_can_be_expressed(self):
        for rid, r in self.recipes.items():
            with self.subTest(recipe=rid):
                self.assertFalse(FORBIDDEN & set(r), FORBIDDEN & set(r))
                self.assertFalse(FORBIDDEN & set(r['launch']), FORBIDDEN & set(r['launch']))
                self.assertRegex(r['image'], r'@sha256:[0-9a-f]{64}$')
                self.assertIsInstance(r['launch']['port'], int)
                for w in r['weights']:
                    self.assertIn(w['layout'], ('dir', 'hub'))
                    self.assertRegex(w['revision'], r'^[0-9a-f]{40,64}$')
                    self.assertTrue(w['mountPath'].startswith('/'))

    def test_first_recipe_is_the_recommended_one(self):
        v1_recipes = exporter.v1.load('recipe')
        for hardware_id, hw in self.document['hardware'].items():
            first = hw['recipes'][0]['id']
            self.assertTrue(v1_recipes[first].get('recommended'), f'{hardware_id}: {first}')

    def test_hub_layout_for_engines_that_read_the_hub_cache(self):
        r = self.recipes['lfm25-26b-bf16-rtx3090-sglang-tp1']
        self.assertEqual([w['layout'] for w in r['weights']], ['hub'])
        self.assertEqual(r['weights'][0]['mountPath'], '/root/.cache/huggingface')

    def test_dir_layout_with_subdir_and_asset(self):
        r = self.recipes['qwen3827b-exl3-sc4bpw-rtx3090-tabbyapi-tp1']
        self.assertEqual(r['weights'][0]['layout'], 'dir')
        self.assertEqual(r['weights'][0]['dir'], 'Qwen3.8-27B-EXL3-SC4bpw-H5')
        self.assertEqual(r['weights'][0]['mountPath'], '/workspace/models')
        self.assertEqual(r['asset']['mountPath'], '/app/config.yml')
        self.assertIn('model_dir', r['asset']['text'])

    def test_gguf_names_its_one_file(self):
        r = self.recipes['qwen38-q4km-arcb70-llamacpp-tp1']
        self.assertEqual(r['weights'][0]['files'], 'Qwen3.8-27B-Q4_K_M.gguf')

    def test_scratch_and_two_weight_sets(self):
        self.assertEqual(self.recipes['qwen38-awq-int4-rtx3090-vllm-tp2']['scratch'], '/root/.cache/vllm')
        glm = self.recipes['glm53-flash-lil-r35-rtxpro6000-vllm-tp4']
        self.assertEqual([w['mountPath'] for w in glm['weights']], ['/model', '/draft'])
        self.assertEqual(glm['cards'], 4)

    def test_weights_baked_into_the_image(self):
        r = self.recipes['ornith15-9b-rtxpro4500-sglang-tp1']
        self.assertEqual(r['weights'], [])
        self.assertEqual(r['sizeGb'], 0)

    def test_no_host_recipes(self):
        self.assertNotIn('xdna2-krackan-16gb', self.document['hardware'])
        self.assertFalse([r for r in self.recipes.values() if r['engine'] == 'flm'])

    def test_multi_card_alternates_survive(self):
        for name in ['qwen38-q4km-arcb70-llamacpp-tp2', 'qwen38-awq-int4-rtx3090-vllm-tp2']:
            with self.subTest(recipe=name):
                self.assertEqual(self.recipes[name]['cards'], 2)
                self.assertEqual(self.recipes[name]['serving']['ctxTokens'], 262144)


if __name__ == '__main__':
    unittest.main()
