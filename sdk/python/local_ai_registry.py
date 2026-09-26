"""Local AI registry, Python. Standard library only.

    from local_ai_registry import pick, command
    print(command(pick("NVIDIA GeForce RTX 4090", vram=24)))

    python3 local_ai_registry.py "RTX 4090" 24      # prints the command for your GPU
"""
import json
import re
import shlex
import sys
import urllib.request

URL = "https://local.sybilsolutions.ai/api/v2/catalog.json"
_cache = {}


def catalog(url=URL):
    """The whole catalog: cards (with their picks), recipes (with rendered launches), models."""
    if url not in _cache:
        with urllib.request.urlopen(url, timeout=30) as r:
            _cache[url] = json.load(r)
    return _cache[url]


def _norm(s):
    s = re.sub(r"\((r|tm)\)", "", s.lower())
    return re.sub(r"geforce|nvidia|amd|radeon|intel|graphics|[^a-z0-9]", "", s)


def _names(i, c):
    return [_norm(c["name"]), _norm(i)] + list((c.get("match") or {}).get("names") or [])


def detect(cat, gpu, vram=None):
    """The card id for a GPU as the driver names it, and its memory in GB."""
    n = _norm(gpu)
    hits = [(i, c) for i, c in cat["cards"].items()
            if any(x and x in n for x in _names(i, c)) and (not vram or abs(c["vram_gb"] - vram) <= 2)]
    hits.sort(key=lambda x: -max(len(y) for y in _names(*x) if y and y in n))
    return hits[0][0] if hits else None


def pick(gpu, vram=None, all=False, cat=None):
    """The recommended recipe for a GPU (or None); all=True returns the card's top three."""
    cat = cat or catalog()
    i = detect(cat, gpu, vram)
    if not i:
        return [] if all else None
    rs = [{"key": k, **cat["recipes"][k]} for k in cat["cards"][i]["picks"]]
    return rs if all else rs[0]


GPU = {"nvidia": "--gpus all", "amd-rocm": "--device /dev/kfd --device /dev/dri", "amd-vulkan": "--device /dev/dri", "intel-xpu": "--device /dev/dri"}


def _q(s):
    return s if re.fullmatch(r"[\w@%+=:,./-]+", s) else shlex.quote(s)


def steps(r):
    """The steps to run a recipe by hand: download the weights, write the config, start the container."""
    l = r["launch"]
    name = (r.get("key") or r["model"]).split("/")[-1]
    if l.get("kind") == "host":
        return [{"title": "Install", "code": f"# {l['install']}"}, {"title": "Start the server", "code": " ".join(l["command"])}]
    ws = [w for w in (l["weights"] if isinstance(l["weights"], list) else [l["weights"]]) if w and w.get("repo")]
    out, mounts, dl = [], [], []
    for w in ws:
        d = f"~/models/{w['repo'].split('/')[1]}-{w['revision'][:8]}"
        if w.get("layout") == "hub":
            dl.append(f"hf download {w['repo']} \\\n  --revision {w['revision']}")
            mounts.append("-v ~/.cache/huggingface:/root/.cache/huggingface")
        else:
            dl.append(f"hf download {w['repo']} \\\n  --revision {w['revision']} \\\n  --local-dir {d}")
            mounts.append(f"-v {d}:{w['at']}:ro")
    if dl:
        out.append({"title": "Download the weights", "code": "\n\n".join(dl)})
    if l.get("config"):
        out.append({"title": "Write the server config", "code": f"cat > {name}.yml <<'EOF'\n{l['config']['text'].rstrip()}\nEOF"})
        mounts.append(f"-v $PWD/{name}.yml:{l['config']['at']}:ro")
    args, a = [], l["args"]
    i = 0
    while i < len(a):
        if a[i].startswith("-") and i + 1 < len(a) and not a[i + 1].startswith("-"):
            args.append(f"{a[i]} {_q(a[i + 1])}"); i += 2
        else:
            args.append(_q(a[i])); i += 1
    run = ["docker run --rm", GPU.get(l.get("backend") or "nvidia", GPU["nvidia"]), f"-p 8000:{l['port']}"] + list(l.get("flags") or [])
    run += [f"--shm-size {l['shm']}"] if l.get("shm") else []
    run += [f"-e {k}={_q(v)}" for k, v in (l.get("env") or {}).items()] + mounts
    run += [f"--entrypoint {l['entrypoint']}"] if l.get("entrypoint") else []
    m = l.get("machines")
    title = f"Start the server on each of the {m} machines (NODE_RANK 0 to {m - 1})" if m else "Start the server"
    out.append({"title": title, "code": " \\\n  ".join(run + [l["image"]] + args)})
    return out


def command(r):
    """All the steps as one shell script."""
    return "\n\n".join(f"# {s['title']}\n{s['code']}" for s in steps(r))


if __name__ == "__main__":
    r = pick(sys.argv[1], float(sys.argv[2]) if len(sys.argv) > 2 else None)
    print(command(r) if r else f"no tested recipe for {sys.argv[1]!r} yet: https://local.sybilsolutions.ai")
