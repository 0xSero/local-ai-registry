#!/usr/bin/env python3
"""Recover missing benchmark contexts from immutable Hugging Face model cards.

The matrix scrape retains exact Markdown evidence but sometimes loses the column
header or clips the row inside a cell. This script follows the matrix's exact
model-page link, resolves that repository's current 40-character Hugging Face
revision, and accepts a context only when the immutable README has one exact
evidence-prefix occurrence and an unambiguous benchmark/score mapping.
Ambiguous or unavailable evidence stays null.
"""

import argparse
import html
import hashlib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


MANIFEST_VERSION = "local-ai-registry/hf-benchmark-context-evidence/v1"
DEFAULT_MANIFEST = "docs/notes/hf-benchmark-contexts.json"
USER_AGENT = "local-ai-registry-benchmark-context-enricher/1.0"
NUMBER_RE = re.compile(r"(?<![A-Za-z0-9])[-+]?(?:\d+(?:\.\d+)?|\.\d+)(?![A-Za-z0-9])")
SEPARATOR_RE = re.compile(r"^:?-+:?$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
BENCHMARK_ALIASES = {
    "aime-2024": ("aime24",),
    "aime-2025": ("aime25",),
    "aime-2026": ("aime26",),
    "bbh": ("BigBench-Hard",),
    "cer": ("Mandarin (Avg CER%)",),
    "chatbot-arena": ("Arena-Hard", "ArenaHard-v2"),
    "commonsenseqa": ("JCommonsenseQA",),
    "if-eval": ("M-ifeval", "MM-IFEval"),
    "mt-bench": ("MT-Bench", "MT_Bench"),
    "math-olympiad": ("Olympiad Bench",),
    "quality": ("Audio Quality", "PBench Quality Score"),
    "rtf": ("Real-Time Factor", "RT factor"),
    "speaker-sim": ("Speaker Similarity", "Speaker SIM", "SIM", "ZH - SIM"),
    "wer": ("Average WER", "Avg WER", "CV WER", "CV18 (WER)", "Mean WER", "Published WER", "ZH - WER"),
    "wer-ami": ("AMI", "AMI Test IHM", "AMI WER"),
    "wer-common-voice": ("Common Voice", "CommonVoice 8 (Japanese test set.)"),
    "wer-earnings22": ("Earnings22",),
    "wer-fleurs": ("FLEURS", "Khmer (`fleurs`)"),
    "wer-gigaspeech": ("GigaSpeech",),
    "wer-librispeech": (
        "English (`librispeech.clean`)",
        "LibriSpeech",
        "LibriSpeech test-clean",
        "LS test-clean",
        "librispeech_test_clean",
    ),
    "wer-multilibri": ("MLS",),
    "wer-spgispeech": ("SPGISpeech",),
    "wer-tedlium": ("Tedlium",),
    "wer-voxpopuli": ("VoxPopuli", "voxpopuli_v1.0_en"),
}


def json_dump(value):
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def strip_html(value):
    return html.unescape(re.sub(r"<[^>]+>", "", value)).strip()


def parse_cells(row_html):
    return [strip_html(cell) for cell in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row_html, re.S | re.I)]


def parse_matrix_rows(page):
    text = page.read_text()
    tables = re.findall(r"<table[^>]*>(.*?)</table>", text, re.S | re.I)
    if not tables:
        return {}
    result = {}
    for row_html in re.findall(r"<tr[^>]*>(.*?)</tr>", tables[0], re.S | re.I):
        cells = parse_cells(row_html)
        if len(cells) != 7 or not cells[0].isdigit():
            continue
        href = re.search(r'href=["\']\.\./models/([^"\']+\.html)["\']', row_html, re.I)
        if not href:
            continue
        score_text = cells[4].rstrip("*").strip()
        if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", score_text):
            continue
        result[int(cells[0])] = {
            "rank": int(cells[0]),
            "variant": cells[1],
            "root": cells[2],
            "org": cells[3],
            "score": float(score_text),
            "conf": cells[5],
            "context": cells[6] or None,
            "model_page": href.group(1),
        }
    return result


