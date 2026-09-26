import unittest
from check_lil_import import check


class LocalInferenceLabImport(unittest.TestCase):
    def test_source_coverage_and_external_trust_boundary(self):
        self.assertGreater(check(), 0)
