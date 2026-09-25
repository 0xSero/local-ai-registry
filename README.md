# Local AI registry

The model to run on your GPU, and exactly how to run it. Every recipe here is the output of a run that passed six checks on that card: it loads, chats, reasons, calls tools, holds its context window, and decodes at 15 tok/s or more.

```
cards/<vendor>/<card>.json                     a GPU: name, memory, how programs detect it
engines/<profile>.json                         an engine: pinned image, arguments, config
recipes/<vendor>/<card>/<model>.<engine>.<context>k.json
                                               one recipe (~400 bytes): weights, engine, settings, proof
dist/catalog.json                              everything above in one file, at most 3 picks per card
plugin/v2/recipes.json                         the same, in the Omarchy Local AI plugin's format
lab/                                           the tools that run, check and publish recipes
docs/design.md                                 how it works and why
```

The data behind it (every model, build, hardware record, price, benchmark and community measurement) is in [local-ai-data](https://github.com/0xSero/local-ai-data).

## A recipe

`recipes/nvidia/rtx-3070-ti-8gb/qwen3.5-9b.tabbyapi.64k.json`:

```json
{"model":"qwen3.5-9b","weights":"TheMelonGod/Qwen3.5-9B-exl3@22ef1303062e0f6d0b282440f8c1f685947f4938",
 "engine":"tabbyapi-exl3@0f83e6198dc3","set":{"ctx":65536,"draft":"mtp"},"card":"rtx-3070-ti-8gb",
 "proof":[{"at":"2026-09-25","on":"vast","gpu":"RTX 3070 Ti","gates":"load chat reasoning tools context speed",
           "tps":105.3,"prefill":1485,"served":"Qwen3.5-9B-exl3-22ef1303","log":"sha256:6fc6fe2e6f2cead9"}]}
```

- `weights`: a Hugging Face repo at a full commit.
- `engine`: a profile in `engines/`, pinned to its image digest.
- `set`: only the settings that differ from the profile's defaults.
- `proof`: the latest passing runs. A proof marked `proxy` was run on the sibling card it names; one marked `legacy` passed the older acceptance (load and chat) and is waiting for a full run.

`python3 lab/lab.py render <recipe>` prints the full launch: image, arguments, config file, weights location, port.

## Running a recipe

Every program runs one the same way:

1. Download the weights at the pinned commit.
2. Write the config file.
3. Start the image on a bridge network with the card passed through (`--gpus` on NVIDIA, the render node on AMD and Intel).
4. Put the [gateway](https://github.com/0xSero/local-ai-images) in front, which serves the OpenAI, Anthropic and Responses APIs.

## Adding or updating a recipe

Recipes are never written by hand. Run one:

```bash
python3 lab/lab.py try <repo>@<commit> --model <id> --engine tabbyapi-exl3 --card <card> --set ctx=65536 --set draft=mtp
```

`try` rents the card on Vast (or RunPod, or `--on endpoint --endpoint <url>` for your own machine), runs the six checks, writes the recipe only if all pass, and destroys the machine. `lab.py convert <card>` re-runs a `legacy` recipe the same way. Then `make` and open a pull request; CI runs `make check`.

## Using it

- **Omarchy Local AI** reads `plugin/v2/recipes.json`.
- **Anything else** reads `dist/catalog.json`: `cards.<card>.picks` lists recipe keys, first one recommended, and `recipes.<key>.launch` is the rendered launch.
