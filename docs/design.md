# Local AI Registry: design

Status: proposal, 2026-09-25, revised the same day. Two rules drive it:

- **Nothing is deleted.** The repository holds two systems. **Data** (`registry/`) keeps everything it has today: 3,049 recipes and observations, sweeps, models, builds, hardware, prices and benchmarks. It feeds the website and research. **Production** (`engines/`, `recipes/`, `dist/`) is small, and it is the only thing programs read.
- **A recipe is output, not input.** Nobody writes one. `lab/lab.py try` runs a model on a card, checks it, and writes the recipe only if every gate passes. A recipe is about 600 bytes: the pinned weights, a pinned engine profile, the settings that differ from the profile's defaults, the card, and the proof. The full launch is rendered from the profile.

A production recipe, as the lab writes it:

```json
{"model":"qwen3.5-9b","weights":"TheMelonGod/Qwen3.5-9B-exl3@22ef1303062e0f6d0b282440f8c1f685947f4938",
 "engine":"tabbyapi-exl3@0f83e6198dc3","set":{"ctx":65536,"draft":"mtp"},"card":"rtx-3070-8gb",
 "proof":[{"at":"2026-09-25","on":"vast","gpu":"RTX 3070","gates":"load chat reasoning tools context speed",
           "tps":61.2,"prefill":1450,"served":"Qwen3.5-9B-exl3-22ef1303","log":"sha256:…"}]}
```

- **`engine`:** a profile in `engines/` (image digest, entrypoint, arguments, config template, defaults), pinned by the first 12 characters of its image digest. Changing a profile's image makes every recipe that names the old digest fail `lab.py check` until it is run again.
- **`proof`:** the latest three passing runs, newest first. The full evidence of every run, passed or failed, is kept in `lab/runs/`, which is data.
- **Confirmation:** anyone who runs the same recipe on the same card adds a proof. A recipe with proofs from two different hosts is confirmed.

The rest of this document is the longer version. Where it describes records and fields for data, those stay in `registry/` as they are; production uses only the recipe above, the profiles, the cards (`registry/hardware/`) and `lab/models.json`.

## 1. What the registry is

The registry answers one question for a program that runs models: **on this GPU, which models can I run, and exactly how?** Every answer it gives has been run on that GPU (or, flagged, on its twin) and passed the same checks.

