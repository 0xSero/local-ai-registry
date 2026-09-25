#!/usr/bin/env python3
"""The recipe lab: run a model on a card, check it, and only then write its recipe.

A recipe is the output of a passing run, never written by hand. It names the weights (pinned), an
engine profile (pinned), the few settings that differ from the profile's defaults, the card, and the
proof. Everything a program needs to launch it is rendered from the profile, so a recipe is ~600 bytes.

    lab.py try <repo>@<revision> --model <id> --engine <profile> --card <card> [--set k=v ...]
               [--on vast|runpod|endpoint] [--endpoint URL] [--proxy-gpu NAME]
    lab.py render <recipe.json>        # the launch a program runs, as JSON
    lab.py check                       # every recipe: format, pins, profile, card, proof (CI)

Gates (all must pass): load, chat, reasoning, tools, context, speed. The full evidence goes to
lab/runs/ (data, kept); the recipe goes to recipes/<card>/ (production). Standard library only.
"""

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import string
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
ENGINES, RECIPES, RUNS, CARDS = ROOT / "engines", ROOT / "recipes", ROOT / "lab" / "runs", ROOT / "registry" / "hardware"
GATES = ["load", "chat", "reasoning", "tools", "context", "speed"]
MIN_TPS = 15.0
MAX_RECIPE_BYTES = 1024


def log(msg):
    print(f"[lab {dt.datetime.now().strftime('%H:%M:%S')}] {msg}", file=sys.stderr, flush=True)


# ----------------------------------------------------------------------------- rendering
def profile(ref):
    """`tabbyapi-exl3@0f83e6198dc3` -> the profile, checked against the digest prefix."""
    name, _, digest = ref.partition("@")
    p = json.loads((ENGINES / f"{name}.json").read_text())
    if digest and not p["image"].split("@sha256:")[1].startswith(digest):
        raise SystemExit(f"{ref}: the profile's image is now {p['image']}; rerun the recipe")
    return p


def dirname(weights):
    repo, rev = weights.split("@")
    return f"{repo.split('/')[1]}-{rev[:8]}"


def render(recipe):
    """The launch contract for a recipe: image, entrypoint, args, env, port, shm, weights and config file."""
    if recipe["engine"].startswith("registry@"):
        return legacy(recipe["engine"].split("@", 1)[1])
    p = profile(recipe["engine"])
    s = {**p["defaults"], **recipe.get("set", {})}
    name = dirname(recipe["weights"])
    values = {**{k: str(v).lower() if isinstance(v, bool) else v for k, v in s.items()}, "name": name,
              "cache_tokens": int(s["ctx"]) * int(s["seqs"]) + 1024 * int(s["seqs"]),
              "draft_block": "{draft_mode: mtp}" if s["draft"] == "mtp" else "{}"}
    config = "\n".join(string.Template(line).substitute(values) for line in p["config"]) + "\n"
    repo, rev = recipe["weights"].split("@")
    return {"image": p["image"], "entrypoint": p["entrypoint"], "args": p["args"], "port": p["port"], "shm": p["shm"],
            "env": {}, "weights": {"repo": repo, "revision": rev, "at": string.Template(p["weights_at"]).substitute(name=name)},
            "config": {"at": p["config_at"], "text": config, "sha256": hashlib.sha256(config.encode()).hexdigest()},
            "ctx": int(s["ctx"]), "seqs": int(s["seqs"]), "vision": bool(s["vision"]), "backend": p["backend"]}


def legacy(recipe_id):
    """The launch of a recipe validated before the lab, as the plugin export carries it."""
    v2 = json.loads((ROOT / "plugin" / "v2" / "recipes.json").read_text())
    for hw in v2["hardware"].values():
        for e in hw["recipes"]:
            if e["id"] == recipe_id:
                a = e.get("asset")
                return {"image": e["image"], "entrypoint": e["launch"].get("entrypoint"), "args": e["launch"].get("arguments") or [],
                        "port": e["launch"]["port"], "shm": e["launch"].get("shm"), "env": e["launch"].get("environment") or {},
                        "weights": [{"repo": w["repository"], "revision": w["revision"], "at": w["mountPath"] + ("/" + w["dir"] if w.get("dir") else ""),
                                     "layout": w["layout"], "files": w.get("files")} for w in e["weights"]],
                        "config": {"at": a["mountPath"], "text": a["text"]} if a else None,
                        "ctx": (e.get("serving") or {}).get("ctxTokens") or 0, "seqs": 1, "cards": e.get("cards", 1),
                        "vision": bool((e.get("capabilities") or {}).get("vision")), "backend": None, "legacy": recipe_id}
    raise SystemExit(f"{recipe_id} is not in plugin/v2/recipes.json")


