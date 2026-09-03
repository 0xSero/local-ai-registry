#!/usr/bin/env python3

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import trust  # noqa: E402

from import_market_snapshot import (
    gpu_signature,
    listing_title_matches,
    listing_url_is_specific,
    product_name,
)
from tokenize_observed_command import REFERENCE_LAUNCH_FORBIDDEN


COLLECTIONS = ("hardware", "model", "model-instance", "recipe", "speed-sweep", "benchmark", "asset")
SCHEMA = "local-ai-registry/v1"
FORBIDDEN_LAUNCH = ("--enforce-eager", "disable-cuda-graph", "disable-prefill-cuda-graph")
HF_REPOSITORY = re.compile(r"^[^/\s]+/[^/\s]+$")
HF_URL = re.compile(r"^https://huggingface\.co/[^/]+/[^/]+/?$")
HF_SEARCH = re.compile(r"^https://huggingface\.co/models\?search=.+$")
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


def load_collection(root, name, errors):
    records = {}
    for path in sorted((root / name).glob("*.json")):
        try:
            record = json.loads(path.read_text())
        except json.JSONDecodeError as error:
            errors.append(f"{path}: invalid JSON: {error}")
            continue
        identifier = record.get("id")
        if identifier != path.stem:
            errors.append(f"{path}: id {identifier!r} does not match filename")
        if record.get("schema_version") != SCHEMA:
            errors.append(f"{path}: schema_version must be {SCHEMA}")
        if identifier in records:
            errors.append(f"{path}: duplicate id {identifier}")
        records[identifier] = record
    return records


def require_reference(record, field, collection, errors):
    identifier = record.get(field)
    if identifier not in collection:
        errors.append(f"{record.get('id')}: unresolved {field} {identifier!r}")


def valid_timestamp(value):
    if not isinstance(value, str):
        return False
    try:
        dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        return value.endswith("Z")
    except ValueError:
        return False


def validate_provenance(value, label, errors):
    if not isinstance(value, dict):
        errors.append(f"{label}: provenance must be an object")
        return
    if not value.get("sources"):
        errors.append(f"{label}: provenance has no sources")
    if not isinstance(value.get("sources"), list):
        errors.append(f"{label}: provenance sources must be a list")
        return
    for source in value.get("sources", []):
        if not isinstance(source, dict) or not source.get("kind") or not source.get("url"):
            errors.append(f"{label}: provenance source requires kind and url")
        elif not isinstance(source["url"], str) or not re.match(r"^[a-z][a-z0-9+.-]*:", source["url"]):
            errors.append(f"{label}: provenance source URL is malformed")
        elif "captured_at" in source and not valid_timestamp(source["captured_at"]):
            errors.append(f"{label}: provenance source captured_at must be RFC3339 UTC")
    if not valid_timestamp(value.get("captured_at")):
        errors.append(f"{label}: provenance captured_at must be RFC3339 UTC")


def validate_facts(record, errors):
    identifier = record.get("id")
    facts = record.get("facts")
    if not isinstance(facts, dict):
        errors.append(f"{identifier}: facts must be an object")
        return
    for path, fact in facts.items():
        label = f"{identifier}: facts.{path}"
        if not isinstance(fact, dict):
            errors.append(f"{label} must be an object")
            continue
        if fact.get("state") not in ("known", "unknown", "unavailable", "not_applicable"):
            errors.append(f"{label}: invalid state")
        reason = fact.get("reason")
        structured_reason = isinstance(reason, dict) and isinstance(reason.get("code"), str) and bool(reason.get("code")) and isinstance(reason.get("detail"), str) and bool(reason.get("detail"))
        if fact.get("state") != "known" and not ((isinstance(reason, str) and bool(reason)) or structured_reason):
            errors.append(f"{label}: missing reason")
        if "value" in fact:
            errors.append(f"{label}: facts must not duplicate the record value")
        if not path.startswith("audit."):
            target = record
            for part in path.split("."):
                if isinstance(target, dict) and part in target:
                    target = target[part]
                else:
                    errors.append(f"{label}: fact path does not resolve to a record field")
                    break
        validate_provenance(fact.get("provenance"), label, errors)


