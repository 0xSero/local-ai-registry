#!/usr/bin/env python3

import argparse
import json
import re
from pathlib import Path


SCHEMA = "local-ai-registry/v1"
APPLE_SOURCE = "https://support.apple.com/specs/mac"
NVIDIA_SOURCE = "https://www.nvidia.com/en-us/geforce/graphics-cards/compare/"


APPLE = {
    "m1": ([8, 16], 68.25, ["MacBook Air", "MacBook Pro 13-inch", "Mac mini", "iMac"]),
    "m1-pro": ([16, 32], 200, ["MacBook Pro"]),
    "m1-max": ([32, 64], 400, ["MacBook Pro", "Mac Studio"]),
    "m1-ultra": ([64, 128], 800, ["Mac Studio"]),
    "m2": ([8, 16, 24], 100, ["MacBook Air", "MacBook Pro 13-inch", "Mac mini"]),
    "m2-pro": ([16, 32], 200, ["MacBook Pro", "Mac mini"]),
    "m2-max": ([32, 64, 96], 400, ["MacBook Pro", "Mac Studio"]),
    "m2-ultra": ([64, 128, 192], 800, ["Mac Studio", "Mac Pro"]),
    "m3": ([8, 16, 24], 100, ["MacBook Air", "MacBook Pro", "iMac"]),
    "m3-pro": ([18, 36], 150, ["MacBook Pro"]),
    "m3-max": ([36, 48, 64, 96, 128], {"min": 300, "max": 400}, ["MacBook Pro"]),
    "m3-ultra": ([96, 256, 512], 819, ["Mac Studio"]),
    "m4": ([16, 24, 32], 120, ["MacBook Pro", "Mac mini", "iMac"]),
    "m4-pro": ([24, 48, 64], 273, ["MacBook Pro", "Mac mini"]),
    "m4-max": ([36, 48, 64, 128], {"min": 410, "max": 546}, ["MacBook Pro", "Mac Studio"]),
    "m5": ([16, 24, 32], 153, ["MacBook Pro"]),
    "m5-pro": ([24, 48, 64], 307, ["MacBook Pro"]),
    "m5-max": ([36, 48, 64, 128], {"min": 460, "max": 614}, ["MacBook Pro"]),
}

NVIDIA = {
    "rtx-3060-12gb": ("GeForce RTX 3060", 12, "GDDR6"),
    "rtx-3060-ti-8gb": ("GeForce RTX 3060 Ti", 8, "GDDR6"),
    "rtx-3070-8gb": ("GeForce RTX 3070", 8, "GDDR6"),
    "rtx-3070-ti-8gb": ("GeForce RTX 3070 Ti", 8, "GDDR6X"),
    "rtx-3080-10gb": ("GeForce RTX 3080", 10, "GDDR6X"),
    "rtx-3080-12gb": ("GeForce RTX 3080", 12, "GDDR6X"),
    "rtx-3080-ti-12gb": ("GeForce RTX 3080 Ti", 12, "GDDR6X"),
    "rtx-3090-24gb": ("GeForce RTX 3090", 24, "GDDR6X"),
    "rtx-3090-ti-24gb": ("GeForce RTX 3090 Ti", 24, "GDDR6X"),
    "rtx-4060-8gb": ("GeForce RTX 4060", 8, "GDDR6"),
    "rtx-4060-ti-8gb": ("GeForce RTX 4060 Ti", 8, "GDDR6"),
    "rtx-4060-ti-16gb": ("GeForce RTX 4060 Ti", 16, "GDDR6"),
    "rtx-4070-12gb": ("GeForce RTX 4070", 12, "GDDR6X"),
    "rtx-4070-super-12gb": ("GeForce RTX 4070 SUPER", 12, "GDDR6X"),
    "rtx-4070-ti-12gb": ("GeForce RTX 4070 Ti", 12, "GDDR6X"),
    "rtx-4070-ti-super-16gb": ("GeForce RTX 4070 Ti SUPER", 16, "GDDR6X"),
    "rtx-4080-16gb": ("GeForce RTX 4080", 16, "GDDR6X"),
    "rtx-4080-super-16gb": ("GeForce RTX 4080 SUPER", 16, "GDDR6X"),
    "rtx-4090-24gb": ("GeForce RTX 4090", 24, "GDDR6X"),
    "rtx-5060-8gb": ("GeForce RTX 5060", 8, "GDDR7"),
    "rtx-5060-ti-8gb": ("GeForce RTX 5060 Ti", 8, "GDDR7"),
    "rtx-5060-ti-16gb": ("GeForce RTX 5060 Ti", 16, "GDDR7"),
    "rtx-5070-12gb": ("GeForce RTX 5070", 12, "GDDR7"),
    "rtx-5070-ti-16gb": ("GeForce RTX 5070 Ti", 16, "GDDR7"),
    "rtx-5080-16gb": ("GeForce RTX 5080", 16, "GDDR7"),
    "rtx-5090-32gb": ("GeForce RTX 5090", 32, "GDDR7"),
    "rtx-a6000-48gb": ("RTX A6000", 48, "GDDR6"),
    "rtx-6000-ada-48gb": ("RTX 6000 Ada Generation", 48, "GDDR6"),
    "rtx-pro-6000-blackwell-96gb": ("RTX PRO 6000 Blackwell", 96, "GDDR7"),
}

