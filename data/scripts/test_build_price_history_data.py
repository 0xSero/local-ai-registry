"""The price-history payload's two claim-bearing derivations.

Both of these decide something the published page asserts, and both are easy to get
wrong in a way that still renders:

  * candles: a source that publishes one price a day has no true open/close, so the
    candle must come from the bucket's first and last day, not from the extremes;
  * the chain-wide price claim: Micro Center prices its cards centrally, so stores may
    only be compared inside one run. Comparing each store's *latest* observation would
    measure the time between runs and invent price differences.
"""

import unittest

from build_price_history_data import STORE_LABELS, microcenter, ohlc, short_name


def observation(product, store, amount, at, in_stock=True):
    url = f"https://www.microcenter.com/product/1/{product}"
    if store:
        url = f"{url}?storeid={store}"
    return {
        "amount": amount,
        "condition": "new",
        "currency": "USD",
        "in_stock": in_stock,
        "observed_at": at,
        "quantity": None,
        "retailer": "microcenter",
        "title": product,
        "url": url,
    }


def record(product, observations):
    return {
        "product": {"category": "gpu", "id": product, "name": product.upper()},
        "region": {"code": "US", "currency": "USD", "name": "United States"},
        "observations": observations,
    }


class Candles(unittest.TestCase):
    def test_bucket_opens_on_the_first_day_and_closes_on_the_last(self):
        points = [
            ["2026-01-05", 100.0],  # Monday
            ["2026-01-07", 130.0],
            ["2026-01-09", 90.0],  # Friday, same ISO week
            ["2026-01-12", 95.0],  # next week
        ]
        first, second = ohlc(points, "week")

        self.assertEqual(first["k"], "2026-W02")
        self.assertEqual((first["o"], first["c"]), (100.0, 90.0))
        self.assertEqual((first["h"], first["l"]), (130.0, 90.0))
        self.assertEqual(first["n"], 3)
        self.assertEqual((second["o"], second["c"]), (95.0, 95.0))
        self.assertEqual(second["k"], "2026-W03")

    def test_month_buckets_split_on_the_calendar(self):
        points = [["2026-01-31", 10.0], ["2026-02-01", 20.0]]
        january, february = ohlc(points, "month")
        self.assertEqual((january["k"], january["c"]), ("2026-01", 10.0))
        self.assertEqual((february["k"], february["o"]), ("2026-02", 20.0))


class ChainWidePricing(unittest.TestCase):
    def test_prices_are_only_compared_inside_one_run(self):
        # The same SKU at a different price, but observed on a different day, is the
        # chain changing its price, not two stores disagreeing.
        records = [
            record("rtx-5070", [
                observation("rtx-5070", "101", 549.99, "2026-09-01T10:00:00Z"),
                observation("rtx-5070", "115", 549.99, "2026-09-01T10:00:00Z"),
                observation("rtx-5070", "181", 599.99, "2026-09-08T10:00:00Z"),
            ]),
        ]
        meta, _ = microcenter(records)
        self.assertEqual(meta["run"], "2026-09-08T10:00:00Z")
        self.assertEqual(meta["sku_multi_store"], 0)
        self.assertEqual(meta["sku_price_differs"], 0)

    def test_a_real_divergence_inside_a_run_is_reported(self):
        records = [
            record("rtx-5070", [
                observation("rtx-5070", "101", 549.99, "2026-09-01T10:00:00Z"),
                observation("rtx-5070", "115", 579.99, "2026-09-01T10:00:00Z"),
            ]),
        ]
        meta, _ = microcenter(records)
        self.assertEqual(meta["sku_multi_store"], 1)
        self.assertEqual(meta["sku_price_differs"], 1)

    def test_stores_are_counted_with_their_labels(self):
        records = [
            record("rtx-5070", [
                observation("rtx-5070", "101", 549.99, "2026-09-01T10:00:00Z", in_stock=True),
                observation("rtx-5070", "115", 549.99, "2026-09-01T10:00:00Z", in_stock=False),
            ]),
        ]
        meta, _ = microcenter(records)
        self.assertEqual(meta["stores"]["101"]["label"], STORE_LABELS["101"])
        self.assertEqual(meta["per_store"]["101"], {"listings": 1, "in_stock": 1})
        self.assertEqual(meta["per_store"]["115"], {"listings": 1, "in_stock": 0})

    def test_a_chip_is_its_product_id_without_the_memory_suffix(self):
        records = [
            record("rtx-5070-ti-16gb", [
                observation("rtx-5070-ti-16gb", "101", 549.99, "2026-09-01T10:00:00Z"),
                observation("rtx-5070-ti-16gb", "115", 549.99, "2026-09-01T10:00:00Z"),
                observation("rtx-5070-ti-16gb", "181", 549.99, "2026-09-01T10:00:00Z"),
            ]),
        ]
        _, chips = microcenter(records)
        self.assertEqual([row["chip"] for row in chips], ["5070 TI"])
        self.assertEqual(chips[0]["by_store"], {"101": 549.99, "115": 549.99, "181": 549.99})


class Names(unittest.TestCase):
    def test_short_name_keeps_the_acronyms_and_drops_the_noise(self):
        self.assertEqual(short_name("nvidia-geforce-rtx-5090-founders-edition-a3381601"),
                         "NVIDIA 5090 Founders Edition")
        self.assertEqual(short_name("asus-rog-astral-rtx-5090-oc-a3381601"), "ASUS Astral 5090 OC")
        self.assertEqual(short_name("rx-9070-xt"), "RX 9070 XT")


if __name__ == "__main__":
    unittest.main()