def validate_huggingface(record, errors):
    identifier = record.get("id")
    identity = record.get("huggingface")
    label = f"{identifier}: huggingface"
    if not isinstance(identity, dict):
        errors.append(f"{label} identity is missing")
        return
    status = identity.get("status")
    repository = identity.get("repository")
    url = identity.get("url")
    link_type = identity.get("link_type")
    if status not in ("known", "unknown", "unavailable"):
        errors.append(f"{label}: invalid status")
    identity_reason = identity.get("reason")
    identity_structured_reason = isinstance(identity_reason, dict) and isinstance(identity_reason.get("code"), str) and bool(identity_reason.get("code")) and isinstance(identity_reason.get("detail"), str) and bool(identity_reason.get("detail"))
    if not ((isinstance(identity_reason, str) and bool(identity_reason)) or identity_structured_reason):
        errors.append(f"{label}: missing reason")
    validate_provenance(identity.get("provenance"), label, errors)
    hf_sources = (identity.get("provenance") or {}).get("sources", []) if isinstance(identity.get("provenance"), dict) else []
    source_kinds = {s.get("kind") for s in hf_sources if isinstance(s, dict)}
    if link_type == "repository":
        if not isinstance(repository, str) or not HF_REPOSITORY.fullmatch(repository) or not isinstance(url, str) or not HF_URL.fullmatch(url):
            errors.append(f"{label}: repository link must contain a valid owner/repo and canonical URL")
        elif url.rstrip("/") != f"https://huggingface.co/{repository}":
            errors.append(f"{label}: URL does not match repository")
        if status == "known" and "huggingface-api" not in source_kinds:
            errors.append(f"{label}: known repository requires a Hugging Face API source")
    elif link_type == "search":
        if repository is not None or not isinstance(url, str) or not HF_SEARCH.fullmatch(url):
            errors.append(f"{label}: search link must have null repository and HF search URL")
    else:
        errors.append(f"{label}: invalid link_type")


def validate_tokenized_launch(recipe, errors):
    identifier = recipe.get("id")
    launch = recipe.get("launch") or {}
    launch_text = json.dumps(launch).lower()
    if "command_snippet" in launch_text:
        errors.append(f"{identifier}: launch contains a command snippet")
    arguments = launch.get("arguments")
    if arguments is not None:
        if not isinstance(arguments, list) or not all(isinstance(item, str) for item in arguments):
            errors.append(f"{identifier}: launch.arguments must be a string array")
    environment = launch.get("environment")
    if environment is not None:
        if not isinstance(environment, dict) or not all(
            isinstance(key, str) and isinstance(value, str) for key, value in environment.items()
        ):
            errors.append(f"{identifier}: launch.environment must be a string map")
    steps = launch.get("steps")
    if steps is not None:
        if not isinstance(steps, list) or not all(
            isinstance(step, list) and all(isinstance(token, str) for token in step) for step in steps
        ):
            errors.append(f"{identifier}: launch.steps must be an argv array list")
        elif any("&&" in token for step in steps for token in step):
            errors.append(f"{identifier}: launch.steps still contains a shell && chain")
    source = recipe.get("recipe_source")
    if launch.get("kind") == "reference" or source in ("localmaxxing", "mlxfast", "exo-postgres"):
        for field in REFERENCE_LAUNCH_FORBIDDEN:
            if field in launch:
                errors.append(f"{identifier}: reference launch must not carry contract field {field}")
        meta_key = "mlxfast" if source == "mlxfast" else "localmaxxing" if source == "localmaxxing" else None
        metadata = (recipe.get("metadata") or {}).get(meta_key) or {} if meta_key else {}
        tokenized = metadata.get("tokenized") if isinstance(metadata, dict) else None
        if tokenized is None:
            return
        if not isinstance(tokenized, dict) or tokenized.get("fidelity") not in ("faithful", "lossy"):
            errors.append(f"{identifier}: metadata tokenized fidelity must be faithful or lossy")
            return
        if tokenized.get("fidelity") == "lossy":
            if tokenized.get("arguments") or tokenized.get("steps"):
                errors.append(f"{identifier}: lossy tokenization must not publish argv")
            return
        observed_args = tokenized.get("arguments")
        observed_steps = tokenized.get("steps")
        if observed_args is not None and (
            not isinstance(observed_args, list) or not all(isinstance(item, str) for item in observed_args)
        ):
            errors.append(f"{identifier}: tokenized arguments must be a string array")
        if observed_steps is not None:
            if not isinstance(observed_steps, list) or not all(
                isinstance(step, list) and all(isinstance(token, str) for token in step) for step in observed_steps
            ):
                errors.append(f"{identifier}: tokenized steps must be an argv array list")
            elif any(step and step[0].startswith("-") for step in observed_steps):
                errors.append(f"{identifier}: tokenized step starts with a flag")
        blob = json.dumps({"arguments": observed_args, "steps": observed_steps})
        if "&&" in blob:
            errors.append(f"{identifier}: tokenized argv still contains a shell && chain")
        snippet = metadata.get("observed_command") if isinstance(metadata, dict) else None
        if (
            isinstance(snippet, str)
            and len(snippet.split()) > 1
            and isinstance(observed_args, list)
            and len(observed_args) == 1
            and not observed_steps
            and not tokenized.get("environment")
        ):
            errors.append(f"{identifier}: observed command collapsed to a single token")


