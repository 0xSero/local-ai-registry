#!/usr/bin/env python3

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlparse


SCHEMA = "local-ai-registry/v1"
SCANNER = "https://github.com/0xSero/local-ai-scanner-cli"

GPU_HARDWARE = {
    "rtx-5090": ["rtx-5090-32gb"],
    "rtx-5080": ["rtx-5080-16gb"],
    "rtx-5070-ti": ["rtx-5070-ti-16gb"],
    "rtx-5070": ["rtx-5070-12gb"],
    "rtx-5060-ti": ["rtx-5060-ti-8gb", "rtx-5060-ti-16gb"],
    "rtx-5060": ["rtx-5060-8gb"],
    "rtx-4090": ["rtx-4090-24gb"],
    "rtx-4080-super": ["rtx-4080-super-16gb"],
    "rtx-4080": ["rtx-4080-16gb"],
    "rtx-4070-ti-super": ["rtx-4070-ti-super-16gb"],
    "rtx-4070-ti": ["rtx-4070-ti-12gb"],
    "rtx-4070-super": ["rtx-4070-super-12gb"],
    "rtx-4070": ["rtx-4070-12gb"],
    "rtx-4060-ti": ["rtx-4060-ti-8gb", "rtx-4060-ti-16gb"],
    "rtx-4060": ["rtx-4060-8gb"],
    "rtx-3090-ti": ["rtx-3090-ti-24gb"],
    "rtx-3090": ["rtx-3090-24gb"],
    "rtx-3080-ti": ["rtx-3080-ti-12gb"],
    "rtx-3080": ["rtx-3080-10gb", "rtx-3080-12gb"],
    "rtx-3070-ti": ["rtx-3070-ti-8gb"],
    "rtx-3070": ["rtx-3070-8gb"],
    "rtx-3060-ti": ["rtx-3060-ti-8gb"],
    "rtx-3060": ["rtx-3060-12gb"],
    "rtx-2000-ada": ["rtx-2000-ada-16gb"],
    "rtx-4000-ada": ["rtx-4000-ada-20gb"],
    "rtx-6000-ada": ["rtx-6000-ada-48gb"],
    "rtx-pro-4000-blackwell": ["rtx-pro-4000-blackwell-24gb"],
    "rtx-pro-4500-blackwell": ["rtx-pro-4500-blackwell-32gb"],
    "rtx-pro-6000-blackwell": ["rtx-pro-6000-blackwell-96gb"],
    "rtx-a6000": ["rtx-a6000-48gb"],
    "dgx-spark": ["dgx-spark-gb10-128gb"],
    "intel-arc-pro-b60": ["intel-arc-pro-b60-24gb"],
    "intel-arc-pro-b70": ["intel-arc-pro-b70-32gb"],
    "rx-7700-xt": ["rx-7700-xt-12gb"],
    "rx-7900-xt": ["rx-7900-xt-20gb"],
    "rx-7900-xtx": ["rx-7900-xtx-24gb"],
    "rx-9070-xt": ["rx-9070-xt-16gb"],
    "radeon-ai-pro-r9700": ["radeon-ai-pro-r9700-32gb"],
    "mi300x": ["mi300x-192gb"],
    "b200": ["b200-180gb"],
    "amd-strix-halo-framework-desktop": ["ryzen-ai-max-plus-395-128gb"],
    "amd-strix-halo-mini-pc": ["ryzen-ai-max-plus-395-128gb"],
}

SYSTEM_LISTING_MARKERS = (
    "desktop",
    "gaming pc",
    "mini pc",
    "notebook",
    "laptop",
    "prebuilt",
    "workstation pc",
    "workstation computer",
    "komputer",
    "ordinateur",
    "pc gamer",
    "pc system",
    "tower pc",
    "stacja robocza",
    "stacja graficzna",
    "core i5",
    "core i7",
    "core i9",
    "core ultra",
    "ryzen 5",
    "ryzen 7",
    "ryzen 9",
    "windows 11",
    "actina",
    "g4m3r",
)


