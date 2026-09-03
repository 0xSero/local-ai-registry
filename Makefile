# local-ai-registry pipeline
#
# All Python scripts are stdlib-only (Python >= 3.10). Node is needed for
# tests, typecheck, and the site. `make check` is what CI runs.

.PHONY: check format index types validate test typecheck build py-tests trust

## The full verification suite — identical to CI.
check: format-check validate test typecheck types-check index-check
	python3 -m unittest discover -s scripts -p 'test_*.py'

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