def parse_model_page(page, benchmark_id, expected_score):
    text = page.read_text()
    repo_match = re.search(
        r'class=["\'][^"\']*hf-link[^"\']*["\'][^>]*href=["\']https://huggingface\.co/([^"\']+)["\']',
        text,
        re.I,
    )
    if not repo_match:
        return None
    repo = html.unescape(repo_match.group(1)).strip("/")
    if repo.count("/") != 1:
        return None

    matches = []
    for table_html in re.findall(r"<table[^>]*>(.*?)</table>", text, re.S | re.I):
        for row_html in re.findall(r"<tr[^>]*>(.*?)</tr>", table_html, re.S | re.I):
            link = re.search(r'href=["\']\.\./benchmarks/([^"\']+)\.html["\']', row_html, re.I)
            if not link or link.group(1) != benchmark_id:
                continue
            cells = parse_cells(row_html)
            if len(cells) != 6:
                continue
            try:
                score = float(cells[2])
            except ValueError:
                continue
            if not equivalent_score(score, expected_score):
                continue
            evidence = re.search(r"<code[^>]*>(.*?)</code>", row_html, re.S | re.I)
            if evidence:
                matches.append(html.unescape(strip_html(evidence.group(1))))
    unique = sorted(set(matches))
    if not unique:
        return None
    return {"repo": repo, "evidence_rows": unique}


def equivalent_score(left, right):
    pairs = ((left, right), (left * 100.0, right), (left, right * 100.0))
    return any(abs(a - b) <= max(0.005, abs(b) * 1e-9) for a, b in pairs)


def markdown_cells(line, allow_unterminated=False):
    value = line.strip()
    terminated = value.endswith("|")
    if not value.startswith("|") or (not terminated and not allow_unterminated):
        return None
    content = value[1:-1] if terminated else value[1:]
    cells = []
    current = []
    escaped = False
    for char in content:
        if escaped:
            current.append(char)
            escaped = False
        elif char == "\\":
            current.append(char)
            escaped = True
        elif char == "|":
            cells.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    cells.append("".join(current).strip())
    return cells


def plain_context(value):
    value = re.sub(r"!?(?:\[([^]]*)\])\([^)]*\)", r"\1", value)
    value = re.sub(r"<[^>]+>", "", value)
    value = value.replace("+", " plus ")
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def benchmark_keys(records):
    result = {}
    for benchmark_id, record in records.items():
        keys = {
            plain_context(benchmark_id),
            plain_context(record.get("name") or ""),
            *(plain_context(alias) for alias in BENCHMARK_ALIASES.get(benchmark_id, ())),
        }
        result[benchmark_id] = {key for key in keys if key}
    return result


def header_matches_benchmark(header, benchmark_id, key_map):
    normalized = plain_context(header)
    own = key_map[benchmark_id]
    own_matches = {key for key in own if normalized == key or normalized.startswith(key)}
    contained_aliases = {
        alias
        for value in BENCHMARK_ALIASES.get(benchmark_id, ())
        if len(alias := plain_context(value)) >= 5 and alias in normalized
    }
    own_matches.update(contained_aliases)
    direct_token = (
        "-" not in benchmark_id
        and re.search(
            rf"(?<![A-Za-z0-9]){re.escape(benchmark_id)}(?![A-Za-z0-9])",
            strip_html(header),
            re.IGNORECASE,
        )
        is not None
    )
    if direct_token:
        return True
    if not own_matches and not direct_token:
        return False
    best_own = max(map(len, own_matches)) if own_matches else len(plain_context(benchmark_id))
    for other_id, keys in key_map.items():
        if other_id == benchmark_id:
            continue
        if any(normalized == key or normalized.startswith(key) for key in keys if len(key) > best_own):
            return False
    return True


def cell_matches_score(cell, score):
    values = [float(value) for value in NUMBER_RE.findall(cell.replace(",", ""))]
    return any(equivalent_score(value, score) for value in values)
