# Omarchy Local AI — design

Consolidated 2026-09-03. Decisions are recorded once agreed; open items carry a
recommendation and are settled one at a time, bottom-up.

## What it is

One Omarchy bar plugin that runs the one validated recipe for the user's GPU
and hands the served model to every installed coding agent. The user sees a
model name, Start/Stop, an agent selector, and a Tailscale share toggle.
Everything else is automatic and refuses out loud: hardware match, download,
launch, acceptance, agent wiring, rollback.

Three parts, one job:

- **Registry** (data, `0xSero/local-ai-registry`): validates one recipe per
  hardware id on the exact card and exports the file the plugin vendors.
- **Controller** (bash, `bin/omarchy-local-ai` + `lib/`): turns that recipe
  into a running, verified container and reports state.
- **Panel** (QML, `Panel.qml`): renders the snapshot and issues the verbs.

## Scope (Sero, 2026-09-02)

Single GPU. NVIDIA and Intel Arc Pro B70. Five models by VRAM tier, 4-bit,
128K context everywhere and 256K where it fits, EXL3 on TabbyAPI or SGLang
ahead of llama.cpp:

| Tier | Model | Engine | Context |
|---|---|---|---|
| 8 to 10 GB | lfm2.5-2.6B bf16 | SGLang | 128K |
| 12 GB | Qwen3.5-9B EXL3 4bpw | TabbyAPI | 128K |
| 16 to 20 GB | Qwen3.5-9B EXL3 4bpw | TabbyAPI | 256K |
| 24 GB | Gemma-4-12B-it EXL3 4bpw | TabbyAPI | 128K |
| 32 GB and up | Qwen3.8-27B EXL3 4bpw (Qwen3.6-35B alternate) | TabbyAPI | 256K |
| B70 32 GB | Qwen3.8-27B Q4_K_M | llama.cpp SYCL | 128K |

Multi-GPU, AMD, and Mac follow once this ships. Target: PRs updated
2026-09-03, ready for review 2026-09-05.

## Decided

### 1.1 Registry data is vendored, not fetched
The registry build (`scripts/export_plugin_recipes.py`) emits `recipes.json`:
validated, recommended, single-GPU docker recipes, joined flat, keyed by
hardware id, stamped with the registry commit. Committed into the plugin; it
replaces `registry.pin`. No git or network at runtime for recipe data. The
safety gate still runs on every load. A sync step regenerates the file and
CI checks it matches the commit it claims.

### 1.2 Exact hardware id, one recipe per card
Each entry carries its own match data: backend, VRAM, normalized product
names. The export fails on two recommended recipes for one card
(`scripts/recommend.py` keeps exactly one by the tier map). No tier or family
inference in the plugin. A card not in the file is unsupported, and the panel
says so.

### 1.3 Coverage comes from validation on rented cards
`scripts/validate_rented.py` rents the exact card on Vast.ai, runs the
recipe's own digest-pinned image, materializes weights and config
in-container where the plugin would bind-mount them, runs the registry's
acceptance, and promotes. 34 hardware ids validated as of 2026-09-03 (branch
`runpod-validation`, worktree `~/local-registry/registry-runpod`, unpushed).
Missing: RTX 3080 12 GB (no rental stock), Intel B60 and DGX Spark (need
real hardware), RTX 2000 Ada's tier model (no stock; covered by its lfm
fallback).

### 1.4 Self-built, attested images where upstream cannot run the recipe
`0xSero/local-ai-images`, one directory per image, built only by a workflow
with BuildKit provenance, SBOM, and a GitHub build attestation. First image
`tabbyapi-exl3`: upstream TabbyAPI digest plus python3-dev, because Triton
cannot JIT ExLlamaV3's gated-delta-net kernels without Python.h. Recipes pin
the digest and carry `launch.provenance` linking the run.

## The vendored file contract (`recipes.json`)

Per hardware id: `match {backend, vramGb, names[]}` and `recipe`:

- `id`, `model {id, name, repository, revision, servedName, precision, sizeGb}`
- `engine`, `capabilities`, `serving {ctxTokens, concurrency}`, `speed {tps}`
- `weights.subdir`: where the download goes under a `${MODEL_ROOT}` mount
  (TabbyAPI loads `<mount>/<model_name>`)
- `image {provenance, attestation}`
- `launch {image, containerPort, entrypoint, arguments, environment, mounts,
  shm, ipc, networkMode, capAdd, securityOpt}`
- `validated {harness, acceptedAt}`

Mount sources are one of: `${MODEL_ROOT}/<dir>` (plugin downloads the
instance there, read-only into the container), `~/.cache/huggingface` (the
engine fetches into the shared HF cache), `asset/<file>` (registry asset,
must be shipped with the file; not yet exported, see open item 3c).

## Findings that constrain the runtime

- **CPU fallback looks like success.** A host whose driver cannot init the
  image's CUDA serves from the CPU at under 1 tok/s while every health check
  passes. Acceptance needs a decode floor; launch needs a driver check.
- **Images pin a CUDA version, cards pin a driver.** The SGLang image is CUDA
  12.9, TabbyAPI cu13 with forward-compat, llama.cpp newer than 12.4. The
  recipe must declare the minimum driver and the plugin must gate on it.
