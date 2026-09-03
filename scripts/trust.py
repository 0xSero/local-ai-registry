#!/usr/bin/env python3
"""The trust boundary as one function.

`status` on a recipe is not an opinion. It is derived from facts already in the
registry, so anyone can rerun this and get the same answer:

    validated  <=  every criterion below holds
    candidate  <=  anything else

Criteria (each returns a reason string when it fails):

  1. launch.kind is executable: docker, compose, or script. Never reference.
  2. the model instance pins a full revision (a commit hash, not a branch).
  3. the launch pins its artifact: docker/compose image by @sha256 digest,
     script by a 40-hex commit in its path.
  4. at least one attached speed sweep is real acceptance evidence: either an
     `acceptance-run` recorded by accept_recipe.py / validate_rented.py, or a
     campaign sweep whose source repository is under EVIDENCE_ORG (our own campaign
     artifacts) pinned to a commit. Third-party repos and imported observations
     (LocalMaxxing, local.ai Postgres, mlx.fast) are compatibility evidence only.
  5. the launch never disables CUDA graphs or forces eager execution.
  6. a docker launch is materializable: entrypoint or arguments, host and
     container ports, accelerator backend, and a stated serving.max_context_tokens.

`recommended` additionally requires validated, hardware_count == 1, docker, bridge
networking, and no host IPC (the plugin gate refuses anything else).

    python3 scripts/trust.py            # report every recipe whose stored status disagrees
    python3 scripts/trust.py --apply    # rewrite status to the derived value
"""

import argparse
import json
import re
import sys
from pathlib import Path

REG = Path(__file__).resolve().parent.parent / "registry"
DIGEST = re.compile(r"@sha256:[0-9a-f]{64}$")
COMMIT_PIN = re.compile(r"(?:^|/)[0-9a-f]{40}/")
FULL_REVISION = re.compile(r"^[0-9a-f]{40}$")
FORBIDDEN_LAUNCH = ("--enforce-eager", "disable-cuda-graph", "disable-prefill-cuda-graph")
# Campaign artifacts we ran ourselves. A sweep pinned to a commit in a repo under this org is acceptance evidence.
EVIDENCE_ORG = "https://github.com/0xSero/"


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


def failures(recipe, instance, sweeps):
    """Every reason this recipe cannot be validated. Empty list means validated."""
    launch = recipe.get("launch") or {}
    kind = launch.get("kind")
    reasons = []

    if kind not in ("docker", "compose", "script"):
        reasons.append(f"launch kind {kind!r} is not executable")

    revision = (instance or {}).get("revision") or ""
    if not FULL_REVISION.match(str(revision)):
        reasons.append("model instance revision is not a full commit hash")

    if kind in ("docker", "compose") and not DIGEST.search(str(launch.get("image") or "")):
        reasons.append("image is not digest-pinned")
    if kind == "script" and not COMMIT_PIN.search(str((launch.get("script") or {}).get("file") or "")):
        reasons.append("script launch has no commit pin")

    if not any(is_acceptance_evidence(s) for s in sweeps):
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


def derive_status(recipe, instance, sweeps):
    return "validated" if not failures(recipe, instance, sweeps) else "candidate"


def recommendable(recipe):
    """Why a recipe cannot carry `recommended`, or None."""
    if recipe.get("status") != "validated":
        return "not validated"
    if (recipe.get("launch") or {}).get("kind") != "docker":
        return "not a docker launch"
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
        sweeps = [load("speed-sweep", s) for s in recipe.get("speed_sweep_ids") or []]
        derived = derive_status(recipe, instance, sweeps)
        changed = recipe.get("status") != derived
        if changed:
            flips.append((recipe["id"], recipe.get("status"), derived, failures(recipe, instance, sweeps)))
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