def apple_chip(product_id):
    for prefix in ("mac-studio-", "macbook-pro-", "mac-mini-"):
        if product_id.startswith(prefix):
            return product_id.removeprefix(prefix)
    return None


def hardware_links(product_id, hardware_ids):
    ids = GPU_HARDWARE.get(product_id)
    if not ids:
        prefix = f"{product_id}-"
        ids = sorted(
            identifier
            for identifier in hardware_ids
            if identifier == product_id or identifier.startswith(prefix)
        )
    if ids:
        scope = "exact" if product_id == "dgx-spark" else "family"
        return [{"id": identifier, "match_scope": scope} for identifier in ids if identifier in hardware_ids]
    chip = apple_chip(product_id)
    if not chip:
        return []
    matches = sorted(identifier for identifier in hardware_ids if re.match(rf"^apple-{re.escape(chip)}-\d", identifier))
    return [{"id": identifier, "match_scope": "family"} for identifier in matches]


def product_name(product_id):
    value = product_id.replace("macbook-pro", "MacBook Pro").replace("mac-studio", "Mac Studio").replace("mac-mini", "Mac mini")
    value = value.replace("dgx-spark", "NVIDIA DGX Spark").replace("rtx-pro", "RTX PRO").replace("rtx-a6000", "RTX A6000").replace("rtx-", "RTX ")
    value = value.replace("intel-arc-pro", "Intel Arc Pro").replace("radeon-ai-pro", "Radeon AI PRO").replace("rx-", "RX ").replace("mi300x", "MI300X").replace("b200", "B200")
    value = value.replace("amd-strix-halo-framework-desktop", "Framework Desktop Ryzen AI Max+ 395").replace("amd-strix-halo-mini-pc", "Ryzen AI Max+ 395 Mini PC")
    value = re.sub(r"\bm([1-5])\b", lambda match: f"M{match.group(1)}", value.replace("-", " "), flags=re.IGNORECASE)
    return re.sub(r"\b(max|pro|ultra)\b", lambda match: match.group(1).title(), value, flags=re.IGNORECASE)

def normalized(value):
    text = re.sub(r"[^a-z0-9\s]", " ", str(value).lower())
    text = re.sub(
        r"\b(rtx|rx)(\d{4})(ti|super|xtx|xt)?\b",
        lambda match: " ".join(part for part in match.groups() if part),
        text,
    )
    return re.sub(r"\s+", " ", text).strip()


def gpu_signature(value):
    text = normalized(value)
    match = re.search(r"\brtx\s+(?:(pro)\s+)?([a]?\d{4})(e)?\b", text)
    if match:
        window = text[match.start() : match.end() + 64]
        return (
            "rtx",
            bool(match.group(1)),
            match.group(2),
            bool(re.search(r"\bti\b", window)),
            bool(re.search(r"\bsuper\b", window)),
            "blackwell"
            if re.search(r"\bblackwell\b", window)
            else "ada"
            if re.search(r"\bada\b", window)
            else "",
        )
    match = re.search(r"\brx\s+(\d{4})\s*(xtx|xt)?\b", text)
    if match:
        return ("rx", match.group(1), match.group(2) or "")
    match = re.search(r"\bradeon\s+ai\s+pro\s+(r\d{4})\b", text)
    if match:
        return ("radeon-ai-pro", match.group(1))
    match = re.search(r"\b(?:intel\s+)?arc\s+pro\s+(b\d{2})\b", text)
    if match:
        return ("arc-pro", match.group(1))
    if re.search(r"\bdgx\s+spark\b", text):
        return ("dgx-spark",)
    if re.search(r"\bmi\s*300x\b", text):
        return ("mi300x",)
    if re.search(r"\bb200\b", text):
        return ("b200",)
    return None


