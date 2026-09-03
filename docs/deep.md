# Deep breakdown

Everything that is true about the registry, in the order a recipe experiences it.

## 1. Identity

Every record id is a lowercase slug and equals its filename. Recipe ids follow `<model>-<weights>-<hardware>-<engine>-<profile>`, for example `gemma-4-12b-it-nvfp4-rtxpro6000-sglang-tp1`. Hardware ids are chip plus memory capacity, never a product name; product names are aliases on the hardware record. A generic label such as "Apple Max 128GB" stays generation-unspecified instead of being guessed into an M-series.

## 2. Where records come from

| Source | Script | Produces | Trust |
|---|---|---|---|
| Our own acceptance runs | `accept_recipe.py`, `validate_rented.py`, `validate_batch.sh` | `speed-sweep` with `source.kind: acceptance-run`, `metadata.acceptance` on the recipe | can validate |
| Our campaign artifacts (inference-index, per-model repos under 0xSero) | `import_verified_sources.py`, `import_lane_evidence.py` | commit-pinned `speed-sweep` | can validate |
| local.ai Postgres publication | `import_postgres_publication.py` | `candidate` recipes, `reference` launches, Mac evidence | candidate only |
| LocalMaxxing public API | `import_localmaxxing.py`, `enrich_localmaxxing_live.py` | `candidate` recipes, `reference` launches | candidate only |
| mlx.fast official scores | `import_verified_sources.py` | `candidate`, `apple-m5-max-128gb` only | candidate only |
| Hugging Face | `import_hf_models.py`, `import_hf_benchmarks.py`, `enrich_hf_*.py` | `model`, `model-instance`, `benchmark` rows, download counts | metadata |
| Retail price scanner | `import_market_snapshot.py`, `fetch_extra_prices.py`, `enrich_hardware_prices.py` | `price` observations | observations, never MSRP |

Provenance is recorded on every record: `provenance.sources[]` with `kind`, `url`, `captured_at`. `docs/PROVENANCE.md` keeps the hashes of each upstream snapshot.

## 3. Launch contracts

A `launch` is data that is executable in effect, so the rules are strict:

- No shell strings. `arguments` is an argv array; `steps` is a list of argv arrays. A `&&` chain is an error.
- `reference` launches must not carry contract fields (`image`, `arguments`, ports). Their observed command may appear tokenized under `metadata.<source>.tokenized` with `fidelity: faithful | lossy`; lossy tokenizations never publish argv.
- Validated docker launches pin `image` by digest, name `accelerator_backend`, both ports, and mounts with `source` and `target`. `local/` images are unpullable and refused.
- Forbidden anywhere in a validated launch: `--enforce-eager`, `disable-cuda-graph`, `disable-prefill-cuda-graph`.
- Recommended launches additionally use bridge networking and no host IPC. Clients refuse host networking, extra capabilities, weakened seccomp, and mounts outside their owned roots; the registry does not carry those.
- `draft_launch` is allowed only on candidates and must already be digest-pinned. It is the promotion pipeline's staging area (`synthesize_launches.py`).
- Image provenance is machine-readable on every runnable single-GPU recipe: `launch.provenance.kind` is `upstream-published` (with publisher and source project) or `self-built-attested` (with source repo, Dockerfile, workflow run, and the `gh attestation verify` command).

## 4. Evidence

A `speed-sweep` belongs to one recipe. It states `accepted_at`, `measured_at`, a `source` (`kind`, `repository`, `commit`, `paths`), summary `metrics`, and `rows`. Row vocabulary: `prefill_tok_s`, `decode_tok_s`, `ttft_ms_p50`, `context_tokens`, `concurrency`, `cache_state`, `peak_vram_gb`. Blank means unmeasured. Measured limits never exceed configured limits. Community results and our own results never share a sweep.

Acceptance itself is: the served model id matches the recipe, a real chat completion returns, a tool call returns if the recipe claims tools, and, in the plugin, the same completion in the Anthropic Messages and OpenAI Responses dialects through the gateway, plus a decode-speed floor that catches silent CPU fallback.

## 5. Trust derivation

`scripts/trust.py` is the whole definition. `failures(recipe, instance, sweeps)` returns the list of reasons a recipe is not validated; empty means validated. `derive_status` wraps it. `recommendable(recipe)` returns why a recipe cannot be recommended. `validate_registry.py` imports these and errors on any stored value that disagrees, so CI and `make check` refuse drift. `make trust` rewrites statuses to the derived value and drops `recommended` from anything that no longer qualifies.

There is no third status. Rejected or unsupported outcomes stay in the source audit and in `docs/notes`, not in the registry.

## 6. Recommendation

`scripts/recommend.py` keeps exactly one `recommended: true` per hardware id among validated, single-GPU, bridge-network docker recipes. Order: the VRAM tier picks the model family (32 GB: Qwen3.8-27B or Qwen3.6-35B-A3B; 24 GB: Gemma 4 12B; 12 GB: Qwen3.5-9B; below: LFM2.5-2.6B; a card falls back down the tiers), then engine rank (TabbyAPI EXL3, SGLang, vLLM, llama.cpp), then largest context, then newest acceptance. Current direction from the Omarchy maintainers: Qwen3.8-27B wherever it fits. `curate_registry.py` writes the result to `index/recommendations.json`; the validator refuses duplicates.

## 7. Pipeline

```
make trust      derive status, drop stale recommended flags, format
make index      rebuild registry/index/* from records
make check      format-check, validate (schemas, references, trust, launch), tests, typecheck, types-check, index-check
```

CI (`.github/workflows/ci.yml`) runs `make check` on every push and pull request. `main` requires it.

## 8. Consumers

- **Omarchy plugin** (`0xSero/omarchy-local-ai`): vendors `recipes.json`, produced by `scripts/export_plugin_recipes.py` from the recommendations plus the attested gateway image. It re-gates every entry on load and never fetches the registry at runtime.
- **Read API** (`app/api/v1`): the same JSON, paginated, with `relationships` links. Deployed on Vercel from `main`.
- **Browser** (`app/`): search, facets, record sheets, compare, resources.
- **bin/local-ai**: detect hardware, list, choose, show a recipe from a checkout.

## 9. What the registry refuses to be

Not a model host. Not a mutable database. Not a place to run unreviewed community recipes. Not a leaderboard of self-reported numbers. Not a claim that two cards with the same VRAM are the same card.
