#!/usr/bin/env python3
"""Fetch Geizhals (DE/AT) price history for GPU product pages.

Geizhals publishes a per-product price history ("Preisentwicklung") that goes back
to product launch and is served from a public JSON endpoint:

    POST https://geizhals.de/api/gh0/price_history
    {"id": <productId>, "params": {"days": <7|31|91|183|365|9999>, "loc": "de"}}
    -> {"response": [[epoch_ms, price, units], ...]}

The endpoint sits behind a Cloudflare JS challenge, so the first request must come
from a real browser session that has cleared the challenge.  This script launches
Brave once, clears the challenge on the Grafikkarten category page, then reuses that
page context for every API call.  Requests are sequential and rate-limited.

Usage:
    python3 geizhals_history.py --match 5090,5080 --days 9999 --limit 40
    python3 geizhals_history.py --pages 2 --days 365 --limit 60 --loc de
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import re
import sys
import time

from playwright.sync_api import Page, sync_playwright

BRAVE = "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"
LAUNCH_ARGS = [
    "--webrtc-ip-handling-policy=disable_non_proxied_udp",
    "--disable-blink-features=AutomationControlled",
]
CATEGORY_GPU = "gra16_512"  # Grafikkarten PCIe
CF_BLOCK_MARKERS = (
    "nur einen moment",
    "just a moment",
    "sichere verbindung",
    "attention required",
    "you have been blocked",
    "überprüfung",
)
VALID_DAYS = (7, 31, 91, 183, 365, 9999)
PRODUCT_LINK_RE = re.compile(r'href="([^"]*-a(\d{5,})\.html[^"]*)"')
API_JS = """async ([id, days, loc]) => {
  const r = await fetch('https://geizhals.de/api/gh0/price_history', {
    method: 'POST',
    headers: {'accept': 'application/json', 'content-type': 'application/json'},
    body: JSON.stringify({id: id, params: {days: days, loc: loc}}),
    credentials: 'include'
  });
  const text = await r.text();
  return {status: r.status, text: text};
}"""


CARD_RE = re.compile(r'<div class="galleryview__item card">(.*?)(?=<div class="galleryview__item card">|</section>)', re.S)
PRICE_RES = (
    re.compile(r'class="[^"]*galleryview__price[^"]*"[^>]*>(.*?)</'),
    re.compile(r'class="[^"]*gh_price[^"]*"[^>]*>(.*?)</'),
    re.compile(r'"price"\s*:\s*"?([\d.]+)'),
)


def card_price(card: str) -> float | None:
    """Lowest price shown on a listing card, in the region's currency."""
    for pattern in PRICE_RES:
        match = pattern.search(card)
        if not match:
            continue
        raw = re.sub(r"<[^>]+>", " ", match.group(1))
        raw = re.sub(r"[^0-9.,]", "", raw).replace(".", "").replace(",", ".")
        try:
            value = float(raw)
        except ValueError:
            continue
        if value > 0:
            return value
    return None


def page_title(page: Page) -> str:
    """Current title, or '' while a navigation is tearing down the context."""
    try:
        return page.title()
    except Exception:
        return ""


def wait_for_challenge(page: Page, tries: int = 90) -> bool:
    """Wait until the Cloudflare interstitial is gone."""
    for _ in range(tries):
        title = page_title(page)
        if title and not any(m in title.lower() for m in CF_BLOCK_MARKERS):
            return True
        page.wait_for_timeout(2000)
    return False


def clear_challenge(page: Page, loc: str) -> str:
    """Load the Grafikkarten category page and return its HTML once the challenge clears."""
    html = load_with_challenge(page, f"https://geizhals.de/?cat={CATEGORY_GPU}&hloc={loc}")
    if html is None:
        raise RuntimeError("Cloudflare challenge did not clear")
    return html