def listing_title_matches(product_id, title):
    expected = gpu_signature(product_name(product_id))
    if expected is None:
        return True
    text = normalized(title)
    system_marker = any(
        re.search(rf"\b{re.escape(marker)}\b", text)
        for marker in SYSTEM_LISTING_MARKERS
    )
    system_cpu = bool(
        re.search(r"\b(?:intel\s+)?i[3579]\s+\d{4,5}[a-z]*\b", text)
        or re.search(r"\bryzen\s+[3579]\s+\d{4,5}[a-z0-9]*\b", text)
    )
    if product_id != "dgx-spark" and (system_marker or system_cpu):
        return False
    return gpu_signature(title) == expected


def listing_url_is_specific(url):
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    host = parsed.netloc.lower()
    path = parsed.path.rstrip("/")
    path_lower = path.lower()
    if not host or not path:
        return False
    if any(marker in path_lower for marker in ("/category/", "/catalogsearch/", "/search_results/")):
        return False
    if host.endswith("alternate.de") and path_lower.endswith("/listing.xhtml"):
        return False
    if host.endswith("dospara.co.jp") and path_lower.endswith("/products/all-item"):
        return False
    return True


def median(values):
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def lowest(rows, condition):
    values = [row["price"] for row in rows if row["condition"] == condition and row["inStock"] is not False]
    return min(values) if values else None

def observation_lowest(rows, condition):
    values = [
        row["amount"]
        for row in rows
        if row.get("condition") == condition and row.get("in_stock") is not False
    ]
    return min(values) if values else None


def clean_scanner_record(record):
    if not isinstance((record.get("provenance") or {}).get("scanner"), str):
        return record, 0
    product_id = (record.get("product") or {}).get("id")
    if not isinstance(product_id, str) or gpu_signature(product_name(product_id)) is None:
        return record, 0
    observations = record.get("observations") or []
    accepted = [
        row
        for row in observations
        if isinstance(row, dict)
        and listing_title_matches(product_id, row.get("title") or "")
        and listing_url_is_specific(row.get("url") or "")
    ]
    removed = len(observations) - len(accepted)
    if removed == 0:
        return record, 0
    if not accepted:
        return None, removed
    record["observations"] = accepted
    record["observed_at"] = max(row["observed_at"] for row in accepted)
    record["summary"] = {
        "listing_count": len(accepted),
        "retailer_count": len({row["retailer"] for row in accepted}),
        "in_stock_count": sum(row.get("in_stock") is True for row in accepted),
        "lowest_new": observation_lowest(accepted, "new"),
        "lowest_refurbished": observation_lowest(accepted, "refurbished"),
        "lowest_used": observation_lowest(accepted, "used"),
    }
    verification = record.get("verification")
    if isinstance(verification, dict):
        verification["rejected_observations"] = (
            int(verification.get("rejected_observations") or 0) + removed
        )
    return record, removed


