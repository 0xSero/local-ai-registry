#!/usr/bin/env python3

import argparse
import datetime as dt
import json
import math
import subprocess
from collections import Counter, defaultdict
from pathlib import Path


SCHEMA = "local-ai-registry/v1"
SOURCE_REPO = "https://github.com/0xSero/hf-model-benchmarks"
SOURCE_PAGES = "https://0xsero.github.io/hf-model-benchmarks"
LM_EVAL_REPO = "https://github.com/EleutherAI/lm-evaluation-harness"
LM_EVAL_TASKS = {
    "agieval": "agieval",
    "aime-2024": "aime24",
    "aime-2025": "aime25",
    "arc": "arc_challenge",
    "bbh": "bbh_cot_fewshot",
    "boolq": "boolq",
    "ceval": "ceval-valid",
    "cmmlu": "cmmlu",
    "commonsenseqa": "commonsense_qa",
    "drop": "drop",
    "gpqa": "gpqa_diamond_cot_zeroshot",
    "gpqa-diamond": "gpqa_diamond_cot_zeroshot",
    "gpqa-extended": "gpqa_extended_cot_zeroshot",
    "gpqa-main": "gpqa_main_cot_zeroshot",
    "gsm8k": "gsm8k",
    "hellaswag": "hellaswag",
    "humaneval": "humaneval",
    "if-eval": "ifeval",
    "infinitebench": "infinitebench",
    "legalbench": "legalbench",
    "longbench": "longbench",
    "math": "hendrycks_math",
    "mbpp": "mbpp",
    "medqa": "medqa_4options",
    "mmlu": "mmlu",
    "mmlu-pro": "mmlu_pro",
    "mmlu-pro-math": "mmlu_pro_math",
    "musr": "leaderboard_musr",
    "openbookqa": "openbookqa",
    "piqa": "piqa",
    "ruler": "ruler",
    "triviaqa": "triviaqa",
    "winogrande": "winogrande",
}
LOWER_IS_BETTER = {
    "cer",
    "rtf",
    "tts-wer",
    "wer",
    "wer-ami",
    "wer-common-voice",
    "wer-earnings22",
    "wer-fleurs",
    "wer-gigaspeech",
    "wer-librispeech",
    "wer-multilibri",
    "wer-spgispeech",
    "wer-switchboard",
    "wer-tedlium",
    "wer-voxpopuli",
}


def load_records(directory):
    return {path.stem: json.loads(path.read_text()) for path in sorted(directory.glob("*.json"))}


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def repository(record):
    identity = record.get("huggingface") or {}
    return identity.get("repository")


