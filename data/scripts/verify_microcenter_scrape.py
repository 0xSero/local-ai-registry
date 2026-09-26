#!/usr/bin/env python3
"""Validate and summarise a scrape.py run.

Checks that the scrape is complete and internally consistent, then prints the
cross-store price table per GPU chip.

    python3 scripts/verify_microcenter_scrape.py out/latest.json
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

# Micro Center lists some in-store-only SKUs with an empty price element, so a row
# without a price is only a defect when the listing was expected to carry one.
NO_PRICE_OK_RE = re.compile(r"buy in store|not carried", re.I)


def main() -> None:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "out/latest.json")
    data = json.loads(path.read_text())
    items = data["items"]
    stores = data["stores"]
    failures: list[str] = []

    print(f"run {data['generated_at']}  {len(items)} rows  {len(stores)} stores")
    print(f"source {data['source']}")
    print(f"method {data['method']}\n")

    if not items:
        failures.append("no rows scraped")

    # every row must be identifiable; a missing price is only a defect when the SKU
    # is priced elsewhere or the listing was expected to carry a price
    priced_skus = {i["sku"] for i in items if i.get("price") is not None}
    priceless = 0
    for it in items:
        if not it.get("sku"):
            failures.append(f"row without SKU: {it.get('name')!r}")
        if not it.get("url"):
            failures.append(f"row without product URL: {it.get('sku')}")
        if not it.get("name"):
            failures.append(f"row without name: {it.get('sku')}")
        if not it.get("chip"):
            failures.append(f"unclassified GPU: {it.get('name')!r}")
        if it.get("price") is None:
            if it["sku"] not in priced_skus or NO_PRICE_OK_RE.search(it.get("stock_text") or ""):
                priceless += 1
            else:
                failures.append(f"unparsed price {it.get('price_text')!r} ({it.get('sku')})")
        if it.get("stock_text") is None:
            failures.append(f"missing stock text ({it.get('sku')})")
    print(f"rows without a listed price (in-store-only SKUs): {priceless}")

    # per store: SKUs must be unique (no pagination overlap), prices must parse
    for sid, name in stores.items():
        mine = [i for i in items if i["store_id"] == sid]
        skus = [i["sku"] for i in mine]
        dupes = {s for s in skus if skus.count(s) > 1}
        if dupes:
            failures.append(f"{name}: duplicate SKUs across pages {sorted(dupes)}")
        if not mine:
            failures.append(f"{name}: no rows")
        print(f"{name:<22} {len(mine):>4} cards  "
              f"{len({i['sku'] for i in mine}):>4} unique SKUs  "
              f"{sum(1 for i in mine if i['in_stock']):>4} in stock  "
              f"{sum(1 for i in mine if i['in_store_only']):>4} in-store only")

    # chip coverage: the headline GPU families must be present
    by_chip: dict[str, list[dict]] = defaultdict(list)  # type: ignore[name-defined]
    for it in items:
        if it.get("chip"):
            by_chip[it["chip"]].append(it)
    unchipped = [i for i in items if not i.get("chip")]
    print(f"\nchips found: {len(by_chip)}  unclassified rows: {len(unchipped)}")

    def floor_price(chip: str) -> float:
        prices = [i["price"] for i in by_chip[chip] if i["price"]]
        return min(prices) if prices else float("inf")

    for chip in sorted(by_chip, key=floor_price):
        rows = [i for i in by_chip[chip] if i["price"]]
        if not rows:
            print(f"{chip:<18} {len(by_chip[chip]):>3} listings  no listed price")
            continue
        cheapest = min(rows, key=lambda i: i["price"])
        print(f"{chip:<18} {len(by_chip[chip]):>3} listings  "
              f"min ${cheapest['price']:>8,.2f} ({stores.get(cheapest['store_id'], '?')})  "
              f"max ${max(i['price'] for i in rows):>8,.2f}")
    for chip in ("RTX 5090", "RTX 5080", "RTX 5070 Ti", "RTX 5070", "RTX 5060 Ti", "RTX PRO 6000"):
        if not any(c.startswith(chip) for c in by_chip):
            failures.append(f"expected chip missing from results: {chip}")

    print()
    if failures:
        print(f"FAIL ({len(failures)} issues)")
        for f in failures[:40]:
            print(f"  - {f}")
        raise SystemExit(1)
    print("OK: every row has SKU, URL, name and a parsed price; no duplicate SKUs per store")


if __name__ == "__main__":
    from collections import defaultdict

    main()
