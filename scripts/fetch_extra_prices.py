#!/usr/bin/env python3
"""Fetch additional retailer listings for hardware the market snapshot missed.

Hits public search pages that already work in local-ai-scanner-cli (Alternate,
Ceneo, AWD-IT, Dospara) plus Geizhals for extra GPU SKUs. Writes a scanner-
compatible snapshot that import_market_snapshot.py can merge.
"""

from __future__ import annotations

import argparse
import json
import re
import ssl
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from urllib.parse import quote_plus, urljoin
from import_market_snapshot import listing_title_matches, listing_url_is_specific

TIMEOUT = 8
UA = "Mozilla/5.0 (compatible; local-ai-registry-price-fetch/1.0)"
SSL = ssl.create_default_context()

REGIONS = {
    "DE": {"code": "DE", "name": "Germany", "currency": "EUR"},
    "GB": {"code": "GB", "name": "United Kingdom", "currency": "GBP"},
    "JP": {"code": "JP", "name": "Japan", "currency": "JPY"},
    "PL": {"code": "PL", "name": "Poland", "currency": "PLN"},
    "US": {"code": "US", "name": "United States", "currency": "USD"},
}

PRODUCTS = [
    ("rtx-5090", "RTX 5090", "gpu"),
    ("rtx-5080", "RTX 5080", "gpu"),
    ("rtx-5070-ti", "RTX 5070 Ti", "gpu"),
    ("rtx-5070", "RTX 5070", "gpu"),
    ("rtx-5060-ti", "RTX 5060 Ti", "gpu"),
    ("rtx-5060", "RTX 5060", "gpu"),
    ("rtx-4090", "RTX 4090", "gpu"),
    ("rtx-4080-super", "RTX 4080 Super", "gpu"),
    ("rtx-4080", "RTX 4080", "gpu"),
    ("rtx-4070-ti-super", "RTX 4070 Ti Super", "gpu"),
    ("rtx-4070-ti", "RTX 4070 Ti", "gpu"),
    ("rtx-4070-super", "RTX 4070 Super", "gpu"),
    ("rtx-4070", "RTX 4070", "gpu"),
    ("rtx-4060-ti", "RTX 4060 Ti", "gpu"),
    ("rtx-4060", "RTX 4060", "gpu"),
    ("rtx-3090-ti", "RTX 3090 Ti", "gpu"),
    ("rtx-3090", "RTX 3090", "gpu"),
    ("rtx-3080-ti", "RTX 3080 Ti", "gpu"),
    ("rtx-3080", "RTX 3080", "gpu"),
    ("rtx-3070-ti", "RTX 3070 Ti", "gpu"),
    ("rtx-3070", "RTX 3070", "gpu"),
    ("rtx-3060-ti", "RTX 3060 Ti", "gpu"),
    ("rtx-3060", "RTX 3060", "gpu"),
    ("rtx-2000-ada", "RTX 2000 Ada", "gpu"),
    ("rtx-4000-ada", "RTX 4000 Ada", "gpu"),
    ("rtx-6000-ada", "RTX 6000 Ada", "gpu"),
    ("rtx-pro-4000-blackwell", "RTX PRO 4000 Blackwell", "gpu"),
    ("rtx-pro-4500-blackwell", "RTX PRO 4500 Blackwell", "gpu"),
    ("rtx-pro-6000-blackwell", "RTX PRO 6000 Blackwell", "gpu"),
    ("rtx-a6000", "RTX A6000", "gpu"),
    ("intel-arc-pro-b60", "Arc Pro B60", "gpu"),
    ("intel-arc-pro-b70", "Arc Pro B70", "gpu"),
    ("rx-7700-xt", "RX 7700 XT", "gpu"),
    ("rx-7900-xt", "RX 7900 XT", "gpu"),
    ("rx-7900-xtx", "RX 7900 XTX", "gpu"),
    ("rx-9070-xt", "RX 9070 XT", "gpu"),
    ("radeon-ai-pro-r9700", "Radeon AI PRO R9700", "gpu"),
    ("dgx-spark", "DGX Spark", "gpu"),
]

PRODUCT_IDS_BY_QUERY = {name: product_id for product_id, name, _ in PRODUCTS}

ACCESSORIES = (
    "cable", "adapter", "bracket", "riser", "laptop", "notebook",
    "prebuilt", "pre-built", "gaming pc", "sticker", "waterblock",
)
MIN_PRICE = {
    ("DE", "EUR"): 180,
    ("GB", "GBP"): 150,
    ("JP", "JPY"): 25000,
    ("PL", "PLN"): 600,
    ("US", "USD"): 150,
}


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def fetch(url):
    request = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT, context=SSL) as response:
            return response.status, response.read().decode("utf-8", "replace")
    except (urllib.error.URLError, TimeoutError, ssl.SSLError) as error:
        return None, str(error)


