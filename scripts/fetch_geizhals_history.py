#!/usr/bin/env python3
"""Convert a Geizhals price-history dump into registry observations.

Geizhals publishes a per-product daily price series (its "Preisentwicklung"
chart) from a public JSON endpoint, and it reaches back to product launch. That
series is the only year-deep, machine-readable GPU price history available to this
registry, so every point becomes one DE observation under the `geizhals`
retailer.

The dump is produced outside the registry by
`~/ai/microcenter-gpu-prices/geizhals_history.py`, because the endpoint sits
behind a Cloudflare JS challenge that needs a real browser session.

Appending, never replacing
--------------------------
`import_market_snapshot.py` replaces a price record wholesale by id, so importing
the series alone would drop every other retailer's observations for the same product
and region. This script therefore reads the observations already recorded for each
product and region, unions them with the Geizhals series, and writes the union back:
prior observations survive, re-importing the same dump is idempotent, and a product
that loses its Geizhals series keeps every observation it had.

Reading the series
------------------
Each point is `[epoch_ms, price, units]`. Geizhals charts the lowest offer it
tracks for that product on that day, so a point exists only while an offer was
available: `in_stock` is true and `quantity` stays null, because the series records
neither stock nor units. Prices below the regional floor (the same floor
`fetch_extra_prices.py` applies to Geizhals listings) are dropped as parse noise or
accessory listings and counted.

Usage
-----
    python3 scripts/fetch_geizhals_history.py ~/ai/microcenter-gpu-prices/out/geizhals-history-*.json
    python3 scripts/import_market_snapshot.py cache/geizhals-history.json
    python3 scripts/curate_registry.py
    python3 scripts/validate_registry.py
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from fetch_extra_prices import MIN_PRICE, REGIONS
from fetch_microcenter_prices import dedupe, prior_listings, signature_index, utc_stamp
from import_market_snapshot import gpu_signature

REGION = REGIONS["DE"]
RETAILER = "geizhals"
CATEGORY = "gpu"


def day_stamp(milliseconds: float) -> str:
    """Geizhals points carry epoch milliseconds; the registry wants RFC3339 UTC."""
    return datetime.fromtimestamp(milliseconds / 1000, timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def geizhals_listings(dump: dict, index: dict[tuple, str]) -> tuple[list[dict], Counter, Counter, Counter]:
    """Map a Geizhals history dump onto scanner-compatible listings.

    Returns the listings plus counters for products with no registry product, days
    with no tracked offer (`absent`), and points rejected by the price floor.
    """
    fetched_at = utc_stamp(dump.get("generated_at"))
    floor = MIN_PRICE.get((REGION["code"], REGION["currency"]))
    listings: list[dict] = []
    unmatched: Counter = Counter()
    absent: Counter = Counter()
    rejected: Counter = Counter()
    for product in dump.get("products") or []:
        if not isinstance(product, dict):
            continue
        slug = product.get("slug")
        title = product.get("name") or ""
        if not isinstance(slug, str) or not slug:
            continue
        product_id = index.get(gpu_signature(title))
        if product_id is None:
            unmatched[title or slug] += 1
            continue
        url = f"https://geizhals.de/{slug}"
        for point in product.get("series") or []:
            if not isinstance(point, list) or len(point) < 2:
                rejected[title] += 1
                continue
            stamp, amount = point[0], point[1]
            if amount is None:
                absent[title] += 1
                continue
            if not isinstance(stamp, (int, float)) or not isinstance(amount, (int, float)):
                rejected[title] += 1
                continue
            if floor is not None and amount < floor:
                rejected[title] += 1
                continue
            listings.append(
                {
                    "retailer": RETAILER,
                    "productId": product_id,
                    "productName": title,
                    "category": CATEGORY,
                    "price": amount,
                    "condition": "new",
                    "currency": REGION["currency"],
                    "inStock": True,
                    "quantity": None,
                    "url": url,
                    "fetchedAt": day_stamp(stamp),
                    "region": REGION,
                }
            )
    return listings, unmatched, absent, rejected


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("dump")
    parser.add_argument("--root", type=Path, default=Path("registry"))
    parser.add_argument("--out", type=Path, default=Path("cache/geizhals-history.json"))
    args = parser.parse_args()

    dump = json.loads(Path(args.dump).read_text())
    index = signature_index(args.root)
    listings, unmatched, absent, rejected = geizhals_listings(dump, index)

    products = {listing["productId"] for listing in listings}
    fresh = {
        (listing["retailer"], listing["url"], listing["condition"], listing["price"], listing["fetchedAt"])
        for listing in listings
    }
    carried = []
    for product_id in sorted(products):
        carried.extend(
            prior
            for prior in prior_listings(args.root, product_id, REGION)
            if (prior["retailer"], prior["url"], prior["condition"], prior["price"], prior["fetchedAt"])
            not in fresh
        )
    merged = dedupe(listings + carried)

    snapshot = {
        "generatedAt": utc_stamp(dump.get("generated_at")),
        "listings": merged,
        "summaries": [],
        "errors": [],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n")

    print(
        f"{len(listings)} Geizhals observations across {len(products)} registry products; "
        f"{len(merged)} listings after keeping prior observations -> {args.out}"
    )
    for name, count in unmatched.most_common():
        print(f"  no registry product for {name!r}: {count} products")
    for name, count in absent.most_common():
        print(f"  no tracked offer that day for {name!r}: {count} days")
    for name, count in rejected.most_common():
        print(f"  rejected points for {name!r}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
