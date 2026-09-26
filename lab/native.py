"""Pinned native Apple engine profiles. No installation or execution on import."""
import hashlib
import json
import re
import shlex
import string


def digest(p):
    return hashlib.sha256(json.dumps(p, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def validate(p):
    if p.get("platform") != "darwin-arm64" or p.get("backend") != "metal":
        raise ValueError("native profile must target darwin-arm64/metal")
    if not re.fullmatch(r"[a-z0-9][a-z0-9.-]*", p["id"]):
        raise ValueError("invalid native profile id")
    if not re.fullmatch(r"3\.\d+\.\d+", p["runtime"]["python"]):
        raise ValueError("native Python version must be pinned")
    requirements = p["runtime"]["requirements"]
    if not requirements or not all(re.fullmatch(r"[A-Za-z0-9_.-]+==[A-Za-z0-9.+_-]+", r) for r in requirements):
        raise ValueError("native dependencies must use exact versions")
    if not p["args"] or not all(isinstance(a, str) and "\x00" not in a for a in p["args"]):
        raise ValueError("native arguments must be argv strings")
    for k, v in p["env"].items():
        if not re.fullmatch(r"[A-Z_][A-Z0-9_]*", k) or not isinstance(v, str):
            raise ValueError("invalid native environment")
    if p.get("defaults") or type(p["ctx"]) is not int or p["ctx"] <= 0:
        raise ValueError("native profiles currently have fixed positive context")
    if type(p["port"]) is not int or not 1 <= p["port"] <= 65535:
        raise ValueError("invalid native port")
    w = p["weights"]
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", w["repo"]) or not re.fullmatch(r"[0-9a-f]{40}", w["revision"]):
        raise ValueError("native weights must be commit-pinned")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", p["args"][0]):
        raise ValueError("native executable must be a virtualenv entry point")
    if p["engine"] == "mtplx":
        for flag, expected in (("--host", "127.0.0.1"), ("--port", str(p["port"])),
                               ("--context-window", str(p["ctx"])), ("--model-id", p["served_name"])):
            at = p["args"].index(flag) if flag in p["args"] else -1
            if p["args"].count(flag) != 1 or at + 1 >= len(p["args"]) or p["args"][at + 1] != expected:
                raise ValueError(f"native {flag} differs from the launch contract")


def render(p, recipe):
    validate(p)
    if recipe.get("set"):
        raise ValueError("native profile has no overridable settings; create a new pinned profile")
    w = p["weights"]
    if recipe["weights"] != f"{w['repo']}@{w['revision']}":
        raise ValueError("native weights differ from the pinned profile")
    root = f".local-ai/{p['id']}"
    model_dir = f"{root}/models/{w['repo'].split('/')[1]}-{w['revision'][:8]}"
    args = [string.Template(a).substitute(model_dir=model_dir) for a in p["args"]]
    venv = f"{root}/venv"
    lock = "\n".join(p["runtime"]["requirements"]) + "\n"
    q = shlex.quote
    steps = [
        {"title": "Install the pinned native runtime (macOS arm64)", "code":
         f"mkdir -p {q(root)}\ncat > {q(root + '/requirements.txt')} <<'REQUIREMENTS'\n{lock}REQUIREMENTS\n"
         f"uv venv --python {q(p['runtime']['python'])} {q(venv)}\n"
         f"uv pip install --python {q(venv + '/bin/python')} -r {q(root + '/requirements.txt')}"},
        {"title": "Download the pinned weights", "code":
         "HF_HUB_DISABLE_IMPLICIT_TOKEN=1 HF_HUB_DISABLE_TELEMETRY=1 "
         f"{q(venv + '/bin/hf')} download {q(w['repo'])} --revision {q(w['revision'])} --local-dir {q(model_dir)}"},
        {"title": "Start the local server", "code":
         "env " + " ".join(q(k + "=" + v) for k, v in sorted(p["env"].items())) + " "
         + q(venv + "/bin/" + args[0]) + " " + " ".join(q(a) for a in args[1:])},
    ]
    return {"kind": "native", "platform": p["platform"], "runtime": p["runtime"], "steps": steps,
            "image": None, "entrypoint": None, "shm": None, "config": None,
            "args": args, "env": p["env"], "weights": {**w, "at": model_dir},
            "ctx": p["ctx"], "seqs": 1, "vision": p["vision"], "backend": "metal", "cards": 1,
            "port": p["port"], "served_name": p["served_name"]}
