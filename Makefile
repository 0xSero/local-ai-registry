# local-ai-registry pipeline
#
# All Python scripts are stdlib-only (Python >= 3.10). Node is needed for
# tests, typecheck, and the site. `make check` is what CI runs.

.PHONY: check format index types validate plugin-gate plugin-recipes plugin-recipes-check supported test typecheck build py-tests trust price-visual price-visual-check weekly-prices

## The full verification suite — identical to CI.
check: format-check validate plugin-gate test typecheck types-check index-check price-visual-check
	python3 -m unittest discover -s scripts -p 'test_*.py'

## Rebuild the price-history visual from the registry records. The payload is a
## pure function of registry/price/, so this needs no scrape dump and no network.
price-visual:
	python3 scripts/build_price_history_data.py
	python3 scripts/gen_price_history_visual.py

price-visual-check: price-visual
	git diff --exit-code public/gpu-price-history.html

## Weekly price accumulation: scrape both sources, verify, import, enrich, index,
## validate, then rebuild the visual. Needs Playwright and a US egress for the
## Micro Center scrape; see scripts/README.md.
weekly-prices:
	bash scripts/weekly_prices.sh

## Derive `status` (validated/candidate) from evidence and rewrite it. validate refuses any drift.
trust:
	python3 scripts/trust.py --apply
	python3 scripts/format_registry.py

## Rewrite every registry JSON file into canonical form.
format:
	python3 scripts/format_registry.py

format-check:
	python3 scripts/format_registry.py --check

## Rebuild registry/index.json from the records on disk.
index:
	python3 scripts/curate_registry.py --index-only
	python3 scripts/format_registry.py

index-check:
	python3 scripts/curate_registry.py --index-only
	git diff --exit-code registry/index/
	test ! -f registry/index.json

## Regenerate registry/schema/types.ts from the JSON Schemas.
types:
	npm run gen:types

types-check:
	npm run gen:types
	git diff --exit-code registry/schema/types.ts

## Referential integrity, trust boundary, index staleness.
validate:
	python3 scripts/validate_registry.py

## Omarchy local-ai plugin gate over every validated docker or host/flm recipe.
plugin-gate:
	python3 scripts/check_plugin_gate.py

## The recipe file the Omarchy plugin vendors and fetches (plugin/recipes.json); CI requires it current.
plugin-recipes:
	python3 scripts/export_plugin_recipes.py --out plugin/recipes.json

plugin-recipes-check: plugin-recipes
	git diff --exit-code plugin/recipes.json

## supported/: one page per GPU the plugin catalog runs a model on; CI requires it current.
supported:
	python3 scripts/gen_supported.py

## Node test suite (includes ajv validation of every record).
test:
	npm test

py-tests:
	python3 -m unittest discover -s scripts -p 'test_*.py'

typecheck:
	npm run typecheck

build:
	npm run build

## Refresh Hugging Face download counts (models-page sort order).
downloads:
	python3 scripts/fetch_hf_downloads.py
	python3 scripts/format_registry.py
