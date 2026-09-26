#!/usr/bin/env python3
"""Build the price-history payload the visual page renders.

Every number on the page is recomputed here from `registry/price/<product>/<region>.json`,
so the page is a pure function of the records and `make price-visual-check` can prove it
is current. Nothing is taken from a scrape dump: the dumps live in the gitignored `out/`
directory and are inputs to the importers, not to the visual.

What is derived, per source:

  * Geizhals: the daily lowest tracked offer per listing, the weekly and monthly OHLC
    candles built from it, and the depth of every GPU class series.
  * Micro Center: the most recent run (one `observed_at` timestamp), the listings and
    stock per store, the SKUs priced in more than one store and whether their price
    differs, and the cheapest listing per store per chip.
  * Every other source: observation counts and the day span each one covers.

Usage
-----
    python3 scripts/build_price_history_data.py
    python3 scripts/build_price_history_data.py --featured rtx-5090 --out cache/price-history-data.json
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from import_market_snapshot import GPU_HARDWARE  # noqa: E402  (registry GPU classes)

DEFAULT_FEATURED = "rtx-5090"
REGION = "DE"
CURRENCY = "EUR"

# Micro Center labels its stores by id in every listing URL; these are the labels the
# retailer itself prints on the store page, for the ids the registry has observations for.
STORE_LABELS = {
    "101": "CA - Tustin",
    "115": "NY - Brooklyn",
    "181": "CO - Denver",
    "029": "Shippable Items",
}
STORE_QUERY_RE = re.compile(r"[?&]storeid=(\d+)")
MEMORY_SUFFIX_RE = re.compile(r"-\d+gb$")
# The three stores the chain-wide price comparison uses: the ones it stocks in person.
COMPARED_STORES = ("101", "115", "181")


def bucket_key(day: str, bucket: str) -> str:
    date = dt.date.fromisoformat(day)
    if bucket == "week":
        iso = date.isocalendar()
        return f"{iso[0]}-W{iso[1]:02d}"
    return f"{date.year}-{date.month:02d}"


def ohlc(points, bucket: str) -> list[dict]:
    """Collapse a daily lowest-offer series into OHLC candles.

    A source that publishes one price a day has no true open and close, so a candle opens
    on the first day of its bucket, closes on the last, and its wick is that bucket's
    range. `n` keeps how many days the bucket actually holds.
    """
    groups: dict[str, list[float]] = {}
    for day, price in sorted(points):
        groups.setdefault(bucket_key(day, bucket), []).append(price)
    candles = []
    for key in sorted(groups):
        prices = groups[key]
        candles.append({
            "k": key,
            "o": prices[0],
            "h": max(prices),
            "l": min(prices),
            "c": prices[-1],
            "n": len(prices),
        })
    return candles


def load_records(root: Path) -> list[dict]:
    """Every regional price record, sorted by product then region."""
    records = []
    for path in sorted(root.glob("registry/price/*/*.json")):
        record = json.loads(path.read_text())
        record["_path"] = str(path.relative_to(root))
        records.append(record)
    return records


def priced(record, retailer: str | None = None) -> list[dict]:
    observations = record.get("observations") or []
    return [
        o for o in observations
        if isinstance(o.get("amount"), (int, float)) and o["amount"] > 0
        and (retailer is None or o.get("retailer") == retailer)
    ]


def daily_series(observations: list[dict]) -> list[list]:
    """One point per day: the lowest offer the source tracked that day."""
    per_day: dict[str, list[float]] = collections.defaultdict(list)
    for o in observations:
        per_day[o["observed_at"][:10]].append(o["amount"])
    return [[day, min(prices)] for day, prices in sorted(per_day.items())]


def short_name(slug: str) -> str:
    words = [w for w in slug.split("-") if w not in NOISE and not w.startswith("a3")]
    acronym = {"oc", "xt", "xtx", "ti", "gre", "super", "x3", "v2"}
    return " ".join(
        w.upper() if (i == 0 or w.lower() in acronym) else w.title()
        for i, w in enumerate(words)
    )


NOISE = {"geforce", "rtx", "rog", "gddr7", "html", "32g", "16g", "24gb", "32gb"}


def geizhals(records: list[dict], featured: str) -> tuple[list[dict], dict]:
    """The featured class: one series per listing, plus the market floor across them."""
    record = next(
        (r for r in records if r["product"]["id"] == featured and r["region"]["code"] == REGION),
        None,
    )
    if record is None:
        return [], {}
    by_url: dict[str, list] = collections.defaultdict(list)
    for o in priced(record):
        by_url[o["url"]].append((o["observed_at"][:10], o["amount"]))
    listings = []
    for url, rows in by_url.items():
        slug = url.rsplit("/", 1)[-1].replace(".html", "")
        points = sorted(rows)
        listings.append({
            "slug": slug,
            "short": short_name(slug),
            "name": short_name(slug),
            "points": [[day, price] for day, price in points],
            "min": min(price for _, price in points),
            "max": max(price for _, price in points),
            "current": points[-1][1],
            "days": len(points),
        })
    listings.sort(key=lambda g: -g["days"])

    floor = daily_series(priced(record))
    days = [day for day, _ in floor]
    meta = {
        "id": featured,
        "name": record["product"]["name"],
        "region": record["region"]["name"],
        "currency": record["region"]["currency"],
        "observations": len(priced(record)),
        "days": len(floor),
        "listings": len(by_url),
        "first": days[0] if days else None,
        "last": days[-1] if days else None,
        "lowest": record.get("summary", {}).get("lowest_new"),
        "floor": floor,
    }
    return listings, meta


def microcenter(records: list[dict]) -> tuple[dict, list[dict]]:
    """Micro Center: store-level stock and chain-wide pricing, from the newest run.

    The chain prices its cards centrally, so the honest comparison is between stores
    priced in the *same* run; comparing a store's latest observation with another
    store's older one would measure time, not price.
    """
    observations = [
        (r["product"]["id"], o)
        for r in records if r["region"]["code"] == "US"
        for o in priced(r, "microcenter")
    ]
    if not observations:
        return {}, []
    run = max(o["observed_at"] for _, o in observations)
    latest: dict[tuple[str, str, str], dict] = {}
    for product, o in observations:
        if o["observed_at"] != run:
            continue
        match = STORE_QUERY_RE.search(o.get("url") or "")
        store = match.group(1) if match else ""
        sku = STORE_QUERY_RE.search(o.get("url") or "")
        sku = re.sub(r"[?&]storeid=\d+", "", o.get("url") or "")
        latest[(product, sku, store)] = o

    per_store: dict[str, dict] = collections.defaultdict(lambda: {"listings": 0, "in_stock": 0})
    sku_prices: dict[tuple[str, str], dict[str, float]] = collections.defaultdict(dict)
    chips: dict[str, dict] = collections.defaultdict(lambda: {"prices": [], "stores": collections.defaultdict(list)})
    for (product, sku, store), o in latest.items():
        per_store[store]["listings"] += 1
        if o.get("in_stock"):
            per_store[store]["in_stock"] += 1
        sku_prices[(product, sku)][store] = o["amount"]
        chip = MEMORY_SUFFIX_RE.sub("", product)
        chips[chip]["prices"].append(o["amount"])
        chips[chip]["stores"][store].append(o["amount"])

    compared = {
        key: prices for key, prices in sku_prices.items()
        if len([s for s in prices if s in COMPARED_STORES]) >= 2
    }
    divergence = []
    for chip, data in chips.items():
        mins = {
            store: min(values) for store, values in data["stores"].items()
            if store in COMPARED_STORES
        }
        if len(mins) == len(COMPARED_STORES) and max(mins.values()) > min(mins.values()):
            divergence.append({
                "chip": short_name(chip),
                "mins": mins,
                "spread": max(mins.values()) - min(mins.values()),
            })
    divergence.sort(key=lambda row: row["spread"])

    stores = {
        store: {"id": store, "label": STORE_LABELS.get(store) or ("Unattributed" if not store else f"Store {store}")}
        for store in sorted(per_store, key=lambda s: -per_store[s]["listings"])
    }
    meta = {
        "run": run,
        "listings": len(latest),
        "stores": stores,
        "compared": list(COMPARED_STORES),
        "per_store": {store: per_store[store] for store in stores},
        "sku_multi_store": len(compared),
        "sku_price_differs": sum(
            1 for prices in compared.values() if len(set(prices.values())) > 1
        ),
        "divergence": divergence,
    }
    chip_rows = [
        {
            "chip": short_name(chip),
            "count": len(data["prices"]),
            "min": min(data["prices"]),
            "max": max(data["prices"]),
            "by_store": {s: min(v) for s, v in data["stores"].items()},
        }
        for chip, data in chips.items() if len(data["prices"]) >= 3
    ]
    chip_rows.sort(key=lambda row: row["min"])
    return meta, chip_rows


def registry(records: list[dict], grid: dict, geizhals_meta: dict) -> dict:
    """Observation counts, per-source depth, and the depth rows the page charts."""
    by_retailer: collections.Counter = collections.Counter()
    days_by_retailer: dict[str, set] = collections.defaultdict(set)
    for record in records:
        for o in record.get("observations") or []:
            by_retailer[o["retailer"]] += 1
            days_by_retailer[o["retailer"]].add(o["observed_at"][:10])

    de_days = [day for day, _ in geizhals_meta.get("floor", [])]
    other_days = sorted({
        day for retailer, days in days_by_retailer.items() if retailer != "geizhals"
        for day in days
    })
    class_days = sorted((c["days"] for c in grid.get("cards", [])), reverse=True)
    span = lambda days: (
        dt.date.fromisoformat(days[-1]) - dt.date.fromisoformat(days[0])
    ).days + 1 if days else 0
    depth = [
        {"label": "Geizhals · deepest class", "value": class_days[0] if class_days else 0, "tone": "gold"},
        {"label": "Geizhals · median class",
         "value": class_days[len(class_days) // 2] if class_days else 0, "tone": "gold"},
        {"label": f"Geizhals · {geizhals_meta['name']}", "value": len(de_days), "tone": "gold"},
        {"label": "Registry · every other source", "value": span(other_days), "tone": "navy"},
        {"label": "Micro Center · runs recorded",
         "value": len(days_by_retailer.get("microcenter", set())), "tone": "sage"},
        {"label": "Scanner · snapshot days", "value": len(other_days), "tone": "sage"},
    ]
    return {
        "observations": sum(by_retailer.values()),
        "records": len(records),
        "by_retailer": dict(by_retailer.most_common()),
        "days_by_retailer": {k: len(v) for k, v in days_by_retailer.items()},
        "depth": depth,
        "span_days": span(sorted({d for days in days_by_retailer.values() for d in days})),
    }


def grid(records: list[dict]) -> dict:
    """Every GPU class the hardware collection describes, deepest first."""
    classes = set(GPU_HARDWARE)
    cards = []
    for record in records:
        if record["region"]["currency"] != CURRENCY or record["product"]["id"] not in classes:
            continue
        points = daily_series(priced(record))
        if len(points) < 2:
            continue
        first, last = points[0][1], points[-1][1]
        change = round((last - first) / first * 100, 1) if first else None
        cards.append({
            "id": record["product"]["id"],
            "name": record["product"]["name"],
            "listings": len({o["url"] for o in priced(record)}),
            "days": len(points),
            "current": last,
            "first": first,
            "lo": min(price for _, price in points),
            "hi": max(price for _, price in points),
            "change_pct": change,
            "direction": "up" if (change or 0) > 0.5 else "down" if (change or 0) < -0.5 else "flat",
            "points": points,
            "candles": ohlc(points, "week" if len(points) < 500 else "month"),
        })
    cards.sort(key=lambda c: -c["days"])
    return {
        "cards": cards,
        "classes": len(cards),
        "observations": sum(len(priced(r)) for r in records if r["region"]["currency"] == CURRENCY
                            and r["product"]["id"] in classes),
        "year_deep": sum(1 for c in cards if c["days"] >= 365),
        "deepest": cards[0]["days"] if cards else 0,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=".", help="registry root (default: current directory)")
    ap.add_argument("--featured", default=DEFAULT_FEATURED,
                    help=f"GPU class the page leads with (default: {DEFAULT_FEATURED})")
    ap.add_argument("--out", default="cache/price-history-data.json",
                    help="payload path (default: cache/price-history-data.json)")
    args = ap.parse_args()

    root = Path(args.root).expanduser().resolve()
    records = load_records(root)

    listings, geizhals_meta = geizhals(records, args.featured)
    mc_meta, mc_chips = microcenter(records)
    classes = grid(records)
    totals = registry(records, classes, geizhals_meta)

    deepest = classes["cards"][0] if classes["cards"] else None
    payload = {
        "geizhals": listings,
        "geizhals_meta": geizhals_meta,
        "mc": mc_meta,
        "mc_chips": mc_chips,
        "registry": totals,
        "gpu": classes,
        "candles": {
            "featured": {
                "title": f"{geizhals_meta.get('name', args.featured)} · market floor",
                "bucket": "week",
                "listings": geizhals_meta.get("listings", 0),
                "days": geizhals_meta.get("days", 0),
                "first": geizhals_meta.get("first"),
                "last": geizhals_meta.get("last"),
                "candles": ohlc(geizhals_meta.get("floor", []), "week"),
            },
            "deepest": {
                "id": deepest["id"] if deepest else None,
                "title": deepest["name"] if deepest else "",
                "bucket": "month",
                "days": deepest["days"] if deepest else 0,
                "candles": ohlc(deepest["points"], "month") if deepest else [],
            },
        },
    }

    out = Path(args.out).expanduser()
    if not out.is_absolute():
        out = root / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload))
    print(f"{len(listings)} listings in {geizhals_meta.get('id')} · {geizhals_meta.get('days')} days · "
          f"{geizhals_meta.get('observations')} observations")
    print(f"microcenter: run {mc_meta.get('run')} · {mc_meta.get('listings')} listings across "
          f"{len(mc_meta.get('stores', {}))} stores · "
          f"{mc_meta.get('sku_price_differs')} of {mc_meta.get('sku_multi_store')} multi-store SKUs differ")
    print(f"{classes['classes']} classes · {classes['observations']:,} observations · deepest {classes['deepest']}d")
    print(f"wrote {out} ({out.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
