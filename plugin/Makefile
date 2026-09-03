# sync:  regenerate recipes.json from a registry checkout (its export stamps the commit)
# check: tests plus a recipes.json sanity check
REGISTRY ?= ..

.PHONY: sync check test

sync:
	python3 $(REGISTRY)/scripts/export_plugin_recipes.py --out recipes.json
	@jq -r '"recipes.json: \(.hardware|length) hardware ids from registry \(.registryCommit[:12])"' recipes.json

test:
	bash test/all

check: test
	@jq -e '.schemaVersion=="omarchy-local-ai/recipes/1" and (.registryCommit|test("^[0-9a-f]{40}$$")) and (.gateway.image|test("@sha256:[0-9a-f]{64}$$")) and (.hardware|length>0)' recipes.json >/dev/null \
	  && echo "recipes.json: ok" || { echo "recipes.json: missing schema, registry commit, or gateway image" >&2; exit 1; }
