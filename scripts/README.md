# Registry scripts

All scripts are **Python standard library only** (Python ≥ 3.10) — there is no
dependency manifest because there are no dependencies. Run them from the
repository root; each resolves `registry/` relative to the current directory
(or takes a root as its first positional argument).

`make check` runs the same verification suite as CI.

## The pipeline, in order

Importers and enrichment rewrite records; everything downstream of them is
regeneration and verification. After any step that writes records, finish the
pipeline before committing.

| Step | Script | Reads | Writes |
|---|---|---|---|
| 1. Import | `import_localmaxxing.py` | LocalMaxxing snapshot | candidate recipes, instances (`launch.kind: reference`) |
| 1. Import | `import_postgres_publication.py` | local.ai Postgres publication (see docs/PROVENANCE.md) | candidate recipes + speed-sweep |
| 1. Import | `import_hf_benchmarks.py` | HF Model & Benchmark Matrix scrape | `registry/benchmark/` |
| 1. Import | `import_market_snapshot.py` | local-ai-scanner-cli snapshot | `registry/price/` |
| 1. Import | `fetch_extra_prices.py` | public retailer search pages | scanner-style snapshot for the market import |
| 1. Import | `fetch_hf_downloads.py` | public Hugging Face API | `model.downloads` (30-day + all-time counts; drives the models-page sort) |
| 1. Import | `import_verified_sources.py` | LocalMaxxing / Mia Labs / mlx.fast / HF configs | candidate + validated recipes |
| 2. Tokenize | `tokenize_observed_command.py` | observed shell strings on records | `metadata.<source>.tokenized` (never the launch contract) |
| 3. Enrich | `enrich_registry.py` | records | shared enrichment contract fields (facts, provenance) |
| 4. Curate | `curate_registry.py` | records | curated hardware, sanitized candidates, **`registry/index/` shards** (`--index-only` for just the index) |
| 5. Format | `format_registry.py` | every `registry/**/*.json` | canonical form: 2-space indent, sorted keys (schemas keep hand order), raw UTF-8, trailing newline |
| 6. Verify | `validate_registry.py` | records + index | nothing — referential integrity, trust boundary, index staleness |
| 6. Verify | `npm test` | records + schemas | nothing — ajv validates every record against `registry/schema/*.schema.json` |

Standalone tool: `benchmark_openai_chat.py` measures prefill/decode of a
running OpenAI-compatible endpoint (no hidden token caps) to produce
speed-sweep evidence.

## Contract notes

- **Shape rules live in the JSON Schemas** (`registry/schema/`), enforced by
  ajv in `npm test`. `validate_registry.py` covers only what schemas cannot
  express. Change the schema first, then run `npm run gen:types` — `types.ts`
  is generated output.
- Observed source commands never become launch contracts: candidate imports
  stay `launch.kind: "reference"` and tokenized argv lives in metadata
  (`tokenize_observed_command.py` docstring has the full rules).
