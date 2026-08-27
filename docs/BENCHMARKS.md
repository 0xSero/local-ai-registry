# Benchmark registry

The benchmark registry answers two separate questions: what an evaluation is, and which score a source reports for a model artifact. Keeping those as separate records prevents a leaderboard number from becoming an unsupported claim about every quantization of a model.

## Data graph

```text
benchmark/<benchmark-id>.json
  definition, source link, reproducible command, runner contract, coverage
    |
    +-- benchmark-run/<model-instance-id>--<benchmark-id>.json
          score, protocol, source model card, provenance
          model_id          -> model/<model-id>.json
          model_instance_id -> model-instance/<model-instance-id>.json
```

A benchmark definition has the fields requested by all clients:

- `name`: human-readable evaluation name.
- `link`: the benchmark catalog page used to inspect its reported results.
- `command`: the stable Local AI CLI command for running it against a selected model instance.
- `coverage.model_count`: canonical models with a sourced score.
- `coverage.model_instance_count`: model instances to which direct or inherited scores are attached.
- `coverage.benchmark_run_count`: total direct and inherited records.
- `runner`: whether an automated runner is available, its task name, implementation link, and command template.

The remaining fields make the definition useful without guessing: stable ID, category, aliases, metric semantics, description, and source provenance.

## Direct and inherited scores

`score_origin: "direct"` means the score's model-card repository exactly matches the selected registry model instance. Its `inherited_from` value must be `null`.

`score_origin: "inherited"` means the source reports the score for the same canonical model or another registered artifact, not for this exact quantization. `inherited_from` identifies the origin repository and, when present, its registry model instance and direct run record.

An inherited record is a discovery aid, not evidence that the selected artifact was evaluated. Clients must label it inherited and keep its source link visible. Scores from a related model family, a similarly named repository, or an unverified descendant are not inherited.

Protocol fields can be `null` when a source model card did not state them. Missing protocol detail is not silently inferred. Compare scores only when their benchmark, protocol, and source context are compatible.

## Running a benchmark

List definitions and inspect coverage:

```bash
bin/local-ai benchmark list
bin/local-ai benchmark show mmlu-pro
bin/local-ai benchmark runs mmlu-pro
```

Print the resolved command without executing it:

```bash
bin/local-ai benchmark command mmlu-pro <model-instance-id>
```

Run an automated definition against an OpenAI-compatible local endpoint:

```bash
LOCAL_AI_BASE_URL=http://127.0.0.1:8000/v1/chat/completions \
  bin/local-ai benchmark run mmlu-pro <model-instance-id>
```

The CLI refuses to invent a command for a definition whose runner is `manual`. It prints the reference protocol URL instead. An available runner requires `lm-eval` and resolves the selected instance's served model name into the reviewed command template.

## Importing the catalog

The source catalog is [`0xSero/hf-model-benchmarks`](https://github.com/0xSero/hf-model-benchmarks), published at [`0xsero.github.io/hf-model-benchmarks`](https://0xsero.github.io/hf-model-benchmarks/). The importer reads its language and speech indexes, matches exact Hugging Face repositories to registered model instances, and selects 100 benchmark families by:

1. Number of canonical registry models with scores.
2. Number of source-catalog model roots with scores.
3. Benchmark name as a deterministic tie-breaker.

```bash
python3 scripts/import_benchmark_catalog.py \
  --source ~/projects/hf-model-benchmarks \
  --registry registry \
  --limit 100
python3 scripts/curate_registry.py --index-only
python3 scripts/validate_registry.py
```

The generated definitions retain the source repository commit and capture time. Each score links back to the exact Hugging Face model card from which the catalog extracted it. `terminal-bench` values that are evidently version identifiers rather than scores are rejected during import.

## Contributing a benchmark definition

Create `registry/benchmark/<benchmark-id>.json` and validate it against `registry/schema/benchmark.schema.json`. Submit:

- A stable lowercase ID and human name.
- Category and short factual description.
- A primary benchmark, paper, or maintained implementation link.
- A Local AI wrapper command.
- Runner status, framework, exact task name, implementation URL, and executable template when automation is verified.
- Metric name, unit, and direction.
- Coverage derived from committed run records.
- URLs, capture timestamps, and immutable source revisions where available.

Use `runner.status: "manual"`, `task: null`, and `command_template: null` until the command has been checked against the maintained runner. A plausible task name is not sufficient.

## Contributing a benchmark run

Create `registry/benchmark-run/<model-instance-id>--<benchmark-id>.json` and validate it against `registry/schema/benchmark-run.schema.json`. Submit:

- Existing benchmark, canonical model, and model-instance IDs.
- Numeric score, metric, unit, and direction.
- `direct` or `inherited` origin with a valid inheritance pointer.
- Protocol name, version, split, shot count, and relevant details, using `null` for facts the source does not state.
- Direct model card, research paper, or leaderboard result URL.
- Reported source model identity and capture time.
- Provenance entries sufficient to reproduce how the record entered the registry.

Do not submit a score copied from a search snippet, an uncited table, or a model with only a similar name. Do not relabel inherited results as direct. Do not fill unknown protocol fields from memory.

Before opening a pull request:

```bash
python3 scripts/curate_registry.py --index-only
python3 scripts/validate_registry.py
npm test
npm run typecheck
npm run build
```