AMD = {
    "ryzen-ai-max-plus-395-128gb": ("Ryzen AI Max+ 395", 128, "LPDDR5X unified", "integrated", "https://www.amd.com/en/products/processors/laptop/ryzen/ai-300-series/amd-ryzen-ai-max-plus-395.html"),
    "radeon-ai-pro-r9700-32gb": ("Radeon AI PRO R9700", 32, "GDDR6", "discrete", "https://www.amd.com/en/products/graphics/workstations/radeon-ai-pro/ai-9000-series/amd-radeon-ai-pro-r9700.html"),
    "rx-7900-xtx-24gb": ("Radeon RX 7900 XTX", 24, "GDDR6", "discrete", "https://www.amd.com/en/products/graphics/desktops/radeon/7000-series/amd-radeon-rx-7900xtx.html"),
    "rx-9070-xt-16gb": ("Radeon RX 9070 XT", 16, "GDDR6", "discrete", "https://www.amd.com/en/products/graphics/desktops/radeon/9000-series/amd-radeon-rx-9070xt.html"),
}

LEGACY = {
    "b200-180gb": ("NVIDIA B200", "https://www.nvidia.com/en-us/data-center/b200/"),
    "dgx-spark-gb10-128gb": ("NVIDIA DGX Spark GB10", "https://www.nvidia.com/en-us/products/workstations/dgx-spark/"),
    "intel-arc-pro-b60-24gb": ("Intel Arc Pro B60", "https://www.intel.com/content/www/us/en/products/docs/discrete-gpus/arc/workstations/b-series/overview.html"),
    "intel-arc-pro-b70-32gb": ("Intel Arc Pro B70", "https://www.intel.com/content/www/us/en/products/docs/discrete-gpus/arc/workstations/b-series/overview.html"),
    "mi300x-192gb": ("AMD Instinct MI300X", "https://www.amd.com/en/products/accelerators/instinct/mi300/mi300x.html"),
    "rtx-2000-ada-16gb": ("NVIDIA RTX 2000 Ada Generation", "https://www.nvidia.com/en-us/design-visualization/rtx-2000/"),
    "rtx-4000-ada-20gb": ("NVIDIA RTX 4000 Ada Generation", "https://www.nvidia.com/en-us/design-visualization/rtx-4000/"),
    "rtx-pro-4000-blackwell-24gb": ("NVIDIA RTX PRO 4000 Blackwell", "https://www.nvidia.com/en-us/products/workstations/professional-desktop-gpus/"),
    "rtx-pro-4500-blackwell-32gb": ("NVIDIA RTX PRO 4500 Blackwell", "https://www.nvidia.com/en-us/products/workstations/professional-desktop-gpus/"),
    "rx-7700-xt-12gb": ("AMD Radeon RX 7700 XT", "https://www.amd.com/en/products/graphics/desktops/radeon/7000-series/amd-radeon-rx-7700-xt.html"),
    "rx-7900-xt-20gb": ("AMD Radeon RX 7900 XT", "https://www.amd.com/en/products/graphics/desktops/radeon/7000-series/amd-radeon-rx-7900-xt.html"),
}


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def title_chip(chip):
    return "Apple " + " ".join(part.upper() if re.fullmatch(r"m\d+", part) else part.title() for part in chip.split("-"))