It is not:
- **a measurement database:** community speed runs belong to [LocalMaxxing](https://www.localmaxxing.com), and the registry links to them;
- **an image or recipe source:** engines and launch profiles come from [Local Inference Lab](https://github.com/local-inference-lab) and [0xSero/local-ai-images](https://github.com/0xSero/local-ai-images), and the registry imports a profile only as a candidate to validate;
- **a price site:** hardware and price data stay, as reference, but nothing is chosen by them.

Consumers:
- the Omarchy Local AI panel (upstream `omarchy-local-ai`, and the `sero.local-ai` plugin);
- the Local Studio controller and its setup wizard;
- Local AI for Linux (`local-ai`);
- the website.

They all read the same published catalog (section 6).

## 2. The objects

Six record types. Ids are lowercase, `-` inside a name and `.` between parts, and never change once published.

| Record | One record is | Id | Typical size | Count (target) |
|---|---|---|---|---|
| **card** | a GPU kind a program can detect | `rtx-3090-24gb` | 0.5 KB | ~40 (NVIDIA, AMD, Intel; Apple kept as data only) |
| **model** | a released model | `qwen3.8-27b` | 0.5 KB | ~15 |
| **build** | one exact set of weight files | `qwen3.8-27b.exl3-6.0-h6` | 1 KB | ~30 |
| **recipe** | one runnable server: a build, an engine image and its config | `qwen3.8-27b.exl3-6.0-h6.tabbyapi.256k-x8` | 2 KB | ~40 |
| **run** | one validation of one recipe on one card | `<recipe>@<card>.<yyyymmdd>` | 3 KB | ~150 |
| **pick** | the ranked recipes for one card (derived) | `<card>` | 0.3 KB | ~40 |

The records are described below, and section 6 describes the published catalog.

### card
- **Fields:**
  - `vendor`: nvidia, amd or intel (apple is data only);
  - `backend`: nvidia, amd-rocm or intel-xpu;
  - `vram_gb` and `bandwidth_gb_s`;
  - `compute`: `sm_86` for NVIDIA, `gfx1100` for AMD, `xe2` for Intel;
  - `match`: what a program sees, i.e. the names nvidia-smi, amd-smi or lspci report, plus the VRAM, which tells the 8 GB and 16 GB versions of a 5060 Ti apart.
- **Laptops:** a laptop part is its own card (`rtx-4060-laptop-8gb`). It has a different power limit, so its speed is not the desktop part's.

### model
- **Fields:**
  - `family`;
  - `org`;
  - `released`: the Hugging Face creation date of the original repo, following `base_model` links;
  - `params` and `active_params`;
  - `reasoning`: whether the model thinks;
  - `vision`;
  - `license`.
- **Kind:** instruct or chat models only. Base models are never published.

### build
- **Fields:**
  - `model`;
  - `repo` and `revision` (40 hex characters, never a branch name);
  - `format`: EXL3, GGUF, NVFP4, FP8, AWQ or BF16;
  - `precision`: for example `6.0 bpw, 6-bit head`;
  - `files`: every file's name, byte size and sha256, which is the Hub's LFS oid;
  - `bytes`: the total;
  - `draft`: the draft or MTP head, if any.
- **Downloads:** a program downloads exactly these files and checks every hash.

### recipe
The unit a program launches. It is not tied to a card: the same recipe runs on every card that has a passing run.

- **Fields:**
  - `build`, plus an optional draft build;
  - `engine`: the name (`tabbyapi`, `vllm`, `sglang`, `llama.cpp`) and its version;
  - `image`: `registry/name@sha256:…`, digest-pinned and with an attestation where we build it;
  - `launch`: entrypoint, arguments, environment, and at most one config file (inline text plus its sha256 and the path it is mounted at);
  - `serving`: `context` (tokens per sequence), `sequences`, `cache` (dtype and total tokens) and `cards` (how many cards of one kind, the tensor-parallel size);
  - `needs`: `backend`, `min_vram_gb` per card, `compute` (minimum and maximum) and `min_driver`;
  - `capabilities`: chat, reasoning, tools, vision. Each is `true` only if the run gates check it.
- **Weight:**
  - about 2 KB, including the config file;
  - its downloads are the build's `bytes`, plus the image once per engine.
- **Id:** `<build>.<engine>.<context>-x<sequences>`, with `-tp<cards>` added when `cards` is more than 1.

### run
One validation of one recipe on one card: the only way anything becomes published.

- **Fields:**
  - `recipe`, `card` and `date`;
  - `where`:
    - `provider`: local, vast, runpod or owner;
    - `gpu`: the exact name the driver reported;
    - `driver` and `host`;
    - `proxy`: see section 4;
  - `harness`: its version and the sha256 of the log;
  - `gates`: pass or fail for each, with the evidence;
  - `speed`: decode and prefill tokens per second and time to first token, at the contexts and concurrencies in section 4;
  - `peak_vram_gb`.
- **Speed source:** speed comes from runs only. Nothing else in the registry stores a speed.

### pick
Derived, never hand-edited. For each card, at most three recipes, ranked, one per model; the first is the recommended one. Section 5 gives the rules.

### What production leaves out (it stays in data)
- **Launch kinds:** `reference`, `docker-compose`, `script`, `native`, `controller` and `host`. There is one launch shape: a container.
- **Records:** the 2,707 reference observations and the unvalidated candidates stay in `registry/` and are never read by programs.
- **Fields and duplicates:**
  - `draft_launch`;
  - the `facts` boilerplate (53% of a recipe's bytes today);
  - three of the five context fields and three of the speed copies;
  - `recommended` as a stored flag;
  - `index/recommendations.json`;
  - the benchmark scrapes.

## 3. How a recipe runs

Every consumer runs a recipe the same way. The contract:

1. **Weights:** download the build's files into `<models>/<build>/` and check every sha256. Mount that directory read-only at `/models`.
2. **Config:** write the recipe's config file and mount it read-only at its path.
3. **Container:** start the image with the recipe's entrypoint, arguments and environment:
   - bridge network only;
   - no host IPC, no added capabilities, `no-new-privileges`;
   - `shm` as the recipe says;
   - the engine listens on `launch.port`.
4. **Cards:**
   - NVIDIA: `--gpus device=<index,…>`;
   - AMD: `/dev/kfd` plus the cards' render nodes;
   - Intel: the cards' render nodes and their by-path links.

   The recipe never names cards; the program chooses them.
5. **Gateway:** put the gateway in front (`ghcr.io/0xsero/gateway@sha256:…`). It holds the key and speaks the OpenAI Chat, Anthropic Messages and OpenAI Responses APIs.
6. **Ready:** the recipe is up when `/v1/models` lists `served_name`.

Docker and rootless Podman both satisfy this. A recipe that needs anything outside it (host networking, a script, a build from source) is not a recipe.

## 4. Validation

- **One harness:** `scripts/validate.py <recipe> --card <card> --on local|vast|runpod`. It runs the section 3 contract (in-container on rented hosts, where the weights are placed by the same downloader) and writes a run record.
- **Automatic retries:** none. A failed run is written too, with `passed: false`.

### Gates
All must pass for a recipe to be published on a card:

| Gate | What it checks |
|---|---|
| **load** | Ready within 30 minutes; `peak_vram_gb` at most the card's VRAM minus 0.5 GB |
| **chat** | Three fixed prompts answered through all three gateway APIs, each ending with a stop reason |
| **reasoning** | A reasoning model returns its thinking separately (`reasoning_content` or thinking blocks) and a correct final answer to a fixed arithmetic question. Templates or flags that turn thinking off fail. |
| **tools** | A forced tool call parses into a valid call with the right arguments, and the tool result is used in the reply |
| **vision** | Only if claimed: the text in a generated image is read back |
| **context** | A fact planted at 90% of `context` is recalled |
| **speed** | Decode at concurrency 1 on an empty prompt, and at 32k where `context` is 32k or more, is at least 15 tok/s. Also at full concurrency. |

### Proxy runs
- **When:** a card that no provider rents and no owner has run (for example the RTX 5060 8GB, the 5060 Ti 8GB and every laptop part) may be validated on its twin.
- **Twin:** the same chip or the next one up, with engine memory capped to the card's VRAM.
- **Labelling:** the run carries `proxy: {on: "rtx-5060-ti-16gb", method: "vram-cap"}`, and every consumer shows "tested on a sibling card".
- **Replacement:** a run on the real card replaces it.

### Freshness
A run stops counting when any of these happens:
- the recipe's image, build revision or config changes;
- the model passes the age limit (section 5);
- it is more than 180 days old. The nightly job then lists the recipe for a rerun.

## 5. What gets published, and how many

The curation policy. `scripts/policy.py --check` runs it in CI; every rule is a function there, not prose.

1. **Cards:** NVIDIA, AMD and Intel GPUs that a consumer can detect. Apple cards and prices stay as data, with no recipes until an MLX path passes the same gates on a Mac.
2. **Models:**
   - released within the last **8 months**;
   - instruct or chat;
   - from the prioritized families: **Qwen, Gemma, DeepSeek, GLM (Z.ai), Step, Kimi and MiniMax**. Adding a family is a one-line change reviewed like any other.
   - **Superseded:** a model is dropped when a newer model of the same family and size class has a passing run on the same card.
3. **Recipes:** a recipe is published on a card only if its latest run there passed every gate. Reasoning models run with reasoning on.
4. **Picks:** for each card, at most **3** recipes and one per model, ranked by:
   1. family priority, in the order above;
   2. newest model;
   3. highest precision that fits;
   4. decode at concurrency 1.

   The first is recommended.
5. **Coverage goal:** every supported NVIDIA card has at least one **EXL3 Qwen** recipe in its pick, and every AMD and Intel card has at least one recipe.

Projection from `main` today: 59 of the 153 validated recipes meet rules 1–3, on 25 cards; the picks hold 42. They use 25 distinct launches, 11 of which already run unchanged on more than one card. Eleven NVIDIA cards (every 8 GB card, the 3080 10GB, the RTX 2000 Ada and the RTX PRO 6000) have no EXL3 Qwen recipe yet; their candidates are written and waiting for runs.

## 6. How programs get it

**Published files:** generated in CI from the records, on every merge to `main`.

| File | For | Size |
|---|---|---|
| `dist/catalog.json` | Everything a program needs to choose and run: cards (with `match`), picks, and the recipes and builds they use, inlined | ~150 KB |
| `dist/cards/<card>.json` | One card's pick, self-contained | ~5 KB |
| `dist/schema/catalog.schema.json` | The contract | — |

**Versioning and integrity:**
- `catalog.json` carries `schema: "local-ai-registry/catalog/3"`, the registry commit and a sha256 of its own body.
- A consumer vendors a copy when it is released, and may fetch a newer one from `https://raw.githubusercontent.com/0xSero/local-ai-registry/<commit>/dist/catalog.json`. It accepts it only if the schema major matches.

**API:** the website serves the same data at `/api/v2`, with the same shapes. It covers cards, models, builds, recipes, runs, picks, and `/api/v2/pick?gpu=<name>&vram=<gb>` for detection. `/api/v1` keeps answering for 90 days, from the new records, for Local Studio.

**Consumers:**
- **Omarchy panel and plugin:** read `catalog.json`. The v1 and v2 plugin files keep being generated from the new records until the plugin moves to catalog 3, so nothing installed breaks.
- **Local Studio:** reads `/api/v2/pick` for its setup wizard and `catalog.json` for its model list, and launches through the section 3 contract.
- **Local AI for Linux:** vendors `catalog.json`, as the Omarchy plugin does.

## 7. Jobs in the repository

| Job | When | What it does |
|---|---|---|
| `check` | every push and PR | Schemas; references; `policy.py --check`; `dist/` is current; every recipe's image digest exists and is attested where we build it; every build revision exists on the Hub. The API tests run too, and so does the build. |
| `drift` | nightly | Finds model ages past the limit, new commits on build repos, newer images of the same tag, and runs older than 180 days. Opens one PR that drops what aged out and one issue listing what needs a rerun. |
| `discover` | weekly | New models from the prioritized orgs and new EXL3, NVFP4 and GGUF builds of them (turboderp, the orgs' own quants). Writes candidate recipes into an issue. |
| `validate` | manual, with a card and a recipe | Rents the card (Vast first, then RunPod), runs the harness, and opens a PR with the run. It has a monthly spend cap. |

## 8. Migration

1. **Land the lab:** `engines/`, `lab/lab.py`, `lab/catalog.py`, `lab/models.json`, an empty `recipes/`, and CI running `lab.py check` and `catalog.py --check`. Nothing in `registry/` changes, and the plugin v1 and v2 files keep being generated from it.
2. **Fill production by running:** production starts empty and fills only through `lab.py try`. The first runs are EXL3 Qwen on every NVIDIA card (the 22 that have a legacy recipe are re-run through the new gates, and the 11 that don't get their first), then AMD and Intel.
3. **Switch the exports:** once production covers every card the plugin supports, `plugin/v2/recipes.json` is generated from `dist/catalog.json` instead of `registry/`, so installed plugins move over without an update.
4. **Consumers:** the plugin, Local AI for Linux and Local Studio read `dist/catalog.json` (or `/api/v2`). `/api/v1` keeps serving `registry/` for as long as anyone uses it.

## 9. Open decisions

- Whether the AMD Ryzen AI NPU (`xdna2-krackan-16gb`, FastFlowLM) stays. It is not a GPU and it needs a host process, which breaks section 3.
- Whether Local Inference Lab's GLM and DeepSeek images count as "we build it" for attestation, or are pinned by digest only.
- Whether proxy runs may be recommended, or only listed.
