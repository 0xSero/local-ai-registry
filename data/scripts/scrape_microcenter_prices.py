#!/usr/bin/env python3
"""Micro Center GPU price + stock scraper.

WHY A US HOP IS REQUIRED
-------------------------
microcenter.com is fronted by Cloudflare and rejects requests originating outside
the US. From a European IP every request - curl, plain HTTP client, or a real
browser - gets Cloudflare 1020 "Sorry, you have been blocked". A US IP alone is
not enough either: a datacenter IP from a plain HTTP client gets the managed
challenge page ("Just a moment..."), which needs JavaScript.

The working path is therefore both things at once:

    local Chromium --socks5--> ssh -D tunnel --> US IP --> Cloudflare --> microcenter.com

 1. an SSH SOCKS5 tunnel to a US host provides the US source address;
 2. a real consumer browser solves the Cloudflare challenge and keeps the
    clearance cookie for the rest of the run. Measured from a US IP: a *headed*
    Brave window clears it in ~8s, sometimes only after clicking the Turnstile
    widget, and clearance is per browser session; Playwright's bundled Chrome for
    Testing fails the challenge, Brave in `--headless=new` fails it too, and
    `launch_persistent_context` stays blocked even headed - so the browser is
    launched plainly, headed by default (`--browser chromium` / `--headless` to
    experiment). Repeated hits make Cloudflare escalate, so the challenge wait
    clicks the Turnstile widget and retries with a fresh browser;
 3. every listing page is then fetched from inside that page context with
    fetch(), same-origin, reusing the cleared session - no repeated challenges.

Prices are per-store: Micro Center runs store-specific pricing and stock, so the
store id is part of every listing URL. The category listing carries name, SKU,
price, sale/rebate price and the per-store stock string for every card, so one
request per page is enough - no product-page crawl needed.

COMPLIANCE
----------
robots.txt only disallows /admin, /orders, /checkouts, /cart, /account,
/quickViewConfigurator and /? - the listing paths used here are permitted and no
crawl-delay is specified. Requests are still rate-limited (--delay, default 4s with
jitter) and the whole catalogue is a few dozen requests.

USAGE
-----
    python3 scripts/scrape_microcenter_prices.py            # default stores, headed Brave over a US SOCKS tunnel
    python3 scripts/scrape_microcenter_prices.py --stores all
    python3 scripts/scrape_microcenter_prices.py --headless   # Cloudflare refuses it
    python3 scripts/scrape_microcenter_prices.py --browser chromium
    python3 scripts/scrape_microcenter_prices.py --no-tunnel # direct: already egresses US
    python3 scripts/scrape_microcenter_prices.py --no-tunnel --proxy socks5://127.0.0.1:1080
    python3 scripts/scrape_microcenter_prices.py --help

OUTPUT (in --out, default <repo>/out, gitignored)
    latest.json / latest.csv   machine-readable price list (one row per card per store)
    run-<utc>.json            timestamped copy of the same run
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import re
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import Error as PWError
from playwright.sync_api import sync_playwright

BASE = "https://www.microcenter.com"
CATEGORY_ID = "4294966937"
CATEGORY_SLUG = "graphics-cards"
DEFAULT_STORES = ["101", "115", "181", "029"]  # Tustin CA, Brooklyn NY, Denver CO, Shippable Items
DEFAULT_SOCKS_HOST = "do-vibrant"  # DigitalOcean North Bergen NJ, verified US egress
PER_PAGE = 24

# ---------------------------------------------------------------------------
# in-page extractor: runs same-origin, reuses the Cloudflare-cleared session
# ---------------------------------------------------------------------------
EXTRACT_JS = r"""
async (url) => {
  const resp = await fetch(url, { credentials: 'include' });
  const html = await resp.text();
  if (!resp.ok) return { ok: false, status: resp.status, body: html.slice(0, 300) };
  const doc = new DOMParser().parseFromString(html, 'text/html');
  const norm = (s) => (s || '').replace(/\s+/g, ' ').trim();
  const txt = (el, sel) => { const n = el.querySelector(sel); return norm(n && n.textContent); };
  const rows = [...doc.querySelectorAll('li.product_wrapper')].map((li) => {
    const nameA = li.querySelector('a[data-name]');
    const link = li.querySelector('a[id^="hypProductH2_"]')
      || li.querySelector('a.productClickItemV2')
      || li.querySelector('a[href^="/product/"]');
    const priceText = txt(li, '.price_wrapper .price');
    const priceMatch = priceText.match(/\$([\d,]+\.\d{2})/);
    const stockText = txt(li, '.stock');
    const flagsText = txt(li, '.price_wrapper');
    return {
      name: nameA ? norm(nameA.getAttribute('data-name')) : norm((li.querySelector('img') || {}).alt),
      brand: nameA ? norm(nameA.getAttribute('data-brand')) : '',
      sku: txt(li, 'p.sku').replace(/^SKU:\s*/i, ''),
      url: link ? new URL(link.getAttribute('href'), location.origin).href : null,
      price: priceMatch ? Number(priceMatch[1].replace(/,/g, '')) : null,
      price_text: priceText,
      was_text: txt(li, '.mapped'),
      rebate_text: txt(li, '.rebate-price'),
      clearance_text: txt(li, '.clearance'),
      stock_text: stockText,
      in_store_only: /in store only|buy in store/i.test(flagsText),
      add_to_cart: /add to cart/i.test(flagsText),
    };
  });
  const itemTotal = html.match(/([\d,]+)\s+items?\b/i);
  return {
    ok: true,
    rows,
    item_total: itemTotal ? Number(itemTotal[1].replace(/,/g, '')) : null,
  };
}
"""

# store locator rows are either
#   <a href="/site/stores/default.aspx?storeid=101"><span class="storeState">CA</span>
#   <span class="dash"> - </span><span class="storeName">Tustin</span></a>
# or a plain <a href="/?storeid=101">CA - Tustin</a>
STORE_SPAN_RE = re.compile(
    r'href="[^"]*[?&]storeid=(\d+)"[^>]*>'
    r'(?:<span class="storeState">([^<]*)</span>)?.*?'
    r'<span class="storeName">([^<]+)</span>',
    re.I | re.S,
)
STORE_LINK_RE = re.compile(r'href="[^"]*[?&]storeid=(\d+)[^"]*"[^>]*>([^<]{2,60})<', re.I)
NAMED_STORE_RE = re.compile(r"^[A-Z]{2}\s-\s")

STORE_LIST_JS = r"""
async () => {
  const resp = await fetch('/site/stores/', { credentials: 'include' });
  return { status: resp.status, html: await resp.text() };
}
"""

# chip model normalisation, most specific first (matched against an uppercased name)
CHIP_RE = re.compile(
    r"\b("
    r"RTX PRO \d+"
    r"|RTX \d{4}\s?(?:TI|SUPER)?"
    r"|RADEON AI PRO R\d{4}"
    r"|RX \d{4}\s?(?:XTX|XT|GRE)?"
    r"|ARC PRO [AB]\d{2}"
    r"|ARC [AB]\d{3}"
    r"|GT \d{3,4}"
    r"|TESLA [A-Z]\d+"
    r")\b"
)
ACRONYMS = {"RTX", "RX", "PRO", "XT", "XTX", "GRE", "AI", "GT"}
FIXED_CASE = {"TI": "Ti", "SUPER": "Super", "RADEON": "Radeon"}
VRAM_RE = re.compile(r"(\d+)\s?GB", re.I)
IN_STOCK_RE = re.compile(r"\bin stock\b|usually ships", re.I)
OUT_OF_STOCK_RE = re.compile(r"sold out|out of stock|no longer", re.I)


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


# ---------------------------------------------------------------------------
# US egress
# ---------------------------------------------------------------------------
def port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


class SocksTunnel:
    """SSH dynamic (SOCKS5) tunnel to a US host; reuses an existing one if present."""

    def __init__(self, host: str, port: int):
        self.host, self.port = host, port
        self.proc: subprocess.Popen | None = None

    def __enter__(self) -> "SocksTunnel":
        if port_open("127.0.0.1", self.port):
            log(f"reusing existing SOCKS tunnel on 127.0.0.1:{self.port}")
            return self
        log(f"opening SOCKS tunnel 127.0.0.1:{self.port} -> {self.host}")
        self.proc = subprocess.Popen(
            [
                "ssh", "-N", "-D", str(self.port),
                "-o", "BatchMode=yes",
                "-o", "ExitOnForwardFailure=yes",
                "-o", "ServerAliveInterval=30",
                "-o", "ConnectTimeout=15",
                self.host,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        deadline = time.time() + 25
        while time.time() < deadline:
            if port_open("127.0.0.1", self.port):
                log("tunnel up")
                return self
            if self.proc.poll() is not None:
                err = (self.proc.stderr.read() or "").strip()
                raise SystemExit(f"ssh tunnel to {self.host} died: {err}")
            time.sleep(0.5)
        raise SystemExit(f"ssh tunnel to {self.host} did not come up on port {self.port}")

    def __exit__(self, *exc) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
            log("closed tunnel we started")


# ---------------------------------------------------------------------------
# browser
# ---------------------------------------------------------------------------
CF_BLOCK_RE = re.compile(r"just a moment|attention required|you have been blocked", re.I)

# Cloudflare on microcenter.com clears for a real consumer browser but not for the
# bundled "Google Chrome for Testing" build, so Brave is the default. Pass
# --browser chromium to use Playwright's bundled Chromium instead.
BROWSER_PATHS = {
    "brave": "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    "chrome": "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
}
BASE_ARGS = [
    "--webrtc-ip-handling-policy=disable_non_proxied_udp",
    "--disable-blink-features=AutomationControlled",
    "--lang=en-US",
]


def launch(pw, browser: str, proxy: str, headless: bool):
    """Launch a full browser in a fresh throwaway profile.

    Measured against this site: a plain headed launch of Brave clears the
    Cloudflare challenge in ~10s, while Playwright's `launch_persistent_context`
    stays blocked even headed, so the profile is deliberately not persisted.
    """
    kw = {"channel": "chromium"} if browser == "chromium" else {"executable_path": BROWSER_PATHS[browser]}
    return pw.chromium.launch(
        headless=False,
        proxy={"server": proxy},
        args=BASE_ARGS + (["--headless=new"] if headless else []),
        **kw,
    )


def solve_turnstile(page) -> bool:
    """Click the Cloudflare Turnstile widget if the challenge shows one.

    The managed challenge sometimes waits for a click on a checkbox inside the
    challenges.cloudflare.com frame; clicking it clears the page immediately.
    """
    for frame in page.frames:
        if "challenges.cloudflare.com" not in (frame.url or ""):
            continue
        for sel in ("input[type=checkbox]", "label", "body"):
            try:
                el = frame.query_selector(sel)
            except PWError:
                continue
            if el is None:
                continue
            try:
                el.click(timeout=2000)
                return True
            except PWError:
                continue
    return False


def clear_cloudflare(page, attempts: int = 3, per_attempt: float = 40.0) -> None:
    """Load microcenter.com and wait out the Cloudflare challenge.

    The challenge navigates away when it succeeds, so `title()` can throw mid-poll;
    that is progress, not failure. If an attempt stays challenged, reload it - each
    load is a fresh challenge attempt - and keep clicking any Turnstile widget.
    """
    last = ""
    for attempt in range(1, attempts + 1):
        try:
            if attempt == 1:
                page.goto(f"{BASE}/", wait_until="domcontentloaded", timeout=90_000)
            else:
                page.reload(wait_until="domcontentloaded", timeout=90_000)
        except PWError as err:
            log(f"challenge navigation interrupted ({type(err).__name__}); re-checking")
        deadline = time.time() + per_attempt
        tick = 0
        while time.time() < deadline:
            try:
                last = page.title()
            except PWError:
                page.wait_for_timeout(1500)
                continue
            if not CF_BLOCK_RE.search(last):
                log(f"Cloudflare cleared on attempt {attempt}: {last}")
                return
            tick += 1
            if tick % 2 == 0 and solve_turnstile(page):
                log("clicked Cloudflare Turnstile widget")
            page.wait_for_timeout(2000)
        log(f"still challenged after attempt {attempt} ({last!r})")
    body = page.inner_text("body")[:200].replace("\n", " ")
    raise SystemExit(f"Cloudflare not cleared (title={last!r}, body={body!r})")


def check_egress(page, expect_country: str = "US") -> dict:
    page.goto("https://ipinfo.io/json", wait_until="domcontentloaded", timeout=45_000)
    info = json.loads(page.inner_text("body"))
    if info.get("country") != expect_country:
        raise SystemExit(
            f"egress is {info.get('country')} ({info.get('ip')}), expected {expect_country}: "
            "microcenter.com blocks non-US IPs"
        )
    log(f"egress {info.get('ip')} ({info.get('city')}, {info.get('country')})")
    return info


# ---------------------------------------------------------------------------
# scraping
# ---------------------------------------------------------------------------
def store_map(page) -> dict[str, str]:
    """Store id -> store name, from the locator page fetched in the cleared session."""
    res = page.evaluate(STORE_LIST_JS)
    if res.get("status") != 200:
        raise SystemExit(f"store locator returned HTTP {res.get('status')}")
    names: dict[str, str] = {}
    for sid, state, name in STORE_SPAN_RE.findall(res["html"]):
        state, name = state.strip(), name.strip()
        label = f"{state} - {name}" if state else name
        names.setdefault(sid, label)
    if not names:
        for sid, label in STORE_LINK_RE.findall(res["html"]):
            label = label.strip()
            if sid not in names or NAMED_STORE_RE.match(label):
                names[sid] = label
    if not names:
        raise SystemExit("could not parse any store ids from the store locator")
    return names


def canonical_chip(raw: str) -> str:
    """'RTX 5070 TI' -> 'RTX 5070 Ti', 'ARC B580' -> 'Arc B580'."""
    return " ".join(
        w if w in ACRONYMS else FIXED_CASE.get(w, w.capitalize())
        for w in re.sub(r"\s+", " ", raw).split()
    )


def classify(row: dict) -> dict:
    name = row["name"] or ""
    chip = CHIP_RE.search(name.upper())
    vram = VRAM_RE.search(name)
    stock = row["stock_text"] or ""
    return {
        **row,
        "chip": canonical_chip(chip.group(1)) if chip else None,
        "vram_gb": int(vram.group(1)) if vram else None,
        "in_stock": bool(IN_STOCK_RE.search(stock)) and not OUT_OF_STOCK_RE.search(stock),
        "sold_out": bool(OUT_OF_STOCK_RE.search(stock)),
    }


def scrape_store(page, store_id: str, delay: float, max_pages: int) -> list[dict]:
    rows: list[dict] = []
    seen: set[str] = set()
    for page_no in range(1, max_pages + 1):
        url = f"{BASE}/category/{CATEGORY_ID}/{CATEGORY_SLUG}?storeid={store_id}&page={page_no}"
        res = page.evaluate(EXTRACT_JS, url)
        if not res.get("ok"):
            raise SystemExit(f"store {store_id} page {page_no}: HTTP {res.get('status')} {res.get('body')!r}")
        batch = res["rows"]
        if page_no == 1:
            log(f"store {store_id}: {res.get('item_total')} items in category")
        new = [r for r in batch if r["sku"] and r["sku"] not in seen]
        for r in new:
            seen.add(r["sku"])
            rows.append({**classify(r), "store_id": store_id})
        log(f"  page {page_no}: {len(batch)} cards ({len(new)} new)")
        if len(batch) < PER_PAGE or not new:
            break
        time.sleep(delay + random.uniform(0, 1.5))
    return rows


def summarize(items: list[dict], stores: dict[str, str]) -> None:
    print("\n=== cheapest per chip ===")
    by_chip: dict[str, list[dict]] = {}
    for it in items:
        if it["chip"] and it["price"]:
            by_chip.setdefault(it["chip"], []).append(it)
    for chip in sorted(by_chip, key=lambda c: min(i["price"] for i in by_chip[c])):
        rows = sorted(by_chip[chip], key=lambda i: i["price"])
        cheapest, priciest = rows[0], rows[-1]
        print(
            f"{chip:<16} n={len(rows):<3} "
            f"${cheapest['price']:>9,.2f} - ${priciest['price']:>9,.2f}   "
            f"cheapest: {cheapest['name'][:52]} @ {stores.get(cheapest['store_id'], cheapest['store_id'])}"
        )
    print("\n=== per store ===")
    for sid, name in stores.items():
        mine = [i for i in items if i["store_id"] == sid]
        priced = [i for i in mine if i["price"]]
        in_stock = [i for i in priced if i["in_stock"]]
        print(f"{name:<22} {len(mine):>4} cards, {len(in_stock):>4} in stock, "
              f"{len([i for i in mine if i['in_store_only']]):>4} in-store only")


# ---------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(
        description="Scrape Micro Center GPU prices/stock (requires US egress).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("--stores", default=",".join(DEFAULT_STORES),
                    help="comma-separated store ids, or 'all' (default: %(default)s)")
    ap.add_argument("--out", default=str(Path(__file__).resolve().parents[1] / "out"))
    ap.add_argument("--socks-host", default=DEFAULT_SOCKS_HOST,
                    help="SSH host used for the US SOCKS tunnel (default: %(default)s)")
    ap.add_argument("--socks-port", type=int, default=1080)
    ap.add_argument("--no-tunnel", action="store_true", help="use an existing proxy instead")
    ap.add_argument("--proxy", default=None, help="browser proxy URL (default: socks5://127.0.0.1:<port>)")
    ap.add_argument("--browser", default="brave", choices=["brave", "chrome", "chromium"],
                    help="browser to drive (default: %(default)s; 'chromium' = bundled build)")
    ap.add_argument("--headless", action="store_true",
                    help="try headless first (Cloudflare refuses it in practice; falls back to headed)")
    ap.add_argument("--launch-attempts", type=int, default=3,
                    help="browser launches to try before giving up on Cloudflare (default: %(default)s)")
    ap.add_argument("--delay", type=float, default=4.0, help="seconds between page fetches")
    ap.add_argument("--max-pages", type=int, default=12, help="page cap per store")
    args = ap.parse_args()

    out = Path(args.out).expanduser()
    out.mkdir(parents=True, exist_ok=True)

    tunnel = None
    if args.no_tunnel:
        # no proxy: use whatever egress the machine already has (VPN / exit node)
        proxy = args.proxy
    else:
        proxy = args.proxy or f"socks5://127.0.0.1:{args.socks_port}"
        tunnel = SocksTunnel(args.socks_host, args.socks_port)
        tunnel.__enter__()

    started = time.time()
    try:
        with sync_playwright() as pw:
            browser = None
            for attempt in range(1, args.launch_attempts + 1):
                headless = args.headless and attempt == 1
                browser = launch(pw, args.browser, proxy, headless)
                page = browser.new_page(locale="en-US", timezone_id="America/New_York")
                try:
                    check_egress(page)
                    clear_cloudflare(page)
                    break
                except SystemExit as err:
                    browser.close()
                    browser = None
                    log(f"launch attempt {attempt} failed: {err}")
            if browser is None:
                raise SystemExit(
                    f"could not get a Cloudflare-cleared {args.browser} session in "
                    f"{args.launch_attempts} attempts"
                )
            stores_all = store_map(page)
            wanted = list(stores_all) if args.stores == "all" else [
                s.strip() for s in args.stores.split(",") if s.strip()
            ]
            unknown = [s for s in wanted if s not in stores_all]
            if unknown:
                raise SystemExit(f"unknown store ids {unknown}; known: {sorted(stores_all)}")
            stores = {s: stores_all[s] for s in wanted}
            log(f"stores: {', '.join(f'{s}={n}' for s, n in stores.items())}")

            items: list[dict] = []
            for store_id in stores:
                items.extend(scrape_store(page, store_id, args.delay, args.max_pages))
                time.sleep(args.delay + random.uniform(0, 1.5))
            browser.close()
    finally:
        if tunnel:
            tunnel.__exit__(None, None, None)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": f"{BASE}/category/{CATEGORY_ID}/{CATEGORY_SLUG}",
        "category": "Graphics Cards",
        "method": f"US SOCKS tunnel via {args.socks_host or 'existing proxy'} + {args.browser} (Playwright)",
        "stores": stores,
        "item_count": len(items),
        "items": items,
    }
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    (out / f"run-{stamp}.json").write_text(json.dumps(payload, indent=2) + "\n")
    (out / "latest.json").write_text(json.dumps(payload, indent=2) + "\n")

    fields = ["store_id", "store_name", "chip", "vram_gb", "name", "brand", "sku", "price",
              "price_text", "was_text", "rebate_text", "stock_text", "in_stock", "sold_out",
              "in_store_only", "add_to_cart", "url"]
    with (out / "latest.csv").open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for it in items:
            writer.writerow({**it, "store_name": stores.get(it["store_id"], "")})

    summarize(items, stores)
    print(f"\n{len(items)} rows -> {out}/latest.json, {out}/latest.csv "
          f"({time.time() - started:.0f}s)")


if __name__ == "__main__":
    main()
