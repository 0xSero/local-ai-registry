# Design

The registry answers one question for a program: on this GPU, which model should I run, and exactly how? It holds only what has been run and checked. The data behind it lives in [local-ai-data](https://github.com/0xSero/local-ai-data).

## Four kinds of file

| File | What it is | Written by |
|---|---|---|
| `cards/<vendor>/<card>.json` | A GPU: name, vendor, backend, memory, bandwidth, and the `match` block programs use to recognise it | Hand, rarely |
| `engines/<profile>.json` | An engine: pinned image, entrypoint, arguments, environment, port, config file. A template profile (`tabbyapi-exl3`, `vllm`, `sglang`, `sglang-exl3`) has `defaults` a recipe can change; a frozen profile is a launch exactly as it was validated before the lab, or as its publisher runs it | Hand, reviewed |
| `recipes/<vendor>/<card>/<model>.<engine>.<ctx>k[.<n>x].json` | A recipe: weights at a commit, a profile pinned to its image digest, settings that differ from the profile's defaults, the card, and the proof | `lab/lab.py` only |
| `dist/catalog.json`, `plugin/v2/recipes.json` | Everything above, rendered, with at most 3 picks per card | `make` |

`lab/models.json` names each model (family, release date) and each build's size and format.

## A recipe is output

`lab.py try` runs weights on a card and writes the recipe only if all six gates pass:

| Gate | Passes when |
|---|---|
| load | The server lists the model within an hour |
| chat | A plain question gets an answer that ends on its own |
| reasoning | The thinking comes back separately and 17 × 23 is answered 391 |
| tools | A weather tool is called with the right city, and its result is used in the reply |
| context | A code planted in a prompt filling ~85% of the window is recalled |
| speed | Decode over the first 30 seconds of an answer is at least 15 tok/s |

No answer is ever capped; each runs to its natural end. The full evidence of every run goes to `lab/runs/` and then to `lab-runs/` in the data repo; the recipe keeps a hash of it.

A proof may carry:
- `proxy: <card>`: run on a sibling card, because nobody rents this one.
- `legacy: true`: the recipe passed the older acceptance (load and chat only). `lab.py convert` re-runs it through all six gates.
- `reported: true`: someone else published the launch and its numbers (`src` names their repo at a commit; `claims` what they say it does). `lab/import_reported.py` brings these in from `data/reported/<source>/`. Our gates have not run; a lab run replaces it.

A recipe for several computers ends in `.<n>x` and its profile says `machines: n`. A profile may also name `flags` (host networking or IPC), a `build` (an image built from a source's Dockerfile at a commit), `setup` (what the source needs outside the container) and `source`.

A new proof from another host on the same recipe confirms it.

## What gets picked

For each card, `catalog.py` keeps at most three recipes, one per model, ranked by: lab proof over legacy over reported, then family order (Qwen, Gemma, DeepSeek, GLM, Step, Kimi, MiniMax), newest model, and decode speed. A model older than 240 days is dropped. The first pick is the recommended one. Every other recipe for the card is listed after the picks (`more`), best first. See [data.md](data.md) for where recipes come from.

## Running a recipe

`lab.py render <recipe>` gives the full launch. Every program:
1. downloads the weights at the pinned commit;
2. writes the config file;
3. starts the image on a bridge network, with no host IPC and no added capabilities, passing the card through;
4. puts the Local AI gateway in front.

## Rules CI enforces

- Every recipe is at its path, with weights pinned to a commit and a profile pinned to an image digest.
- Every recipe's latest proof passed all six gates, or is marked `legacy`, or is `reported` with its source.
- `dist/catalog.json` and `plugin/v2/recipes.json` are current.
