# Local AI Registry

To add or validate records, see [CONTRIBUTING.md](CONTRIBUTING.md).

A hardware-aware registry of local model artifacts, launch recipes, measured speed sweeps, and public quality leaderboards. The standalone registry is data first: clients can read it from disk, serve it as static JSON, or resolve it over any static HTTP host.

## Start here

[`registry/index/`](registry/index/) holds the discovery shards. A client fetches only what its question needs: `collections.json` (ids + counts), `recipes.json` (compact filter rows), and five reverse lookups — `recipes-by-hardware.json`, `instances-by-model.json`, `benchmarks-by-model.json`, `prices-by-hardware.json`, `hardware-speed-evidence.json`. Fetch full records only after the user chooses something.

```text
index/collections.json          ids + counts for every collection
index/recipes.json              compact recipe rows for filtering
index/recipes-by-hardware.json  hardware_id -> [recipe ids]
index/instances-by-model.json   model_id    -> [model-instance ids]
index/benchmarks-by-model.json  model_id    -> [leaderboard score rows]
index/hardware-speed-evidence.json hardware_id -> aggregated sweep evidence

recipe/<id>.json
  model_instance_id -> model-instance/<id>.json
    model_id        -> model/<id>.json
  hardware_id       -> hardware/<id>.json
  speed_sweep_ids[] -> speed-sweep/<id>.json
  launch.asset_ids[]-> asset/<id>.json
price/<product-id>/<region>.json
  hardware[].id     -> hardware/<id>.json  (hardware.products[] points back)
```

This is the progressive-disclosure rule: index, choice, then the exact record and immediate references needed for the selected view. The API adds compact `relationships` links to the same records used by the site; it does not maintain a second UI-specific dataset or recursively embed the entire graph.

## Collections

| Collection | Meaning |
|---|---|
| `hardware/` | One accelerator or Apple chip and memory configuration |
| `model/` | One canonical base model |
| `model-instance/` | One downloadable artifact or quantization |
| `recipe/` | One artifact × hardware × engine compatibility unit |
| `speed-sweep/` | Measured inference evidence attached to one recipe |
| `benchmark/` | Scraped public leaderboard scores per benchmark, keyed by model variant |
| `price/<product-id>/` | Current retailer observations split by region and native currency |
| `asset/` | Engine configs and patches recipes mount, stored as manifest + blob |

Current counts are published from the source of truth in [`registry/index/collections.json`](registry/index/collections.json) and `/api/v1/index`.

The shared contract is defined twice for different consumers: JSON Schema files under [`registry/schema/`](registry/schema/) and TypeScript interfaces in [`registry/schema/types.ts`](registry/schema/types.ts).

## Trust boundary

`validated` means the model revision and runtime are pinned and the launch contract has acceptance evidence. `candidate` means the registry has useful compatibility or speed evidence but cannot yet promise a reproducible launch.

LocalMaxxing, local.ai Postgres, and mlx.fast imports are always `candidate` and `launch.kind: "reference"`. Observed source commands stay in metadata. When they can be split faithfully they also appear as `metadata.<source>.tokenized` argv, environment, and steps. That split is a mechanical rendering, unverified against the engine CLI, and does not satisfy promotion criterion 3. mlx.fast official scores attach only to `apple-m5-max-128gb`. Speculative engine docs without a measured SKU, including oMLX serve templates, are not imported. Promotion requires a separately curated, pinned recipe and a real completion plus speed acceptance.

Regional price records are observations, not universal hardware values. A product can link to an exact hardware specification or to a compatible hardware family when a listing does not identify memory capacity. Every observation preserves retailer, condition, stock state, native currency, direct URL, and fetch time. Scanner matches remain `candidate`; launch prices and MSRP stay as historical hardware metadata and do not populate the market-price collection.

## Hardware coverage

The hardware collection covers Apple M1 through M5 families at their supported memory tiers, including Pro, Max, and the Ultra generations Apple has actually shipped. It also includes GeForce RTX 30/40/50 cards, NVIDIA workstation accelerators, four current AMD local-AI targets, Intel Arc workstation cards, and the existing audited server/workstation classes.

Apple product names are discovery aliases; compatibility keys are chip plus unified-memory capacity. A generic LocalMaxxing label such as `Apple Max 128GB` remains explicitly generation-unspecified instead of being guessed into an M-series generation.

## Website

The Next.js application reads `registry/` directly at runtime. It does not copy records into a database or a second dataset.

