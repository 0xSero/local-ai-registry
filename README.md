# Local AI Registry

A hardware-aware registry of local model artifacts, launch recipes, measured speed sweeps, and public quality leaderboards. The standalone registry is data first: clients can read it from disk, serve it as static JSON, or resolve it over any static HTTP host.

## Start here

[`registry/index.json`](registry/index.json) is the only discovery document a client needs. It contains collection IDs and compact recipe rows for filtering. Fetch full records only after the user chooses something.

```text
index.json
  recipe/<id>.json
    model_instance_id  -> model-instance/<id>.json
      model_id         -> model/<id>.json
    hardware_id        -> hardware/<id>.json
    speed_sweeps_ids[] -> speed-sweeps/<id>.json
  price/<product-id>/<region>.json
    hardware[].id      -> hardware/<id>.json
```

This is the progressive-disclosure rule: index, choice, then the exact record and immediate references needed for the selected view. The API adds compact `relationships` links to the same records used by the site; it does not maintain a second UI-specific dataset or recursively embed the entire graph.

## Collections

| Collection | Meaning |
|---|---|
| `hardware/` | One accelerator or Apple chip and memory configuration |
| `model/` | One canonical base model |
| `model-instance/` | One downloadable artifact or quantization |
| `recipe/` | One artifact × hardware × engine compatibility unit |
| `speed-sweeps/` | Measured inference evidence attached to one recipe |
| `benchmarks/` | Scraped public leaderboard scores per benchmark, keyed by model variant |
| `price/<product-id>/` | Current retailer observations split by region and native currency |

Current counts are published from the source of truth in [`registry/index.json`](registry/index.json) and `/api/v1/index`.

The shared contract is defined twice for different consumers: JSON Schema files under [`registry/schema/`](registry/schema/) and TypeScript interfaces in [`registry/schema/types.ts`](registry/schema/types.ts).

## Trust boundary

`validated` means the model revision and runtime are pinned and the launch contract has acceptance evidence. `candidate` means the registry has useful compatibility or speed evidence but cannot yet promise a reproducible launch.

LocalMaxxing and local.ai Postgres imports are always `candidate` and `launch.kind: "reference"`. Their source commands are deliberately not copied into the executable contract. mlx.fast official scores are `candidate` native evidence on `apple-m5-max-128gb` only. Speculative engine docs without a measured SKU, including oMLX serve templates, are not imported. Promotion requires a separately curated, pinned recipe and a real completion plus speed acceptance.

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
| `/api/v1/speed-sweeps` and `/api/v1/speed-sweeps/:id` | Measured speed evidence |
| `/api/v1/benchmarks` and `/api/v1/benchmarks/:id` | Scraped public leaderboard scores |

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

`registry/` is the normalized contract and the schema for new imports. Measured local inference evidence lives in `speed-sweeps/`. Public quality leaderboards such as Terminal-Bench 2.1 live in `benchmarks/` and never attach to recipes. `local-ai/` is the earlier denormalized dataset retained temporarily for existing consumers; it is not the schema for new imports.

Data provenance and recovery decisions are in [`docs/PROVENANCE.md`](docs/PROVENANCE.md). The behavior-only product prompt for a registry browser is in [`docs/UI_BEHAVIOR_PROMPT.md`](docs/UI_BEHAVIOR_PROMPT.md).

## License

MIT
