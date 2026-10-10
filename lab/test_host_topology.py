import contextlib
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import import_reported
import lab

CARD = 'cmp-170hx-64gb'
HOST = {'kind': 'host', 'command': ['llama-server', '--split-mode', 'layer'], 'port': 8080, 'ctx': 131072, 'backend': 'nvidia'}
GATES = 'load chat reasoning tools context speed'


def recipe(engine='fixture@host'):
    return {'model': 'test-model', 'weights': 'test/raw@' + 'b'*40, 'engine': engine, 'set': {}, 'card': CARD,
            'proof': [{'gates': GATES, 'tps': 20.0}]}


class HostTopologyTest(unittest.TestCase):
    def test_pin_counts_cards_and_machines(self):
        self.assertNotEqual(lab.pin(HOST), lab.pin({**HOST, 'cards': 2}))
        self.assertNotEqual(lab.pin(HOST), lab.pin({**HOST, 'machines': 2}))
        self.assertEqual(lab.pin(HOST), lab.pin({**HOST, 'cards': 1, 'machines': 1}))

    def test_existing_host_pins_unchanged(self):
        # the pin before cards and machines counted: every host profile in the registry still gets it
        keys = ('command', 'install', 'pip', 'env', 'port', 'weights', 'ctx', 'seqs', 'vision', 'wired_limit_reserve_mb')
        old = lambda p: hashlib.sha256(json.dumps({**{k: p.get(k) for k in keys}, 'config': lab.config_text(p)}, sort_keys=True).encode()).hexdigest()
        hosts = [p for p in (json.loads(f.read_text()) for f in sorted(lab.LAUNCHES.glob('*.json'))) if p.get('kind') == 'host']
        self.assertTrue(hosts)
        for p in hosts:
            self.assertEqual(lab.pin(p), old(p), p.get('id'))

    def test_render_and_name_keep_cards(self):
        with patch.object(lab, 'profile', return_value={**HOST, 'cards': 2}):
            L = lab.render(recipe())
            self.assertEqual((L['cards'], L.get('machines')), (2, None))
            self.assertTrue(lab.recipe_path(recipe(), L).name.endswith('.128k.2x.json'))

    def test_check_rejects_host_on_several_machines(self):
        with tempfile.TemporaryDirectory() as d, patch.object(lab, 'ROOT', Path(d)), patch.object(lab, 'RECIPES', Path(d) / 'recipes'), \
                patch.object(lab, 'profile', return_value={**HOST, 'machines': 2}):
            r = recipe()
            out = lab.recipe_path(r, lab.render(r)); out.parent.mkdir(parents=True); out.write_text(json.dumps(r))
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.assertEqual(lab.cmd_check(None), 1)
            self.assertIn('several machines need a container launch', buf.getvalue())

    def test_import_names_match_recipe_path(self):
        base = {'format': 'exl3', 'model_id': 'test-model', 'model': 'Test', 'hf_repo': 'test/raw', 'hf_revision': 'b'*40,
                'engine': 'vllm', 'ctx': 131072, 'card': CARD, 'repo': 'test/src', 'commit': 'c'*40, 'port': 8000, 'args': []}
        variants = [{**base, 'entrypoint': 'serve', 'machines': 1, 'gpus_per_machine': 2},  # a program on the host, two cards
                    {**base, 'image': 'ghcr.io/test/engine@sha256:' + 'a'*64, 'gpus_per_machine': 2}]  # a container, two cards
        for v in variants:
            out, prof, r = import_reported.freeze(v, 'test')
            with patch.object(lab, 'profile', return_value=prof):
                self.assertEqual(out, lab.recipe_path(r, lab.render(r)), v.get('image', 'host'))
            self.assertTrue(out.name.endswith('.2x.json'))


if __name__ == '__main__':
    unittest.main()