def strip_tags(html):
    return unescape(re.sub(r"<[^>]+>", " ", html))


def norm(text):
    return re.sub(r"[^a-z0-9\s]", " ", text.lower())


def title_ok(text, query):
    haystack = norm(text)
    if any(word in haystack for word in ACCESSORIES):
        return False
    product_id = PRODUCT_IDS_BY_QUERY.get(query)
    return product_id is not None and listing_title_matches(product_id, text)


def parse_number(text, decimal=","):
    cleaned = re.sub(r"[^0-9.,]", "", text)
    if not cleaned:
        return None
    if decimal == ",":
        cleaned = cleaned.replace(".", "").replace(",", ".")
    else:
        cleaned = cleaned.replace(",", "")
    try:
        value = float(cleaned)
    except ValueError:
        return None
    return value if value > 0 else None


def listing(product, retailer, region_code, title, amount, url, in_stock=None):
    region = REGIONS[region_code]
    floor = MIN_PRICE.get((region_code, region["currency"]))
    if floor and amount < floor:
        return None
    if not listing_url_is_specific(url):
        return None
    return {
        "productId": product[0],
        "productName": title.strip() or product[1],
        "category": product[2],
        "retailer": retailer,
        "region": region,
        "condition": "new",
        "price": amount,
        "currency": region["currency"],
        "inStock": in_stock,
        "quantity": None,
        "url": url.split("#")[0],
        "fetchedAt": now_iso(),
    }


def scan_alternate(product):
    status, html = fetch(f"https://www.alternate.de/listing.xhtml?q={quote_plus(product[1])}")
    if status != 200:
        return [], f"alternate {status}"
    rows = []
    for card in re.findall(r'(<div[^>]*class="[^"]*productBox[^"]*".*?</div>\s*</div>)', html, re.S):
        href = re.search(r'href="([^"]+)"', card)
        price = re.search(r'class="price"[^>]*>(.*?)</', card, re.S)
        if not href or not price:
            continue
        amount = parse_number(strip_tags(price.group(1)))
        title = strip_tags(card)
        if amount is None or not title_ok(title + " " + href.group(1), product[1]):
            continue
        url = urljoin("https://www.alternate.de", href.group(1))
        in_stock = True if re.search(r"auf\s*lager", title, re.I) else False if re.search(r"nicht\s*lieferbar|ausverkauft", title, re.I) else None
        item = listing(product, "alternate", "DE", title, amount, url, in_stock)
        if item:
            rows.append(item)
        if len(rows) >= 8:
            break
    return rows, None


def scan_geizhals(product):
    status, html = fetch(f"https://geizhals.de/?fs={quote_plus(product[1])}")
    if status != 200:
        return [], f"geizhals {status}"
    rows = []
    for item in re.findall(r'<div[^>]*class="[^"]*listview__item[^"]*".*?</div>\s*</div>', html, re.S)[:12]:
        href = re.search(r'href="([^"]+)"', item)
        price = re.search(r'class="[^"]*gh_price[^"]*"[^>]*>(.*?)</', item, re.S)
        name = re.search(r'class="[^"]*listview__name[^"]*"[^>]*>(.*?)</a>', item, re.S)
        if not href or not price:
            continue
        amount = parse_number(strip_tags(price.group(1)))
        title = strip_tags(name.group(1) if name else item)
        if amount is None or not title_ok(title, product[1]):
            continue
        url = urljoin("https://geizhals.de/", href.group(1))
        item_row = listing(product, "geizhals", "DE", title, amount, url, None)
        if item_row:
            rows.append(item_row)
        if len(rows) >= 6:
            break
    return rows, None


def scan_ceneo(product):
    status, html = fetch(f"https://www.ceneo.pl/Komputery;szukaj-{quote_plus(product[1])}")
    if status != 200:
        return [], f"ceneo {status}"
    rows = []
    for block in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S):
        try:
            payload = json.loads(block)
        except json.JSONDecodeError:
            continue
        elements = payload.get("itemListElement") if isinstance(payload, dict) else None
        if not isinstance(elements, list):
            continue
        for entry in elements:
            product_obj = entry.get("item") if isinstance(entry, dict) else None
            if not isinstance(product_obj, dict):
                continue
            offers = product_obj.get("offers") or {}
            amount = offers.get("lowPrice")
            try:
                amount = float(amount)
            except (TypeError, ValueError):
                continue
            name = str(product_obj.get("name") or "")
            url = str(product_obj.get("url") or "")
            if not title_ok(name, product[1]):
                continue
            item = listing(product, "ceneo", "PL", name, amount, url, True if offers.get("offerCount") else None)
            if item:
                rows.append(item)
            if len(rows) >= 8:
                return rows, None
    return rows, None