def load_with_challenge(page: Page, url: str, tries: int = 2) -> str | None:
    """Navigate to `url`, waiting out the Cloudflare interstitial. None if it never clears."""
    for attempt in range(1, tries + 1):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        except Exception as exc:  # navigation raced with the challenge redirect
            print(f"  navigation error ({exc.__class__.__name__}), retrying", file=sys.stderr)
            page.wait_for_timeout(3000)
            continue
        if wait_for_challenge(page):
            page.wait_for_timeout(3500)
            return page.content()
        print(f"  challenge not cleared (attempt {attempt}/{tries})", file=sys.stderr)
        page.wait_for_timeout(3000)
    return None


def harvest_page(html: str, found: dict[str, dict]) -> int:
    """Add every product card on one listing page to `found`; return new products."""
    before = len(found)
    for card in CARD_RE.findall(html):
        link = re.search(r'href="([^"]*-a(\d{5,})\.html[^"]*)"', card)
        if not link:
            continue
        slug, pid = link.group(1).split("?")[0], link.group(2)
        name = re.search(r'class="galleryview__name-link"[^>]*title="([^"]{3,160})"', card)
        record = found.setdefault(pid, {"id": int(pid), "slug": slug})
        if name and "name" not in record:
            record["name"] = re.sub(r"\s+", " ", name.group(1)).strip()
        if "price" not in record:
            price = card_price(card)
            if price is not None:
                record["price"] = price
    return len(found) - before


def collect_products(
    page: Page, loc: str, pages: int, first_html: str
) -> list[dict]:
    """Walk the GPU category, returning every product with its current price.

    `first_html` is the already-cleared category page. `pages=0` walks the pagination
    control until it stops yielding new products; any other value caps the walk.
    """
    found: dict[str, dict] = {}
    harvest_page(first_html, found)
    print(f"  page 1: {len(found)} products", file=sys.stderr)
    page_no = 1
    while pages == 0 or page_no < pages:
        page_no += 1
        try:
            button = page.query_selector(".pagination__page--next")
            if button is None:
                print(f"  page {page_no}: no next control, stopping", file=sys.stderr)
                break
            disabled = (button.get_attribute("class") or "").find("disabled") >= 0 or not button.is_enabled()
            if disabled:
                print(f"  page {page_no}: next control disabled, stopping", file=sys.stderr)
                break
            button.click()
        except Exception as exc:
            print(f"  page {page_no}: pagination stopped ({exc.__class__.__name__})", file=sys.stderr)
            break
        page.wait_for_timeout(2500)
        if not wait_for_challenge(page, tries=20):
            print(f"  page {page_no}: challenge blocked, stopping", file=sys.stderr)
            break
        page.wait_for_timeout(2500)
        added = harvest_page(page.content(), found)
        print(f"  page {page_no}: +{added} products ({len(found)} total)", file=sys.stderr)
        if added == 0:
            break
    return [found[k] for k in sorted(found, key=lambda k: int(k))]


def fetch_history(page: Page, product_id: int, days: int, loc: str) -> list[list[float]]:
    res = page.evaluate(API_JS, [product_id, days, loc])
    if res["status"] != 200:
        raise RuntimeError(f"price_history HTTP {res['status']}: {res['text'][:200]}")
    return json.loads(res["text"]).get("response") or []


def fmt_day(ms: float) -> str:
    return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).strftime("%Y-%m-%d")