def source_revision(source):
    try:
        return subprocess.check_output(
            ["git", "-C", str(source), "rev-parse", "HEAD"],
            text=True,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def usable_score(benchmark_id, scores):
    value = scores.get(benchmark_id)
    if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        return None
    if benchmark_id == "terminal-bench" and value <= 3:
        return None
    return value


def model_source_rows(models, instances, rows):
    variants = defaultdict(list)
    for row in rows:
        variants[row[0].lower()].append(row)

    by_model = defaultdict(list)
    for instance in instances.values():
        by_model[instance["model_id"]].append(instance)

    selected = {}
    for model_id, model in models.items():
        repos = []
        for candidate in [repository(model), *(repository(item) for item in by_model[model_id])]:
            if candidate and candidate not in repos:
                repos.append(candidate)
        candidates = []
        for repo in repos:
            candidates.extend(variants.get(repo.lower(), []))
        if candidates:
            selected[model_id] = max(candidates, key=lambda row: (len(row[5]), row[0].lower() in {repo.lower() for repo in repos}))
    return selected, by_model


def benchmark_catalog(source):
    benchmarks = {}
    rows = []
    for filename in ("benchmarks.data.json", "speech.data.json"):
        value = json.loads((source / filename).read_text())
        for benchmark in value["b"]:
            benchmarks[benchmark["id"]] = benchmark
        rows.extend(value["r"])
    return benchmarks, rows


def global_coverage(rows):
    roots = defaultdict(set)
    for row in rows:
        for benchmark_id in row[5]:
            if usable_score(benchmark_id, row[5]) is not None:
                roots[benchmark_id].add(row[3] or row[0])
    return {benchmark_id: len(models) for benchmark_id, models in roots.items()}


def command_for(benchmark_id, task):
    wrapper = f"local-ai benchmark run {benchmark_id} --model-instance <model-instance-id>"
    if task is None:
        return wrapper, None
    command = (
        "lm-eval run --model local-chat-completions "
        "--model_args model={served_model},base_url={base_url},num_concurrent=1,max_retries=3 "
        f"--tasks {task} --apply_chat_template --output_path ./benchmark-results/{benchmark_id}"
    )
    return wrapper, command


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", default="registry")
    parser.add_argument("--source", default=str(Path.home() / "projects" / "hf-model-benchmarks"))
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()

    root = Path(args.registry)
    source = Path(args.source)
    captured_at = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    revision = source_revision(source)
    models = load_records(root / "model")
    instances = load_records(root / "model-instance")
    benchmark_source, rows = benchmark_catalog(source)
    selected_rows, instances_by_model = model_source_rows(models, instances, rows)
    global_counts = global_coverage(rows)

    registry_counts = Counter()
    for row in selected_rows.values():
        for benchmark_id in row[5]:
            if usable_score(benchmark_id, row[5]) is not None:
                registry_counts[benchmark_id] += 1

    ranked = sorted(
        benchmark_source,
        key=lambda benchmark_id: (
            -registry_counts[benchmark_id],
            -global_counts.get(benchmark_id, 0),
            benchmark_source[benchmark_id]["name"].lower(),
        ),
    )[: args.limit]
    selected_benchmarks = set(ranked)

    benchmark_dir = root / "benchmark"
    run_dir = root / "benchmark-run"
    benchmark_dir.mkdir(exist_ok=True)
    run_dir.mkdir(exist_ok=True)
    for path in benchmark_dir.glob("*.json"):
        path.unlink()
    for path in run_dir.glob("*.json"):
        path.unlink()

    runs = []
    for model_id, row in selected_rows.items():
        source_repository = row[0]
        root_repository = row[3]
        model_instances = sorted(instances_by_model[model_id], key=lambda item: item["id"])
        direct_instance = next(
            (
                item for item in model_instances
                if (repository(item) or "").lower() == source_repository.lower()
            ),
            None,
        )
        for benchmark_id in sorted(selected_benchmarks.intersection(row[5])):
            score = usable_score(benchmark_id, row[5])
            if score is None:
                continue
            direct_id = f"{direct_instance['id']}--{benchmark_id}" if direct_instance else None
            for instance in model_instances:
                is_direct = direct_instance is not None and instance["id"] == direct_instance["id"]
                run_id = f"{instance['id']}--{benchmark_id}"
                higher = benchmark_id not in LOWER_IS_BETTER
                run = {
                    "schema_version": SCHEMA,
                    "id": run_id,
                    "benchmark_id": benchmark_id,
                    "model_id": model_id,
                    "model_instance_id": instance["id"],
                    "score": {
                        "value": score,
                        "metric": "reported_score",
                        "unit": "points",
                        "higher_is_better": higher,
                    },
                    "score_origin": "direct" if is_direct else "inherited",
                    "inherited_from": None if is_direct else {
                        "model_id": model_id,
                        "source_model_repository": root_repository or source_repository,
                        "source_model_instance_id": direct_instance["id"] if direct_instance else None,
                        "benchmark_run_id": direct_id,
                    },
                    "protocol": {
                        "name": benchmark_source[benchmark_id]["name"],
                        "version": None,
                        "split": None,
                        "shots": None,
                        "details": "Protocol details were not structured in the source model card; compare only with runs that cite the same source.",
                    },
                    "source": {
                        "kind": "model-card",
                        "url": f"https://huggingface.co/{source_repository}",
                        "reported_model": source_repository,
                        "captured_at": captured_at,
                    },
                    "provenance": {
                        "sources": [
                            {
                                "kind": "model-card-index",
                                "url": SOURCE_REPO,
                                "commit": revision,
                                "captured_at": captured_at,
                            },
                            {
                                "kind": "model-card",
                                "url": f"https://huggingface.co/{source_repository}",
                                "captured_at": captured_at,
                            },
                        ],
                        "captured_at": captured_at,
                    },
                }
                write(run_dir / f"{run_id}.json", run)
                runs.append(run)

    runs_by_benchmark = defaultdict(list)
    for run in runs:
        runs_by_benchmark[run["benchmark_id"]].append(run)

    for benchmark_id in ranked:
        benchmark = benchmark_source[benchmark_id]
        task = LM_EVAL_TASKS.get(benchmark_id)
        command, command_template = command_for(benchmark_id, task)
        benchmark_runs = runs_by_benchmark[benchmark_id]
        direct = sum(run["score_origin"] == "direct" for run in benchmark_runs)
        inherited = len(benchmark_runs) - direct
        implementation = (
            f"{LM_EVAL_REPO}/tree/main/lm_eval/tasks"
            if task else f"{SOURCE_PAGES}/benchmarks/{benchmark_id}.html"
        )
        record = {
            "schema_version": SCHEMA,
            "id": benchmark_id,
            "name": benchmark["name"],
            "category": benchmark["cat"],
            "description": f"{benchmark['name']} is tracked as a {benchmark['cat']} evaluation reported by registered model sources.",
            "link": f"{SOURCE_PAGES}/benchmarks/{benchmark_id}.html",
            "aliases": sorted({benchmark_id, benchmark["name"]}),
            "command": command,
            "runner": {
                "status": "available" if task else "manual",
                "framework": "lm-evaluation-harness" if task else "reference-protocol",
                "task": task,
                "implementation_url": implementation,
                "command_template": command_template,
            },
            "metric": {
                "name": "reported_score",
                "unit": "points",
                "higher_is_better": benchmark_id not in LOWER_IS_BETTER,
            },
            "coverage": {
                "model_count": len({run["model_id"] for run in benchmark_runs}),
                "model_instance_count": len({run["model_instance_id"] for run in benchmark_runs}),
                "benchmark_run_count": len(benchmark_runs),
                "direct_run_count": direct,
                "inherited_run_count": inherited,
            },
            "provenance": {
                "sources": [
                    {
                        "kind": "benchmark-catalog",
                        "url": SOURCE_REPO,
                        "commit": revision,
                        "captured_at": captured_at,
                    },
                    {
                        "kind": "benchmark-page",
                        "url": f"{SOURCE_PAGES}/benchmarks/{benchmark_id}.html",
                        "captured_at": captured_at,
                    },
                ],
                "captured_at": captured_at,
            },
        }
        write(benchmark_dir / f"{benchmark_id}.json", record)

    print(
        f"benchmarks={len(ranked)} benchmark-runs={len(runs)} "
        f"models-with-scores={len({run['model_id'] for run in runs})} "
        f"instances-with-scores={len({run['model_instance_id'] for run in runs})}"
    )


if __name__ == "__main__":
    main()