# ----------------------------------------------------------------------------- the server under test
def call(endpoint, path, body=None, timeout=900):
    headers = {"Content-Type": "application/json"}
    if os.environ.get("LAB_API_KEY"):  # an owner's server behind a keyed gateway
        headers["Authorization"] = f"Bearer {os.environ['LAB_API_KEY']}"
    req = urllib.request.Request(endpoint + path, data=json.dumps(body).encode() if body else None, headers=headers)
    t = time.monotonic()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        out = json.loads(r.read())
    return out, time.monotonic() - t


def count(endpoint, text):
    """Tokens in text, from the server's tokenizer when it has one (TabbyAPI: /v1/token/encode)."""
    try:
        out, _ = call(endpoint, "/v1/token/encode", {"text": text}, timeout=120)
        return int(out.get("length") or len(out.get("tokens") or [])), "tokenizer"
    except Exception:
        return len(text) // 4, "estimate"


def chat(endpoint, model, messages, **kw):
    out, secs = call(endpoint, "/v1/chat/completions", {"model": model, "messages": messages, "temperature": 0.6, **kw})
    c, u = out["choices"][0], dict(out.get("usage") or {})
    if not u.get("prompt_tokens"):  # TabbyAPI called directly leaves usage empty; count what went in and came out
        u["prompt_tokens"], u["counted"] = count(endpoint, "\n".join(m.get("content") or "" for m in messages))
    if not u.get("completion_tokens"):
        m = c.get("message") or {}
        u["completion_tokens"], u["counted"] = count(endpoint, (m.get("reasoning_content") or m.get("reasoning") or "") + (m.get("content") or ""))
    return c, u, secs