def normalize(snapshot, hardware_ids):
    source_errors = defaultdict(int)
    for error in snapshot.get("errors", []):
        source_errors[error.get("region")] += 1

    grouped = defaultdict(list)
    for listing in snapshot.get("listings", []):
        links = hardware_links(listing.get("productId", ""), hardware_ids)
        region = listing.get("region") or {}
        if not links or listing.get("currency") != region.get("currency"):
            continue
        if not isinstance(listing.get("price"), (int, float)) or listing["price"] <= 0:
            continue
        if not isinstance(listing.get("url"), str) or not listing["url"].startswith(("http://", "https://")):
            continue
        product_id = listing.get("productId", "")
        if not listing_title_matches(product_id, listing.get("productName") or ""):
            continue
        if not listing_url_is_specific(listing["url"]):
            continue
        grouped[(listing["productId"], region["code"])].append(listing)

    records = []
    for (product_id, region_code), listings in sorted(grouped.items()):
        medians = {}
        for condition in ("new", "refurbished", "used"):
            values = [row["price"] for row in listings if row["condition"] == condition]
            if len(values) >= 3:
                medians[condition] = median(values)

        accepted = []
        rejected = 0
        seen = set()
        for listing in sorted(listings, key=lambda row: (row["price"], row["retailer"], row["url"])):
            key = (listing["retailer"], listing["url"], listing["condition"], listing["price"])
            floor = medians.get(listing["condition"])
            if key in seen or (floor is not None and listing["price"] < floor * 0.3):
                rejected += 1
                continue
            seen.add(key)
            accepted.append(listing)
        if not accepted:
            continue

        region = accepted[0]["region"]
        observations = [{
            "retailer": row["retailer"],
            "title": row["productName"],
            "condition": row["condition"],
            "amount": row["price"],
            "currency": row["currency"],
            "in_stock": row["inStock"],
            "quantity": row["quantity"],
            "url": row["url"],
            "observed_at": row["fetchedAt"],
        } for row in accepted]
        records.append({
            "schema_version": SCHEMA,
            "id": f"{product_id}--{region_code.lower()}",
            "product": {
                "id": product_id,
                "name": product_name(product_id),
                "category": accepted[0]["category"],
            },
            "region": region,
            "hardware": hardware_links(product_id, hardware_ids),
            "observed_at": max(row["fetchedAt"] for row in accepted),
            "summary": {
                "listing_count": len(accepted),
                "retailer_count": len({row["retailer"] for row in accepted}),
                "in_stock_count": sum(row["inStock"] is True for row in accepted),
                "lowest_new": lowest(accepted, "new"),
                "lowest_refurbished": lowest(accepted, "refurbished"),
                "lowest_used": lowest(accepted, "used"),
            },
            "observations": observations,
            "verification": {
                "state": "candidate",
                "method": "retailer query result with regional currency and robust lower-outlier rejection",
                "rejected_observations": rejected,
            },
            "provenance": {
                "scanner": SCANNER,
                "snapshot_generated_at": snapshot["generatedAt"],
                "source_error_count": source_errors[region_code],
            },
        })
    return records


def write_records(price_root, records, replace):
    existing = {}
    removed_records = 0
    removed_observations = 0
    if not replace:
        for path in price_root.glob("*/*.json"):
            record = json.loads(path.read_text())
            record, removed = clean_scanner_record(record)
            removed_observations += removed
            if record is None:
                removed_records += 1
                continue
            existing[record["id"]] = record
    for record in records:
        existing[record["id"]] = record
    for path in list(price_root.glob("*/*.json")):
        path.unlink()
    for directory in list(price_root.iterdir()):
        if directory.is_dir() and not any(directory.iterdir()):
            directory.rmdir()
    for record in existing.values():
        product_root = price_root / record["product"]["id"]
        product_root.mkdir(parents=True, exist_ok=True)
        (product_root / f"{record['region']['code'].lower()}.json").write_text(
            json.dumps(record, indent=2, ensure_ascii=False) + "\n"
        )
    return existing, removed_records, removed_observations


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("snapshot")
    parser.add_argument("--root", default="registry")
    parser.add_argument(
        "--replace",
        action="store_true",
        help="replace the market-price collection instead of merging by product and region",
    )
    args = parser.parse_args()
    root = Path(args.root)
    snapshot = json.loads(Path(args.snapshot).read_text())
    hardware_ids = {path.stem for path in (root / "hardware").glob("*.json")}
    records = normalize(snapshot, hardware_ids)
    existing, removed_records, removed_observations = write_records(
        root / "price", records, args.replace
    )
    print(
        f"imported {len(records)} snapshot records; "
        f"{len(existing)} regional price records with "
        f"{sum(len(record['observations']) for record in existing.values())} observations; "
        f"removed {removed_observations} invalid observations and {removed_records} empty records"
    )


if __name__ == "__main__":
    main()
