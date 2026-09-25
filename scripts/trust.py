#!/usr/bin/env python3
"""The trust boundary as one function.

`status` on a recipe is not an opinion. It is derived from facts already in the
registry, so anyone can rerun this and get the same answer:

    validated  <=  every criterion below holds
    candidate  <=  anything else

Criteria (each returns a reason string when it fails):

  1. launch.kind is executable: docker, compose, script, host (FastFlowLM),
     or native (one Apple Silicon machine with Metal). Never reference.
  2. the model instance pins a full revision (a commit hash, not a branch).
  3. the launch pins its artifact: docker/compose image by @sha256 digest,
     script by a 40-hex commit in its path, host/flm by that same model revision,
     native by a source repository and full commit hash.
  4. at least one attached speed sweep is real acceptance evidence: either an
     `acceptance-run` recorded by accept_recipe.py / validate_rented.py, or a
     campaign sweep whose source repository is under EVIDENCE_ORG (our own campaign
     artifacts) pinned to a commit. Third-party repos and imported observations
     (LocalMaxxing, local.ai Postgres, mlx.fast) are compatibility evidence only.
  5. the launch never disables CUDA graphs or forces eager execution.
  6. a docker launch is materializable: entrypoint or arguments, host and
     container ports, accelerator backend, and a stated serving.max_context_tokens.

`recommended` additionally requires validated, hardware_count == 1, bridge
networking, no host IPC, and either docker or a host/flm launch (the plugin
gate refuses anything else).

    python3 scripts/trust.py            # report every recipe whose stored status disagrees
    python3 scripts/trust.py --apply    # rewrite status to the derived value
"""

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

REG = Path(__file__).resolve().parent.parent / "registry"
DIGEST = re.compile(r"@sha256:[0-9a-f]{64}$")
COMMIT_PIN = re.compile(r"(?:^|/)[0-9a-f]{40}/")
FULL_REVISION = re.compile(r"^[0-9a-f]{40}$")
FORBIDDEN_LAUNCH = ("--enforce-eager", "disable-cuda-graph", "disable-prefill-cuda-graph")
# Campaign artifacts we ran ourselves. A sweep pinned to a commit in a repo under this org is acceptance evidence.
EVIDENCE_ORG = "https://github.com/0xSero/"