def gates(endpoint, launch):
    """Run every gate; returns (passed, proof, evidence)."""
    ev, ok = {}, {}
    models, _ = call(endpoint, "/v1/models", timeout=30)
    served = models["data"][0]["id"]
    ok["load"] = True
    # chat: an answer that ends by itself
    c, u, _ = chat(endpoint, served, [{"role": "user", "content": "Name three primary colors, comma separated."}])
    ok["chat"] = bool((c["message"].get("content") or "").strip()) and c.get("finish_reason") == "stop"
    ev["chat"] = {"content": c["message"].get("content"), "finish": c.get("finish_reason")}
    # reasoning: thinking comes back separately, and the answer is right
    c, u, _ = chat(endpoint, served, [{"role": "user", "content": "What is 17 * 23? Reply with only the number."}])
    thinking = c["message"].get("reasoning_content") or c["message"].get("reasoning") or ""
    content = c["message"].get("content") or ""
    ok["reasoning"] = bool(thinking.strip()) and "391" in content and "<think>" not in content
    ev["reasoning"] = {"thinking_chars": len(thinking), "content": content[-200:]}
    # tools: a call with the right arguments, then the result used in the reply
    tool = {"type": "function", "function": {"name": "get_weather", "description": "Current weather for a city",
            "parameters": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]}}}
    msgs = [{"role": "user", "content": "What's the weather in Paris right now? Use the tool."}]
    c, u, _ = chat(endpoint, served, msgs, tools=[tool])
    calls = c["message"].get("tool_calls") or []
    args = {}
    try:
        args = json.loads(calls[0]["function"]["arguments"]) if calls else {}
    except (ValueError, KeyError):
        pass
    first = bool(calls) and calls[0]["function"]["name"] == "get_weather" and "paris" in str(args.get("city", "")).lower()
    reply = ""
    if first:
        msgs += [{"role": "assistant", "content": c["message"].get("content") or "", "tool_calls": calls},
                 {"role": "tool", "tool_call_id": calls[0].get("id", "0"), "content": json.dumps({"city": "Paris", "temp_c": 17, "sky": "overcast"})}]
        c2, _, _ = chat(endpoint, served, msgs, tools=[tool])
        reply = c2["message"].get("content") or ""
    ok["tools"] = first and "17" in reply
    ev["tools"] = {"call": calls[:1], "reply": reply[-200:]}
    # context: a code planted near the end of a prompt that fills ~85% of the window
    target = int(launch["ctx"] * 0.85)
    filler = " ".join(f"Line {i}: the archive notes that shipment {i * 7 % 997} left dock {i % 13} on schedule." for i in range(target // 24))  # ~23.6 tokens a line (measured: 32,834 tokens from 1,473 lines)
    prompt = filler + " The access code for the vault is 58213. " + "Anything else is routine."
    c, u, secs = chat(endpoint, served, [{"role": "user", "content": prompt + "\n\nWhat is the access code for the vault? Reply with only the code."}])
    got = u.get("prompt_tokens") or 0
    ok["context"] = "58213" in (c["message"].get("content") or "") and got >= launch["ctx"] * 0.6
    ev["context"] = {"prompt_tokens": got, "seconds": round(secs, 1), "content": (c["message"].get("content") or "")[-80:]}
    # speed: decode at concurrency 1 on a short prompt; no generation is ever capped, it runs to its natural end
    c, u, secs = chat(endpoint, served, [{"role": "user", "content": "Write a detailed 600-word story about a lighthouse keeper."}], temperature=0.8)
    tps = (u.get("completion_tokens") or 0) / secs if secs else 0
    ok["speed"] = tps >= MIN_TPS
    ev["speed"] = {"completion_tokens": u.get("completion_tokens"), "seconds": round(secs, 2), "counted": u.get("counted", "server")}
    prefill = round(got / ev["context"]["seconds"]) if got and ev["context"]["seconds"] else None
    proof = {"gates": " ".join(g for g in GATES if ok.get(g)), "tps": round(tps, 1), "prefill": prefill, "served": served}
    return all(ok.get(g) for g in GATES), proof, {"ok": ok, **ev}


# ----------------------------------------------------------------------------- where it runs
def rented(recipe, launch, args):
    import validate_rented as vr

    class LabSpec(vr.Spec):
        def __init__(self):
            self.recipe, self.image, self.entrypoint = {"id": "lab"}, launch["image"], launch["entrypoint"]
            self.arguments, self.port, self.disk = list(launch["args"]), launch["port"], args.disk
            self.name = f"local-ai-lab-{recipe['card']}"[:60]
            tok = Path.home() / ".cache" / "huggingface" / "token"
            self.env = {"HF_TOKEN": tok.read_text().strip()} if tok.exists() else {}
            hw = json.loads((CARDS / f"{recipe['card']}.json").read_text())
            self.vram_gb = (hw.get("memory") or {}).get("vram_gb") or 0
            self.gpu_override, self.hardware_id = args.proxy_gpu or args.gpu, recipe["card"]
            if args.proxy_gpu:  # a twin card with more memory: search by its own size
                self.vram_gb = args.proxy_vram
            self.provision = [("asset", launch["config"]["at"], launch["config"]["text"]),
                              ("weights", launch["weights"]["at"], (launch["weights"]["repo"], launch["weights"]["revision"]))]

    ns = argparse.Namespace(vast_min_inet=500, vast_min_cuda=args.min_cuda or profile(recipe["engine"]).get("min_cuda", 12.9), vast_max_price=args.max_price, cloud="COMMUNITY", disk=args.disk)
    provider = vr.PROVIDERS[args.on](ns)
    spec = LabSpec()
    exclude = set()
    for attempt in range(1, 3):
        handle = provider.create(spec, exclude)
        handle["port"] = spec.port
        t0 = time.monotonic()
        log(f"{args.on} {handle['id']}: {handle.get('gpu')} at {handle.get('cost')}/h")
        try:
            while True:
                ep = handle.get("endpoint")
                if ep and vr.http_probe(f"{ep}/v1/models") == "ok":
                    break
                started, note = provider.poll(handle)
                if not started and time.monotonic() - t0 > 900:
                    exclude.update({handle.get("offer"), handle.get("machine")})
                    raise vr.StartStalled(note)
                if time.monotonic() - t0 > 3600:
                    raise SystemExit("not ready within an hour")
                time.sleep(10)
            log(f"ready after {int(time.monotonic() - t0)}s at {handle['endpoint']}")
            return handle["endpoint"], {"on": args.on, "gpu": handle.get("gpu"), "host": handle.get("host"), "cost_h": handle.get("cost")}, \
                lambda: provider.destroy(handle)
        except vr.StartStalled as stall:
            provider.destroy(handle)
            log(f"attempt {attempt}: {stall}; trying another host")
    raise SystemExit("no host started the container")


# ----------------------------------------------------------------------------- commands
def cmd_try(args):
    if not re.fullmatch(r"[\w.-]+/[\w.-]+@[0-9a-f]{40}", args.weights):
        raise SystemExit("weights must be <repo>@<40-hex revision>")
    if not (CARDS / f"{args.card}.json").exists():
        raise SystemExit(f"unknown card {args.card}")
    p = profile(args.engine)
    sets = {}
    for kv in args.set:
        k, _, v = kv.partition("=")
        if k not in p["defaults"]:
            raise SystemExit(f"{k} is not a setting of {p['id']}: {sorted(p['defaults'])}")
        v = int(v) if v.isdigit() else {"true": True, "false": False}.get(v, v)
        if v != p["defaults"][k]:
            sets[k] = v
    recipe = {"model": args.model, "weights": args.weights, "engine": f"{p['id']}@{p['image'].split('@sha256:')[1][:12]}",
              "set": sets, "card": args.card}
    launch = render(recipe)
    if args.dry_run:
        print(json.dumps({"recipe": recipe, "launch": launch}, indent=2))
        return 0
    stop = lambda: None
    if args.on == "endpoint":
        endpoint, where = args.endpoint.rstrip("/"), {"on": "owner", "gpu": args.gpu}
    else:
        endpoint, where, stop = rented(recipe, launch, args)
    try:
        passed, proof, evidence = gates(endpoint, launch)
    finally:
        stop()
    at = dt.datetime.now(dt.timezone.utc)
    proof = {"at": at.strftime("%Y-%m-%d"), "on": where["on"], "gpu": where.get("gpu"), **proof}
    if args.proxy_gpu:
        proof["proxy"] = f"{args.proxy_gpu}, memory capped to the card"
    slug = f"{args.model}.{p['id']}.{launch['ctx'] // 1024}k"
    RUNS.mkdir(parents=True, exist_ok=True)
    run = {"recipe": recipe, "where": where, "passed": passed, "proof": proof, "evidence": evidence, "launch_config_sha256": launch["config"]["sha256"]}
    text = json.dumps(run, indent=1, ensure_ascii=False)
    run_path = RUNS / f"{args.card}.{slug}.{at.strftime('%Y%m%dT%H%M%S')}.json"
    run_path.write_text(text + "\n")
    proof["log"] = "sha256:" + hashlib.sha256(text.encode()).hexdigest()[:16]
    log(f"gates: {evidence['ok']}  decode {proof['tps']} tok/s, prefill {proof['prefill']} tok/s; evidence {run_path.relative_to(ROOT)}")
    if not passed:
        log("FAILED: no recipe written")
        return 1
    out = RECIPES / args.card / f"{slug}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    old = json.loads(out.read_text()) if out.exists() else None
    proofs = [proof] + ([q for q in old["proof"] if old.get("weights") == recipe["weights"] and old.get("engine") == recipe["engine"] and old.get("set") == sets][:2] if old else [])
    out.write_text(json.dumps({**recipe, "proof": proofs}, separators=(",", ":")) + "\n")
    log(f"PASSED: wrote {out.relative_to(ROOT)} ({out.stat().st_size} bytes)")
    return 0


def cmd_render(args):
    print(json.dumps(render(json.loads(Path(args.recipe).read_text())), indent=2))
    return 0


def cmd_check(_):
    bad = []
    for f in sorted(RECIPES.rglob("*.json")):
        r = json.loads(f.read_text())
        name = f.relative_to(ROOT)
        try:
            assert set(r) == {"model", "weights", "engine", "set", "card", "proof"}, f"fields {sorted(r)}"
            assert re.fullmatch(r"[\w.-]+/[\w.-]+@[0-9a-f]{40}", r["weights"]), "weights not pinned"
            assert f.parent.name == r["card"] and (CARDS / f"{r['card']}.json").exists(), "card"
            launch = render(r)
            assert f.name == f"{r['model']}.{r['engine'].split('@')[0]}.{launch['ctx'] // 1024}k.json", "file name"
            need = {"load", "chat"} if r["proof"][0].get("legacy") else set(GATES)
            assert need <= set(r["proof"][0]["gates"].split()), "latest proof lacks a gate"
            assert f.stat().st_size <= MAX_RECIPE_BYTES, f"{f.stat().st_size} bytes"
        except (AssertionError, KeyError, ValueError, SystemExit, FileNotFoundError) as e:
            bad.append(f"{name}: {e}")
    print("\n".join(bad) or f"recipes ok: {len(list(RECIPES.rglob('*.json')))}")
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("try")
    t.add_argument("weights")
    t.add_argument("--model", required=True)
    t.add_argument("--engine", required=True)
    t.add_argument("--card", required=True)
    t.add_argument("--set", action="append", default=[])
    t.add_argument("--on", default="vast", choices=["vast", "runpod", "endpoint"])
    t.add_argument("--endpoint")
    t.add_argument("--gpu", help="provider GPU name (default from the card) or, with --on endpoint, the GPU the owner ran it on")
    t.add_argument("--proxy-gpu", help="run on this twin card, memory capped to the card's")
    t.add_argument("--proxy-vram", type=int, default=16)
    t.add_argument("--min-cuda", type=float)
    t.add_argument("--max-price", type=float, default=1.5)
    t.add_argument("--disk", type=int, default=60)
    t.add_argument("--dry-run", action="store_true")
    sub.add_parser("render").add_argument("recipe")
    sub.add_parser("check")
    a = ap.parse_args()
    return {"try": cmd_try, "render": cmd_render, "check": cmd_check}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