```bash
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). Search model text, hardware text, or both. Filters come from registry fields: trust status, launchability, engine, weight precision, vendor, accelerator memory, hardware count, capability states, and attached speed evidence. Result cards progressively reveal the full model instance, canonical artifact link, hardware fields, launch contract, container image, and speed-sweep links.

For a production check:

```bash
npm test
npm run typecheck
npm run build
npm start
```

## Read-only API

Versioned JSON routes live under `/api/v1`. `GET` and `HEAD` are supported. Mutation methods receive `405 Method Not Allowed`; the application has no write path.

| Route | Purpose |
|---|---|
| `/api/v1` | API discovery document |
| `/api/v1/index` | Normalized registry discovery index |
| `/api/v1/facets` | Values available for useful filters |
| `/api/v1/models` and `/api/v1/models/:id` | Canonical models and model details |
| `/api/v1/model-instances` and `/api/v1/model-instances/:id` | Downloadable artifacts and quantizations |
| `/api/v1/hardware` and `/api/v1/hardware/:id` | Accelerator profiles and specifications |
| `/api/v1/prices` and `/api/v1/prices/:id` | Regional market observations and linked hardware specifications |
| `/api/v1/recipes` and `/api/v1/recipes/:id` | Compatibility units and fully resolved details |
| `/api/v1/compatibility` | Model × hardware compatibility query |
| `/api/v1/speed-sweep` and `/api/v1/speed-sweep/:id` | Measured speed evidence |
| `/api/v1/benchmark` and `/api/v1/benchmark/:id` | Scraped public leaderboard scores |

List routes accept `limit` (maximum 100) and `offset`. Common compatibility filters are `model`, `hardware`, `model_id`, `model_instance_id`, `hardware_id`, `status`, `launchable`, `engine`, `launch_kind`, `precision`, `instance_kind`, `vendor`, `backend`, `min_vram_gb`, `max_vram_gb`, `hardware_count`, `evidence`, and the tri-state capability filters `chat`, `reasoning`, `tools`, and `vision`. Capability values are `true`, `false`, or `unknown`. Model-instance lists also accept `huggingface_status` and `huggingface_link_type`.

Examples:

```bash
curl 'http://localhost:3000/api/v1/models?q=gemma'
curl 'http://localhost:3000/api/v1/hardware?vendor=nvidia&min_vram_gb=48'
curl 'http://localhost:3000/api/v1/prices?region=US&condition=new&in_stock=true'
curl 'http://localhost:3000/api/v1/model-instances?huggingface_link_type=search&limit=10'
curl 'http://localhost:3000/api/v1/compatibility?model=gemma&hardware=rtx%20pro%206000&launchable=true'
curl 'http://localhost:3000/api/v1/recipes/gemma-4-12b-it-nvfp4-rtxpro6000-sglang-tp1'
```

Every model-instance body carries an authoritative `huggingface` object with a nonempty `url`, `status`, and `link_type`. API model-instance results also expose `hugging_face_url` as the exact value of `huggingface.url`. A `repository` link type is an exact Hugging Face repository; a `search` link type is an explicitly labeled search fallback, not an artifact claim. The API preserves both types and their status and never derives a Hugging Face link from the model-instance `repository` text or legacy `url`. Full records remain nested in detail and compatibility responses, so newly sourced pricing, availability, bandwidth, precision-specific compute, container provenance, and explicit unknown fields pass through without an application schema update.

## Validate

```bash
python3 scripts/curate_registry.py
python3 scripts/validate_registry.py
```

To refresh regional market data from a fresh scanner snapshot, import the snapshot before rebuilding and validating the index. Pass `--replace` only when the snapshot is a complete scan that should wipe previous market records:

```bash
python3 scripts/import_market_snapshot.py ~/projects/local-ai-scanner-cli/cache/latest.json --replace
python3 scripts/curate_registry.py --index-only
python3 scripts/validate_registry.py
```

To refresh measured Mac compatibility from a local.ai publication snapshot, import its compact `pg_read_models.jsonl` and `pg_read_speed_runs.jsonl` views before rebuilding the index:

```bash
python3 scripts/import_postgres_publication.py ~/local-ai-data/private/publication-<timestamp>
python3 scripts/curate_registry.py
python3 scripts/validate_registry.py
```

To refresh the scraped public leaderboard scores from the HF Model & Benchmark Matrix scrape, import before rebuilding and validating the index:

```bash
python3 scripts/import_hf_benchmarks.py ~/projects/hf-model-benchmarks
python3 scripts/curate_registry.py --index-only
python3 scripts/validate_registry.py
```

To add more retailer observations on top of an existing market snapshot (without wiping regions the scanner already covered):

```bash
python3 scripts/fetch_extra_prices.py --out /tmp/extra-prices.json
python3 scripts/import_market_snapshot.py /tmp/extra-prices.json
python3 scripts/curate_registry.py --index-only
python3 scripts/validate_registry.py
```

To refresh Micro Center GPU prices, scrape the category through a US egress and map it onto the registry contract. microcenter.com rejects non-US IPs and challenges a datacenter IP with Cloudflare, so `scrape_microcenter_prices.py` opens a SOCKS tunnel to a US host and drives a headed consumer browser through it, then fetches every listing page from inside that cleared session. `fetch_microcenter_prices.py` only maps the scrape onto the registry, keeps prior observations for the same product, and leaves GPUs the hardware collection does not describe unimported and reported:

```bash
python3 scripts/scrape_microcenter_prices.py --stores all --out out
python3 scripts/verify_microcenter_scrape.py out/latest.json
python3 scripts/fetch_microcenter_prices.py out/latest.json
python3 scripts/import_market_snapshot.py cache/microcenter-prices.json
python3 scripts/enrich_hardware_prices.py
python3 scripts/curate_registry.py --index-only
python3 scripts/validate_registry.py
```

`enrich_hardware_prices.py` runs after the index rebuild because a full `curate_registry.py` rewrites hardware records from its source tables and would drop the commercial summaries it derives.

Geizhals publishes the only year-deep GPU price history this registry can reach: its per-product "Preisentwicklung" series runs from product launch, daily, in EUR. That series comes from a public JSON endpoint behind a Cloudflare challenge, so `scrape_geizhals_history.py` clears the challenge once in a headed browser and reuses that session for every call; `fetch_geizhals_history.py` maps each daily point onto the registry product for its GPU SKU, keeps the observations already recorded for that product and region, and reports products the hardware collection does not describe instead of inventing them:

```bash
python3 scripts/scrape_geizhals_history.py --match 5090 --days 9999 --pages 2 --limit 40
python3 scripts/fetch_geizhals_history.py out/geizhals-history-*.json
python3 scripts/import_market_snapshot.py cache/geizhals-history.json
python3 scripts/curate_registry.py --index-only
python3 scripts/validate_registry.py
```

A Geizhals point is the lowest offer it tracked that day, so it becomes one `new`, in-stock DE observation with no quantity, and days with no tracked offer are absent rather than zero-priced. Every observation keeps its own timestamp, so re-importing the same dump adds nothing, a listing that holds its price still records a new point on a later run, and no prior observation is dropped.

Both sources accumulate on a weekly schedule, which is the only way a Micro Center series can exist at all: `make weekly-prices` runs the whole chain — scrape, verify, map, import, enrich, rebuild the index, validate — and then rebuilds the visual.

The visual is [`public/gpu-price-history.html`](public/gpu-price-history.html), served by the site at `/gpu-price-history.html`. Every number on it is recomputed from `registry/price/` alone: `make price-visual` rebuilds the payload and the page, and `make price-visual-check` regenerates it and requires no diff, so the page cannot drift from the records.

Benchmark scores are reported measurements from public leaderboards. They never attach to recipes or affect launch validation; a leaderboard row proves what was reported for a model variant, not that a local run reproduces it.

The validator checks IDs, references, counts, status boundaries, pinned validated artifacts, positive evidence values, and the CUDA-graph policy. `curate_registry.py` is deterministic and rebuilds the compact index after data changes.

## Local CLI

`bin/local-ai` reads the standalone tree directly. It detects Apple Silicon on macOS and NVIDIA, AMD, or Intel accelerators on Linux, counts identical NVIDIA devices, finds exact or capacity-compatible recipes, and resolves only the records selected by the user.

```bash
bin/local-ai detect
bin/local-ai list --json
bin/local-ai choose
bin/local-ai search qwen
bin/local-ai show <recipe-id>
```

The default `choose` command uses `gum` when available and a numbered terminal menu otherwise. Capacity matches are recommendations, not claims that another hardware profile's benchmark applies unchanged. Candidate recipes remain inspectable but are never presented as validated launch contracts. Set `LOCAL_AI_HARDWARE` and `LOCAL_AI_HARDWARE_COUNT` to override detection.

## Source layout

`registry/` is the normalized contract and the schema for new imports. Measured local inference evidence lives in `speed-sweep/`. Public quality leaderboards such as Terminal-Bench 2.1 live in `benchmark/` and never attach to recipes.

Every number carries its own `provenance` source (URL and `captured_at`) inside the record that holds it.

## License

MIT

## Local Inference Lab sources

The pinned inventory [`sources/local-inference-lab/2026-09-13.json`](sources/local-inference-lab/2026-09-13.json) catalogs 230 concrete source configurations and all nine catalog manifests; `scripts/check_lil_import.py` (run in CI) checks the imported recipes against it. Imported upstream recipes are reference-only candidates with visible attribution. The separately accepted [GLM-5.3-Flash R35 TP4 recipe](registry/recipe/glm53-flash-lil-r35-rtxpro6000-vllm-tp4.json) links the [public Docker package](https://github.com/0xSero/glm-5.3-flash-4x-rtx-pro-6000), measured total/per-request decode speeds and its validation limits.