def validate_container(recipe, errors):
    identifier = recipe.get("id")
    launch = recipe.get("launch", {})
    container = launch.get("container")
    label = f"{identifier}: launch.container"
    if not isinstance(container, dict):
        errors.append(f"{label} is missing")
        return
    state = container.get("state")
    if state not in ("digest-pinned", "mutable", "indirect", "none"):
        errors.append(f"{label}: invalid state")
    if not container.get("reason"):
        errors.append(f"{label}: missing reason")
    if not isinstance(container.get("source"), list) or not container.get("source"):
        errors.append(f"{label}: source is required")
    for source in container.get("source", []):
        if not isinstance(source, dict) or not source.get("kind") or not source.get("url"):
            errors.append(f"{label}: malformed source")
    if not valid_timestamp(container.get("captured_at")):
        errors.append(f"{label}: captured_at must be RFC3339 UTC")
    kind = launch.get("kind")
    if kind == "reference" and state != "none":
        errors.append(f"{identifier}: reference launch must have container state none")
    if kind == "docker":
        image = launch.get("image")
        if not image:
            errors.append(f"{identifier}: Docker launch has no image")
        if recipe.get("status") == "validated" and str(image).startswith("local/"):
            errors.append(f"{identifier}: validated Docker launch cannot use an unpullable local/ image")
        expected = "digest-pinned" if isinstance(image, str) and re.search(r"@sha256:[0-9a-f]{64}$", image) else "mutable"
        if state != expected:
            errors.append(f"{identifier}: Docker container state does not match image digest")
        if state == "digest-pinned" and (not isinstance(container.get("digest"), str) or not DIGEST.fullmatch(container["digest"])):
            errors.append(f"{identifier}: digest-pinned Docker launch has malformed digest")
        if state == "mutable" and container.get("digest") is not None:
            errors.append(f"{identifier}: mutable Docker launch cannot claim a digest")
    elif kind == "docker-compose":
        if not (launch.get("compose") or {}).get("file"):
            errors.append(f"{identifier}: compose launch has no compose file")
        if state not in ("indirect", "digest-pinned"):
            errors.append(f"{identifier}: compose launch has ambiguous container state")
        if container.get("compose_file") != (launch.get("compose") or {}).get("file"):
            errors.append(f"{identifier}: compose container provenance does not identify launch compose file")
    elif kind not in ("reference", "docker", "docker-compose") and state != "none":
        errors.append(f"{identifier}: non-container launch must have container state none")
    if state == "none" and any(container.get(field) is not None for field in ("runtime", "image", "digest", "compose_file")):
        errors.append(f"{identifier}: container state none must not carry runtime/image/digest/compose_file")


def validate_launch_assets(root, recipe, errors):
    identifier = recipe.get("id")
    launch = recipe.get("launch", {})
    if recipe.get("status") != "validated" or launch.get("kind") != "docker":
        return
    paths = [mount.get("source") for mount in launch.get("mounts", []) if isinstance(mount, dict)]
    for value in filter(None, paths):
        if value.startswith(("/", "~/", "${")):
            continue
        path = (root / value).resolve()
        if root.resolve() not in path.parents or not path.is_file():
            errors.append(f"{identifier}: launch asset is missing or outside registry: {value}")


