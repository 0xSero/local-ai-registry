# Contributing

Everything in `registry/` is data. A contribution is a pull request that adds or corrects records and passes `make check`. Read [docs/system.md](docs/system.md) first (five minutes).

## Setup

```bash
git clone https://github.com/0xSero/local-ai-registry
cd local-ai-registry
npm ci
make check
```

Python 3.10+ (stdlib only) and Node 24.

## Add hardware

Create `registry/hardware/<chip>-<memory>.json` from `registry/schema/hardware.schema.json`. The id is chip plus memory capacity, never a product name. Put product names in `aliases` and retail SKUs in `products`. State `accelerator_backend`, `memory.capacity_gb`, `memory.bandwidth_gbps` when sourced, and a `provenance` source for every number. Unknown stays absent or `null`, never guessed.

## Add a model or artifact

`registry/model/<id>.json` for the base model; `registry/model-instance/<id>.json` for each downloadable quantization. `revision` must be the full Hugging Face commit hash. `huggingface.link_type` is `repository` for an exact repo or `search` for an explicit fallback; never derive one from the other. `scripts/import_hf_models.py` fills most of this from the Hub.

## Add a recipe

1. Copy the closest existing recipe or run `scripts/clone_candidate.py`.
2. Set `hardware_id`, `hardware_count`, `model_instance_id`, `engine`, `serving.max_context_tokens`, `capabilities`.
3. Write the `launch`: `kind: docker`, digest-pinned `image` with `provenance`, argv `arguments`, `environment`, `mounts`, both ports, `accelerator_backend`, `network_mode: bridge`. No shell strings.
4. Leave `status` out or set `candidate`. **You cannot set `validated`.** It is derived.
5. `make index && make check`.

## Validate a recipe

Run it on the exact hardware and record the acceptance:

```bash
python3 scripts/accept_recipe.py <recipe-id> --endpoint http://127.0.0.1:<port>/v1
# or, on a rented card:
python3 scripts/validate_rented.py <recipe-id>
```

`accept_recipe.py` checks the served model id, a real completion, a tool call if claimed, measures decode, and writes a `speed-sweep` with `source.kind: acceptance-run` plus `metadata.acceptance` on the recipe. Then:

```bash
make trust    # status becomes validated because the evidence now proves it
make index
make check
```

If `make trust` leaves the recipe as `candidate`, `python3 scripts/trust.py` prints the exact reasons. Fix the record, not the status.

## Recommend a recipe

`recommended` is chosen by `scripts/recommend.py`, one per hardware id. To change a recommendation, change the inputs it ranks on (tier map, engine rank, context, acceptance date) and run it. The validator refuses two recommended recipes on one card.

## Import external evidence

Importers under `scripts/import_*.py` normalize LocalMaxxing, local.ai publications, Hugging Face, and price snapshots into candidates and metadata. Imported observations are always `candidate` with `launch.kind: reference`. Record the snapshot hash in `docs/PROVENANCE.md`.

## Pull request checklist

- `make check` passes locally.
- Every new number has a `provenance` source with a URL and `captured_at`.
- No hand-edited files under `registry/index/` or `registry/schema/types.ts`; both are generated.
- The PR description says what was run on what hardware, with the command.

## Rules that will fail review

- A `validated` status typed by hand.
- A launch with a shell string, a mutable image tag, host networking, or eager-mode flags.
- A benchmark number without the workload that produced it.
- Guessing a generation, a memory size, or a capability. `null` with a reason is correct.