def recover_plain_context(readme, evidence, benchmark_id, score, key_map):
    value = evidence.strip()
    if not value or readme.count(value) != 1:
        return None
    match = re.fullmatch(
        r"[*_`\s]*(?P<label>.+?)\s*[:=]\s*[*_`\s]*"
        r"(?P<score>[-+]?(?:\d+(?:\.\d+)?|\.\d+)%?)[*_`\s]*",
        value,
    )
    if not match:
        score_matches = [
            candidate
            for candidate in NUMBER_RE.finditer(value)
            if equivalent_score(float(candidate.group()), score)
        ]
        if len(score_matches) != 1:
            return None
        score_match = score_matches[0]
        suffix = value[score_match.end() :].strip()
        if suffix and not re.fullmatch(r"[%*_`~\s\]\[().,:;+\-/×x]*", suffix):
            return None
        label = value[: score_match.start()].strip(" *_`").rstrip(" :=-")
        if not label or not header_matches_benchmark(label, benchmark_id, key_map):
            return None
        return label
    label = match.group("label").strip(" *_`").rstrip(" :=")
    if not header_matches_benchmark(label, benchmark_id, key_map):
        return None
    if not cell_matches_score(match.group("score"), score):
        return None
    return label




def normalized_markdown_cell(value):
    value = html.unescape(value)
    value = re.sub(r"!?\[([^]]*)\]\([^)]*\)", r"\1", value)
    value = re.sub(r"<[^>]+>", "", value)
    value = re.sub(r"\\([\\`*_{}\[\]()#+\-.!|])", r"\1", value)
    value = re.sub(r"[*_`~]+", "", value)
    return re.sub(r"\s+", " ", value).strip().casefold()


def normalized_evidence_matches_cells(cells, evidence_cells, evidence_is_prefix):
    normalized_cells = [normalized_markdown_cell(cell) for cell in cells]
    normalized_evidence = [normalized_markdown_cell(cell) for cell in evidence_cells]
    if not evidence_is_prefix:
        return normalized_cells == normalized_evidence
    if len(normalized_cells) < len(normalized_evidence):
        return False
    return (
        normalized_cells[: len(normalized_evidence) - 1] == normalized_evidence[:-1]
        and normalized_cells[len(normalized_evidence) - 1].startswith(normalized_evidence[-1])
    )


def evidence_matches_cells(cells, evidence_cells, evidence_is_prefix):
    if not evidence_is_prefix:
        return cells == evidence_cells
    if len(cells) < len(evidence_cells):
        return False
    return (
        cells[: len(evidence_cells) - 1] == evidence_cells[:-1]
        and cells[len(evidence_cells) - 1].startswith(evidence_cells[-1])
    )


def recover_context(readme, evidence_row, benchmark_id, score, key_map):
    evidence_cells = markdown_cells(evidence_row, allow_unterminated=True)
    if not evidence_cells:
        return recover_plain_context(readme, evidence_row, benchmark_id, score, key_map)
    evidence_is_prefix = not evidence_row.strip().endswith("|")
    lines = readme.splitlines()
    occurrences = [
        (index, cells)
        for index, line in enumerate(lines)
        if (cells := markdown_cells(line))
        and evidence_matches_cells(cells, evidence_cells, evidence_is_prefix)
    ]
    if not occurrences:
        occurrences = [
            (index, cells)
            for index, line in enumerate(lines)
            if (cells := markdown_cells(line))
            and normalized_evidence_matches_cells(cells, evidence_cells, evidence_is_prefix)
        ]
    if not occurrences:
        return None
    contexts = set()
    resolved_occurrences = 0
    for row_index, row_cells in occurrences:
        separator_index = None
        for index in range(row_index - 1, max(-1, row_index - 200), -1):
            cells = markdown_cells(lines[index])
            if cells and all(SEPARATOR_RE.fullmatch(cell.replace(" ", "")) for cell in cells):
                separator_index = index
                break
            if not cells and lines[index].strip():
                break
        if separator_index is None or separator_index == 0:
            continue
        headers = markdown_cells(lines[separator_index - 1])
        if headers and len(row_cells) == len(headers) + 1:
            row_cells = row_cells[:-1]
        if not headers or len(headers) != len(row_cells):
            continue
        candidates = [
            header
            for header, cell in zip(headers, row_cells)
            if header_matches_benchmark(header, benchmark_id, key_map) and cell_matches_score(cell, score)
        ]
        if len(candidates) == 1:
            contexts.add(candidates[0].strip())
            resolved_occurrences += 1
        elif not candidates:
            benchmark_cells = [
                cell
                for cell in row_cells
                if header_matches_benchmark(cell, benchmark_id, key_map)
            ]
            score_cells = [cell for cell in row_cells if cell_matches_score(cell, score)]
            if len(benchmark_cells) == 1 and len(score_cells) == 1:
                contexts.add(benchmark_cells[0].strip())
                resolved_occurrences += 1
    if len(contexts) != 1 or resolved_occurrences != len(occurrences):
        return None
    return next(iter(contexts))


