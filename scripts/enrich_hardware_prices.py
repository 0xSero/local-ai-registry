#!/usr/bin/env python3
"""Roll fresh, exact US retailer observations into hardware commercial summaries."""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
import re
from typing import Any


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def save(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n")


def parse_time(value: Any) -> dt.datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=dt.timezone.utc)


def source(observation: dict[str, Any]) -> dict[str, Any]:
    return {
        "captured_at": observation["observed_at"],
        "kind": "retailer",
        "publisher": observation["retailer"],
        "url": observation["url"],
    }


def provenance(observation: dict[str, Any]) -> dict[str, Any]:
    return {
        "captured_at": observation["observed_at"],
        "sources": [source(observation)],
    }


def known_fact(reason: str, observation: dict[str, Any]) -> dict[str, Any]:
    return {
        "state": "known",
        "reason": reason,
        "provenance": provenance(observation),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", type=Path, default=Path("registry"))
    parser.add_argument("--max-age-days", type=int, default=7)
    args = parser.parse_args()

    now = dt.datetime.now(dt.timezone.utc)
    candidates: dict[str, list[dict[str, Any]]] = {}
    for price_path in sorted((args.registry / "price").glob("*/us.json")):
        price = load(price_path)
        hardware_refs = [
            item for item in (price.get("hardware") or []) if isinstance(item, dict)
        ]
        if not hardware_refs:
            continue
        hardware_records: list[tuple[str, dict[str, Any]]] = []
        for hardware_ref in hardware_refs:
            hardware_id = hardware_ref.get("id")
            if not isinstance(hardware_id, str):
                continue
            hardware_path = args.registry / "hardware" / f"{hardware_id}.json"
            if hardware_path.exists():
                hardware_records.append((hardware_id, load(hardware_path)))

        for observation in price.get("observations") or []:
            if not isinstance(observation, dict):
                continue
            observed_at = parse_time(observation.get("observed_at"))
            title_memory = {
                int(value)
                for value in re.findall(
                    r"(?<!\d)(\d+)\s*G(?:B)?\b",
                    str(observation.get("title") or ""),
                    re.IGNORECASE,
                )
            }
            if (
                observation.get("condition") != "new"
                or observation.get("in_stock") is not True
                or observation.get("currency") != "USD"
                or not isinstance(observation.get("amount"), (int, float))
                or observation["amount"] <= 0
                or not isinstance(observation.get("retailer"), str)
                or not isinstance(observation.get("url"), str)
                or not observation["url"].startswith("https://")
                or observed_at is None
                or now - observed_at > dt.timedelta(days=args.max_age_days)
            ):
                continue

            matches = []
            for hardware_id, hardware_record in hardware_records:
                memory_gb = (hardware_record.get("memory") or {}).get("vram_gb")
                if (
                    isinstance(memory_gb, (int, float))
                    and int(memory_gb) not in title_memory
                    and (
                        bool(title_memory)
                        or hardware_record.get("kind") == "integrated"
                        or len(hardware_records) > 1
                    )
                ):
                    continue
                matches.append(hardware_id)
            if len(matches) == 1:
                candidates.setdefault(matches[0], []).append(observation)

    files_updated = street_prices = system_prices = stocks = availability = price_rows = 0
    for hardware_id, observations in sorted(candidates.items()):
        hardware_path = args.registry / "hardware" / f"{hardware_id}.json"
        if not hardware_path.exists():
            continue
        record = load(hardware_path)
        commercial = record.get("commercial")
        if not isinstance(commercial, dict):
            continue
        observation = min(observations, key=lambda item: item["amount"])
        changed = False
        facts = record.setdefault("facts", {})

        if "current_street_price" in commercial and commercial["current_street_price"] is None:
            commercial["current_street_price"] = {
                "amount": observation["amount"],
                "currency": observation["currency"],
            }
            facts["commercial.current_street_price"] = known_fact(
                "fresh-in-stock-us-retailer-observation", observation
            )
            street_prices += 1
            changed = True
        if "current_system_price" in commercial and commercial["current_system_price"] is None:
            commercial["current_system_price"] = {
                "amount": observation["amount"],
                "currency": observation["currency"],
            }
            facts["commercial.current_system_price"] = known_fact(
                "fresh-in-stock-exact-system-configuration", observation
            )
            system_prices += 1
            changed = True

        if "current_stock" in commercial and commercial["current_stock"] is None:
            commercial["current_stock"] = True
            facts["commercial.current_stock"] = known_fact(
                "fresh-in-stock-us-retailer-observation", observation
            )
            stocks += 1
            changed = True

        availability_record = commercial.get("availability")
        if isinstance(availability_record, dict) and availability_record.get("state") == "unknown":
            availability_record.clear()
            availability_record.update(
                {
                    "state": "available",
                    "scope": "at-least-one-us-retailer",
                    "reason": "fresh-in-stock-retailer-observation",
                    "provenance": provenance(observation),
                }
            )
            facts["commercial.availability"] = known_fact(
                "fresh-in-stock-us-retailer-observation", observation
            )
            availability += 1
            changed = True

        prices = commercial.get("prices")
        if isinstance(prices, list) and not any(
            isinstance(item, dict)
            and item.get("source", {}).get("url") == observation["url"]
            and item.get("amount") == observation["amount"]
            for item in prices
        ):
            prices.append(
                {
                    "amount": observation["amount"],
                    "currency": observation["currency"],
                    "unit": "one_time",
                    "region": "US",
                    "kind": "street_price",
                    "scope": "current_in_stock_retail_listing",
                    "configuration": observation["title"],
                    "as_of": observation["observed_at"],
                    "source": source(observation),
                    "captured_at": observation["observed_at"],
                }
            )
            price_rows += 1
            changed = True

        if changed:
            save(hardware_path, record)
            files_updated += 1

    print(
        f"hardware files updated: {files_updated}; current street prices: {street_prices}; "
        f"current system prices: {system_prices}; stock states: {stocks}; "
        f"availability states: {availability}; price rows: {price_rows}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
