# Registry provenance

The registry separates observed source data from audited launch contracts. Source presence proves that a model/hardware/engine combination was reported or measured; it does not by itself make that combination safe or reproducible to run.

## Current local.ai publication

The current database publication is `pg-20260827T060320709Z`, captured from a read-only repeatable-read transaction on 2026-08-27. Its manifest records:

- 353 public model rows, SHA-256 `1813c8556be979b81abd22377cee42ea851cbdeaa6310563f0189677e99e7831`
- 3,797 public speed-run rows, SHA-256 `1e43ef6ef4232b93066c74c0e1b9d881dbda530a03a3d2991b6cec63f62da8f6`
- latest evaluation run at `2026-08-26T18:30:28.412Z`
- latest speed point at `2026-08-26T11:24:21.520Z`

The upstream audit counted 374 models, 4,113 speed sweeps, 707,032 sweep points, and 5,228 inference configurations before public-release filtering. The registry imports 1,349 real Mac runs across nine exact Apple hardware keys and excludes all synthetic M5 Ultra rows. Those runs collapse into 787 artifact × hardware × engine candidates with separate evidence records for each source run.

The publication stays outside this repository because it is a private source snapshot. Only normalized public facts and evidence rows are committed here. The hardware read view currently has schema drift against `eval_config`, so hardware identity comes from the exact measured `hardware_key` on each speed run and resolves only through the explicit mapping in `scripts/import_postgres_publication.py`.

The public Convex deployment was cross-checked on 2026-08-27. Its active publication is still `pg-20260721-ui-refresh`, with 312 model rows, 1,216 speed runs, and a latest speed point from 2026-07-21. It is a valid published subset but is older than the repeatable-read Postgres snapshot, so it was not used as the refresh authority.

The live public site was independently checked in Brave on 2026-08-27 through the canonical [models](https://local.ai/models) and [hardware](https://local.ai/hardware) routes. Its server-rendered catalog was generated on 2026-08-27 and contained 61 model families, 195 variants, and 12 measured hardware configurations. The live hardware catalog resolves legacy source key `m4_pro_64_20c` to a 48GB M4 Pro and `m3_ultra_512_80c` to a 96GB M3 Ultra with an 80-core GPU. The importer therefore maps the M4 key to the canonical 48GB record and separates the 60-core and 80-core M3 Ultra measurements into exact 96GB hardware records while preserving the original keys in recipe metadata.

## Recovered OMP normalization

An earlier OMP session had already normalized the local publication and selected LocalMaxxing results, but the generated tree was never committed to the standalone registry. That recovered build contributed 68 models, 202 model instances, 240 recipes, and 224 speed sweeps.

It was treated as an import candidate, not as final truth. This pass corrected three unsafe assumptions before publication:

- generic Apple labels remain generation-unspecified rather than being assigned to a guessed chip;
- LocalMaxxing commands became non-executable `reference` launches;
- capabilities from unverified candidates became `null` rather than guessed booleans.

## Database source boundary

The local.ai Postgres source is accessed only by the external ETL workflow. No database URL or credential is stored here. The importer accepts the compact, checksummed publication directory and never opens a database connection itself.

## LocalMaxxing refresh

The public API was refreshed on 2026-08-26 at 19:33 EDT through its documented paginated endpoints. The local response contained 5,747 leaderboard rows across 98 hardware groups and 615 used Hugging Face model IDs; the model endpoint contained 793 records.

Response hashes:

- leaderboard: `198336939c76e88bd7e32925ade48be62c697517a20aed73b2ffdd4aede39806`
- models: `653bcaf27702ea919654e12a1f5f6a32cfd05a742d759ce1744dcf33aa5469c2`

Nine newly observed rows mapped to hardware already supported by this registry and were added as reference-only candidates. One Tesla P100 row was intentionally skipped because that hardware is outside the current workstation/local-device coverage target.

The same-day live GLM-5.3 Flash NVFP4 four-RTX-PRO-6000 record was normalized separately from repository evidence. Its model revision and source bundle commit are pinned and its completion, multimodal, context, concurrency, and speed evidence are retained. It remains a candidate because the locally built launch image is still identified by a mutable tag rather than a published digest.

A later LocalMaxxing refresh mapped NVIDIA GB10 / DGX Spark UNIFIED 128GB rows onto the exact `dgx-spark-gb10-128gb` record and left 256GB GB10 rows unmapped. Quantized artifact names attach to an existing canonical model when one exists; they do not become a second canonical with guessed parameter counts.

oMLX `omlx serve` templates were rejected. They copied a native command onto Apple SKUs that had some other MLX evidence, without a measured oMLX run on those chips.

mlx.fast official Gemma 4 26B A4B scores from [yukon.org/mlxfast](https://www.yukon.org/mlxfast) attach to canonical `gemma-4-26b-a4b-it` through Hub-confirmed `mlx-community/gemma-4-26B-A4B-it-qat-4bit` revision `0e3cbab38ce568cf6e23543010d08d03b731910c`. Hardware is `apple-m5-max-128gb` only. The recipe is a reference-only candidate: observed setup stays in metadata, and the launch object does not carry a command.

## Promotion rule

A candidate becomes validated only when all of these are present:

1. an exact model artifact revision;
2. a pinned runtime, such as a digest-pinned image or checksum-pinned native binary;
3. tokenized launch arguments rather than a shell snippet;
4. compatible detected hardware and memory capacity;
5. a real model-dialect completion;
6. measured speed evidence attached to the same recipe;
7. no eager-mode or CUDA-graph-disabling workaround.

Until then, the candidate is searchable and useful as evidence, but clients must not offer its Run action.

## Enrichment contract

Model, model-instance, and recipe records carry a `provenance` object with one or more source URLs and a UTC `captured_at` timestamp. Sourced values that can be absent or ambiguous are represented in the `facts` map as `{state, reason, provenance}`; `known` facts also carry `value`. The permitted states are `known`, `unknown`, `unavailable`, and `not_applicable`. A JSON `null` or empty value without a matching fact is not an explanation of absence and fails validation for enriched records.

Every model and model-instance carries a `huggingface` identity object. A public owner/repository is represented by its canonical `https://huggingface.co/<owner>/<repo>` URL and is only marked `known` after a primary Hub lookup. Non-Hugging-Face or unresolved artifacts retain their original identity and use an explicit `unavailable` or `unknown` status with a precise Hub search URL; a search result is never presented as a repository match.

Hardware records may carry sourced commercial availability/prices and precision-specific accelerator compute under `compute.stats`, keyed by precision (`fp32`, `tf32`, `fp16`, `bf16`, `fp8`, `fp4`, `int8`, `int4`) and sparsity (`dense`, `structured_2_4`, `unstructured`, `unknown`). Missing published throughput is an explicit unknown fact; it is never inferred from a neighboring precision or marketing peak expressed in another unit. Memory bandwidth uses `memory.bandwidth_gb_per_s` and is either a positive value, a bounded positive range, or an explicitly sourced unknown.

Every recipe launch carries `launch.container`. Its state is `digest-pinned`, `mutable`, `indirect`, or `none`, with runtime, image/digest or compose-file details, source, reason, and capture time. Reference-only, controller, and native-script launches use `none` unless their existing launch data proves a container. Docker tags without content digests are `mutable`; compose launches are `indirect` unless a resolved digest is present. A candidate remains a candidate regardless of its evidence, and no container image is invented for it. Only validated recipes may be launchable, and their promotion requirements above remain unchanged.
