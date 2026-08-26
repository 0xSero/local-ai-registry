# Registry provenance

The registry separates observed source data from audited launch contracts. Source presence proves that a model/hardware/engine combination was reported or measured; it does not by itself make that combination safe or reproducible to run.

## Recovered local publication

The most complete local database publication is `pg-20260820T063452765Z`, captured from the public read schema on 2026-08-20. Its manifest records:

- 280 model rows, SHA-256 `da051cfd1f5473ed74dbb55c43dfb0605a6ac6e59ca02979c08381f96c48dad8`
- 15 hardware rows, SHA-256 `71b0196f61ab0b6e368d0060a7e0df54e694f1289cb91d72cc4dfd82b1499ca0`
- 2,534 speed-run rows, SHA-256 `3d7ca14b4c05afc828f877d7859c4f28faa948ced2e48b8e4247f69b0cf7501c`
- 537 weighted-frontier rows, SHA-256 `59eb966866a3c45211b22682c2092f498dfeac13c3412103e6e0709b059f4aa5`

The publication stays outside this repository because it is a private raw snapshot. Only normalized public facts and evidence rows are committed here.

## Recovered OMP normalization

An earlier OMP session had already normalized the local publication and selected LocalMaxxing results, but the generated tree was never committed to the standalone registry. That recovered build contributed 68 models, 202 model instances, 240 recipes, and 224 speed sweeps.

It was treated as an import candidate, not as final truth. This pass corrected three unsafe assumptions before publication:

- generic Apple labels remain generation-unspecified rather than being assigned to a guessed chip;
- LocalMaxxing commands became non-executable `reference` launches;
- capabilities from unverified candidates became `null` rather than guessed booleans.

## Live database regression

The configured read-only Postgres endpoint was checked in a read-only transaction on 2026-08-26. It currently exposes 12 model rows, no inference configurations, 29 evaluation runs with a latest timestamp of 2026-07-24, and no speed-sweep tables. The live endpoint therefore cannot replace the more complete 2026-08-20 local publication. No database URL or credential is stored here.

## LocalMaxxing refresh

The public API was refreshed on 2026-08-26 at 19:33 EDT through its documented paginated endpoints. The local response contained 5,747 leaderboard rows across 98 hardware groups and 615 used Hugging Face model IDs; the model endpoint contained 793 records.

Response hashes:

- leaderboard: `198336939c76e88bd7e32925ade48be62c697517a20aed73b2ffdd4aede39806`
- models: `653bcaf27702ea919654e12a1f5f6a32cfd05a742d759ce1744dcf33aa5469c2`

Nine newly observed rows mapped to hardware already supported by this registry and were added as reference-only candidates. One Tesla P100 row was intentionally skipped because that hardware is outside the current workstation/local-device coverage target.

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