def hardware_record(identifier, vendor, name, backend, kind, memory, source, **extra):
    return {
        "schema_version": SCHEMA,
        "id": identifier,
        "vendor": vendor,
        "name": name,
        "family": extra.get("family"),
        "kind": kind,
        "accelerator_backend": backend,
        "memory": memory,
        "aliases": extra.get("aliases", []),
        "products": extra.get("products", []),
        "sources": [{"kind": "vendor", "url": source}],
    }


def curate_hardware(root):
    directory = root / "hardware"
    for path in sorted(directory.glob("*.json")):
        record = json.loads(path.read_text())
        legacy_name, legacy_source = LEGACY.get(record["id"], (None, None))
        normalized = hardware_record(
            record["id"],
            record["vendor"],
            legacy_name or record.get("name") or record["id"].replace("-", " ").title(),
            record["accelerator_backend"],
            record.get("kind") or ("unified" if record["vendor"] == "apple" else "discrete"),
            record["memory"],
            legacy_source or "https://github.com/0xSero/local-ai-registry",
            family=record.get("family") or re.sub(r"-\d+gb$", "", record["id"]),
            aliases=record.get("aliases", []),
            products=record.get("products", []),
        )
        if legacy_source:
            normalized["sources"] = [{"kind": "vendor", "url": legacy_source}]
        elif record.get("sources") and not any(source.get("url") == "https://github.com/0xSero/local-ai-registry" for source in record["sources"]):
            normalized["sources"] = record["sources"]
        else:
            normalized["sources"] = [{"kind": "registry", "url": "https://github.com/0xSero/local-ai-registry"}]
        write(path, normalized)
    for chip, (capacities, bandwidth, products) in APPLE.items():
        for capacity in capacities:
            identifier = f"apple-{chip}-{capacity}gb"
            write(directory / f"{identifier}.json", hardware_record(
                identifier, "apple", f"{title_chip(chip)} {capacity}GB", "metal", "unified",
                {"vram_gb": capacity, "cpu_memory_gb": capacity, "vram_type": "unified", "bandwidth_gb_per_s": bandwidth},
                APPLE_SOURCE, family=chip, aliases=[f"{chip.replace('-', ' ')} {capacity}gb"], products=products,
            ))

    for identifier, (name, capacity, memory_type) in NVIDIA.items():
        write(directory / f"{identifier}.json", hardware_record(
            identifier, "nvidia", name, "nvidia", "discrete",
            {"vram_gb": capacity, "cpu_memory_gb": None, "vram_type": memory_type, "bandwidth_gb_per_s": None},
            NVIDIA_SOURCE, family=re.sub(r"-\d+gb$", "", identifier), aliases=[name.lower().replace("geforce ", "")],
        ))

    for identifier, (name, capacity, memory_type, kind, source) in AMD.items():
        write(directory / f"{identifier}.json", hardware_record(
            identifier, "amd", name, "amd-rocm", kind,
            {"vram_gb": capacity, "cpu_memory_gb": capacity if kind == "integrated" else None, "vram_type": memory_type, "bandwidth_gb_per_s": None},
            source, family=re.sub(r"-\d+gb$", "", identifier), aliases=[name.lower()],
        ))

    generic = {
        "apple-max-128gb": ("Apple Max 128GB, generation unspecified", "max"),
        "apple-pro-64gb": ("Apple Pro 64GB, generation unspecified", "pro"),
    }
    for identifier, (name, family) in generic.items():
        write(directory / f"{identifier}.json", hardware_record(
            identifier, "apple", name, "metal", "unified",
            {"vram_gb": int(re.search(r"(\d+)gb", identifier).group(1)), "cpu_memory_gb": int(re.search(r"(\d+)gb", identifier).group(1)), "vram_type": "unified", "bandwidth_gb_per_s": None},
            "https://www.localmaxxing.com/en/api-docs", family=family,
        ))


