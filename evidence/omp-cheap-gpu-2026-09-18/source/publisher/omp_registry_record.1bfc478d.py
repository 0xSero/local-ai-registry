#!/usr/bin/env python3
"""Turn one campaign artifact directory into local-ai-registry records.

The campaign produces evidence; the registry consumes it. This reads the
artifacts of one run and writes:

  registry/asset/<asset-id>.yml + .json   the exact config that ran, with only
                                          the plugin's model mount path restored
  registry/speed-sweep/<recipe-id>-campaign.json
  registry/recipe/<recipe-id>.json        patched: draft_launch promoted to
                                          launch, capabilities and serving from
                                          the measured acceptance

It never invents a number: a value the artifacts do not contain is written as
null with the reason in `facts`, and the recipe is left for `make trust` to
classify.

    python3 scripts/omp_registry_record.py \
        --registry ~/local-registry/registry-cheapgpu \
        --campaign campaigns/omp-cheap-gpu-2026-09-18 \
        --slug rtx-3090-24gb-minicpm5-2b \
        --recipe sglang-minicpm5-gptq-rtx-3090-24gb-tp1 \
        --evidence-repo https://github.com/0xSero/local-ai-registry \
        --evidence-path evidence/rtx-3090-24gb-minicpm5-2b \
        --evidence-commit <an ALREADY-PUBLISHED, immutable commit on the PUBLIC mirror>

    --evidence-repo (REQUIRED) is the PUBLIC evidence mirror the published record
    cites; --evidence-commit MUST be a commit already pushed to that mirror (an
    immutable historical snapshot), NOT the moving private HEAD via $(git ...).
    The private campaign origin is retained separately in recipe.metadata.origin.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sweep_to_benchmark import recompute_from_details  # noqa: E402

EVIDENCE_REPO = "https://github.com/0xSero/inference-index"
NOW = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load(path: Path) -> dict:
    return json.loads(path.read_text())


# Ratified SGLang producer-chain source hashes (Main/Opus-approved): the exact
# installed files whose bytes prove cached_tokens is OMITTED iff count==0 and
# flag-gated (usage_processor._details_if_cached + calculate_response_usage). A
# run's witness must match THESE approved hashes, not self-declared arbitrary
# ones, for an omitted (None) cached_tokens to be read as a derived zero.
APPROVED_SGLANG_SOURCE_SHAS = {
    "detokenizer_manager.py": "ed520fec2ee3060c7945b283ee138b8e3c4a81bb2d0edef668e5cce5a12a4f6a",
    "io_struct.py": "ebe1d216c98d0918c39089832f872a225977ce53c244680c9bcee51dee70e9e6",
    "output_streamer.py": "67bd9278d0680c6a8b4ead37faa1970e2a5c200b676f62b73125a8461e3ea676",
    "schedule_batch.py": "170f847aba6701d8d876a98c5edb8a66f188f5bc12fc30973596d132fcbb8c72",
    "serving_completions.py": "2a847f393310f985341d3198eb395269afae311b4400ec395959608be78ee9b2",
    "tokenizer_manager.py": "bdfaa4f4f214515f2138a3a82e8215882735490dfa85c271d2c41830b682ad33",
    "usage_processor.py": "883c4c3ba95eb52fa57d5bf732d128063bac0b032f484776331220f61b7498a5",
}


def _utc(value):
    """Parse an ISO-8601 UTC string to a comparable datetime (None on failure).

    Timestamp comparisons MUST be on parsed instants, never lexical: a fractional
    "...07.6Z" vs a plain "...07Z" would misorder as strings.
    """
    if not isinstance(value, str):
        return None
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def cold_witness(artifacts: Path, manifest: dict) -> dict:
    """Deterministic OFFLINE derivation of the source-verified cold witness.

    Decodes an OMITTED cached_tokens (raw None) as a BOUND derived-zero only when
    every explicit witness holds, all pinned to the SAME run - never rewriting the
    raw arrays. Returns a verdict; the caller credits cold ONLY when bound and
    accepts ONLY when the cell is complete. Any missing/mismatch -> not bound.

      FLAG    observed enable_cache_report true in server_info AND the initial and
              final process captures (so the None omission means count==0, per the
              approved usage_processor).
      SOURCE  the seven required producer-chain files are re-hashed from the
              bundle and equal the APPROVED hashes, and source-shas.json declares
              the same approved values (not self-declared arbitrary ones).
      PROCESS witness/process-binding-final.json exists and its pod_id + sglang_pid
              + kernel_process_start_utc EQUAL the initial process-binding.json
              (single PID, no restart), its recorded_at is AFTER the manifest's
              final updated_at (still the same process at/after grid completion),
              and the manifest created_at is >= the kernel start (run inside the
              process lifetime).
    """
    wit = artifacts / "witness"
    if not wit.is_dir():
        return {"bound": False, "bundle": False, "reasons": ["no witness bundle"]}

    def _j(name):
        path = wit / name
        return json.loads(path.read_text()) if path.is_file() else None

    init = _j("process-binding.json") or {}
    final = _j("process-binding-final.json")
    server_info = _j("server_info_whitelist.json") or {}
    declared = _j("source-shas.json") or {}
    reasons = []
    if server_info.get("enable_cache_report") is not True:
        reasons.append("server_info enable_cache_report not true")
    if init.get("enable_cache_report") is not True:
        reasons.append("initial process-binding enable_cache_report not true")
    for name, approved in APPROVED_SGLANG_SOURCE_SHAS.items():
        path = wit / name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != approved:
            reasons.append(f"source file not approved: {name}")
        if declared.get(name) != approved:
            reasons.append(f"declared source sha not approved: {name}")
    if final is None:
        reasons.append("no process-binding-final.json (final continuity pending)")
    else:
        for key in ("pod_id", "sglang_pid", "kernel_process_start_utc"):
            if init.get(key) is None or init.get(key) != final.get(key):
                reasons.append(f"final process identity mismatch: {key}")
        if final.get("enable_cache_report") is not True:
            reasons.append("final enable_cache_report not true")
        updated = _utc((manifest or {}).get("updated_at"))
        frec = _utc(final.get("recorded_at"))
        if not (frec and updated and frec >= updated):
            reasons.append("final recorded_at not after grid completion")
    kstart = _utc(init.get("kernel_process_start_utc"))
    created = _utc((manifest or {}).get("created_at"))
    if not (kstart and created and created >= kstart):
        reasons.append("manifest created_at not >= kernel_process_start_utc")
    # BIND the witness to THIS run's grid: the initial capture records the grid
    # manifest created time, which must equal this manifest's created_at, so a
    # witness bundle COPIED from another run cannot promote this one.
    grid = _utc(init.get("grid_manifest_created_utc"))
    if not (grid and created and grid == created):
        reasons.append("witness grid_manifest_created_utc != this run manifest created_at")
    # Bind to the ACTUAL run pod from PROVIDER STATE (artifacts/calibration.json,
    # recorded by omp_calibrate from the pod state), not just witness-internal
    # identity: a witness COPIED with the same timestamps but a different real run
    # pod cannot promote. Missing authoritative pod id -> not bound.
    run_pod = None
    calibration_path = artifacts / "calibration.json"
    if calibration_path.is_file():
        try:
            run_pod = (json.loads(calibration_path.read_text()) or {}).get("pod_id")
        except (OSError, ValueError):
            run_pod = None
    if not run_pod:
        reasons.append("no authoritative run pod_id (artifacts/calibration.json)")
    else:
        if init.get("pod_id") != run_pod:
            reasons.append("witness pod_id != authoritative run pod_id (calibration.json)")
        if final is not None and final.get("pod_id") != run_pod:
            reasons.append("final witness pod_id != authoritative run pod_id")
    return {"bound": not reasons, "bundle": True, "reasons": reasons,
            "pid": init.get("sglang_pid"), "pod": init.get("pod_id")}

def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n")


def plugin_config(pod_config: str) -> str:
    """The config the registry ships: the pod's file with the plugin's mount."""
    lines = []
    for line in pod_config.splitlines():
        if line.startswith("  model_dir:"):
            lines.append("  model_dir: /workspace/models")
        elif line.startswith("  host:"):
            lines.append("  host: 0.0.0.0")
        elif line.startswith(("  allowed_origins:", "  log_live_status:")):
            continue
        else:
            lines.append(line)
    return "\n".join(lines).rstrip("\n") + "\n"


def measured_context(acceptance: dict, plan: dict) -> int:
    # The launch ceiling is the negotiated context; acceptance proves the model
    # serves at it. The sweep proves which concurrency reaches it.
    return int(plan["context_tokens"])

def engine_version_of(engine: dict) -> str | None:
    """The ACTUAL engine version from the run's engine.json, engine-agnostic.

    TabbyAPI records tabbyapi_version/commit; SGLang and vLLM record a plain
    version (from /get_server_info) and optionally a commit. A run without an
    engine.json, or one whose version the probe did not capture, yields None so
    the recipe keeps the candidate's own engine block rather than a wrong label.
    """
    if not engine:
        return None
    if "tabbyapi_version" in engine:
        commit = (engine.get("tabbyapi_commit") or "")[:8]
        return engine["tabbyapi_version"] + (f"+{commit}" if commit else "")
    version = engine.get("version") or engine.get("sglang_version") or engine.get("vllm_version")
    if not version:
        return None
    commit = (engine.get("commit") or engine.get("sglang_revision") or "")[:8]
    return f"{version}+{commit}" if commit else str(version)


def image_provenance(image: str) -> tuple[dict, dict]:
    """Container + provenance blocks DERIVED from the launch image reference.

    The provenance is the digest-pinned OCI package the candidate actually
    launched, never a hardcoded upstream URL that may not be the image that ran.
    Works for an owned image (ghcr.io/<owner>/<name>) and an upstream one alike.
    """
    reference, _, digest = image.partition("@")
    package = reference.split(":", 1)[0]  # strip any tag
    url = f"https://{package}" if "/" in package else image
    source = [{"captured_at": NOW, "kind": "oci-image", "url": url}]
    container = {
        "captured_at": NOW,
        "compose_file": None,
        "digest": digest,
        "image": image,
        "reason": "image-reference-in-launch",
        "runtime": "docker",
        "source": source,
        "state": "digest-pinned",
    }
    provenance = {"captured_at": NOW, "kind": "container-image", "sources": source}
    return provenance, container


def sweep_arms(artifacts: Path) -> list[tuple[Path, dict]]:
    """Every sweep arm in the artifact directory, in directory order.

    A run can need more than one arm: a first pass covers the contexts that fit
    the rental, a second measures a window the first could not reach. Each arm
    is a real manifest with its own protocol, and `metadata.measurements` keeps
    them separate rather than blending them into one implied protocol.
    """
    arms = []
    for manifest_path in sorted(artifacts.glob("sweep*/manifest.json")):
        arms.append((manifest_path.parent, load(manifest_path)))
    if not arms:
        raise SystemExit(f"no sweep manifest under {artifacts}")
    return arms


def _classify_v2(run: dict, fallback: dict, row: dict,
                 witness: dict | None = None) -> tuple[str, str | None]:
    """Truthful protocol-v2 status for one measured run.

    A completed run is "accepted" only when its cell survived every measured
    request (cell_complete) AND its cache scenario was verified as requested;
    otherwise it stays "candidate". A cold cell whose in-run evidence is
    unverified because cached_tokens was OMITTED (raw None) is credited cold ONLY
    when the deterministic source-verified-zero-omission witness is BOUND (see
    cold_witness) and accepted ONLY when the cell is complete; the raw arrays are
    never rewritten and the provenance marks the zero DERIVED, not reported.
    """
    stat = run.get("status")
    if stat in (None, "planned", "running", "interrupted"):
        return "not-run", None
    if stat == "measurement-invalid":
        return "measurement-invalid", None
    if stat != "completed":
        return "infra-invalid", None
    intent = run.get("scenario")
    verified = fallback.get("scenario")  # cold / warm / unverified / mixed
    row["cache_state"] = verified if verified in ("cold", "warm") else f"{intent}-unverified"
    row["cache_evidence"] = fallback.get("scenario_evidence")
    cell_complete = fallback.get("cell_complete")
    row["cell_complete"] = cell_complete
    row["survivor_request_count"] = fallback.get("survivor_request_count")
    row["expected_request_count"] = fallback.get("expected_request_count")
    if cell_complete is False:
        return "candidate", (
            "cell incomplete: %s of %s measured requests survived per-request validation"
            % (fallback.get("survivor_request_count"), fallback.get("expected_request_count"))
        )
    if verified != intent:
        # Cold whose in-run cache evidence is unverified because cached_tokens was
        # omitted (raw None). Credit cold ONLY on the bound deterministic witness.
        # Eligible ONLY when the cell's cached_tokens were ALL OMITTED (None): a
        # warm/mixed cell has OBSERVED positive counts and is never derived-cold.
        if intent == "cold" and witness and fallback.get("cache_all_omitted"):
            if witness.get("bound") and cell_complete is True:
                row["cache_state"] = "cold"
                row["cache_evidence"] = (
                    "source-verified-zero-omission (DERIVED from witness/; cached_tokens "
                    "omitted, not directly reported)"
                )
                return "accepted", None
            if witness.get("bundle"):
                row["cache_evidence"] = (
                    "witness-bundle:witness/ (source-verified-zero-omission NOT bound: "
                    + "; ".join(witness.get("reasons") or ["unverified"]) + ")"
                )
        return "candidate", (
            "cache scenario unverified: requested %s, evidence %s (%s)"
            % (intent, verified, fallback.get("scenario_evidence"))
        )
    # Accepted requires cell_complete IS True: unknown completeness (None) stays
    # candidate, never accepted on a fall-through.
    return ("accepted", None) if cell_complete is True else (
        "candidate", "cell completeness unknown")


def sweep_rows(sweep_dir: Path, manifest: dict, witness: dict | None = None) -> list[dict]:
    # §3.9b: the manifest's aggregated summary fields stay null when a sweep is
    # interrupted before its aggregation pass, but the real per-request numbers
    # survive in sweep/raw/*.jsonl. Recompute from those detail files and use the
    # recomputed value wherever the summary field is null, so an interrupted run
    # yields honest partial rows instead of a wall of nulls.
    recomputed = recompute_from_details(sweep_dir, manifest)
    if witness is None:
        witness = cold_witness(sweep_dir.parent, manifest)
    protocol_v2 = manifest.get("schema_version") == "inference-index/omp-bench-client-v1"
    rows = []
    for run in manifest["runs"]:
        stat = run.get("status")
        fallback = recomputed.get(run.get("id")) or {}
        decode = run.get("decode_tok_s_per_stream")
        ttft = run.get("ttft_ms_p50")
        prefill = run.get("prefill_tok_s")
        end_to_end = run.get("end_to_end_tok_s_per_stream")
        configured_samples = run.get("measurement_samples")
        samples = configured_samples
        used_fallback = False
        if decode is None and fallback:
            decode = fallback.get("decode_tok_s_per_stream")
            ttft = fallback.get("ttft_ms_p50")
            prefill = fallback.get("prefill_tok_s")
            end_to_end = fallback.get("end_to_end_tok_s_per_stream")
            samples = fallback.get("samples", samples)
            used_fallback = True
        row = {
            "concurrency": run.get("concurrency"),
            "context_tokens": run.get("prompt_tokens", 0) + run.get("measurement_output_tokens", 0),
            "total_context_tokens": run.get("total_context_tokens"),
            "decode_tok_s": run.get("decode_tok_s_aggregate") or fallback.get("decode_tok_s_aggregate"),
            "decode_tok_s_per_stream": decode,
            "end_to_end_tok_s_per_stream": end_to_end,
            "output_tokens": run.get("measurement_output_tokens"),
            "peak_vram_gb": run.get("peak_vram_gb"),
            "prefill_tok_s": prefill,
            # v2: the ACTUAL observed sample count (0 when never executed) - a
            # planned/not-run cell must not look like the configured repetitions;
            # legacy keeps its configured-count handling. Configured stays alongside.
            # v2: ACTUAL observed samples (>=1) or NULL when none were observed
            # (schema allows int>=1 or null; never 0 and never the configured count).
            "samples": (fallback.get("samples") if fallback else None) if protocol_v2
                       else (samples if samples is not None else 1),
            "configured_samples": configured_samples,
            "ttft_ms_p50": ttft,
            # Row provenance: the ORIGINAL run identity + its raw detail file and
            # artifact hash, so same-point (context, concurrency, scenario) sample
            # rows are each directly traceable to their own source run and replayable
            # by run_id. Exact source values; null (never fabricated) when absent.
            "run_id": run.get("id"),
            "detail_file": run.get("detail_file"),
            "artifact_sha256": run.get("artifact_sha256"),
        }
        if protocol_v2:
            status, candidate_reason = _classify_v2(run, fallback, row, witness)
            # Prefill on a warm/unverified/mixed cache is a CACHED-prefill artifact
            # (prompt already in KV cache -> near-zero prefill time inflates the rate
            # by orders of magnitude), NOT real uncached prompt processing. Null it
            # AFTER cache classification (the derived-cold witness binding is known
            # only here, not to the normalizer); TTFT, end-to-end and the raw detail
            # are retained unchanged - no raw mutation, no invented measurement.
            if row.get("prefill_tok_s") is not None and row.get("cache_state") != "cold":
                row["prefill_tok_s_null_reason"] = (
                    "cache_state=%s: prefill reflects a cached prompt (KV-cache hit), "
                    "not uncached prompt processing; nulled - TTFT and end-to-end retained"
                    % row.get("cache_state"))
                row["prefill_tok_s"] = None
        else:
            status = ("accepted" if stat == "completed"
                      else "not-run" if stat in (None, "planned", "running", "interrupted")
                      else "infra-invalid")
            candidate_reason = None
        row["status"] = status
        if used_fallback:
            # The detail-file recompute IS the protocol-v2 measurement path (§3.9)
            # for a protocol-v2 client manifest: the run carries no aggregate
            # because the per-request detail records ARE the measurement. For a
            # genuinely legacy manifest it is legacy data made legible.
            row["metrics_source"] = "recomputed-from-detail-files"
            row["bench"] = "protocol-v2" if protocol_v2 else "legacy-recovered"
        if status == "not-run":
            row["reason"] = "no accepted measurement (cell did not complete)"
            row["cause"] = "not_run"
        elif status == "measurement-invalid":
            causes = run.get("invalid_causes")
            if not causes and run.get("invalid_cause"):
                causes = [run["invalid_cause"]]
            row["reason"] = run.get("invalid_reason") or "per-request validation failed"
            row["cause"] = ",".join(causes) if causes else None
            row["failure_scope"] = run.get("failure_scope") or "measurement"
            row["survivor_count"] = run.get("survivor_count")
        elif status == "candidate" and candidate_reason:
            row["reason"] = candidate_reason
            row["cause"] = "cell_incomplete" if row.get("cell_complete") is False else "cache_unverified"
        elif status == "infra-invalid":
            row["reason"] = run.get("invalid_reason") or stat
            row["cause"] = run.get("invalid_cause")
        rows.append(row)
    rows.sort(key=lambda row: (row["context_tokens"], row["concurrency"]))
    return rows


def peak_vram_gb(telemetry: Path) -> float | None:
    """The highest `memory.used` the sampler saw while the sweep ran."""
    if not telemetry.exists():
        return None
    peak = 0.0
    for line in telemetry.read_text().splitlines():
        fields = [field.strip() for field in line.split(",")]
        if len(fields) < 3:
            continue
        try:
            peak = max(peak, float(fields[2]))
        except ValueError:
            continue
    return round(peak / 1024, 2) if peak else None


def mtp_acceptance(artifacts: Path) -> dict | None:
    """Server-reported speculative acceptance across every raw stream, every arm.

    §3.8, amended: the engine emits accepted/rejected SCORED counters, not a
    proposals counter, so `proposed` is null-with-reason (accepted+rejected is
    `scored`, not proposed — a model that drops proposals before scoring would
    otherwise report a flattering denominator). An acceptance rate is emitted only
    when scored > 0, computed within the streams that actually scored (proposed>0
    counts the same run); 0/0 is undefined and printed as such.
    """
    scored = accepted = rejected = streams = scoring_streams = 0
    for raw in sorted(artifacts.glob("sweep*/raw/*.jsonl")):
        for line in raw.read_text().splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            details = (payload.get("usage") or {}).get("completion_tokens_details") or {}
            if "accepted_prediction_tokens" not in details:
                continue
            streams += 1
            a = details.get("accepted_prediction_tokens") or 0
            r = details.get("rejected_prediction_tokens") or 0
            if a + r <= 0:
                continue  # this stream scored nothing; excluded from the rate
            scoring_streams += 1
            accepted += a
            rejected += r
            scored += a + r
    if not streams:
        return None
    result = {
        "proposed": None,
        "proposed_reason": (
            "engine emits accepted/rejected scored counters but no proposals "
            "counter; proposed undefined"
        ),
        "scored": scored,
        "accepted": accepted,
        "rejected": rejected,
        "measured_streams": streams,
        "scoring_streams": scoring_streams,
    }
    if scored <= 0:
        result["acceptance_rate"] = None
        result["acceptance_rate_reason"] = "no speculative tokens scored; acceptance undefined"
    else:
        result["acceptance_rate"] = round(accepted / scored, 4)
        result["acceptance_rate_source"] = "engine-reported (accepted/scored within scoring streams)"
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--campaign", type=Path, required=True)
    parser.add_argument("--slug", required=True)
    parser.add_argument("--recipe", required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--evidence-commit", required=True)
    parser.add_argument("--evidence-repo", required=True,
                        help="PUBLIC evidence mirror repository URL cited in the published "
                             "record; the private campaign origin is kept in metadata.origin")
    parser.add_argument("--evidence-path",
                        help="path to this run's evidence under the public mirror; defaults "
                             "to the campaign-relative artifacts path")
    parser.add_argument(
        "--asset",
        help="registry asset id to publish; omit for argv-configured engines, which "
             "carry their whole configuration in the launch arguments",
    )
    parser.add_argument(
        "--entrypoint",
        help="the published entrypoint of a config-file engine's image, verified from "
             "the image's own OCI config; required when that engine's config is baked",
    )
    parser.add_argument(
        "--arguments",
        help="JSON list of launch arguments for a config-file engine's image; "
             "empty when the image's entrypoint carries the whole command",
    )
    parser.add_argument("--attempt", type=int, default=1)
    args = parser.parse_args(argv)
    evidence_path = args.evidence_path or f"campaigns/{args.campaign.name}/artifacts/{args.slug}"

    registry = args.registry.resolve() / "registry"
    plan = load(args.plan)
    artifacts = args.campaign.resolve() / "artifacts" / (
        args.slug if args.attempt == 1 else f"{args.slug}-attempt{args.attempt}"
    )
    acceptance = load(artifacts / "acceptance.json") if (artifacts / "acceptance.json").exists() else {}
    probe = load(artifacts / "probe.json") if (artifacts / "probe.json").exists() else {}
    weights = load(artifacts / "weights.json") if (artifacts / "weights.json").exists() else {}
    recipe_path = registry / "recipe" / f"{args.recipe}.json"
    recipe = load(recipe_path)
    engine_path = artifacts / "engine.json"
    engine = load(engine_path) if engine_path.exists() else {}
    engine_version = engine_version_of(engine)

    # TabbyAPI is configured by a mounted YAML file. vLLM and SGLang take their
    # configuration as argv, so there is no asset to publish and the arguments the
    # candidate already records are the whole configuration.
    asset_id = args.asset
    argv_engine = not (plan.get("tabby_config") or (artifacts / "config.yml").exists())
    config_text = ""
    config_source_note = ""
    if not argv_engine:
        # A config-file engine (TabbyAPI) is configured by the YAML the image
        # ships. A SELF-SERVING deploy image bakes its own weights and loads
        # them by name, so the configuration the run served IS the image's own
        # config: it is published byte-identical, with NO mount rewrite and NO
        # forced /workspace/models mount. The old generic rewrite republished a
        # config that could DIFFER from the image actually tested, which is not
        # honest evidence; that route stays removed.
        if not asset_id:
            raise SystemExit(
                "--asset is required to publish a config-file engine's asset"
            )
        config_text = (artifacts / "config.yml").read_text()
        config_source_note = (
            "byte-identical to the configuration the run served, with no mount "
            "rewrite: the deploy image bakes its weights and loads them by name"
        )

    def normalise(text: str) -> str:
        keep = []
        for line in text.splitlines():
            if line.startswith(("  model_dir:", "  host:", "  allowed_origins:",
                                "  log_live_status:")):
                continue
            keep.append(line.strip())
        return "\n".join(keep)

    if argv_engine:
        shipped = None
    shipped = registry / "asset" / f"{asset_id}.yml" if not argv_engine else None
    if shipped is not None:
        if shipped.exists() and normalise(shipped.read_text()) != normalise(config_text):
            raise SystemExit(
                f"{shipped} does not match the configuration the run used; regenerate the "
                "candidate from this run's config before publishing"
            )
        shipped.write_text(config_text)
        write_json(registry / "asset" / f"{asset_id}.json", {
        "schema_version": "local-ai-registry/v1",
        "id": asset_id,
        "file": f"{asset_id}.yml",
        "filename": "config.yml",
        "media_type": "application/yaml",
        "purpose": (
            f"TabbyAPI server configuration for {plan['served_name']} at "
            f"{plan.get('context_tokens')} tokens with {plan.get('cache_mode')} cache, vision and "
            f"reasoning parsing enabled; {config_source_note}."
        ),
            "sha256": hashlib.sha256(config_text.encode()).hexdigest(),
            "size_bytes": len(config_text.encode()),
        })

    arms = sweep_arms(artifacts)
    # sweep_rows derives the deterministic source-verified-zero-omission cold
    # witness per arm from artifacts/<slug>/witness/ (cold_witness): raw arrays are
    # never rewritten and cold is credited only when the witness is bound + the
    # cell complete; absent/unbound bundle keeps cells cold-unverified/candidate.
    rows = [row for directory, manifest in arms for row in sweep_rows(directory, manifest)]
    accepted = [row for row in rows if row["status"] == "accepted"]
    def _expected_cells(protocol: dict) -> int:
        return (len(protocol.get("total_context_tokens") or [])
                * len(protocol.get("concurrencies") or [])
                * len(protocol.get("scenarios") or [])
                * (protocol.get("samples_per_scenario")
                   or protocol.get("samples_per_concurrency") or 1))
    expected_cells = sum(_expected_cells(manifest.get("protocol") or {}) for _, manifest in arms)
    sweep_id = f"{args.recipe}-campaign"
    # Truthful timestamps: prefer the acceptance probe time, else the sweep
    # manifest's own created_at (the sweep really ran); NEVER stamp NOW as if the
    # run were measured now. accepted_at stays null when no acceptance was captured.
    sweep_captured = next((m.get("created_at") for _, m in arms if m.get("created_at")), None)
    _acc_at = acceptance.get("captured_at")
    _measured_at = _acc_at or sweep_captured
    write_json(registry / "speed-sweep" / f"{sweep_id}.json", {
        "schema_version": "local-ai-registry/v1",
        "id": sweep_id,
        "recipe_id": args.recipe,
        "measured_at": _measured_at[:10] if _measured_at else None,
        "accepted_at": _acc_at[:10] if _acc_at else None,
        "source": {
            "kind": "campaign",
            "repository": args.evidence_repo,
            "commit": args.evidence_commit,
            "paths": [evidence_path],
            "url": f"{args.evidence_repo}/commit/{args.evidence_commit}",
        },
        "metrics": {
            "concurrency": max((row["concurrency"] for row in accepted), default=None),
            "inference_engine_version": engine_version,
            "latest_point_at": _acc_at or sweep_captured,
            "max_context_tokens": max((row["context_tokens"] for row in accepted), default=None),
            "peak_memory_bytes": (
                str(int(peak_vram_gb(artifacts / "telemetry.csv") * 1024 ** 3))
                if peak_vram_gb(artifacts / "telemetry.csv") else None
            ),
            # §3.3: the headline generation rate is the client end-to-end rate,
            # never the engine decode-only figure (publishing decode-only here
            # overstated the top window ~20x). Stays null until a run supplies it.
            "peak_generation_tps": max(
                (row["end_to_end_tok_s_per_stream"] for row in accepted
                 if row.get("end_to_end_tok_s_per_stream")),
                default=None,
            ),
            # §3.3: prompt-processing rate is real ONLY on COLD cells (uncached
            # prefill). A warm cell's prompt is already in KV cache, so its near-zero
            # prefill time inflates prefill_tok_s by orders of magnitude (the 3090
            # warm artifact was ~1.3M tok/s vs cold ~2-6k) - the same inflated
            # throughput PR62 nulled. Never the warm cached-prefill max; null if no
            # accepted cold cell supplies it.
            "peak_prompt_tps": max(
                (row["prefill_tok_s"] for row in accepted
                 if row["prefill_tok_s"] and row.get("cache_state") == "cold"),
                default=None,
            ),
            "point_count": len(accepted),
        },
        "rows": rows,
    })

    capabilities = {name: bool(value) for name, value in (acceptance.get("capabilities") or {}).items()}
    failures = set(acceptance.get("failed_probes") or [])
    for name in failures:
        capabilities[name] = False
    launch = {
        key: value
        for key, value in (recipe.get("draft_launch") or recipe.get("launch") or {}).items()
        if key != "synthesized"
    }
    launch["kind"] = "docker"
    if argv_engine:
        # The server argv is the configuration, so the candidate's arguments and
        # ports are already complete and there is no asset to bind.
        launch["asset_ids"] = []
        launch["container_port"] = int(plan["port"])
        launch["host_port"] = int(plan["port"])
    else:
        # The config-file engine's image is self-serving: it bakes its own
        # weights and its own config, so the launch binds the published asset as
        # the record of the configuration and needs NO model or config mount.
        # The container is the image the run ACTUALLY rented, taken from this
        # attempt's pod state, never the candidate's possibly-stale reference.
        pod_state_path = args.campaign.resolve() / "pod-state" / (
            f"{args.slug}.json" if args.attempt == 1
            else f"{args.slug}-attempt{args.attempt}.json"
        )
        if not pod_state_path.exists():
            raise SystemExit(
                f"{pod_state_path} is missing; the launch container cannot be "
                "attributed to the image the run rented"
            )
        rented = str((load(pod_state_path).get("pod") or {}).get("image") or "")
        if "@sha256:" not in rented:
            raise SystemExit(
                f"{pod_state_path} records no digest-pinned image; the launch "
                "container cannot be recorded"
            )
        launch["image"] = rented
        if not args.entrypoint:
            raise SystemExit(
                "--entrypoint is required for a config-file engine: the run's "
                "own launch command is the only served-command evidence"
            )
        launch["entrypoint"] = args.entrypoint
        launch["arguments"] = (
            json.loads(args.arguments) if args.arguments else []
        )
        if not isinstance(launch["arguments"], list):
            raise SystemExit("--arguments must be a JSON list")
        launch["asset_ids"] = [asset_id]
        # The config the run served is mounted over the image's baked copy at the
        # path the driver wrote it to; the weights stay baked in the image, so
        # there is NO model mount. The published asset is byte-identical to the
        # served file - no model_dir rewrite, no forced weights mount.
        launch["mounts"] = [{
            "read_only": True,
            "source": f"asset/{asset_id}.yml",
            "target": "/app/config.yml",
        }]
        launch["container_port"] = int(plan.get("port") or 5000)
        launch["host_port"] = int(plan.get("port") or 5000)
    launch["provenance"], launch["container"] = image_provenance(str(launch["image"]))
    if engine_version:
        recipe["engine"] = {**(recipe.get("engine") or {}), "version": engine_version}
    concurrency_label = "/".join(f"C{c}" for c in sorted({row["concurrency"] for row in accepted}))
    context_label = ", ".join(
        f"{c}" for c in sorted({row["context_tokens"] for row in accepted})
    ).replace(", 262144", " and 262144")
    engine_name = (recipe.get("engine") or {}).get("name") or plan.get("engine") or "the configured engine"
    feature_names = [name for name in ("reasoning", "tools", "vision") if capabilities.get(name)]
    feature_label = (", " + ", ".join(feature_names)) if feature_names else ""
    if accepted:
        measured = f", measured {concurrency_label} at {context_label} prompt tokens"
    else:
        measured = "; no accepted measurement yet (candidate)"
    recipe["description"] = (
        f"{plan['served_name']} on one {plan['hardware_id']} via {engine_name}"
        f"{feature_label} at the model's {plan['context_tokens']}-token window{measured}"
    )
    recipe["launch"] = launch
    recipe.pop("draft_launch", None)
    recipe["capabilities"] = {
        # acceptance absent -> capabilities are UNKNOWN (null), never fabricated
        # true; chat is only asserted when the acceptance probe actually ran.
        "chat": True if acceptance else None,
        "reasoning": capabilities.get("reasoning"),
        "tools": capabilities.get("tools"),
        "vision": capabilities.get("vision"),
    }
    # Concurrency is only meaningful at the advertised context: a row that only
    # fits a shorter prompt does not license more streams at full context.
    # Compare the NOMINAL negotiated window (total_context_tokens), not the used
    # token count: the top window's usable prompt is always a little below nominal
    # (reserved positions + output budget), so a used-vs-nominal comparison would
    # wrongly exclude every full-window row.
    full_context = [
        row for row in accepted
        if (row.get("total_context_tokens") or row["context_tokens"]) >= plan["context_tokens"]
    ]
    recipe["serving"] = {
        "kv_cache_tokens": plan.get("cache_size_tokens") or plan["context_tokens"],
        # PR62: the REQUESTED sweep concurrency is not an engine batch ceiling, and
        # client-observed stream overlap does not prove engine batching. No
        # max_concurrency is claimed without engine-side batch instrumentation;
        # concurrency_observed records the request fan-out that actually ran.
        "max_concurrency": None,
        "concurrency_observed": sorted({row["concurrency"] for row in full_context}) or None,
        "max_context_tokens": measured_context(acceptance, plan),
        "tensor_parallel": 1,
    }
    recipe["speed_sweep_ids"] = [sweep_id]
    recipe["metadata"] = {
        **recipe.get("metadata", {}),
        "weights_subdir": plan.get("weights_subdir") or plan["served_name"],
        "acceptance": {
            "accepted_at": acceptance.get("captured_at"),
            "harness": "omp_accept.py (identity, chat, reasoning, tools, vision) + "
                       "omp_bench_client.py",
            "served_model_id": plan["served_name"],
            "failed_probes": sorted(failures),
        },
    }
    run_provenance = {"captured_at": NOW, "sources": [
        {"captured_at": NOW, "kind": "campaign-run", "url": args.evidence_repo}]}
    # `facts` annotates record fields: the value lives in the field, the fact
    # carries only how it was observed, and the path has to resolve.
    recipe["facts"] = {
        "capabilities.chat": {
            "state": "known" if acceptance else "unknown",
            "reason": ("omp_accept.py chat probe returned the pinned answer" if acceptance
                       else "no acceptance probe was captured for this run"),
            "provenance": run_provenance},
        "capabilities.reasoning": {
            "state": "known" if capabilities.get("reasoning") else "unknown",
            "reason": ("omp_accept.py reasoning probe: a separate reasoning_content phase "
                       "with the answer still in content" if acceptance
                       else "no acceptance probe was captured for this run"),
            "provenance": run_provenance},
        "capabilities.tools": {
            "state": "known" if capabilities.get("tools") else "unknown",
            "reason": ("omp_accept.py tools probe: a forced call with valid arguments and a "
                       "round-tripped tool result" if acceptance
                       else "no acceptance probe was captured for this run"),
            "provenance": run_provenance},
        "capabilities.vision": {
            "state": "known" if capabilities.get("vision") else "unknown",
            "reason": ("omp_accept.py vision probe: solid red and blue PNGs named correctly" if acceptance
                       else "no acceptance probe was captured for this run"),
            "provenance": run_provenance},
        "engine.version": {
            "state": "known" if engine_version else "unknown",
            "reason": (
                f"engine version reported by the running server and recorded in "
                f"engine.json ({engine_name} {engine_version})" if engine_version
                else "no engine version was captured in engine.json for this run"
            ),
            "provenance": {"captured_at": engine.get("captured_at") or NOW, "sources": [
                {"captured_at": engine.get("captured_at") or NOW, "kind": "host-probe",
                 "url": args.evidence_repo}]},
        },
        "launch.image": {
            "state": "known",
            "reason": "container image pinned by digest in the candidate launch",
            "provenance": run_provenance},
        "serving.max_context_tokens": {
            "state": "known",
            "reason": "the window the loaded server was configured with and served on; the "
                      "sweep covers shorter prompts and records every attempted row",
            "provenance": run_provenance},
    }
    coverage_complete = expected_cells > 0 and len(accepted) == expected_cells
    longcontext_present = ((artifacts / "longcontext" / "needle.json").exists()
                           and (artifacts / "longcontext" / "multihop.json").exists())
    # Partial marker for the renderer's evidence-only path (unconstrained metadata,
    # no public-schema expansion): complete ONLY when acceptance ran, coverage is
    # complete, and both retrieval passes landed.
    protocol_complete = bool(acceptance) and coverage_complete and longcontext_present
    # Interrupted-vs-not-reached lives here, sourced from Scheduling's SEPARATE
    # timeout/progress evidence, NEVER asserted from the manifest/rows; null absent.
    interruption_evidence = (load(artifacts / "interruption.json")
                             if (artifacts / "interruption.json").exists() else None)
    recipe["metadata"] = {
        # Preserve EVERY caller-authored metadata key (pilot_control identity/
        # provenance/deploy_image, etc.); the authoritative newly-measured keys
        # below override the SAME keys (e.g. protocol_complete). Generic - no
        # per-key special-case, no manual post-render merge.
        **recipe.get("metadata", {}),
        "weights_subdir": plan["served_name"],
        "origin": {
            "private_repository": EVIDENCE_REPO,
            "campaign_path": f"campaigns/{args.campaign.name}/artifacts/{args.slug}",
        },
        "protocol_complete": protocol_complete,
        "interruption": interruption_evidence,
        "acceptance": {
            "captured": bool(acceptance),
            "accepted_at": acceptance.get("captured_at"),
            "harness": ("omp_accept.py (identity, chat, reasoning, tools, vision) + "
                        "omp_bench_client.py" if acceptance else None),
            "served_model_id": plan["served_name"],
            "failed_probes": sorted(failures),
        },
        "measurements": {
            "configuration": {
                "cache_size_tokens": plan.get("cache_size_tokens"),
                "context_tokens": plan["context_tokens"],
                "sweep_contexts": plan["sweep_contexts"],
                "sweep_concurrencies": plan["sweep_concurrencies"],
                "api_completion_budget_tokens": plan.get("api_completion_budget_tokens"),
            },
            "mtp_acceptance": mtp_acceptance(artifacts),
            "peak_vram_gb": peak_vram_gb(artifacts / "telemetry.csv"),
            "weights_bytes": weights.get("bytes"),
            # Explicit basis so the headline generation rate can NEVER be read as
            # engine decode-only (publishing decode-only overstated the top window
            # ~20x). The value lives in speed-sweep metrics.peak_generation_tps
            # (additionalProperties:false there); its basis is annotated here in the
            # unconstrained recipe metadata alongside the other measurement notes.
            "peak_generation_tps_source": (
                "client end-to-end tok/s per stream (dispatch->last token), "
                "NOT engine decode-only"),
            "sweep_rows": {
                "accepted": len(accepted),
                "attempted": len(rows),
                "candidate": sum(1 for row in rows if row["status"] == "candidate"),
                "measurement_invalid": sum(1 for row in rows if row["status"] == "measurement-invalid"),
                "not_run": sum(1 for row in rows if row["status"] == "not-run"),
                "infra_invalid": sum(1 for row in rows if row["status"] == "infra-invalid"),
                "expected": expected_cells,
                # Coverage-gated: complete only when every EXPECTED cell (protocol
                # dimensions x samples, across arms) was ACCEPTED - never when a
                # survivor subset of an interrupted grid happens to be all-accepted.
                "complete": coverage_complete,
            },
            "sweep_arms": [
                {
                    "directory": directory.name,
                    "created_at": manifest.get("created_at"),
                    "total_contexts": manifest["protocol"]["total_context_tokens"],
                    "concurrencies": manifest["protocol"]["concurrencies"],
                    "samples_per_concurrency": manifest["protocol"].get(
                        "samples_per_concurrency", manifest["protocol"].get("samples_per_scenario")),
                    "accepted": sum(1 for row in sweep_rows(directory, manifest)
                                    if row["status"] == "accepted"),
                }
                for directory, manifest in arms
            ],
        },
    }

    write_json(recipe_path, recipe)
    print(json.dumps({
        "recipe": args.recipe, "asset": asset_id, "sweep": sweep_id,
        "accepted_rows": len(accepted), "capabilities": recipe["capabilities"],
        "max_context_tokens": recipe["serving"]["max_context_tokens"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))