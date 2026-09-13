#!/usr/bin/env python3
"""Verify the curated LIL import against its pinned, non-executable inventory."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT = ROOT / 'sources/local-inference-lab/2026-09-13.json'


def check():
    snapshot = json.loads(SNAPSHOT.read_text())
    expected = set()
    for profile in snapshot['profiles']:
        assert re.fullmatch(r'[a-f0-9]{40}', profile['source_commit']), profile
        assert profile['source_commit'] in profile['source_url'], profile
        assert re.fullmatch(r'[a-f0-9]{64}', profile['source_sha256']), profile
        assert 'block_text' not in profile, 'Do not copy upstream shell code into facts'
        if profile['disposition'] != 'import':
            assert 'registry_recipe_id' not in profile
            continue
        rid = profile['registry_recipe_id']
        assert rid not in expected, rid
        expected.add(rid)
        recipe = json.loads((ROOT / 'registry/recipe' / (rid + '.json')).read_text())
        assert recipe['recipe_source'] == 'local-inference-lab', rid
        assert recipe['status'] == 'candidate', rid
        assert recipe['launch']['kind'] == 'reference', rid
        assert not recipe['speed_sweep_ids'], 'Upstream source import must not fabricate acceptance'
        assert recipe['launch']['url'] == profile['source_url'], rid
        assert recipe['hardware_id'] == profile['hardware_id'], rid
        assert recipe['hardware_count'] == profile['hardware_count'], rid
        assert recipe['model_instance_id'] == profile['model_instance_id'], rid
        assert recipe['metadata']['source_sha256'] == profile['source_sha256'], rid
        credits = recipe['metadata']['credits']
        assert any(c['name'] == 'Local Inference Lab' for c in credits), rid
        assert all(c['name'] and c['role'] and c['url'].startswith('https://') for c in credits), rid
        assert (ROOT / 'registry/model-instance' / (recipe['model_instance_id'] + '.json')).exists(), rid
    actual = {p.stem for p in (ROOT / 'registry/recipe').glob('lil-*.json')
              if json.loads(p.read_text()).get('metadata', {}).get('source_snapshot') == str(SNAPSHOT.relative_to(ROOT))}
    assert actual == expected, (actual - expected, expected - actual)
    assert sum(c['kind'] == 'draft' for c in snapshot['catalog']) == 1
    return len(expected)


if __name__ == '__main__':
    print(f'Validated {check()} source-pinned LIL candidate recipes and catalog coverage')
