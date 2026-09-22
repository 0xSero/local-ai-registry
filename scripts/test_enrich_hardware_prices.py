"""enrich_hardware_prices refreshes a current price only from newer evidence."""

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from enrich_hardware_prices import enrich

PRODUCT = "rtx-5090"
NOW = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def stamp(days_ago: float) -> str:
    moment = NOW - dt.timedelta(days=days_ago)
    return moment.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


RECORDED = stamp(1)
FRESH = stamp(0.5)
STALE = stamp(30)


def hardware(street: float, fact_captured_at: str | None):
    record = {
        "schema_version": "local-ai-registry/v1",
        "id": "rtx-5090-32gb",
        "vendor": "nvidia",
        "name": "NVIDIA GeForce RTX 5090",
        "kind": "discrete",
        "accelerator_backend": "nvidia",
        "memory": {"vram_gb": 32, "cpu_memory_gb": None, "vram_type": "GDDR7"},
        "aliases": ["rtx 5090"],
        "products": [PRODUCT],
        "sources": [{"kind": "vendor", "url": "https://www.nvidia.com/en-us/geforce/graphics-cards/compare/"}],
        "commercial": {
            "availability": {"reason": "unobserved", "state": "unknown"},
            "current_stock": None,
            "current_street_price": {"amount": street, "currency": "USD"},
            "current_system_price": None,
            "msrp": {"amount": 1999, "currency": "USD"},
            "prices": [
                {
                    "amount": 1999,
                    "as_of": "2025-01-30",
                    "currency": "USD",
                    "kind": "MSRP",
                    "region": "US",
                    "scope": "manufacturer_launch_price",
                    "unit": "one_time",
                }
            ],
        },
        "facts": {},
    }
    if fact_captured_at:
        record["facts"]["commercial.current_street_price"] = {
            "state": "known",
            "reason": "fresh-in-stock-us-retailer-observation",
            "provenance": {
                "captured_at": fact_captured_at,
                "sources": [
                    {
                        "captured_at": fact_captured_at,
                        "kind": "retailer",
                        "publisher": "microcenter",
                        "url": "https://www.microcenter.com/product/690483/pny-nvidia-geforce-rtx-5090-overclocked-triple-fan-32gb-gddr7-pcie-50-graphics-card",
                    }
                ],
            },
        }
    return record


def price(observed_at: str, amount: float):
    return {
        "schema_version": "local-ai-registry/v1",
        "id": f"{PRODUCT}--us",
        "product": {"id": PRODUCT, "name": "RTX 5090", "category": "gpu"},
        "region": {"code": "US", "name": "United States", "currency": "USD"},
        "hardware": [{"id": "rtx-5090-32gb", "match_scope": "family"}],
        "observed_at": observed_at,
        "summary": {
            "in_stock_count": 1,
            "listing_count": 1,
            "lowest_new": amount,
            "lowest_refurbished": None,
            "lowest_used": None,
            "retailer_count": 1,
        },
        "observations": [
            {
                "retailer": "microcenter",
                "title": "NVIDIA GeForce RTX 5090 Gaming OC Triple Fan 32GB GDDR7 PCIe 5.0 Graphics Card",
                "condition": "new",
                "amount": amount,
                "currency": "USD",
                "in_stock": True,
                "quantity": None,
                "url": "https://www.microcenter.com/product/690449/gigabyte-nvidia-geforce-rtx-5090-gaming-oc-triple-fan-32gb-gddr7-pcie-50-graphics-card",
                "observed_at": observed_at,
            }
        ],
        "verification": {"state": "candidate", "method": "retailer query", "rejected_observations": 0},
        "provenance": {
            "scanner": "https://github.com/0xSero/local-ai-scanner-cli",
            "snapshot_generated_at": observed_at,
            "source_error_count": 0,
        },
    }


class EnrichHardwarePriceTests(unittest.TestCase):
    def run_enrich(self, record, price, max_age_days=7):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "hardware").mkdir()
            (root / "price" / PRODUCT).mkdir(parents=True)
            (root / "hardware" / "rtx-5090-32gb.json").write_text(json.dumps(record))
            (root / "price" / PRODUCT / "us.json").write_text(json.dumps(price))
            counters = enrich(root, max_age_days)
            after = json.loads((root / "hardware" / "rtx-5090-32gb.json").read_text())
            return counters, after

    def test_newer_observation_replaces_the_current_price(self):
        _, after = self.run_enrich(hardware(2499.99, RECORDED), price(FRESH, 4699.99))
        commercial = after["commercial"]
        self.assertEqual(commercial["current_street_price"], {"amount": 4699.99, "currency": "USD"})
        self.assertEqual(commercial["msrp"], {"amount": 1999, "currency": "USD"})
        self.assertEqual(commercial["current_stock"], True)
        self.assertEqual(commercial["availability"]["state"], "available")
        fact = after["facts"]["commercial.current_street_price"]
        self.assertEqual(fact["provenance"]["captured_at"], FRESH)
        amounts = [row["amount"] for row in commercial["prices"]]
        self.assertEqual(amounts, [1999, 4699.99])

    def test_older_observation_never_regresses_the_current_price(self):
        _, after = self.run_enrich(
            hardware(2499.99, RECORDED), price(STALE, 1899.99), max_age_days=90
        )
        commercial = after["commercial"]
        self.assertEqual(commercial["current_street_price"], {"amount": 2499.99, "currency": "USD"})
        fact = after["facts"]["commercial.current_street_price"]
        self.assertEqual(fact["provenance"]["captured_at"], RECORDED)
        self.assertEqual([row["amount"] for row in commercial["prices"]], [1999, 1899.99])

    def test_missing_fact_is_filled_from_a_fresh_observation(self):
        _, after = self.run_enrich(hardware(2499.99, None), price(FRESH, 4699.99))
        fact = after["facts"]["commercial.current_street_price"]
        self.assertEqual(fact["provenance"]["captured_at"], FRESH)


if __name__ == "__main__":
    unittest.main()
