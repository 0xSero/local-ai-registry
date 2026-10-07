import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import export_plugin as export
import lab


class OffloadContractTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'dist').mkdir(); (self.root / 'registry').mkdir()
        (self.root / 'registry/models.json').write_text('{}')
        self.profile = {'image': 'ghcr.io/example/engine@sha256:' + 'a'*64, 'ids': {'test': 'fixture'},
            'args': [], 'port': 8000, 'ctx': 8192, 'weights': [{'repo': 'test/raw', 'revision': 'b'*40, 'at': '/models/raw'}],
            'plugin': {'name': 'Fixture', 'family': 'test', 'format': 'EXL3', 'engine': 'vllm', 'servedName': 'fixture',
                'sizeGb': 1, 'minDriver': '', 'weights': [{'sizeGb': 1, 'layout': 'dir', 'mountPath': '/models/raw', 'dir': '', 'files': ''}],
                'scratch': None, 'serving': {'ctxTokens': 8192}, 'capabilities': {}}}
        self.prepare = {'at': '/models', 'args': ['prepare'], 'verifyArgs': ['verify-pack'], 'gpu': True, 'sizeGb': 3}
        self.resources = {'memoryBytes': 59055800320, 'memorySwapBytes': 59055800320, 'memlockUnlimited': True, 'ipcLock': True}

    def build(self, version, stale=False):
        with patch.object(lab, 'profile', return_value=self.profile), patch.object(export, 'ROOT', self.root):
            r = {'engine': 'fixture', 'card': 'test', 'model': 'test', 'proof': [{'gates': 'load chat reasoning tools context speed'}]}
            L = lab.render(r)
            r['proof'][0]['launch_sha256'] = '0'*64 if stale else hashlib.sha256(json.dumps(L, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
            cat = {'cards': {'test': {'picks': ['test/fixture'], 'more': [], 'match': {}}}, 'recipes': {'test/fixture': {**r, 'launch': L}}}
            (self.root / 'dist/catalog.json').write_text(json.dumps(cat))
            return json.loads(export.build() if version == 2 else export.build(version))

    def test_v2_excludes_prepare_only_and_resources_only(self):
        for key, value in [('prepare', self.prepare), ('resources', self.resources)]:
            with self.subTest(key=key):
                self.profile[key] = value
                self.assertEqual(self.build(2)['hardware'], {})
                del self.profile[key]

    def test_v3_preserves_exact_mounts_preparation_and_resources(self):
        self.profile.update(prepare=self.prepare, resources=self.resources)
        r = self.build(3)['hardware']['test']['recipes'][0]
        self.assertEqual(r['prepare'], self.prepare)
        self.assertEqual(r['launch']['resources'], self.resources)
        self.assertEqual(r['weights'][0]['mountPath'], '/models/raw')

    def test_changed_typed_launch_needs_new_acceptance(self):
        self.profile['resources'] = self.resources
        self.assertEqual(self.build(3, stale=True)['hardware'], {})

    def test_withdrawal_overrides_historical_acceptance(self):
        with patch.object(lab, 'profile', return_value=self.profile):
            r = {'engine': 'fixture', 'card': 'test', 'proof': [
                {'withdrawn': True}, {'gates': 'load chat reasoning tools context speed'}]}
            r['launch'] = lab.render(r)
            for version in (2, 3):
                self.assertFalse(export.eligible(r, version))

    def test_input_mount_cannot_mask_output(self):
        self.profile['prepare'] = {**self.prepare, 'at': '/models/raw/pack'}
        with self.assertRaisesRegex(AssertionError, 'masks'):
            self.build(3)

    def test_resource_contract_rejects_unbounded_or_unknown_options(self):
        for resource in [{'privileged': True}, {'memoryBytes': True}, {'memorySwapBytes': 1}, {'memoryBytes': 2, 'memorySwapBytes': 1}]:
            with self.subTest(resource=resource), self.assertRaises(AssertionError):
                self.profile['resources'] = resource
                self.build(3)

    def test_prepare_requires_verification_and_explicit_gpu_budget(self):
        self.profile['prepare'] = {'at': '/models', 'args': ['prepare']}
        with self.assertRaisesRegex(AssertionError, 'prepare requires'):
            self.build(3)

    def test_plugin_metadata_cannot_change_accepted_inputs(self):
        self.profile['prepare'] = self.prepare
        for key, value in [('mountPath', '/other'), ('dir', 'other'), ('files', 'partial.safetensors'), ('repository', 'other/repo'), ('revision', 'd'*40), ('layout', 'hub')]:
            with self.subTest(key=key), self.assertRaises(AssertionError):
                original = dict(self.profile['plugin']['weights'][0])
                self.profile['plugin']['weights'][0][key] = value
                try:
                    self.build(3)
                finally:
                    self.profile['plugin']['weights'][0] = original

    def test_nul_or_nonstring_environment_cannot_inject_docker_options(self):
        self.profile['resources'] = self.resources
        for value in ['hello\0--privileged', 1]:
            with self.subTest(value=value), self.assertRaisesRegex(AssertionError, 'environment'):
                self.profile['env'] = {'NOTE': value}
                self.build(3)

    def test_export_cannot_truncate_input_mounts(self):
        self.profile['plugin']['weights'] = []
        with self.assertRaisesRegex(AssertionError, 'input mounts'):
            self.build(3)


if __name__ == '__main__':
    unittest.main()
