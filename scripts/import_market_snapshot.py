#!/usr/bin/env python3

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path


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


def median(values):
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def lowest(rows, condition):
    values = [row["price"] for row in rows if row["condition"] == condition and row["inStock"] is not False]
    return min(values) if values else None


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
    if not replace:
        for path in price_root.glob("*/*.json"):
            record = json.loads(path.read_text())
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
    return existing


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
    existing = write_records(root / "price", records, args.replace)
    print(
        f"imported {len(records)} snapshot records; "
        f"{len(existing)} regional price records with "
        f"{sum(len(record['observations']) for record in existing.values())} observations"
    )


if __name__ == "__main__":
    main()
