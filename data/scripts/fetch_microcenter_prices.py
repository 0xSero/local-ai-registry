#!/usr/bin/env python3
"""Convert a Micro Center GPU scrape into a scanner-compatible price snapshot.

microcenter.com blocks non-US IPs behind Cloudflare, so the scrape happens outside
the registry (see ~/ai/microcenter-gpu-prices/scrape.py). This script only maps
that scrape onto the registry contract:

  * product ids come from the registry itself - the SKU signature rules in
    import_market_snapshot.py applied to existing price products plus the ids
    implied by hardware memory configurations, so a GPU the hardware collection
    does not describe is reported instead of invented;
  * one observation per card listing per store, with the store kept in the listing
    URL exactly like the existing Micro Center observations (`?storeid=101`);
  * Micro Center reports per-store stock and often only a floor ("25+ IN STOCK"), so
    quantity stays null unless the listing gives an exact count;
  * prior observations for the same product are carried into the snapshot so
    import_market_snapshot.py merges instead of dropping other retailers, and
    enrich_hardware_prices.py still ignores anything older than its freshness
    window.

Usage
-----
    python3 scripts/fetch_microcenter_prices.py ~/ai/microcenter-gpu-prices/out/latest.json
    python3 scripts/import_market_snapshot.py cache/microcenter-prices.json
    python3 scripts/enrich_hardware_prices.py
    python3 scripts/curate_registry.py
    python3 scripts/validate_registry.py
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

from fetch_extra_prices import REGIONS
from import_market_snapshot import gpu_signature, product_name

REGION = REGIONS["US"]
RETAILER = "microcenter"
CATEGORY = "gpu"
STORE_SUFFIX_RE = re.compile(r"-\d+gb$")
QUANTITY_RE = re.compile(r"(\d+)\s+IN STOCK", re.IGNORECASE)


def utc_stamp(value: str) -> str:
    """Registry timestamps are RFC3339 UTC with a trailing Z."""
    return re.sub(r"\+00:00$", "Z", str(value))


def condition(title: str) -> str:
    return "refurbished" if re.search(r"refurbished|renewed", title, re.I) else "new"


def quantity(stock_text: str) -> int | None:
    """Exact units in stock, or None when Micro Center only gives a floor."""
    match = QUANTITY_RE.search(stock_text or "")
    if match and "+" not in stock_text:
        return int(match.group(1))
    return None


def signature_index(root: Path) -> dict[tuple, str]:
    """SKU signature -> registry product id, existing products first."""
    existing = {path.parent.name for path in (root / "price").glob("*/*.json")}
    derived = {
        STORE_SUFFIX_RE.sub("", path.stem) for path in (root / "hardware").glob("*.json")
    }
    index: dict[tuple, str] = {}
    for product_id in sorted(existing) + sorted(derived - existing):
        signature = gpu_signature(product_name(product_id))
        if signature is not None:
            index.setdefault(signature, product_id)
    return index


def prior_listings(root: Path, product_id: str, region: dict | None = None) -> list[dict]:
    """Observations already recorded for this product and region, as listings."""
    region = region or REGION
    path = root / "price" / product_id / f"{region['code'].lower()}.json"
    if not path.is_file():
        return []
    record = json.loads(path.read_text())
    listings = []
    for observation in record.get("observations") or []:
        if not isinstance(observation, dict):
            continue
        listings.append(
            {
                "retailer": observation.get("retailer"),
                "productId": product_id,
                "productName": observation.get("title"),
                "category": (record.get("product") or {}).get("category") or CATEGORY,
                "price": observation.get("amount"),
                "condition": observation.get("condition") or "new",
                "currency": observation.get("currency"),
                "inStock": observation.get("in_stock"),
                "quantity": observation.get("quantity"),
                "url": observation.get("url"),
                "fetchedAt": observation.get("observed_at"),
                "region": record.get("region") or region,
            }
        )
    return listings


def microcenter_listings(scrape: dict, index: dict[tuple, str]) -> tuple[list[dict], Counter, Counter]:
    fetched_at = utc_stamp(scrape.get("generated_at"))
    listings: list[dict] = []
    unmatched: Counter = Counter()
    unpriced: Counter = Counter()
    for item in scrape.get("items") or []:
        if not isinstance(item, dict):
            continue
        chip = item.get("chip") or item.get("name") or "unknown"
        title = item.get("name")
        url = item.get("url")
        price = item.get("price")
        if not isinstance(title, str) or not isinstance(url, str) or not url.startswith("https://"):
            continue
        if not isinstance(price, (int, float)) or price <= 0:
            unpriced[chip] += 1
            continue
        product_id = index.get(gpu_signature(title))
        if product_id is None:
            unmatched[chip] += 1
            continue
        store_id = str(item.get("store_id") or "")
        store_url = url if store_id in ("", "029") else f"{url}?storeid={store_id}"
        stock_text = item.get("stock_text") or ""
        listings.append(
            {
                "retailer": RETAILER,
                "productId": product_id,
                "productName": title,
                "category": CATEGORY,
                "price": price,
                "condition": condition(title),
                "currency": REGION["currency"],
                "inStock": bool(item.get("in_stock")),
                "quantity": quantity(stock_text),
                "url": store_url,
                "fetchedAt": fetched_at,
                "region": REGION,
            }
        )
    return listings, unmatched, unpriced


def dedupe(listings: list[dict]) -> list[dict]:
    seen = set()
    unique = []
    for listing in listings:
        key = (
            listing["retailer"],
            listing["url"],
            listing["condition"],
            listing["price"],
            listing["fetchedAt"],
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(listing)
    return unique


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("scrape")
    parser.add_argument("--root", type=Path, default=Path("registry"))
    parser.add_argument("--out", type=Path, default=Path("cache/microcenter-prices.json"))
    args = parser.parse_args()

    scrape = json.loads(Path(args.scrape).read_text())
    index = signature_index(args.root)
    listings, unmatched, unpriced = microcenter_listings(scrape, index)

    products = {listing["productId"] for listing in listings}
    fresh = {
        (listing["retailer"], listing["url"], listing["condition"], listing["price"])
        for listing in listings
    }
    carried = []
    for product_id in sorted(products):
        carried.extend(
            prior
            for prior in prior_listings(args.root, product_id)
            if (prior["retailer"], prior["url"], prior["condition"], prior["price"]) not in fresh
        )
    merged = dedupe(listings + carried)

    snapshot = {
        "generatedAt": utc_stamp(scrape.get("generated_at")),
        "listings": merged,
        "summaries": [],
        "errors": [],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n")

    print(
        f"{len(listings)} Micro Center observations across {len(products)} registry "
        f"products; {len(merged)} listings after keeping prior observations -> {args.out}"
    )
    for chip, count in unmatched.most_common():
        print(f"  no registry product for {chip}: {count} listings")
    for chip, count in unpriced.most_common():
        print(f"  no listed price for {chip}: {count} listings")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