def fetch_url(url, accept="text/plain"):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.read().decode("utf-8")
        except urllib.error.HTTPError as error:
            if error.code not in {429, 500, 502, 503, 504} or attempt == 3:
                raise
        except (TimeoutError, urllib.error.URLError):
            if attempt == 3:
                raise
        time.sleep(2**attempt)
    raise RuntimeError("unreachable")


def fetch_model_card(repo, cache_dir):
    cache_path = cache_dir / f"{hashlib.sha256(repo.encode('utf-8')).hexdigest()}.json"
    if cache_path.exists():
        try:
            cached = json.loads(cache_path.read_text())
            if (
                cached.get("repo") == repo
                and isinstance(cached.get("revision"), str)
                and SHA_RE.fullmatch(cached["revision"])
                and isinstance(cached.get("readme_url"), str)
                and isinstance(cached.get("readme"), str)
            ):
                return cached["revision"], cached["readme_url"], cached["readme"]
        except (OSError, ValueError, TypeError):
            pass

    encoded_repo = "/".join(urllib.parse.quote(part, safe="") for part in repo.split("/"))
    api_url = f"https://huggingface.co/api/models/{encoded_repo}"
    metadata = json.loads(fetch_url(api_url, "application/json"))
    revision = metadata.get("sha")
    if not isinstance(revision, str) or not SHA_RE.fullmatch(revision):
        raise ValueError(f"{repo}: API did not return a 40-character revision")
    readme_url = f"https://huggingface.co/{encoded_repo}/resolve/{revision}/README.md"
    readme = fetch_url(readme_url)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json_dump({"readme": readme, "readme_url": readme_url, "repo": repo, "revision": revision})
    )
    return revision, readme_url, readme


def load_records(root):
    records = {}
    paths = {}
    for path in sorted((root / "benchmark").glob("*.json")):
        record = json.loads(path.read_text())
        records[record["id"]] = record
        paths[record["id"]] = path
    return records, paths


