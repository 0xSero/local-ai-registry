import unittest

import check_plugin_catalog as checker


def document(*hardware):
    """A minimal catalog: one gateway, no assets, the given hardware entries."""
    return {
        "schemaVersion": "omarchy-local-ai/recipes/1",
        "registryCommit": "a" * 40,
        "generatedAt": "2026-09-21T00:00:00Z",
        "gateway": {"image": "ghcr.io/0xsero/gateway@sha256:" + "b" * 64},
        "assets": {},
        "hardware": {
            hardware_id: {"match": {"name": name}, "recipe": {"id": hardware_id}}
            for hardware_id, name in hardware
        },
    }


class PluginCatalogCheckTests(unittest.TestCase):
    def test_provenance_stamp_alone_is_not_staleness(self):
        # A squash merge rewrites the last registry commit, so both stamp fields
        # change while every exported recipe stays identical. That must pass.
        committed = document(("rtx-2000-ada-16gb", "RTX 2000 Ada"))
        fresh = document(("rtx-2000-ada-16gb", "RTX 2000 Ada"))
        fresh["registryCommit"] = "c" * 40
        fresh["generatedAt"] = "2026-09-22T00:00:00Z"
        self.assertEqual(checker.compare(committed, fresh), [])

    def test_missing_hardware_id_is_stale_and_named(self):
        committed = document(("rtx-2000-ada-16gb", "RTX 2000 Ada"))
        fresh = document(("rtx-2000-ada-16gb", "RTX 2000 Ada"),
                         ("rtx-4090-24gb", "RTX 4090"))
        reasons = checker.compare(committed, fresh)
        self.assertTrue(reasons)
        self.assertTrue(any("rtx-4090-24gb" in reason and "missing" in reason
                           for reason in reasons), reasons)

    def test_withdrawn_hardware_id_is_stale_and_named(self):
        committed = document(("rtx-2000-ada-16gb", "RTX 2000 Ada"),
                            ("rtx-4090-24gb", "RTX 4090"))
        fresh = document(("rtx-2000-ada-16gb", "RTX 2000 Ada"))
        reasons = checker.compare(committed, fresh)
        self.assertTrue(reasons)
        self.assertTrue(any("rtx-4090-24gb" in reason for reason in reasons), reasons)

    def test_changed_entry_is_stale_and_named(self):
        committed = document(("rtx-2000-ada-16gb", "RTX 2000 Ada"))
        fresh = document(("rtx-2000-ada-16gb", "RTX 2000 Ada"))
        fresh["hardware"]["rtx-2000-ada-16gb"]["recipe"] = {"id": "renamed"}
        reasons = checker.compare(committed, fresh)
        self.assertTrue(reasons)
        self.assertTrue(any("rtx-2000-ada-16gb" in reason for reason in reasons), reasons)


if __name__ == "__main__":
    unittest.main()
