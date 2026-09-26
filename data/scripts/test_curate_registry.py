"""curate_registry normalizes identity fields without dropping enriched evidence."""

import json
import tempfile
import unittest
from pathlib import Path

from curate_registry import curate_hardware, link_products

RECORD = {
    "schema_version": "local-ai-registry/v1",
    "id": "rtx-5090-32gb",
    "vendor": "nvidia",
    "name": "RTX 5090",
    "family": "rtx-5090",
    "kind": "discrete",
    "accelerator_backend": "nvidia",
    "memory": {
        "vram_gb": 32,
        "cpu_memory_gb": None,
        "vram_type": "GDDR7",
        "bandwidth_gb_per_s": 1792,
    },
    "aliases": ["rtx 5090"],
    "products": ["rtx-5090"],
    "sources": [
        {
            "captured_at": "2026-08-27T04:55:00Z",
            "kind": "vendor",
            "publisher": "NVIDIA",
            "url": "https://www.nvidia.com/en-us/geforce/graphics-cards/compare/?section=compare-specs",
        },
        {
            "captured_at": "2026-08-27T04:55:00Z",
            "kind": "vendor",
            "publisher": "NVIDIA",
            "url": "https://nvidianews.nvidia.com/news/nvidia-blackwell-geforce-rtx-50-series-opens-new-world-of-ai-computer-graphics",
        },
    ],
    "captured_at": "2026-08-27",
    "accelerator": {"count": 1, "unit": "GPU"},
    "compute": {"cuda_cores": 21760},
    "product_names": ["NVIDIA GeForce RTX 5090"],
    "commercial": {
        "availability": {
            "reason": "fresh-in-stock-retailer-observation",
            "scope": "at-least-one-us-retailer",
            "state": "available",
        },
        "current_stock": True,
        "current_street_price": {"amount": 2499.99, "currency": "USD"},
        "msrp": {"amount": 1999, "currency": "USD"},
        "prices": [
            {
                "amount": 2499.99,
                "as_of": "2026-08-31T21:07:10Z",
                "currency": "USD",
                "kind": "street_price",
                "region": "US",
                "scope": "current_in_stock_retail_listing",
                "unit": "one_time",
            }
        ],
    },
    "facts": {
        "commercial.current_street_price": {
            "state": "known",
            "reason": "fresh-in-stock-us-retailer-observation",
            "provenance": {
                "captured_at": "2026-08-31T21:07:10Z",
                "sources": [
                    {
                        "captured_at": "2026-08-31T21:07:10Z",
                        "kind": "retailer",
                        "publisher": "microcenter",
                        "url": "https://www.microcenter.com/product/690483/pny-nvidia-geforce-rtx-5090-overclocked-triple-fan-32gb-gddr7-pcie-50-graphics-card",
                    }
                ],
            },
        }
    },
}

PRICE = {
    "schema_version": "local-ai-registry/v1",
    "id": "rtx-5090--us",
    "product": {"id": "rtx-5090", "name": "RTX 5090", "category": "gpu"},
    "region": {"code": "US", "name": "United States", "currency": "USD"},
    "hardware": [{"id": "rtx-5090-32gb", "match_scope": "family"}],
    "observed_at": "2026-09-22T10:42:37Z",
    "summary": {
        "in_stock_count": 1,
        "listing_count": 1,
        "lowest_new": 4699.99,
        "lowest_refurbished": None,
        "lowest_used": None,
        "retailer_count": 1,
    },
    "observations": [
        {
            "retailer": "microcenter",
            "title": "NVIDIA GeForce RTX 5090 Gaming OC Triple Fan 32GB GDDR7 PCIe 5.0 Graphics Card",
            "condition": "new",
            "amount": 4699.99,
            "currency": "USD",
            "in_stock": True,
            "quantity": None,
            "url": "https://www.microcenter.com/product/690449/gigabyte-nvidia-geforce-rtx-5090-gaming-oc-triple-fan-32gb-gddr7-pcie-50-graphics-card?storeid=101",
            "observed_at": "2026-09-22T10:42:37Z",
        }
    ],
    "verification": {"state": "candidate", "method": "retailer query", "rejected_observations": 0},
    "provenance": {
        "scanner": "https://github.com/0xSero/local-ai-scanner-cli",
        "snapshot_generated_at": "2026-09-22T10:42:37Z",
        "source_error_count": 0,
    },
}

EVIDENCE_KEYS = (
    "commercial",
    "facts",
    "captured_at",
    "accelerator",
    "compute",
    "product_names",
)


class CurateHardwareTests(unittest.TestCase):
    def curate(self, record, with_price=True):
        """Run the same pair of passes main() runs: curate, then link products."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "hardware" / f"{record['id']}.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(record))
            if with_price:
                price_root = root / "price" / "rtx-5090"
                price_root.mkdir(parents=True)
                (price_root / "us.json").write_text(json.dumps(PRICE))
            curate_hardware(root)
            link_products(root)
            return json.loads(path.read_text())

    def test_products_still_come_from_the_price_records(self):
        after = self.curate(RECORD)
        self.assertEqual(after["products"], ["rtx-5090"])
        without = self.curate(RECORD, with_price=False)
        self.assertEqual(without["products"], [])

    def test_evidence_survives_a_rerun(self):
        after = self.curate(RECORD)
        for key in EVIDENCE_KEYS:
            with self.subTest(key=key):
                self.assertEqual(after.get(key), RECORD[key])
        self.assertEqual(after["memory"]["bandwidth_gb_per_s"], 1792)
        self.assertEqual(after["memory"]["vram_type"], "GDDR7")
        self.assertEqual(after["sources"], RECORD["sources"])

    def test_identity_fields_are_still_normalized(self):
        after = self.curate(RECORD)
        self.assertEqual(after["family"], "rtx-5090")
        self.assertEqual(after["id"], "rtx-5090-32gb")
        self.assertTrue(after["name"])

    def test_missing_derived_fields_are_filled(self):
        record = dict(RECORD)
        del record["family"]
        del record["aliases"]
        after = self.curate(record)
        self.assertEqual(after["family"], "rtx-5090")
        self.assertTrue(after["aliases"])


if __name__ == "__main__":
    unittest.main()
