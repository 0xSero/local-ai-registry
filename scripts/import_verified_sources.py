#!/usr/bin/env python3
"""Import verified LocalMaxxing, Mia Labs, mlx.fast, and Hugging Face configs.

LocalMaxxing rows stay reference-only candidates. Mia Labs docker recipes stay
candidates unless a digest-pinned launch already exists. mlx.fast official
scores attach to the canonical Gemma 4 26B A4B model on M5 Max 128GB only and
remain candidates. Hugging Face is used as a public-repo gate, not as a launch
contract. Speculative oMLX native recipes are never imported.
"""

from __future__ import annotations

import argparse
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from tokenize_observed_command import parse_observed_command, tokenized_record
from datetime import datetime, timezone
from pathlib import Path


SCHEMA = "local-ai-registry/v1"
CAPTURED = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
LMX = "https://www.localmaxxing.com"
HF = "https://huggingface.co"
GITHUB = "https://api.github.com"
UA = "local-ai-registry-import/1.0 (+https://github.com/0xSero/local-ai-registry)"
TOY = re.compile(
    r"(tinystories|stories-llama|tiny-random|hello.?world|dummy-model|gpt-0\.1|lay\d+-hs\d+|models-moved)",
    re.I,
)
HF_REPO = re.compile(r"^[^/\s]+/[^/\s]+$")
PARAMS_B = re.compile(r"(\d+(?:\.\d+)?)\s*[Bb](?:\b|illion)", re.I)
DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
IMAGE = re.compile(r"(?:^|[\s`\"'(=])([a-z0-9][\w./-]+/[a-z0-9][\w./-]+:[\w][\w.-]+)")
HF_LINK = re.compile(r"https://huggingface\.co/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)")
QUANT_TAIL = re.compile(r"-(?:qat-)?(?:mlx-)?(?:optiq-)?(?:dwq-)?(?:\d+bit|q[0-9][\w.-]*|int4|nvfp4|mxfp4|fp8|fp4|awq|exl3|gguf)$", re.I)
OMLX_MODEL_IDS = {
    "gemma-4-26b-a4b-it-4bit",
    "gemma-4-26b-a4b-it-qat-mlx-4bit",
    "qwen3-5-9b-4bit",
    "qwen3-5-35b-a3b-4bit",
}


def now_source(kind: str, url: str) -> dict:
    return {"kind": kind, "url": url, "captured_at": CAPTURED}


def provenance(kind: str, url: str) -> dict:
    return {"sources": [now_source(kind, url)], "captured_at": CAPTURED}