def validate(root):
    errors = []
    data = {name: load_collection(root, name, errors) for name in COLLECTIONS}

    # Pure shape rules (required fields, types, ranges, URL formats) live in
    # registry/schema/*.schema.json and are enforced by ajv in `npm test`.
    # This validator keeps what schemas cannot express: referential integrity,
    # cross-field logic, the trust boundary, and index staleness.
    for record in data["hardware"].values():
        if "facts" in record:
            validate_facts(record, errors)
        availability = (record.get("commercial") or {}).get("availability")
        if availability is not None:
            if not isinstance(availability, dict) or availability.get("state") not in ("available", "unavailable", "unknown", "not_applicable"):
                errors.append(f"{record.get('id')}: commercial availability has invalid state")
            elif availability.get("state") in ("unknown", "not_applicable") and not availability.get("reason"):
                errors.append(f"{record.get('id')}: commercial availability requires a reason when not known")

    for record in data["model-instance"].values():
        require_reference(record, "model_id", data["model"], errors)
        validate_huggingface(record, errors)
        validate_provenance(record.get("provenance"), f"{record.get('id')}", errors)
        validate_facts(record, errors)

    for record in data["model"].values():
        validate_huggingface(record, errors)
        validate_provenance(record.get("provenance"), f"{record.get('id')}", errors)
        validate_facts(record, errors)
        params = record.get("params")
        if not isinstance(params, (int, float)) or params <= 0:
            errors.append(f"{record.get('id')}: model params must be positive")

    recommended_by_hardware = {}
    for recipe in data["recipe"].values():
        # status is derived, never asserted: scripts/trust.py is the single definition
        instance = data["model-instance"].get(recipe.get("model_instance_id"))
        sweeps = [data["speed-sweep"].get(s) for s in recipe.get("speed_sweep_ids") or []]
        derived = trust.derive_status(recipe, instance, sweeps)
        if recipe.get("status") != derived:
            why = "; ".join(trust.failures(recipe, instance, sweeps)) or "meets every criterion"
            errors.append(f"{recipe['id']}: status {recipe.get('status')!r} but derived {derived!r} ({why}); run scripts/trust.py --apply")
        if recipe.get("recommended"):
            why = trust.recommendable(recipe)
            if why:
                errors.append(f"{recipe['id']}: recommended but {why}")
            recommended_by_hardware.setdefault(recipe.get("hardware_id"), []).append(recipe["id"])
        require_reference(recipe, "model_instance_id", data["model-instance"], errors)
        require_reference(recipe, "hardware_id", data["hardware"], errors)
        validate_provenance(recipe.get("provenance"), f"{recipe.get('id')}", errors)
        validate_facts(recipe, errors)
        validate_container(recipe, errors)
        validate_launch_assets(root, recipe, errors)
        for asset_id in (recipe.get("launch") or {}).get("asset_ids", []):
            if asset_id not in data["asset"]:
                errors.append(f"{recipe['id']}: unresolved launch.asset_ids {asset_id!r}")
        for sweep_id in recipe.get("speed_sweep_ids", []):
            if sweep_id not in data["speed-sweep"]:
                errors.append(f"{recipe['id']}: unresolved speed_sweep_ids {sweep_id!r}")
        status = recipe.get("status")
        launch = recipe.get("launch", {})
        kind = launch.get("kind")
        if status not in ("candidate", "validated"):
            errors.append(f"{recipe['id']}: invalid status {status!r}")
        if recipe.get("recipe_source") in ("localmaxxing", "exo-postgres"):
            if status != "candidate" or kind != "reference":
                errors.append(f"{recipe['id']}: observed imports must be reference-only candidates")
        if recipe.get("recipe_source") == "mlxfast":
            if status != "candidate" or kind != "reference":
                errors.append(f"{recipe['id']}: mlx.fast imports must be reference-only candidates")
            if recipe.get("hardware_id") != "apple-m5-max-128gb":
                errors.append(f"{recipe['id']}: mlx.fast official scores map only to apple-m5-max-128gb")
        validate_tokenized_launch(recipe, errors)
        draft = recipe.get("draft_launch")
        if draft is not None:
            if status != "candidate":
                errors.append(f"{recipe['id']}: draft_launch is only allowed on candidates")
            if not re.search(r"@sha256:[0-9a-f]{64}$", str(draft.get("image", ""))):
                errors.append(f"{recipe['id']}: draft_launch image must be digest-pinned")
        if recipe.get("recipe_source") == "omlx":
            errors.append(f"{recipe['id']}: speculative oMLX recipes are outside the registry contract")
        if status == "validated":
            if kind == "docker":
                # materializability: a validated docker recipe must produce a complete command
                if not launch.get("entrypoint") and not launch.get("arguments"):
                    errors.append(f"{recipe['id']}: validated docker launch has neither entrypoint nor arguments")
                for port_field in ("host_port", "container_port"):
                    if not isinstance(launch.get(port_field), int):
                        errors.append(f"{recipe['id']}: validated docker launch missing {port_field}")
                if not launch.get("accelerator_backend"):
                    errors.append(f"{recipe['id']}: validated docker launch missing accelerator_backend")
                if (recipe.get("serving") or {}).get("max_context_tokens") is None:
                    errors.append(f"{recipe['id']}: validated recipe must state serving.max_context_tokens")
                for mount in launch.get("mounts", []):
                    if not isinstance(mount, dict) or not mount.get("source") or not mount.get("target"):
                        errors.append(f"{recipe['id']}: validated docker launch has a malformed mount")
            if kind == "reference":
                errors.append(f"{recipe['id']}: validated recipe cannot use a reference launch")
            instance = data["model-instance"].get(recipe.get("model_instance_id"), {})
            if not instance.get("revision"):
                errors.append(f"{recipe['id']}: validated recipe has an unpinned model revision")
            if not recipe.get("speed_sweep_ids"):
                errors.append(f"{recipe['id']}: validated recipe has no speed evidence")
            if kind == "docker" and not re.search(r"@sha256:[0-9a-f]{64}$", launch.get("image", "")):
                errors.append(f"{recipe['id']}: validated Docker launch has no image digest")
            if kind == "script" and not re.search(r"(?:^|/)[0-9a-f]{40}/", launch.get("script", {}).get("file", "")):
                errors.append(f"{recipe['id']}: validated script launch has no commit pin")
            launch_text = json.dumps(launch).lower()
            for forbidden in FORBIDDEN_LAUNCH:
                if forbidden in launch_text:
                    errors.append(f"{recipe['id']}: validated launch contains forbidden option {forbidden}")

    for hardware_id, ids in recommended_by_hardware.items():
        if len(ids) > 1:
            errors.append(f"{hardware_id}: more than one recommended recipe: {', '.join(sorted(ids))}")

    for sweep in data["speed-sweep"].values():
        require_reference(sweep, "recipe_id", data["recipe"], errors)
        if not sweep.get("rows"):
            errors.append(f"{sweep['id']}: speed sweep has no rows")
        for row in sweep.get("rows", []):
            for field in ("decode_tok_s", "prefill_tok_s", "ttft_ms_p50", "peak_vram_gb"):
                value = row.get(field)
                if value is not None and (not isinstance(value, (int, float)) or value < 0):
                    errors.append(f"{sweep['id']}: {field} must be non-negative or null")

    for benchmark in data.get("benchmark", {}).values():
        for row in benchmark.get("rows", []):
            model_id = row.get("model_id")
            if model_id is not None and model_id not in data["model"]:
                errors.append(f"{benchmark['id']}: row model_id {model_id!r} does not resolve to a model")
        if not benchmark.get("name"):
            errors.append(f"{benchmark['id']}: benchmark has no name")
        for row in benchmark.get("rows", []):
            score = row.get("score")
            if score is not None and (not isinstance(score, (int, float)) or score < 0):
                errors.append(f"{benchmark['id']}: score must be non-negative or null")

    prices = {}
    for path in sorted((root / "price").glob("*/*.json")):
        try:
            record = json.loads(path.read_text())
        except json.JSONDecodeError as error:
            errors.append(f"{path}: invalid JSON: {error}")
            continue
        identifier = record.get("id")
        if identifier in prices:
            errors.append(f"{path}: duplicate id {identifier}")
        prices[identifier] = record
        if not valid_timestamp(record.get("observed_at")):
            errors.append(f"{identifier}: observed_at must be RFC3339 UTC")
        currency = (record.get("region") or {}).get("currency")
        for hardware in record.get("hardware", []):
            if hardware.get("id") not in data["hardware"]:
                errors.append(f"{identifier}: unresolved hardware {hardware.get('id')!r}")
            if hardware.get("match_scope") not in ("exact", "family"):
                errors.append(f"{identifier}: invalid hardware match_scope")
        product_id = (record.get("product") or {}).get("id")
        scanner_owned_gpu = (
            isinstance((record.get("provenance") or {}).get("scanner"), str)
            and isinstance(product_id, str)
            and gpu_signature(product_name(product_id)) is not None
        )
        for observation in record.get("observations", []):
            if observation.get("currency") != currency:
                errors.append(f"{identifier}: observation currency does not match region")
            if not valid_timestamp(observation.get("observed_at")):
                errors.append(f"{identifier}: observation observed_at must be RFC3339 UTC")
            if scanner_owned_gpu and not listing_title_matches(
                product_id, observation.get("title") or ""
            ):
                errors.append(
                    f"{identifier}: observation title does not identify the exact GPU SKU"
                )
            if scanner_owned_gpu and not listing_url_is_specific(
                observation.get("url") or ""
            ):
                errors.append(
                    f"{identifier}: observation URL is not a product-specific retailer URL"
                )

    import hashlib
    for asset in data["asset"].values():
        blob = root / "asset" / str(asset.get("file"))
        if not blob.is_file():
            errors.append(f"{asset.get('id')}: asset blob {asset.get('file')} is missing")
        else:
            digest = hashlib.sha256(blob.read_bytes()).hexdigest()
            if digest != asset.get("sha256"):
                errors.append(f"{asset.get('id')}: blob sha256 {digest} does not match manifest")
            if blob.stat().st_size != asset.get("size_bytes"):
                errors.append(f"{asset.get('id')}: blob size does not match manifest")
    manifest_files = {asset.get("file") for asset in data["asset"].values()}
    for blob in sorted((root / "asset").iterdir()):
        if blob.suffix == ".json" or blob.name.startswith("."):
            continue
        if blob.name not in manifest_files:
            errors.append(f"asset/{blob.name}: blob has no manifest record")
    for name in ("hardware", "model", "model-instance", "recipe", "speed-sweep", "benchmark"):
        for stray in sorted((root / name).iterdir()):
            if stray.is_dir() or (stray.suffix != ".json" and not stray.name.startswith(".")):
                errors.append(f"{name}/{stray.name}: collections hold only <id>.json records; launch artifacts belong in asset/")

    expected_products = {}
    for record in prices.values():
        for hardware in record.get("hardware", []):
            expected_products.setdefault(hardware.get("id"), set()).add(record["product"]["id"])
    for record in data["hardware"].values():
        expected = sorted(expected_products.get(record.get("id"), set()))
        if record.get("products") != expected:
            errors.append(
                f"{record.get('id')}: products {record.get('products')} does not match price records {expected}"
            )

    index_path = root / "index" / "collections.json"
    try:
        index = json.loads(index_path.read_text())
    except (FileNotFoundError, json.JSONDecodeError) as error:
        errors.append(f"{index_path}: invalid or missing index: {error}")
        index = {}
    if index.get("schema_version") != SCHEMA:
        errors.append("index/collections.json: wrong schema_version")
    for name in COLLECTIONS:
        expected = sorted(identifier for identifier in data[name] if identifier)
        actual = index.get("collections", {}).get(name)
        if actual != expected:
            errors.append(f"index/collections.json: {name} collection is stale")
        count_key = name.replace("-", "_")
        if index.get("counts", {}).get(count_key) != len(expected):
            errors.append(f"index/collections.json: {count_key} count is stale")
    expected_prices = sorted(identifier for identifier in prices if identifier)
    if index.get("collections", {}).get("price") != expected_prices:
        errors.append("index/collections.json: price collection is stale")
    if index.get("counts", {}).get("price") != len(expected_prices):
        errors.append("index/collections.json: price count is stale")

    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    counts = " ".join(f"{name}={len(data[name])}" for name in COLLECTIONS) + f" price={len(prices)}"
    print(f"registry valid: {counts}")
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", default="registry")
    args = parser.parse_args()
    raise SystemExit(validate(Path(args.root)))


if __name__ == "__main__":
    main()