def sanitize_candidates(root):
    for path in sorted((root / "recipe").glob("*.json")):
        recipe = json.loads(path.read_text())
        if recipe.get("recipe_source") != "localmaxxing":
            recipe["schema_version"] = SCHEMA
            write(path, recipe)
            continue
        metadata = recipe.setdefault("metadata", {}).setdefault("localmaxxing", {})
        run_id = metadata.get("run_id")
        existing_container = recipe.get("launch", {}).get("container")
        recipe["status"] = "candidate"
        recipe["launch"] = {
            "kind": "reference",
            "source": "localmaxxing",
            "run_id": run_id,
            "url": f"https://www.localmaxxing.com/en/runs/{run_id}" if run_id else "https://www.localmaxxing.com/en/leaderboard",
        }
        if existing_container:
            recipe["launch"]["container"] = existing_container
        recipe["capabilities"] = {key: None for key in ("chat", "reasoning", "tools", "vision")}
        recipe["schema_version"] = SCHEMA
        write(path, recipe)

    for collection in ("model", "model-instance", "speed-sweeps"):
        for path in sorted((root / collection).glob("*.json")):
            record = json.loads(path.read_text())
            record["schema_version"] = SCHEMA
            write(path, record)


def rebuild_index(root):
    collections = {}
    for name in ("hardware", "model", "model-instance", "recipe", "speed-sweeps"):
        collections[name] = sorted(path.stem for path in (root / name).glob("*.json"))
    collections["price"] = sorted(
        json.loads(path.read_text())["id"] for path in (root / "price").glob("*/*.json")
    )
    recipes = []
    for path in sorted((root / "recipe").glob("*.json")):
        recipe = json.loads(path.read_text())
        recipes.append({
            "id": recipe["id"],
            "recipe_source": recipe.get("recipe_source"),
            "status": recipe["status"],
            "model_instance_id": recipe["model_instance_id"],
            "hardware_id": recipe["hardware_id"],
            "hardware_count": recipe["hardware_count"],
            "engine": recipe["engine"]["name"],
            "launch_kind": recipe["launch"]["kind"],
            "capabilities": recipe["capabilities"],
            "has_evidence": bool(recipe.get("speed_sweeps_ids")),
        })
    write(root / "index.json", {
        "schema_version": SCHEMA,
        "resolver_rule": "Resolve <field>_id from <field>/<id>.json and <field>_ids as an array of those records; underscores in collection names become hyphens. Resolve price ids from price/<product-id>/<region>.json.",
        "collections": collections,
        "counts": {name.replace("-", "_"): len(ids) for name, ids in collections.items()},
        "recipes": recipes,
    })


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", default="registry")
    parser.add_argument("--index-only", action="store_true", help="rebuild index without rewriting collection records")
    args = parser.parse_args()
    root = Path(args.root)
    if not args.index_only:
        curate_hardware(root)
        sanitize_candidates(root)
    rebuild_index(root)


if __name__ == "__main__":
    main()
