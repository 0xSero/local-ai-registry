# Local AI Registry

A hardware-aware registry of local model artifacts, launch recipes, and measured speed. The standalone registry is data first: clients can read it from disk, serve it as static JSON, or resolve it over any static HTTP host.

## Start here

[`registry/index.json`](registry/index.json) is the only discovery document a client needs. It contains collection IDs and compact recipe rows for filtering. Fetch full records only after the user chooses something.

```text
index.json
  recipe/<id>.json
    model_instance_id  -> model-instance/<id>.json
      model_id         -> model/<id>.json
    hardware_id        -> hardware/<id>.json
    speed_sweeps_ids[] -> speed-sweeps/<id>.json
```

This is the progressive-disclosure rule: index, choice, recipe, then the exact records that recipe references. There is no recursive tree endpoint and no duplicated embedded model or hardware object.

## Collections

| Collection | Meaning | Current count |
|---|---|---:|
| `hardware/` | One accelerator or Apple chip and memory configuration | 98 |
| `model/` | One canonical base model | 69 |
| `model-instance/` | One downloadable artifact or quantization | 207 |
| `recipe/` | One artifact × hardware × engine compatibility unit | 250 |
| `speed-sweeps/` | Benchmark evidence attached to one recipe | 234 |

The shared contract is defined twice for different consumers: JSON Schema files under [`registry/schema/`](registry/schema/) and TypeScript interfaces in [`registry/schema/types.ts`](registry/schema/types.ts).

## Trust boundary

`validated` means the model revision and runtime are pinned and the launch contract has acceptance evidence. `candidate` means the registry has useful compatibility or speed evidence but cannot yet promise a reproducible launch.

LocalMaxxing imports are always `candidate` and `launch.kind: "reference"`. Their human-supplied commands are deliberately not copied into the executable contract. Promotion requires a separately curated, pinned recipe and a real completion plus speed acceptance.

## Hardware coverage

The hardware collection covers Apple M1 through M5 families at their supported memory tiers, including Pro, Max, and the Ultra generations Apple has actually shipped. It also includes GeForce RTX 30/40/50 cards, NVIDIA workstation accelerators, four current AMD local-AI targets, Intel Arc workstation cards, and the existing audited server/workstation classes.

Apple product names are discovery aliases; compatibility keys are chip plus unified-memory capacity. A generic LocalMaxxing label such as `Apple Max 128GB` remains explicitly generation-unspecified instead of being guessed into an M-series generation.

## Validate

```bash
python3 scripts/curate_registry.py
python3 scripts/validate_registry.py
```

The validator checks IDs, references, counts, status boundaries, pinned validated artifacts, positive evidence values, and the CUDA-graph policy. `curate_registry.py` is deterministic and rebuilds the compact index after data changes.

## Source layout

`registry/` is the new normalized contract. `local-ai/` is the earlier denormalized dataset retained temporarily for the existing local Omarchy playground consumer and its newer live-machine evidence. It is not the schema for new imports.

Data provenance and recovery decisions are in [`docs/PROVENANCE.md`](docs/PROVENANCE.md). The behavior-only product prompt for a registry browser is in [`docs/UI_BEHAVIOR_PROMPT.md`](docs/UI_BEHAVIOR_PROMPT.md).

## License

MIT