def select_per_match(
    products: list[dict], needles: list[str], per_match: int
) -> list[dict]:
    """Group products by their most specific matching chip, keep the cheapest N per chip.

    A product matches every needle contained in its name ("RTX 5070" also matches
    "RTX 5070 Ti"), so each product is assigned to the longest needle it matches.
    """
    grouped: dict[str, list[dict]] = {}
    for product in products:
        haystack = (product.get("name") or product["slug"]).lower()
        matches = [needle for needle in needles if needle in haystack]
        if not matches:
            continue
        grouped.setdefault(max(matches, key=len), []).append(product)
    selected: list[dict] = []
    for chip in sorted(grouped):
        rows = grouped[chip]
        priced = sorted(
            (row for row in rows if isinstance(row.get("price"), (int, float))),
            key=lambda row: row["price"],
        )
        keep = (priced or rows)[:per_match] if per_match else rows
        selected.extend(keep)
        print(
            f"  {chip}: {len(rows)} models in category, querying {len(keep)}"
            + (f" (cheapest {keep[0].get('price')})" if keep and keep[0].get("price") else ""),
            file=sys.stderr,
        )
    return selected


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--match", default="", help="comma-separated chip substrings, e.g. 5090,5080")
    ap.add_argument("--days", type=int, default=9999, choices=VALID_DAYS)
    ap.add_argument("--loc", default="de", choices=("de", "at", "uk", "pl", "eu"))
    ap.add_argument("--limit", type=int, default=40, help="max products to query (0 = no cap)")
    ap.add_argument("--pages", type=int, default=1, help="category listing pages to walk (0 = every page)")
    ap.add_argument(
        "--per-match",
        type=int,
        default=0,
        help="keep only the N cheapest listings per --match chip, instead of every model",
    )
    ap.add_argument("--delay", type=float, default=1.2, help="seconds between API calls")
    ap.add_argument("--out", default=None, help="output path (default out/geizhals-history-<utc>.json)")
    ap.add_argument("--headless", action="store_true", help="run browser headless (challenge may fail)")
    args = ap.parse_args()

    default_out = (
        pathlib.Path(__file__).resolve().parents[1]
        / "out"
        / f"geizhals-history-{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    )
    out_path = pathlib.Path(args.out).expanduser() if args.out else default_out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    needles = [s.strip().lower() for s in args.match.split(",") if s.strip()]

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            executable_path=BRAVE, headless=args.headless, args=LAUNCH_ARGS
        )
        page = browser.new_page(locale="de-DE")
        try:
            print(f"clearing Cloudflare challenge ({args.loc})…", file=sys.stderr)
            listing_html = clear_challenge(page, args.loc)
            products = collect_products(page, args.loc, args.pages, listing_html)
            print(f"  category total: {len(products)} products", file=sys.stderr)
            if needles:
                products = select_per_match(products, needles, args.per_match)
            if args.limit:
                products = products[: args.limit]
            print(f"querying {len(products)} products, days={args.days}", file=sys.stderr)

            records = []
            for i, prod in enumerate(products, 1):
                try:
                    series = fetch_history(page, prod["id"], args.days, args.loc)
                except Exception as exc:  # keep going; record the failure
                    print(f"  [{i}/{len(products)}] {prod['slug'][:60]} FAILED {exc}", file=sys.stderr)
                    records.append({**prod, "error": str(exc), "series": []})
                    continue
                if series:
                    print(
                        f"  [{i}/{len(products)}] {prod['slug'][:52]:<52} "
                        f"{len(series):>4} pts  {fmt_day(series[0][0])} -> {fmt_day(series[-1][0])}",
                        file=sys.stderr,
                    )
                else:
                    print(f"  [{i}/{len(products)}] {prod['slug'][:52]} no data", file=sys.stderr)
                amounts = [p[1] for p in series if isinstance(p[1], (int, float))]
                records.append(
                    {
                        **prod,
                        "currency": "EUR" if args.loc == "de" else args.loc.upper(),
                        "points": len(series),
                        "priced_points": len(amounts),
                        "first": fmt_day(series[0][0]) if series else None,
                        "last": fmt_day(series[-1][0]) if series else None,
                        "min": min(amounts) if amounts else None,
                        "max": max(amounts) if amounts else None,
                        "series": series,
                    }
                )
                time.sleep(args.delay)
        finally:
            browser.close()

    payload = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source": "https://geizhals.de/api/gh0/price_history",
        "method": "Brave + cleared Cloudflare session, POST price_history per product",
        "loc": args.loc,
        "days": args.days,
        "product_count": len(records),
        "products": records,
    }
    out_path.write_text(json.dumps(payload, indent=1))
    with_data = [r for r in records if r["points"]]
    print(
        f"\nwrote {out_path}  products={len(records)} with_history={len(with_data)}",
        file=sys.stderr,
    )
    if with_data:
        deepest = max(with_data, key=lambda r: r["points"])
        print(
            f"deepest: {deepest['slug'][:60]} {deepest['points']} pts "
            f"{deepest['first']} -> {deepest['last']}",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