def row_matches_manifest(row, entry):
    return (
        row.get("rank") == entry.get("rank")
        and row.get("variant") == entry.get("variant")
        and row.get("score") is not None
        and equivalent_score(float(row["score"]), float(entry["score"]))
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("matrix", nargs="?", default=str(Path.home() / "projects/hf-model-benchmarks"))
    parser.add_argument("--root", default="registry")
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--cache-dir", default="cache/hf-benchmark-cards")
    parser.add_argument("--repos-file")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    matrix = Path(args.matrix)
    root = Path(args.root)
    manifest_path = Path(args.manifest)
    cache_dir = Path(args.cache_dir)
    manifest_ref = manifest_path.as_posix()
    records, record_paths = load_records(root)
    key_map = benchmark_keys(records)

    prior_entries = []
    if manifest_path.exists():
        prior = json.loads(manifest_path.read_text())
        if prior.get("schema_version") != MANIFEST_VERSION:
            raise ValueError(f"unsupported manifest schema in {manifest_path}")
        prior_entries = prior.get("entries", [])

    changed_benchmarks = set()
    accepted_by_key = {}
    for entry in prior_entries:
        benchmark_id = entry.get("benchmark_id")
        record = records.get(benchmark_id)
        if not record:
            continue
        rows = [row for row in record["rows"] if row.get("rank") == entry.get("rank")]
        if len(rows) != 1 or not row_matches_manifest(rows[0], entry):
            continue
        row = rows[0]
        if row.get("context") is None:
            row["context"] = entry["context"]
            changed_benchmarks.add(benchmark_id)
        if row.get("context") == entry.get("context"):
            accepted_by_key[(benchmark_id, entry["rank"])] = entry

    candidates = []
    local_rejections = 0
    for benchmark_id, record in records.items():
        evidence_rows = [
            row
            for row in record["rows"]
            if row.get("context") is None
            or (
                manifest_ref in (record.get("source") or {}).get("paths", [])
                and (benchmark_id, row.get("rank")) not in accepted_by_key
            )
        ]
        if not evidence_rows:
            continue
        matrix_path = matrix / "benchmarks" / f"{benchmark_id}.html"
        if not matrix_path.is_file():
            local_rejections += len(evidence_rows)
            continue
        matrix_rows = parse_matrix_rows(matrix_path)
        for row in evidence_rows:
            matrix_row = matrix_rows.get(row["rank"])
            if (
                row.get("context") is not None
                and matrix_row
                and matrix_row.get("context") is not None
            ):
                continue
            expected = {key: row.get(key) for key in ("rank", "variant", "root", "org", "conf")}
            observed = {key: matrix_row.get(key) for key in expected} if matrix_row else None
            score_ok = matrix_row and equivalent_score(float(matrix_row["score"]), float(row["score"]))
            if observed != expected or not score_ok or matrix_row.get("context") is not None:
                local_rejections += 1
                continue
            model_page = matrix / "models" / matrix_row["model_page"]
            if not model_page.is_file():
                local_rejections += 1
                continue
            model_evidence = parse_model_page(model_page, benchmark_id, float(row["score"]))
            if not model_evidence:
                local_rejections += 1
                continue
            candidates.append({
                "benchmark_id": benchmark_id,
                "rank": row["rank"],
                "score": row["score"],
                "variant": row["variant"],
                "model_page": str(model_page.relative_to(matrix)),
                **model_evidence,
            })
    if args.repos_file:
        allowed_repos = set(json.loads(Path(args.repos_file).read_text()))
        candidates = [candidate for candidate in candidates if candidate["repo"] in allowed_repos]


    if args.limit is not None:
        candidates = candidates[: args.limit]

    cards = {}
    fetch_errors = {}
    repos = sorted({candidate["repo"] for candidate in candidates})
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        futures = {executor.submit(fetch_model_card, repo, cache_dir): repo for repo in repos}
        for future in as_completed(futures):
            repo = futures[future]
            try:
                cards[repo] = future.result()
            except Exception as error:
                fetch_errors[repo] = f"{type(error).__name__}: {error}"

    recovered = 0
    ambiguous = 0
    for candidate in candidates:
        card = cards.get(candidate["repo"])
        if not card:
            continue
        revision, readme_url, readme = card
        resolved_contexts = [
            recover_context(
                readme,
                evidence_row,
                candidate["benchmark_id"],
                float(candidate["score"]),
                key_map,
            )
            for evidence_row in candidate["evidence_rows"]
        ]
        if any(context is None for context in resolved_contexts):
            context = None
        else:
            unique_contexts = set(resolved_contexts)
            context = next(iter(unique_contexts)) if len(unique_contexts) == 1 else None
        if context is None:
            ambiguous += 1
            continue
        record = records[candidate["benchmark_id"]]
        rows = [row for row in record["rows"] if row.get("rank") == candidate["rank"]]
        if len(rows) != 1 or rows[0].get("context") not in (None, context):
            continue
        if rows[0].get("context") is None:
            rows[0]["context"] = context
            changed_benchmarks.add(candidate["benchmark_id"])
        entry = {
            "benchmark_id": candidate["benchmark_id"],
            "context": context,
            "evidence_row": candidate["evidence_rows"][0],
            "model_page": candidate["model_page"],
            "rank": candidate["rank"],
            "readme_url": readme_url,
            "repo": candidate["repo"],
            "revision": revision,
            "score": candidate["score"],
            "variant": candidate["variant"],
        }
        accepted_by_key[(candidate["benchmark_id"], candidate["rank"])] = entry
        recovered += 1

    for benchmark_id in changed_benchmarks:
        paths = records[benchmark_id]["source"].setdefault("paths", [])
        if manifest_ref not in paths:
            paths.append(manifest_ref)
            paths.sort()

    manifest = {
        "schema_version": MANIFEST_VERSION,
        "entries": sorted(accepted_by_key.values(), key=lambda item: (item["benchmark_id"], item["rank"])),
    }
    if not args.dry_run:
        for benchmark_id in sorted(changed_benchmarks):
            record_paths[benchmark_id].write_text(json_dump(records[benchmark_id]))
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json_dump(manifest))

    print(
        json.dumps(
            {
                "ambiguous_or_nonmatching": ambiguous,
                "candidates": len(candidates),
                "changed_benchmarks": len(changed_benchmarks),
                "fetch_errors": fetch_errors,
                "local_rejections": local_rejections,
                "manifest_entries": len(manifest["entries"]),
                "recovered": recovered,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