def native_launch_fingerprint(recipe):
    """Bind acceptance to the executable contract, not its descriptive provenance."""
    launch = {key: value for key, value in recipe.get("launch", {}).items()
              if key not in ("container", "provenance")}
    contract = {"launch": launch, "engine": recipe.get("engine"), "serving": recipe.get("serving")}
    return hashlib.sha256(json.dumps(contract, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def native_asset_failures(recipe, assets):
    """Bind every declared native artifact to its checked registry manifest."""
    launch = recipe.get("launch") or {}
    identifiers = launch.get("asset_ids", [])
    pins = launch.get("asset_sha256", {})
    if (not isinstance(identifiers, list) or not all(isinstance(i, str) and i for i in identifiers)
            or len(set(identifiers)) != len(identifiers)):
        return ["native launch asset_ids must be a unique string array"]
    if not isinstance(pins, dict) or set(pins) != set(identifiers):
        return ["native launch asset_sha256 must pin exactly the declared asset_ids"]
    reasons = []
    files = set()
    for identifier in identifiers:
        pin = pins[identifier]
        if not isinstance(pin, str) or not re.fullmatch(r"[0-9a-f]{64}", pin):
            reasons.append(f"native asset {identifier} requires a full SHA256 pin")
        asset = (assets or {}).get(identifier)
        if not asset or asset.get("id") != identifier:
            reasons.append(f"native asset {identifier} has no matching manifest")
            continue
        filename = asset.get("file")
        if (not isinstance(filename, str) or not filename or filename in (".", "..")
                or Path(filename).name != filename):
            reasons.append(f"native asset {identifier} must have a blob filename inside registry/asset")
        else:
            files.add(f"registry/asset/{filename}")
        if asset.get("sha256") != pin:
            reasons.append(f"native asset {identifier} manifest differs from its launch SHA256 pin")
    arguments = launch.get("arguments")
    for argument in arguments if isinstance(arguments, list) else []:
        if isinstance(argument, str) and argument.startswith("registry/asset/") and argument not in files:
            reasons.append(f"native launch argument references an undeclared asset: {argument}")
    return reasons


def native_contract_failures(recipe, instance, hardware, assets=None):
    """Structural native requirements; acceptance checks the actual local machine."""
    launch = recipe.get("launch") or {}
    reasons = []
    repository = launch.get("source_repository")
    try:
        parsed = urlsplit(repository) if isinstance(repository, str) else None
        valid_repository = bool(parsed and parsed.scheme == "https" and parsed.hostname
                                and parsed.path.strip("/") and not parsed.username
                                and not parsed.password and not parsed.query and not parsed.fragment)
    except ValueError:
        valid_repository = False
    if not valid_repository:
        reasons.append("native launch missing HTTPS source_repository")
    if not FULL_REVISION.fullmatch(str(launch.get("source_commit") or "")):
        reasons.append("native launch source_commit is not a full commit hash")
    if not FULL_REVISION.fullmatch(str((instance or {}).get("revision") or "")):
        reasons.append("native model revision must be pinned before acceptance")
    if (not instance or instance.get("id") != recipe.get("model_instance_id")
            or not re.fullmatch(r"[^/\s]+/[^/\s]+", str(instance.get("repository") or ""))):
        reasons.append("native launch requires the matching model instance and its repository")
    arguments = launch.get("arguments")
    valid_argv = (isinstance(arguments, list) and bool(arguments)
                  and all(isinstance(arg, str) and "\0" not in arg and "\n" not in arg for arg in arguments)
                  and bool(arguments[0].strip()) and not arguments[0].startswith("-")
                  and not any(arg in ("&&", "||", ";", "|") for arg in arguments))
    if not valid_argv:
        reasons.append("native launch requires executable argv arguments")
    elif Path(arguments[0]).name in ("sh", "bash", "zsh", "dash", "fish") and "-c" in arguments[1:]:
        reasons.append("native launch must not use a shell command string")
    environment = launch.get("environment", {})
    if not isinstance(environment, dict) or not all(isinstance(k, str) and isinstance(v, str)
                                                   for k, v in environment.items()):
        reasons.append("native launch environment must be a string map")
    if launch.get("image"):
        reasons.append("native launch must not pin a docker image")
    if launch.get("accelerator_backend") != "metal":
        reasons.append("native launch requires metal accelerator_backend")
    port = launch.get("host_port")
    if type(port) is not int or not 1 <= port <= 65535:
        reasons.append("native launch requires a valid host_port")
    context = (recipe.get("serving") or {}).get("max_context_tokens")
    if type(context) is not int or context < 1:
        reasons.append("native serving.max_context_tokens must be a positive integer")
    if not (recipe.get("engine") or {}).get("name") or not (recipe.get("engine") or {}).get("version"):
        reasons.append("native launch requires engine name and version")
    if type(recipe.get("hardware_count")) is not int or recipe["hardware_count"] != 1:
        reasons.append("native launch requires exactly one Apple Silicon machine")
    if (not hardware or hardware.get("id") != recipe.get("hardware_id")
            or hardware.get("vendor") != "apple" or hardware.get("accelerator_backend") != "metal"
            or not re.fullmatch(r"apple-m[1-9][0-9]*(?:-(?:pro|max|ultra))?-[1-9][0-9]*gb(?:-[1-9][0-9]*c)?",
                                str(recipe.get("hardware_id") or ""))):
        reasons.append("native launch requires an exact Apple Silicon hardware record")
    reasons.extend(native_asset_failures(recipe, assets))
    return reasons


def is_native_acceptance_evidence(sweep, recipe, instance):
    if not is_acceptance_evidence(sweep):
        return False
    source = sweep.get("source") or {}
    launch = recipe.get("launch") or {}
    return (source.get("kind") == "acceptance-run" and sweep.get("recipe_id") == recipe.get("id")
            and source.get("repository") == launch.get("source_repository")
            and source.get("commit") == launch.get("source_commit")
            and source.get("hardware_id") == recipe.get("hardware_id")
            and source.get("model_instance_id") == recipe.get("model_instance_id")
            and source.get("model_repository") == (instance or {}).get("repository")
            and source.get("model_revision") == (instance or {}).get("revision")
            and isinstance(source.get("served_model_id"), str) and bool(source["served_model_id"])
            and source["served_model_id"] in ((instance or {}).get("repository"), (instance or {}).get("served_name"))
            and source.get("launch_sha256") == native_launch_fingerprint(recipe))


def load(collection, identifier):
    path = REG / collection / f"{identifier}.json"
    return json.loads(path.read_text()) if path.exists() else None


def is_acceptance_evidence(sweep):
    if not sweep or not sweep.get("accepted_at"):
        return False
    source = sweep.get("source") or {}
    if source.get("kind") == "acceptance-run":
        return True
    return bool(source.get("commit")) and str(source.get("repository") or "").startswith(EVIDENCE_ORG)


def failures(recipe, instance, sweeps, hardware=None, assets=None):
    """Every reason this recipe cannot be validated. Empty list means validated."""
    launch = recipe.get("launch") or {}
    kind = launch.get("kind")
    reasons = []

    if kind not in ("docker", "compose", "script", "host", "native"):
        reasons.append(f"launch kind {kind!r} is not executable")

    revision = (instance or {}).get("revision") or ""
    if not FULL_REVISION.match(str(revision)):
        reasons.append("model instance revision is not a full commit hash")

    if kind in ("docker", "compose") and not DIGEST.search(str(launch.get("image") or "")):
        reasons.append("image is not digest-pinned")
    if kind == "script" and not COMMIT_PIN.search(str((launch.get("script") or {}).get("file") or "")):
        reasons.append("script launch has no commit pin")
    if kind == "host":
        if (recipe.get("engine") or {}).get("name") != "flm":
            reasons.append("host launch must use the flm engine")
        if launch.get("image"):
            reasons.append("host launch must not pin a docker image")
        if not isinstance(launch.get("container_port"), int):
            reasons.append("host launch missing container_port")
        if launch.get("accelerator_backend") != "amd-npu":
            reasons.append("host launch missing amd-npu accelerator_backend")
        if (recipe.get("serving") or {}).get("max_context_tokens") is None:
            reasons.append("serving.max_context_tokens not stated")

    if kind == "native":
        reasons.extend(native_contract_failures(recipe, instance, hardware, assets))
        if not any(is_native_acceptance_evidence(s, recipe, instance) for s in sweeps):
            reasons.append("no native acceptance bound to this hardware, model revision, and launch")
    elif not any(is_acceptance_evidence(s) for s in sweeps):
        reasons.append("no acceptance-run sweep and no campaign sweep with a replayable repository + commit")

    text = json.dumps(launch).lower()
    for forbidden in FORBIDDEN_LAUNCH:
        if forbidden in text:
            reasons.append(f"launch contains forbidden option {forbidden}")

    if kind == "docker":
        if not launch.get("entrypoint") and not launch.get("arguments"):
            reasons.append("docker launch has neither entrypoint nor arguments")
        for port_field in ("host_port", "container_port"):
            if not isinstance(launch.get(port_field), int):
                reasons.append(f"docker launch missing {port_field}")
        if not launch.get("accelerator_backend"):
            reasons.append("docker launch missing accelerator_backend")
        if (recipe.get("serving") or {}).get("max_context_tokens") is None:
            reasons.append("serving.max_context_tokens not stated")
    return reasons


def derive_status(recipe, instance, sweeps, hardware=None, assets=None):
    return "validated" if not failures(recipe, instance, sweeps, hardware, assets) else "candidate"


def recommendable(recipe):
    """Why a recipe cannot carry `recommended`, or None."""
    if recipe.get("status") != "validated":
        return "not validated"
    kind = (recipe.get("launch") or {}).get("kind")
    engine = ((recipe.get("engine") or {}).get("name") or "")
    if kind == "host":
        if engine != "flm":
            return "host launch must use the flm engine"
    elif kind != "docker":
        return "not a docker or host/flm launch"
    if recipe.get("hardware_count", 1) != 1:
        return "not single-GPU"
    launch = recipe.get("launch") or {}
    if (launch.get("network_mode") or "bridge") != "bridge":
        return "not bridge networking"
    if launch.get("ipc") == "host":
        return "uses host IPC"
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="rewrite status in place")
    args = parser.parse_args()
    flips = []
    for path in sorted((REG / "recipe").glob("*.json")):
        recipe = json.loads(path.read_text())
        instance = load("model-instance", recipe.get("model_instance_id", ""))
        hardware = load("hardware", recipe.get("hardware_id", ""))
        asset_ids = (recipe.get("launch") or {}).get("asset_ids") or []
        assets = {i: load("asset", i) for i in asset_ids if isinstance(i, str)} if isinstance(asset_ids, list) else {}
        sweeps = [load("speed-sweep", s) for s in recipe.get("speed_sweep_ids") or []]
        derived = derive_status(recipe, instance, sweeps, hardware, assets)
        changed = recipe.get("status") != derived
        if changed:
            flips.append((recipe["id"], recipe.get("status"), derived, failures(recipe, instance, sweeps, hardware, assets)))
            recipe["status"] = derived
        if recipe.get("recommended") and recommendable(recipe):
            print(f"{recipe['id']}: dropping recommended ({recommendable(recipe)})")
            recipe.pop("recommended")
            changed = True
        if changed and args.apply:
            path.write_text(json.dumps(recipe, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    for identifier, stored, derived, reasons in flips:
        detail = "; ".join(reasons) if reasons else "meets every criterion"
        print(f"{identifier}: {stored} -> {derived} ({detail})")
    print(f"{len(flips)} recipe(s) disagree with the derived status", file=sys.stderr)
    return 0 if args.apply or not flips else 1


if __name__ == "__main__":
    raise SystemExit(main())