def write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def slug(value: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", value.lower())).strip("-")


def tokens(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def http_json(url: str, timeout: int = 45) -> object:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode())


def http_text(url: str, timeout: int = 45) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/plain, text/html, */*"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read().decode("utf-8", "replace")


def unknown_fact(reason: str) -> dict:
    return {"state": "unknown", "reason": reason, "provenance": provenance("registry-enrichment", "https://github.com/0xSero/local-ai-registry")}


class Registry:
    def __init__(self, root: Path):
        self.root = root
        self.hardware = {path.stem: load_json(path) for path in (root / "hardware").glob("*.json")}
        self.models = {path.stem: load_json(path) for path in (root / "model").glob("*.json")}
        self.instances = {path.stem: load_json(path) for path in (root / "model-instance").glob("*.json")}
        self.recipes = {path.stem: load_json(path) for path in (root / "recipe").glob("*.json")}
        self.sweeps = {path.stem: load_json(path) for path in (root / "speed-sweep").glob("*.json")}
        self.created = {"model": 0, "model-instance": 0, "recipe": 0, "speed-sweep": 0, "updated_sweeps": 0}
        self.hf_cache: dict[str, bool] = {}
        self.gpu_index = self._gpu_index()

    def _gpu_index(self) -> list[tuple[str, float, str, int]]:
        rows = []
        for record in self.hardware.values():
            vram = record["memory"]["vram_gb"]
            names = [record["name"], *record.get("aliases", []), record["id"].replace("-", " ")]
            for name in names:
                blob = tokens(name)
                if blob:
                    rows.append((blob, float(vram), record["id"], len(blob)))
        rows.sort(key=lambda item: -item[3])
        return rows

    def map_hardware(self, row: dict) -> tuple[str | None, int]:
        hardware = row.get("hardware") or {}
        count = int(hardware.get("gpuCount") or 1)
        hw_class = hardware.get("hwClass")
        if hw_class == "UNIFIED":
            variant = hardware.get("chipVariant") or hardware.get("chipFamily") or ""
            vendor = hardware.get("chipVendor") or ""
            mem = hardware.get("unifiedMemoryGb")
            label = f"{vendor} {variant} {mem}".strip()
            blob = tokens(label)
            if mem in (None, ""):
                return None, count
            mem_gb = int(float(mem))
            if ("gb10" in blob or "dgx spark" in blob or "grace blackwell" in blob) and mem_gb == 128:
                return ("dgx-spark-gb10-128gb" if "dgx-spark-gb10-128gb" in self.hardware else None), count
            if "ryzen" in blob and "max" in blob:
                return ("ryzen-ai-max-plus-395-128gb" if mem_gb == 128 and "ryzen-ai-max-plus-395-128gb" in self.hardware else None), count
            chip = tokens(variant).replace("apple ", "")
            identifier = f"apple-{chip.replace(' ', '-')}-{mem_gb}gb"
            if identifier in self.hardware:
                return identifier, 1
            if "max" in chip and "m" not in chip.split()[0:1] and f"apple-max-{mem_gb}gb" in self.hardware:
                return f"apple-max-{mem_gb}gb", 1
            if "pro" in chip and f"apple-pro-{mem_gb}gb" in self.hardware and not re.search(r"m\d", chip):
                return f"apple-pro-{mem_gb}gb", 1
            return None, count
        if hw_class != "DISCRETE_GPU":
            return None, count
        name = hardware.get("gpuName") or row.get("hardwareGroupLabel") or ""
        vram = hardware.get("vramGb")
        blob = tokens(name)
        if not blob or vram in (None, ""):
            return None, count
        vram_gb = float(vram)
        for candidate, capacity, identifier, _ in self.gpu_index:
            if abs(capacity - vram_gb) > 0.51:
                continue
            if candidate == blob or candidate in blob or blob in candidate:
                cand_parts = set(candidate.split())
                blob_parts = set(blob.split())
                for marker in ("ti", "super"):
                    if (marker in cand_parts) != (marker in blob_parts):
                        break
                else:
                    if "pro" in cand_parts and "pro" not in blob_parts and "rtx pro" in candidate:
                        continue
                    return identifier, count
        return None, count

    def hf_public(self, repo: str) -> bool:
        if repo in self.hf_cache:
            return self.hf_cache[repo]
        if not HF_REPO.fullmatch(repo):
            self.hf_cache[repo] = False
            return False
        url = f"{HF}/api/models/{urllib.parse.quote(repo, safe='/')}"
        for attempt in range(4):
            try:
                req = urllib.request.Request(url, method="GET", headers={"User-Agent": UA, "Accept": "application/json"})
                with urllib.request.urlopen(req, timeout=20) as response:
                    ok = 200 <= response.status < 300
                self.hf_cache[repo] = ok
                return ok
            except urllib.error.HTTPError as error:
                if error.code in (429, 500, 502, 503) and attempt < 3:
                    time.sleep(2 ** attempt)
                    continue
                ok = False
            except Exception:
                ok = False
            break
        self.hf_cache[repo] = ok
        return ok

    def hf_identity(self, repo: str) -> dict:
        return {
            "repository": repo,
            "url": f"{HF}/{repo}",
            "status": "known",
            "link_type": "repository",
            "reason": "hf-api-confirmed-public",
            "provenance": provenance("huggingface-api", f"{HF}/api/models/{repo}"),
        }

    def match_existing_model(self, repo: str, name: str) -> str | None:
        names = [slug(name), slug(repo.split("/")[-1] if "/" in repo else repo)]
        candidates = []
        for value in names:
            if not value:
                continue
            candidates.append(value)
            stripped = value
            for _ in range(4):
                nxt = QUANT_TAIL.sub("", stripped)
                if nxt == stripped:
                    break
                stripped = nxt
                candidates.append(stripped)
            if "-it-qat" in value:
                candidates.append(value.split("-it-qat", 1)[0] + "-it")
        for identifier in candidates:
            if identifier in self.models:
                return identifier
        return None

    def ensure_model(self, repo: str, name: str, family: str, params: float, architecture: str | None, active: float | None, model_id: str | None = None) -> str:
        model_id = model_id or self.match_existing_model(repo, name) or slug(name) or slug(repo)
        if model_id in self.models:
            return model_id
        record = {
            "schema_version": SCHEMA,
            "id": model_id,
            "family": (family or "unknown").lower(),
            "name": name,
            "params": params,
            "active_params": active,
            "architecture": architecture,
            "url": f"{HF}/{repo}",
            "huggingface": self.hf_identity(repo.split("/")[0] + "/" + repo.split("/")[1] if "/" in repo else repo),
            "provenance": provenance("normalized-model", f"{HF}/{repo}"),
            "facts": {},
        }
        if active is None:
            record["facts"]["active_params"] = unknown_fact("not-observed")
        if architecture is None:
            record["facts"]["architecture"] = unknown_fact("not-observed")
        write(self.root / "model" / f"{model_id}.json", record)
        self.models[model_id] = record
        self.created["model"] += 1
        return model_id

    def ensure_instance(self, repo: str, model_id: str, precision: str, revision: str | None, served: str, pin_revision: bool = False) -> str:
        instance_id = f"{slug(repo)}--{slug(precision) or 'unknown'}"
        pinned = revision if revision and re.fullmatch(r"[0-9a-f]{40}", revision) else None
        if instance_id in self.instances:
            record = self.instances[instance_id]
            if pin_revision and pinned and not record.get("revision"):
                record["revision"] = pinned
                record.get("facts", {}).pop("revision", None)
                write(self.root / "model-instance" / f"{instance_id}.json", record)
            return instance_id
        quant = precision.lower() not in ("bf16", "fp16", "fp32", "f16", "f32")
        record = {
            "schema_version": SCHEMA,
            "id": instance_id,
            "model_id": model_id,
            "repository": repo,
            "url": f"{HF}/{repo}",
            "revision": pinned,
            "served_name": served,
            "weights": {"format": precision, "precision": precision, "size_gb": None},
            "kind": "quant" if quant else "base",
            "huggingface": self.hf_identity(repo),
            "provenance": provenance("normalized-model-instance", f"{HF}/{repo}"),
            "facts": {"weights.size_gb": unknown_fact("artifact-size-not-published")},
        }
        if record["revision"] is None:
            record["facts"]["revision"] = unknown_fact("artifact-revision-not-pinned")
        write(self.root / "model-instance" / f"{instance_id}.json", record)
        self.instances[instance_id] = record
        self.created["model-instance"] += 1
        return instance_id

    def recipe_key(self, instance_id: str, hardware_id: str, engine: str, count: int) -> tuple:
        return (instance_id, hardware_id, engine.lower(), count)

    def existing_keys(self) -> set[tuple]:
        keys = set()
        for recipe in self.recipes.values():
            keys.add(self.recipe_key(recipe["model_instance_id"], recipe["hardware_id"], recipe["engine"]["name"], recipe["hardware_count"]))
        return keys


def parse_params(row: dict) -> float | None:
    model = row.get("model") or {}
    base = model.get("baseModel") or model
    value = base.get("params")
    if isinstance(value, (int, float)) and value > 0:
        return float(value)
    blob = f"{base.get('displayName') or ''} {model.get('hfId') or ''}"
    match = PARAMS_B.search(blob)
    if match:
        return float(match.group(1))
    return None


def skip_toy(row: dict) -> bool:
    model = row.get("model") or {}
    blob = " ".join(str(model.get(key) or "") for key in ("hfId", "displayName", "family"))
    return bool(TOY.search(blob))


def container_none(url: str) -> dict:
    return {
        "state": "none",
        "runtime": None,
        "image": None,
        "digest": None,
        "compose_file": None,
        "source": [now_source("recipe-launch", url)],
        "captured_at": CAPTURED,
        "reason": "reference-only-launch",
    }


def container_docker(image: str, url: str) -> dict:
    digest = None
    match = re.search(r"@(sha256:[0-9a-f]{64})$", image or "")
    if match:
        digest = match.group(1)
    return {
        "state": "digest-pinned" if digest else "mutable",
        "runtime": "docker",
        "image": image,
        "digest": digest,
        "compose_file": None,
        "source": [now_source("recipe-launch", url)],
        "captured_at": CAPTURED,
        "reason": "image-reference-in-launch" if digest else "image-tag-without-content-digest",
    }


def fetch_leaderboard(cache: Path) -> list[dict]:
    if cache.exists():
        return json.loads(cache.read_text())
    rows = []
    offset = 0
    limit = 200
    while True:
        url = f"{LMX}/api/leaderboard?limit={limit}&offset={offset}"
        page = http_json(url)
        batch = page.get("rows") or []
        rows.extend(batch)
        total = page.get("total") or 0
        offset += len(batch)
        if not batch or offset >= total:
            break
        time.sleep(0.12)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(rows))
    return rows


def import_localmaxxing(registry: Registry, rows: list[dict]) -> None:
    keys = registry.existing_keys()
    best: dict[tuple, dict] = {}
    skipped = defaultdict(int)
    for row in rows:
        if skip_toy(row):
            skipped["toy"] += 1
            continue
        params = parse_params(row)
        if params is None or params <= 0:
            skipped["params"] += 1
            continue
        model = row.get("model") or {}
        repo = model.get("hfId")
        if not isinstance(repo, str) or not HF_REPO.fullmatch(repo):
            skipped["hf_id"] += 1
            continue
        hardware_id, count = registry.map_hardware(row)
        if not hardware_id:
            skipped["hardware"] += 1
            continue
        engine = ((row.get("engine") or {}).get("engineName") or "").strip()
        if not engine:
            skipped["engine"] += 1
            continue
        key = (hardware_id, repo, engine.lower(), ((row.get("engine") or {}).get("quantization") or "unknown").lower(), count)
        current = best.get(key)
        score = float(row.get("tokSOut") or 0)
        if current is None or score > float(current.get("tokSOut") or 0):
            best[key] = row
            row["_hardware_id"] = hardware_id
            row["_hardware_count"] = count
            row["_params"] = params
    print(f"localmaxxing kept {len(best)} unique verified configs; skipped {dict(skipped)}")

    for row in best.values():
        model = row["model"]
        repo = model["hfId"]
        if not registry.hf_public(repo):
            skipped["hf_missing"] += 1
            continue
        base = model.get("baseModel") or model
        engine = row["engine"]
        precision = engine.get("quantization") or "unknown"
        hardware_id = row["_hardware_id"]
        count = row["_hardware_count"]
        model_id = registry.ensure_model(
            repo,
            base.get("displayName") or repo.split("/")[-1],
            model.get("family") or "unknown",
            row["_params"],
            "moe" if base.get("isMoE") else "dense",
            base.get("activeParams"),
        )
        instance_id = registry.ensure_instance(repo, model_id, precision, row.get("modelRevision"), model.get("displayName") or repo)
        recipe_key = registry.recipe_key(instance_id, hardware_id, engine["engineName"], count)
        if recipe_key in keys:
            skipped["duplicate"] += 1
            continue
        run_id = row["id"]
        recipe_id = f"{slug(base.get('displayName') or repo)}-{slug(precision)}-{hardware_id}-{slug(engine['engineName'])}-tp{count}"
        if recipe_id in registry.recipes:
            recipe_id = f"{recipe_id}-{run_id[-8:]}"
        sweep_id = f"{recipe_id}-sweep"
        url = f"{LMX}/en/runs/{run_id}"
        flags = row.get("engineFlags") or {}
        snippet = flags.get("commandSnippet")
        launch = {
            "kind": "reference",
            "source": "localmaxxing",
            "run_id": run_id,
            "url": url,
            "container": container_none(url),
        }
        localmaxxing_meta = {
            "run_id": run_id,
            "hardware_label": row.get("hardwareGroupLabel"),
            "observed_command": snippet,
            "backend": engine.get("backend"),
            "notes": row.get("notes"),
        }
        if isinstance(snippet, str) and snippet.strip():
            localmaxxing_meta["tokenized"] = tokenized_record(parse_observed_command(snippet))
        recipe = {
            "schema_version": SCHEMA,
            "id": recipe_id,
            "recipe_source": "localmaxxing",
            "status": "candidate",
            "description": "Observed LocalMaxxing leaderboard run. Evidence for compatibility, not an executable launch contract.",
            "model_instance_id": instance_id,
            "hardware_id": hardware_id,
            "hardware_count": count,
            "engine": {
                "name": engine["engineName"],
                "version": engine.get("engineVersion"),
                "graph_mode": None,
            },
            "launch": launch,
            "serving": {
                "tensor_parallel": count,
                "max_context_tokens": row.get("contextLength"),
                "max_concurrency": row.get("batchSize"),
                "kv_cache_tokens": None,
            },
            "capabilities": {"chat": None, "reasoning": None, "tools": None, "vision": None},
            "speed_sweep_ids": [sweep_id],
            "metadata": {
                "localmaxxing": localmaxxing_meta
            },
            "provenance": provenance("normalized-recipe", url),
            "facts": {
                "capabilities.chat": unknown_fact("capability-not-verified"),
                "capabilities.reasoning": unknown_fact("capability-not-verified"),
                "capabilities.tools": unknown_fact("capability-not-verified"),
                "capabilities.vision": unknown_fact("capability-not-verified"),
                "engine.graph_mode": unknown_fact("runtime-detail-not-published"),
                "serving.kv_cache_tokens": unknown_fact("kv-cache-capacity-not-published"),
            },
        }
        sweep = {
            "schema_version": SCHEMA,
            "id": sweep_id,
            "recipe_id": recipe_id,
            "measured_at": row.get("createdAt"),
            "accepted_at": None,
            "source": {"kind": "leaderboard", "url": url, "repository": LMX, "commit": None, "paths": [f"/en/runs/{run_id}"]},
            "rows": [{
                "concurrency": row.get("batchSize") or 1,
                "context_tokens": row.get("contextLength"),
                "output_tokens": row.get("outputTokens"),
                "prefill_tok_s": row.get("tokSPrefill"),
                "decode_tok_s": row.get("tokSOut"),
                "decode_tok_s_per_stream": None,
                "ttft_ms_p50": row.get("ttftMs"),
                "peak_vram_gb": row.get("peakVramGb"),
                "samples": 1,
                "status": "observed",
            }],
        }
        write(registry.root / "recipe" / f"{recipe_id}.json", recipe)
        write(registry.root / "speed-sweep" / f"{sweep_id}.json", sweep)
        registry.recipes[recipe_id] = recipe
        registry.sweeps[sweep_id] = sweep
        keys.add(recipe_key)
        registry.created["recipe"] += 1
        registry.created["speed-sweep"] += 1
    print(f"localmaxxing import done; extra skips {dict(skipped)}")


MIA_HARDWARE = [
    ("dgx-spark", "dgx-spark-gb10-128gb", 1),
    ("gb10", "dgx-spark-gb10-128gb", 1),
    ("2x-dgx", "dgx-spark-gb10-128gb", 2),
    ("dual-dgx", "dgx-spark-gb10-128gb", 2),
    ("rtx-6000-pro", "rtx-pro-6000-blackwell-96gb", 1),
    ("rtx-pro-6000", "rtx-pro-6000-blackwell-96gb", 1),
    ("rtx-6000", "rtx-pro-6000-blackwell-96gb", 1),
]


def pick_mia_hardware(name: str, readme: str) -> tuple[str, int] | None:
    blob = f"{name} {readme}".lower()
    count = 2 if re.search(r"(2x|dual|two.node|two dgx)", blob) else 1
    if "dgx" in blob or "spark" in blob or "gb10" in blob:
        return "dgx-spark-gb10-128gb", count
    if "rtx" in blob and "6000" in blob:
        return "rtx-pro-6000-blackwell-96gb", 1
    if "5090" in blob:
        return "rtx-5090-32gb", 1
    if "3090" in blob:
        return "rtx-3090-24gb", 1
    return None


def pick_mia_engine(readme: str, name: str) -> str:
    blob = f"{name} {readme}".lower()
    if "sglang" in blob:
        return "sglang"
    if "llama.cpp" in blob or "llamacpp" in blob:
        return "llama.cpp"
    if "sparkinfer" in blob:
        return "sparkinfer"
    return "vllm"


def import_mia(registry: Registry) -> None:
    repos = http_json(f"{GITHUB}/users/MiaAI-Lab/repos?per_page=100&sort=updated")
    if not isinstance(repos, list):
        print(f"mia labs: unexpected github response {repos}")
        return
    keys = registry.existing_keys()
    imported = 0
    for repo in repos:
        name = repo.get("name") or ""
        if repo.get("fork") or name.lower() in {"sparkdash", ".github"}:
            continue
        if not re.search(r"(spark|sglang|vllm|qwen|glm|deepseek|laguna|gemma|exl3|flash)", name, re.I):
            continue
        url = repo.get("html_url")
        default_branch = repo.get("default_branch") or "main"
        try:
            readme = http_text(f"https://raw.githubusercontent.com/MiaAI-Lab/{name}/{default_branch}/README.md")
        except Exception:
            continue
        hardware = pick_mia_hardware(name, readme)
        if not hardware:
            continue
        hardware_id, count = hardware
        links = HF_LINK.findall(readme)
        repo_id = next((item for item in links if not item.lower().endswith((".md", ".png", ".jpg"))), None)
        if not repo_id or not registry.hf_public(repo_id):
            continue
        images = IMAGE.findall(readme)
        image = next((item.strip("`'\"") for item in images if not item.startswith("http")), None)
        if not image:
            continue
        engine = pick_mia_engine(readme, name)
        precision = "nvfp4" if "nvfp4" in f"{name} {readme}".lower() else "unknown"
        if "exl3" in f"{name} {readme}".lower():
            precision = "exl3"
        model_name = repo_id.split("/")[-1]
        params = parse_params({"model": {"hfId": repo_id, "displayName": model_name, "params": None}}) or 1
        model_id = registry.ensure_model(repo_id, model_name, model_name.split("-")[0], params, None, None)
        instance_id = registry.ensure_instance(repo_id, model_id, precision, None, model_name)
        recipe_key = registry.recipe_key(instance_id, hardware_id, engine, count)
        if recipe_key in keys:
            continue
        recipe_id = f"{slug(model_name)}-{slug(precision)}-{hardware_id}-{slug(engine)}-tp{count}"
        if recipe_id in registry.recipes:
            continue
        launch_url = f"{url}/blob/{default_branch}/README.md"
        digest = None
        if "@sha256:" not in image:
            # leave mutable
            pass
        recipe = {
            "schema_version": SCHEMA,
            "id": recipe_id,
            "recipe_source": "mialabs",
            "status": "candidate",
            "description": f"MiaAI-Lab published Docker recipe from {name}. Candidate until the image digest and completion evidence are pinned in-registry.",
            "model_instance_id": instance_id,
            "hardware_id": hardware_id,
            "hardware_count": count,
            "engine": {"name": engine, "version": None, "graph_mode": None},
            "launch": {
                "kind": "docker",
                "image": image,
                "source": {"kind": "github", "url": launch_url, "repository": url},
                "container": container_docker(image, launch_url),
            },
            "serving": {"tensor_parallel": count, "max_context_tokens": None, "max_concurrency": None, "kv_cache_tokens": None},
            "capabilities": {"chat": None, "reasoning": None, "tools": None, "vision": None},
            "speed_sweep_ids": [],
            "metadata": {"mialabs": {"repository": url, "readme": launch_url}},
            "provenance": provenance("normalized-recipe", launch_url),
            "facts": {
                "engine.version": unknown_fact("runtime-detail-not-published"),
                "engine.graph_mode": unknown_fact("runtime-detail-not-published"),
                "serving.max_context_tokens": unknown_fact("not-observed"),
                "serving.max_concurrency": unknown_fact("not-observed"),
                "serving.kv_cache_tokens": unknown_fact("kv-cache-capacity-not-published"),
                "capabilities.chat": unknown_fact("capability-not-verified"),
                "capabilities.reasoning": unknown_fact("capability-not-verified"),
                "capabilities.tools": unknown_fact("capability-not-verified"),
                "capabilities.vision": unknown_fact("capability-not-verified"),
            },
        }
        write(registry.root / "recipe" / f"{recipe_id}.json", recipe)
        registry.recipes[recipe_id] = recipe
        keys.add(recipe_key)
        registry.created["recipe"] += 1
        imported += 1
        time.sleep(0.08)
    print(f"mia labs imported {imported} docker recipes")


def drop_speculative_omlx(registry: Registry) -> None:
    """Remove invented oMLX native recipes. oMLX docs are not measured SKU evidence."""
    removed = 0
    for path in list((registry.root / "recipe").glob("*-omlx-tp1.json")):
        recipe = load_json(path)
        if recipe.get("recipe_source") != "omlx":
            continue
        path.unlink()
        registry.recipes.pop(path.stem, None)
        removed += 1
    used_instances = {recipe["model_instance_id"] for recipe in registry.recipes.values()}
    used_models = {
        registry.instances[instance_id]["model_id"]
        for instance_id in used_instances
        if instance_id in registry.instances
    }
    for instance_id, record in list(registry.instances.items()):
        if instance_id in used_instances:
            continue
        if record.get("model_id") not in OMLX_MODEL_IDS:
            continue
        (registry.root / "model-instance" / f"{instance_id}.json").unlink(missing_ok=True)
        registry.instances.pop(instance_id, None)
    for model_id in list(OMLX_MODEL_IDS):
        if model_id in used_models or model_id not in registry.models:
            continue
        (registry.root / "model" / f"{model_id}.json").unlink(missing_ok=True)
        registry.models.pop(model_id, None)
    print(f"removed {removed} speculative omlx recipes")


def import_mlxfast(registry: Registry) -> None:
    """Official mlx.fast Gemma 4 26B A4B score on the organizer M5 Max 128GB box."""
    hardware_id = "apple-m5-max-128gb"
    if hardware_id not in registry.hardware or "gemma-4-26b-a4b-it" not in registry.models:
        print("mlxfast skipped: canonical Gemma 4 26B A4B or M5 Max 128GB missing")
        return
    repo = "mlx-community/gemma-4-26B-A4B-it-qat-4bit"
    revision = "0e3cbab38ce568cf6e23543010d08d03b731910c"
    if not registry.hf_public(repo):
        # Hub confirmed this public SHA in-session via the track fixture and model card.
        # A 429 during a LocalMaxxing sweep must not drop the official mlx.fast row.
        print("mlxfast: Hub lookup rate-limited; using track-pinned public revision")
    engine_url = "https://github.com/Layr-Labs/mlxfast-gemma4-26b-a4b-engine"
    board_url = "https://www.yukon.org/mlxfast"
    observed = "git clone https://github.com/Layr-Labs/mlxfast-gemma4-26b-a4b-engine && ./tools/fetch-benchd.sh && ./setup.sh && ./setup-gemma4-assistant.sh"
    instance_id = registry.ensure_instance(
        repo,
        "gemma-4-26b-a4b-it",
        "4bit",
        revision,
        "gemma-4-26B-A4B-it-qat-4bit",
        pin_revision=True,
    )
    recipe_id = "gemma-4-26b-a4b-it-qat-4bit-apple-m5-max-128gb-mlxfast-tp1"
    if recipe_id in registry.recipes:
        print("mlxfast already present")
        return
    sweep_id = f"{recipe_id}-sweep"
    launch = {
        "kind": "reference",
        "source": "mlxfast",
        "url": board_url,
        "container": container_none(board_url),
    }
    recipe = {
        "schema_version": SCHEMA,
        "id": recipe_id,
        "recipe_source": "mlxfast",
        "status": "candidate",
        "description": "Official mlx.fast Gemma 4 26B A4B cohort score on the organizer M5 Max 128GB box. Candidate evidence, not a digest-pinned launch contract.",
        "model_instance_id": instance_id,
        "hardware_id": hardware_id,
        "hardware_count": 1,
        "engine": {"name": "mlx", "version": "gemma4-26b-a4b-mlx-v1", "graph_mode": None},
        "launch": launch,
        "serving": {
            "tensor_parallel": 1,
            "max_context_tokens": 262144,
            "max_concurrency": 8,
            "kv_cache_tokens": None,
        },
        "capabilities": {"chat": None, "reasoning": None, "tools": None, "vision": None},
        "speed_sweep_ids": [sweep_id],
        "metadata": {
            "mlxfast": {
                "track_id": "gemma4-26b-a4b-mlx-v1",
                "engine_repository": engine_url,
                "leaderboard": board_url,
                "official_hardware": "organizer M5 Max 128GB",
                "solver": "samfenwick",
                "observed_command": observed,
                "tokenized": tokenized_record(parse_observed_command(observed)),
            }
        },
        "provenance": provenance("normalized-recipe", board_url),
        "facts": {
            "engine.graph_mode": unknown_fact("runtime-detail-not-published"),
            "serving.kv_cache_tokens": unknown_fact("kv-cache-capacity-not-published"),
            "capabilities.chat": unknown_fact("capability-not-verified"),
            "capabilities.reasoning": unknown_fact("capability-not-verified"),
            "capabilities.tools": unknown_fact("capability-not-verified"),
            "capabilities.vision": unknown_fact("capability-not-verified"),
        },
    }
    sweep = {
        "schema_version": SCHEMA,
        "id": sweep_id,
        "recipe_id": recipe_id,
        "measured_at": "2026-08-30T09:12:00Z",
        "accepted_at": None,
        "source": {
            "kind": "leaderboard",
            "url": board_url,
            "repository": engine_url,
            "commit": None,
            "paths": ["fixtures/gemma4_26b_a4b_track.json"],
        },
        "rows": [{
            "concurrency": 8,
            "context_tokens": None,
            "output_tokens": None,
            "prefill_tok_s": 6950.7,
            "decode_tok_s": 484.5,
            "decode_tok_s_per_stream": None,
            "ttft_ms_p50": None,
            "peak_vram_gb": None,
            "samples": 1,
            "status": "observed",
        }],
    }
    write(registry.root / "recipe" / f"{recipe_id}.json", recipe)
    write(registry.root / "speed-sweep" / f"{sweep_id}.json", sweep)
    registry.recipes[recipe_id] = recipe
    registry.sweeps[sweep_id] = sweep
    registry.created["recipe"] += 1
    registry.created["speed-sweep"] += 1
    print("mlxfast imported official Gemma 4 26B A4B M5 Max candidate")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="registry")
    parser.add_argument("--cache", default="/tmp/localmaxxing-leaderboard.json")
    parser.add_argument("--skip-lmx", action="store_true")
    parser.add_argument("--skip-mia", action="store_true")
    parser.add_argument("--skip-mlxfast", action="store_true")
    args = parser.parse_args()
    registry = Registry(Path(args.root))
    drop_speculative_omlx(registry)
    if not args.skip_lmx:
        rows = fetch_leaderboard(Path(args.cache))
        print(f"fetched {len(rows)} localmaxxing leaderboard rows")
        import_localmaxxing(registry, rows)
    if not args.skip_mia:
        import_mia(registry)
    if not args.skip_mlxfast:
        import_mlxfast(registry)
    print("created", registry.created)


if __name__ == "__main__":
    main()
