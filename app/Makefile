# install:   the command, its data and the polkit action (PREFIX=/usr/local, DESTDIR for packages)
# uninstall: the same files
# test:      every test (docker, podman, curl, the GPU tools and pkexec are shimmed; node for Model.js)
# sync:      every recipe from the registry's published export (REGISTRY=<checkout>, at its origin/main)
# check:     test, and that recipes.json is a clean export
PREFIX ?= /usr/local
BINDIR = $(PREFIX)/bin
DATADIR = $(PREFIX)/share/local-ai
POLKITDIR ?= /usr/share/polkit-1/actions
REGISTRY ?= ../local-ai-registry
REGISTRY_REF ?= origin/main
SHELL := /bin/bash

.PHONY: install uninstall test sync check

install:
	install -Dm755 core/local-ai "$(DESTDIR)$(BINDIR)/local-ai"
	install -Dm644 core/recipes.json "$(DESTDIR)$(DATADIR)/recipes.json"
	install -Dm644 core/Model.js "$(DESTDIR)$(DATADIR)/Model.js"
	sed 's|@BINDIR@|$(BINDIR)|g' core/org.local-ai.policy.in >core/org.local-ai.policy
	install -Dm644 core/org.local-ai.policy "$(DESTDIR)$(POLKITDIR)/org.local-ai.policy"
	rm -f core/org.local-ai.policy

uninstall:
	rm -f "$(DESTDIR)$(BINDIR)/local-ai" "$(DESTDIR)$(POLKITDIR)/org.local-ai.policy"
	rm -rf "$(DESTDIR)$(DATADIR)"

test:
	bash test/all

# the registry lists each card kind's recipes best first; the bundle keeps them all, one card first, one kind per line
sync:
	@test -d "$(REGISTRY)" || { echo "sync: set REGISTRY=<registry checkout>" >&2; exit 2; }
	@git -C "$(REGISTRY)" show "$(REGISTRY_REF):plugin/v2/recipes.json" | jq -r --arg c "$$(git -C "$(REGISTRY)" rev-parse "$(REGISTRY_REF)")" \
	  '.hardware |= map_values(.recipes |= sort_by(.cards // 1)) | .registryCommit = $$c | (del(.hardware) | tojson | .[:-1]) + ",\"hardware\":{\n" + ([.hardware | to_entries[] | "\(.key | tojson):\(.value | tojson)"] | join(",\n")) + "\n}}"' >core/recipes.json
	@jq -r '"recipes.json: \(.hardware | length) card kinds, \([.hardware[].recipes[]] | length) recipes, registry \(.registryCommit[:12])"' core/recipes.json

check: test
	@jq -e '(.registryCommit | test("^[0-9a-f]{40}$$")) and (.gateway.image | test("@sha256:[0-9a-f]{64}$$")) and all(.hardware[].recipes[]; .image | test("@sha256:[0-9a-f]{64}$$"))' core/recipes.json >/dev/null \
	  && echo "recipes.json: ok" || { echo "recipes.json: not a clean export" >&2; exit 1; }