def scan_awd(product):
    status, html = fetch(f"https://www.awd-it.co.uk/catalogsearch/result/?q={quote_plus(product[1])}")
    if status != 200:
        return [], f"awd-it {status}"
    rows = []
    for card in re.findall(r'(<li[^>]*class="[^"]*product-item[^"]*".*?</li>)', html, re.S):
        href = re.search(r'class="product-item-link"[^>]*href="([^"]+)"', card)
        title_match = re.search(r'class="product-item-link"[^>]*>(.*?)</a>', card, re.S)
        price = re.search(r'data-price-amount="([0-9.]+)"', card)
        if not href or not price:
            continue
        title = strip_tags(title_match.group(1) if title_match else "")
        if not title_ok(title, product[1]):
            continue
        in_stock = True if re.search(r"in stock", card, re.I) else False if re.search(r"out of stock", card, re.I) else None
        item = listing(product, "awd-it", "GB", title, float(price.group(1)), href.group(1), in_stock)
        if item:
            rows.append(item)
        if len(rows) >= 8:
            break
    return rows, None


def scan_dospara(product):
    status, html = fetch(f"https://www.dospara.co.jp/products/all-item?q={quote_plus(product[1])}")
    if status != 200:
        return [], f"dospara {status}"
    rows = []
    for card in re.findall(r'(<div[^>]*class="[^"]*p-products-all-item-product[^"]*".*?</div>\s*</div>)', html, re.S):
        href = re.search(r'href="([^"]+)"', card)
        name = re.search(r'p-products-all-item-product__name__text[^>]*>(.*?)</', card, re.S)
        price = re.search(r'p-products-all-item-product__number[^>]*>(.*?)</', card, re.S)
        if not href or not price:
            continue
        title = strip_tags(name.group(1) if name else "")
        amount = parse_number(strip_tags(price.group(1)), decimal=".")
        if amount is None or not title_ok(title, product[1]):
            continue
        url = urljoin("https://www.dospara.co.jp", href.group(1))
        in_stock = True if "在庫" in card and "在庫切れ" not in card else False if "在庫切れ" in card else None
        item = listing(product, "dospara", "JP", title, amount, url, in_stock)
        if item:
            rows.append(item)
        if len(rows) >= 8:
            break
    return rows, None


def scan_kakaku(product):
    status, html = fetch(f"https://www.kakaku.com/search_results/{quote_plus(product[1])}/")
    if status != 200:
        return [], f"kakaku {status}"
    rows = []
    for match in re.finditer(
        r'p-item_name">\s*<a href="(https://kakaku.com/item/[^"]+)"[^>]*>(.*?)</a>.*?p-item_priceNum[^>]*>(.*?)<',
        html,
        re.S,
    ):
        title = strip_tags(match.group(2))
        amount = parse_number(match.group(3), decimal=".")
        if amount is None or not title_ok(title, product[1]):
            continue
        item = listing(product, "kakaku", "JP", title, amount, match.group(1), None)
        if item:
            rows.append(item)
        if len(rows) >= 8:
            break
    return rows, None


SOURCES = (scan_alternate, scan_geizhals, scan_ceneo, scan_awd, scan_dospara, scan_kakaku)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="cache/extra-prices.json")
    args = parser.parse_args()
    listings = []
    errors = []
    for product in PRODUCTS:
        for scanner in SOURCES:
            try:
                rows, error = scanner(product)
            except Exception as exc:  # noqa: BLE001 — keep the rest of the scan moving
                errors.append({"retailer": scanner.__name__, "region": "?", "message": str(exc), "product": product[0]})
                continue
            listings.extend(rows)
            if error:
                errors.append({"retailer": scanner.__name__, "region": "?", "message": error, "product": product[0]})
            time.sleep(0.15)
        print(f"{product[0]}: {sum(1 for row in listings if row['productId'] == product[0])} listings", flush=True)
    snapshot = {
        "generatedAt": now_iso(),
        "listings": listings,
        "summaries": [],
        "errors": errors,
    }
    dest = Path(args.out)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {len(listings)} listings, {len(errors)} errors -> {dest}")


if __name__ == "__main__":
    main()
