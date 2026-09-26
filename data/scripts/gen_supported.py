#!/usr/bin/env python3
"""Write supported/: one page per GPU that Local AI runs a model on, and an index with the counts.

Each page describes the card's recommended recipe in plugin/v2/recipes.json (the first one), which is
what Omarchy's Local AI vendors. Pages hold no timestamps, so --check can compare them byte for byte.

    python3 scripts/gen_supported.py [--check]
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REG = ROOT / "registry"
OUT = ROOT / "supported"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from recommend import decode_c1  # noqa: E402

VENDOR = {"nvidia": "nvidia", "intel-xpu": "intel", "amd-rocm": "amd"}
ENGINE = {"sglang": "SGLang", "vllm": "vLLM", "tabbyapi": "TabbyAPI (ExLlamaV3)", "llama.cpp": "llama.cpp", "llama-cpp": "llama.cpp"}


def load(kind, id_):
    return json.loads((REG / kind / f"{id_}.json").read_text())


def title(hw):
    return f"{hw['name'].removeprefix('NVIDIA ')} {hw['memory']['vram_gb']} GB"


def page(hw, entry):
    recipe = load("recipe", entry["id"])
    caps = [c for c in ("reasoning", "tools", "vision") if (recipe.get("capabilities") or {}).get(c) is True]
    decode = decode_c1(recipe)
    weights = "<br>".join(
        f"[{w['repository']}](https://huggingface.co/{w['repository']}/tree/{w['revision']}) at `{w['revision'][:8]}`"
        for w in entry["weights"]) or "in the image"
    accepted = ((recipe.get("metadata") or {}).get("acceptance") or {}).get("accepted_at") or ""
    rows = [
        ("Model", f"{entry['name']} · {entry['format']}" if entry["format"] else entry["name"]),
        ("Weights", f"{weights} · {entry['sizeGb']:g} GB"),
        ("Engine", f"{ENGINE.get(entry['engine'], entry['engine'])} · `{entry['image']}`"),
        ("Context", f"{entry['serving']['ctxTokens']:,} tokens"),
        ("Capabilities", ", ".join(caps) or "chat"),
        ("Decode, one stream", f"{decode:.0f} tok/s" if decode else "not measured"),
        ("Accepted", accepted[:10] or "yes"),
        ("Recipe", f"[`{entry['id']}`](../../registry/recipe/{entry['id']}.json)"),
    ]
    lines = [f"# {title(hw)}", "",
             f"Local AI runs {entry['name']} on this card.", "", "| | |", "|---|---|"]
    lines += [f"| {k} | {v} |" for k, v in rows]
    return "\n".join(lines) + "\n", decode


def build():
    catalog = json.loads((ROOT / "plugin" / "v2" / "recipes.json").read_text())["hardware"]
    files, index = {}, []
    for hw_id, spec in sorted(catalog.items()):
        hw = load("hardware", hw_id)
        vendor = VENDOR.get(hw.get("accelerator_backend"), "other")
        entry = spec["recipes"][0]
        text, decode = page(hw, entry)
        files[f"{vendor}/{hw_id}.md"] = text
        index.append((vendor, hw, entry, decode))
    counts = {v: sum(1 for x in index if x[0] == v) for v in ("nvidia", "intel", "amd", "other")}
    lines = ["# Supported GPUs", "",
             f"Local AI runs a validated model on {len(index)} GPUs: {counts['nvidia']} NVIDIA, {counts['intel']} Intel, {counts['amd']} AMD.",
             "Each one was tested on that exact card before it was listed; a card that is not here shows Coming soon.", "",
             "| GPU | Model | Engine | Context | Decode |", "|---|---|---|---|---|"]
    for vendor, hw, entry, decode in sorted(index, key=lambda x: (x[0], title(x[1]))):
        lines.append(f"| [{title(hw)}]({vendor}/{hw['id']}.md) | {entry['name']} | "
                     f"{ENGINE.get(entry['engine'], entry['engine'])} | {entry['serving']['ctxTokens'] // 1024}K | "
                     f"{f'{decode:.0f} tok/s' if decode else '–'} |")
    files["README.md"] = "\n".join(lines) + "\n"
    return files


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    files = build()
    on_disk = {str(p.relative_to(OUT)) for p in OUT.rglob("*.md")} if OUT.exists() else set()
    if args.check:
        stale = sorted(n for n in files if not (OUT / n).exists() or (OUT / n).read_text() != files[n])
        stale += sorted(on_disk - set(files))
        for name in stale:
            print(f"supported/{name} is not current: run python3 scripts/gen_supported.py", file=sys.stderr)
        return 1 if stale else 0
    for name in on_disk - set(files):
        (OUT / name).unlink()
    for name, text in files.items():
        (OUT / name).parent.mkdir(parents=True, exist_ok=True)
        (OUT / name).write_text(text)
    print(f"wrote supported/: {len(files) - 1} GPUs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