- **TabbyAPI weights layout is part of the contract** (`weights.subdir`).
  The old plugin put files at the mount root and could never have started a
  TabbyAPI recipe.
- **Host networking is refused by the gate**; all V1 recipes are bridge.
- **RunPod cannot pull ghcr.io images**; Vast can. Irrelevant to users,
  relevant to validation.

## Open, bottom-up, with recommendations

### 2. Ledger and lock
Persist one tiny JSON: current op `{name, recipeId, pid, startedAt, detail,
percent}`, `error`, `lastAccepted {recipeId, servedModel}`. Written only by a
worker holding `flock` on a file whose fd is closed in every child (the old
orphaned-lock bug). "Busy" derives from the op's pid being alive, never from
a string. Nothing derived lives in the ledger.

### 3. Runtime
- 3a Weights: the plugin downloads for every recipe (`hf download` into
  `${MODEL_ROOT}/<dir>/<subdir>` or into the HF cache), writes a marker with
  the revision after a verified download; presence is the marker, not a byte
  heuristic. Containers never download.
- 3b Driver gate: `recipe.minDriver` in the export (from the image's
  `NVIDIA_REQUIRE_CUDA`), checked against `nvidia-smi` before launch.
- 3c Assets: config assets are exported inline (base64) in `recipes.json`
  and written to a plugin-owned path at launch, mounted read-only.
- 3d Acceptance: `/v1/models` matches, one completion, tool call when the
  recipe claims tools, and decode ≥ one fifth of the recipe's recorded speed.
- 3e Rollback stays: previous container set aside, restored on failure.
- 3f The B70 path (render nodes, SYCL) stays as built.

### 4. Snapshot
**Detection of an already-running recipe is agreed (2026-09-03):** the
container carries labels `io.omarchy.local-ai=1`, `.recipe=<id>`, and
`.registry=<commit>`. On every snapshot the controller finds owned
containers by label, reads the recipe id from the label, probes
`/v1/models`, and reports ready without touching it, even if that recipe is
no longer in the vendored file (then: "running <id> from an older registry;
Stop to update"). Weights already present, from a previous run or placed by
hand, are found by the idempotent download step, not re-fetched. A container
on the port without our label is never touched and is reported as
"port busy: not managed by this plugin".

A pure function of ledger + reality (container state, `/v1/models`,
tailscale, installed agents) + `recipes.json`. Never stored, never mutated
during a read. State rule: op pid alive → busy; else error in ledger → error;
else container running and API answering → ready; else container running →
starting; else idle. Fields: state, error, model (name, sizeGb, downloaded)
or `reason` why none, operation, share, agents. About a dozen fields.

### 5. Agents: launch-only (agreed 2026-09-03)
The local model reaches an agent only when the agent is launched from the
panel. The controller passes the endpoint by environment variables and
flags at launch; nothing on disk is edited, so nothing has to be restored,
and an agent typed in a terminal keeps its own provider. Stop kills the
container; running agent sessions lose their endpoint and say so. The
agent selector lists installed agents whose API dialect the running engine
serves (see open item 5a).

### 5a. One gateway, always, for every engine (agreed 2026-09-03)
Every launch is two owned containers: the engine on an internal port and
the **gateway** on the plugin's port (127.0.0.1:12434), from a tiny attested
image in `local-ai-images`. The gateway serves OpenAI chat completions,
Anthropic Messages, and OpenAI Responses and translates all of them,
including tool calls and streaming, to the engine's chat completions. It
runs for every engine, no per-engine special cases, so every agent and the
Tailscale share talk to one endpoint with one behavior. Codex needs
Responses; it no longer works over chat. Acceptance probes all three
dialects through the gateway; an agent whose dialect fails is hidden from
the selector. The gateway shares the engine's labels, lifecycle, and
rollback. The registry validates engine plus gateway as one recipe.

### 5b. Tailscale share is keyed, auto-configured, user-changeable (agreed 2026-09-03)
Loopback is keyless. The first Share generates a random key, stores it in the
plugin's state directory (mode 600), and the gateway, which reads the key
file on each request, requires it as `Authorization: Bearer` or `x-api-key`
for any non-loopback request. The share dialog shows the URL and the key;
`share --key <value>` (and a panel field) replaces it without a restart.
Stop sharing turns `tailscale serve` off; the key stays for next time.

### 6. Commands
Exactly `snapshot`, `load`, `unload`, `open-agent [name]`, `share`. Drop
`download`, `run`, `switch`, `remove`, `default`, `scan`. Workers log to
`$STATE/log`.

### 7. Panel
Unchanged in shape. Add the "no model for this card" reason and the driver
refusal text. Poll less: snapshot is cheap once it is a pure read.

### 8. Repo hygiene
Bash + QML as before; the same isolated shim tests; `make sync` pulls
`recipes.json` from a registry commit and CI diffs it. Design doc is this
file; CONTEXT.md is retired into it.

## Status 2026-09-03

Built. Plugin on branch `v4` of `0xSero/omarchy-local-ai` (draft PR), registry
on `runpod-validation` (draft PR), gateway and TabbyAPI images attested in
`0xSero/local-ai-images`. Not yet run on real hardware: the Omarchy box is
held by a GLM-5.3 job. Open items: live run, gateway re-validation per engine
family (in progress), driver floors are per image family rather than measured.
