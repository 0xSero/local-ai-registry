#!/usr/bin/env python3
"""Long-context content checks (§3.6) + the pre-grid preflight gate.

Prompts are built with the model's OWN local tokenizer on the pod (the mounted
pinned revision), NOT a server tokenize route. Source review (ExperimentAudit's
librarian, pinned tags) showed the server route is a dead end or silently wrong
on add_generation_prompt for all three engines: SGLang's /tokenize accepts
messages but ignores add_generation_prompt (serving_chat hardcodes it); vLLM
honours it; TabbyAPI's /v1/token/encode HARD-FORCES add_generation_prompt=False.
So an instruct model would be asked to continue a user turn with no assistant
cue. The local tokenizer applies the native pinned chat template correctly and
gives exact ids incl BOS.

Three modes, run ON THE POD against the served OpenAI endpoint:

  gate     - ONE window-sized C1 cold full-horizon request + ONE needle, verdict:
               * pass (rc 0, preflight-ok.json) - clean measurement + needle hit.
               * measurement-invalid (rc 1, preflight-failed.json) - the run
                 cannot be trusted: finish_reason_not_length, prompt_token_mismatch
                 (engine re-tokenised/truncated behind us), missing/non-monotonic
                 timestamps, or ttft_over_threshold. Each carries a specific code;
                 TTFT breach carries cause "unknown" (host/engine/model/window are
                 never distinguished). NOT a host verdict, NOT rerollable by claim.
               * retrieval-fail (rc 2, preflight-format-failed.json) - host served
                 cleanly but the needle was not retrieved, OR the tokenizer has no
                 chat template so no native template could be applied (a bare
                 continuation is refused, never measured).
             Both nonzero verdicts abort the grid (no grid, no wasted cost).
  needle   - needle-in-haystack at 5 depths (5/25/50/75/95 %). Writes needle.json.
  multihop - one two-fact question needing both facts. Writes multihop.json.

The window is "served" only when the horizon request decodes to the cap
(finish_reason == "length", verified) AND usage.prompt_tokens == the token ids we
sent (no silent truncation). Retrieval is scored by exact NUMERIC-BOUNDARY match
of the seeded value (surrounding prose tolerated). The gate records the resolved
chat-template sha256, the tokenizer path and the id counts so the first paid run
leaves proof the local path did what we think.

Local tokenizer requires transformers in-image (confirmed by ImageDelivery) and
the mounted model dir; loaded local_files_only=True, trust_remote_code only when
explicitly requested for a pinned model that needs it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import time
from collections.abc import Mapping
import urllib.request
from pathlib import Path

DEPTHS = (0.05, 0.25, 0.50, 0.75, 0.95)
FILLER = ("The archive records routine maintenance notes across many quiet quarters "
          "with no incident of consequence to report in this section of the log. ")


class TemplateUnavailable(Exception):
    pass


def _post(url: str, payload: dict | None, timeout: float, stream: bool = False):
    data = b"" if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(
        url, data=data, headers={"content-type": "application/json"}, method="POST"
    )
    response = urllib.request.urlopen(request, timeout=timeout)
    return response if stream else json.loads(response.read())


def _score(expected: str, actual: str) -> bool:
    """Exact numeric-boundary match: the value must not be embedded in a longer
    number. Reasoning/prose around it is tolerated."""
    return re.search(rf"(?<!\d){re.escape(expected)}(?!\d)", actual) is not None


def load_tokenizer(model_dir: str, trust_remote_code: bool):
    """The model's own tokenizer from the mounted pinned revision (no network)."""
    from transformers import AutoTokenizer  # in-image dependency, confirmed by ImageDelivery
    return AutoTokenizer.from_pretrained(
        model_dir, local_files_only=True, trust_remote_code=trust_remote_code
    )


def chat_template_sha(tok) -> str | None:
    template = getattr(tok, "chat_template", None)
    if not template:
        return None
    return hashlib.sha256(template.encode()).hexdigest()


def pool_from(tok, minimum: int) -> list[int]:
    ids = tok.encode(FILLER * (minimum // 12 + 32), add_special_tokens=False)
    if len(ids) < minimum:
        raise RuntimeError("tokenizer produced too few tokens for the requested window")
    return list(ids[:minimum])


def templated_ids(tok, content: str) -> list[int]:
    """Native pinned chat template (reasoning ENABLED) applied to one user turn,
    tokenised to a FLAT list of ids. Refuses (harness-invalid) rather than sending
    a bare continuation if the template is missing or does not open a thought.

    - enable_thinking=True passed as a DIRECT kwarg: the local AutoTokenizer reads
      native template vars directly, not via OpenAI's nested chat_template_kwargs.
    - The rendered text is verified to end with '<think>' (the generation prompt
      opening a thought, per the pinned template lines 170-174) BEFORE tokenising,
      enforcing the mode from the tokenizer's actual output, not assumed plumbing.
    - return_dict=True yields a BatchEncoding (UserDict/Mapping, NOT dict): pull
      input_ids via Mapping, flatten if batched, assert a real int sequence with a
      single BOS.
    """
    if not getattr(tok, "chat_template", None):
        raise TemplateUnavailable("tokenizer has no chat_template; native template cannot be applied")
    messages = [{"role": "user", "content": content}]
    text = tok.apply_chat_template(messages, add_generation_prompt=True, tokenize=False,
                                   enable_thinking=True)
    if not text.rstrip().endswith("<think>"):
        raise TemplateUnavailable(
            "generation prompt does not open a <think> block; enable_thinking did not take effect"
        )
    encoded = tok.apply_chat_template(messages, add_generation_prompt=True, tokenize=True,
                                      return_dict=True, enable_thinking=True)
    ids = encoded["input_ids"] if isinstance(encoded, Mapping) else encoded
    if ids and isinstance(ids[0], list):  # batched [[...]]
        ids = ids[0]
    if not (isinstance(ids, list) and len(ids) > 1 and all(isinstance(value, int) for value in ids)):
        raise TemplateUnavailable(
            f"apply_chat_template returned an unexpected shape ({type(encoded).__name__}); "
            "expected a flat list[int] of input_ids"
        )
    bos = getattr(tok, "bos_token_id", None)
    if bos is not None and len(ids) >= 2 and ids[0] == bos and ids[1] == bos:
        raise TemplateUnavailable("double BOS in templated ids; template + tokenizer both added BOS")
    return list(ids)


def _fit(tok, content_fn, budget: int) -> list[int]:
    """Chat-templated ids with len(ids) <= budget GUARANTEED, filled to within
    tolerance from below by varying ONLY the filler (never the question or the
    template tail). Fails closed (RuntimeError) if even minimal content exceeds
    the budget - the earlier version accepted overshoot and returned unchecked
    after 3 tries, so prompt + answer_budget overflowed the window at every scale.
    """
    if budget < 1:
        raise RuntimeError(f"non-positive fit budget {budget}: window too small for the answer reserve")
    tolerance = max(8, budget // 100)
    lo, hi = len(FILLER), max(len(FILLER) + 1, int(budget * 6.0))
    best = None
    for _ in range(28):
        if lo > hi:
            break
        mid = (lo + hi) // 2
        ids = templated_ids(tok, content_fn(mid))
        if len(ids) <= budget:
            best = ids
            if budget - len(ids) <= tolerance:
                return ids
            lo = mid + 1
        else:
            hi = mid - 1
    if best is not None:
        return best
    raise RuntimeError(
        f"cannot fit needle+question+template under {budget} tokens without truncating the question"
    )


def flush_cache(base_url: str, timeout: float) -> tuple[bool, str]:
    try:
        response = _post(base_url.rstrip("/") + "/flush_cache", None, timeout, stream=True)
        body = response.read().decode("utf-8", "replace")
    except Exception as exc:
        return False, f"flush_cache unavailable: {type(exc).__name__}"
    if "will not be performed" in body:
        return False, "flush refused: running or waiting requests"
    return True, "flush_cache"


def stream_completion(base_url: str, model: str, prompt_ids: list[int], max_tokens: int,
                      timeout: float, ignore_eos: bool = False) -> dict:
    body = {
        "model": model,
        "prompt": prompt_ids,
        "max_tokens": max_tokens,
        "stream": True,
        "stream_options": {"include_usage": True},
        "temperature": 0.0,
        "ignore_eos": ignore_eos,
    }
    t_dispatch = time.monotonic()
    t_first = None
    last = t_dispatch
    text_parts: list[str] = []
    usage = None
    finish_reason = None
    error = ""
    try:
        response = _post(base_url.rstrip("/") + "/v1/completions", body, timeout, stream=True)
        for raw in response:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            chunk = line[len("data:"):].strip()
            if chunk == "[DONE]":
                break
            obj = json.loads(chunk)
            if obj.get("usage"):
                usage = obj["usage"]
            choices = obj.get("choices") or []
            if not choices:
                continue
            if choices[0].get("finish_reason"):
                finish_reason = choices[0]["finish_reason"]
            piece = choices[0].get("text") or ""
            if not piece:
                continue
            now = time.monotonic()
            if t_first is None:
                t_first = now
            last = now
            text_parts.append(piece)
    except Exception as exc:
        error = type(exc).__name__
    return {
        "t_dispatch": t_dispatch,
        "t_first": t_first,
        "t_last": last,
        "text": "".join(text_parts),
        "usage": usage or {},
        "finish_reason": finish_reason,
        "error": error,
    }


def _sha(prompt_ids: list[int]) -> str:
    return hashlib.sha256(json.dumps(prompt_ids).encode()).hexdigest()


def _needle_value(seed: int, tag: int) -> str:
    return str(random.Random(f"{seed}:{tag}").randint(10_000_000, 99_999_999))


def _haystack(char_budget: int, depth_frac: float, insert_text: str, question: str,
              extra: tuple[float, str] | None = None) -> str:
    body_chars = max(len(FILLER) * 2, char_budget - len(insert_text)
                     - (len(extra[1]) if extra else 0) - len(question))
    reps = body_chars // len(FILLER) + 1
    body = (FILLER * reps)[:body_chars]
    inserts = [(depth_frac, insert_text)] + ([extra] if extra else [])
    out, cursor = [], 0
    for frac, text in sorted(inserts, key=lambda item: item[0]):
        cut = min(len(body), max(cursor, int(len(body) * frac)))
        out.append(body[cursor:cut])
        out.append(text)
        cursor = cut
    out.append(body[cursor:])
    out.append(question)
    return "".join(out)


def _probe(base_url: str, model: str, prompt_ids: list[int], expected: str,
           depth_pct, needle_id: str, usable: int, answer_budget: int, timeout: float) -> dict:
    # Retrieval answer budget is the plan's output horizon; the prompt was fitted
    # to usable - answer_budget so prompt + answer fits the window. Natural EOS
    # allowed (a reasoning model may use tokens before the final answer).
    budget_ok = len(prompt_ids) + answer_budget <= usable
    result = stream_completion(base_url, model, prompt_ids, answer_budget, timeout, ignore_eos=False)
    usage = result["usage"]
    out_len = usage.get("completion_tokens")
    usage_prompt = usage.get("prompt_tokens")
    t0, tf, tl = result["t_dispatch"], result["t_first"], result["t_last"]
    timestamps_ok = bool(tf is not None and tl >= tf >= t0 and not result["error"])
    ttft = (tf - t0) if tf is not None else None
    e2e = (out_len / (tl - t0)) if (out_len and tl > t0) else None
    actual = result["text"]  # raw stream verbatim (trace); do NOT strip the thought
    no_truncation = usage_prompt == len(prompt_ids)
    valid = bool(
        not result["error"] and timestamps_ok and no_truncation and budget_ok
        and out_len is not None and out_len > 0
    )
    exhausted = result["finish_reason"] == "length"
    # Reasoning is ENABLED: the completion opens inside a thought and the FINAL
    # answer is everything after the FIRST '</think>' (pinned template lines
    # 48-50/120/170-174). No boundary => no final answer produced (not a miss).
    has_boundary = "</think>" in actual
    answer_region = actual.split("</think>", 1)[1].strip() if has_boundary else ""
    scored = has_boundary and _score(expected, answer_region)
    if not valid:
        classification = "invalid"                 # rc1: harness/engine, not the model
    elif exhausted:
        classification = "output-budget-exhausted"  # rc1: cap hit, inconclusive
    elif not has_boundary:
        classification = "no-final-answer"          # rc1: thought never closed
    elif scored:
        classification = "pass"
    else:
        classification = "clean-miss"               # rc2: complete answer, wrong
    return {
        "needle_id": needle_id,
        "depth_pct": depth_pct,
        "expected": expected,
        "raw_completion": actual[:4000],  # verbatim trace incl thought
        "answer_region": answer_region[:500],
        "classification": classification,
        "pass": classification == "pass",
        "valid": valid,
        "has_think_boundary": has_boundary,
        "scored_in_answer_region": bool(scored),
        "scoring": ("reasoning enabled; grade ONLY the region after the first "
                    "</think> by exact numeric-boundary; no boundary or cap-hit is "
                    "inconclusive (rc1), only a complete answer region that lacks the "
                    "value is a miss (rc2)"),
        "answer_budget": answer_budget,
        "budget_ok": budget_ok,
        "template_applied": True,
        "prompt_token_ids_sha256": _sha(prompt_ids),
        "prompt_tokens": len(prompt_ids),
        "usage_prompt_tokens": usage_prompt,
        "no_truncation": no_truncation,
        "usable": usable,
        "output_len": out_len,
        "finish_reason": result["finish_reason"],
        "ttft_s": round(ttft, 4) if ttft is not None else None,
        "end_to_end_tok_s": round(e2e, 3) if e2e is not None else None,
        "timestamps_ok": timestamps_ok,
        "error": result["error"] or None,
    }


def _needle_probe(base_url, model, tok, usable, depth_frac, value, label, needle_id,
                  answer_budget, timeout):
    question = (f"\n\nQuestion: What is the access code for vault {label}? "
                "Reply with only the digits.")

    def content_fn(char_budget):
        needle = f" The access code for vault {label} is {value}. Remember this exact code. "
        return _haystack(char_budget, depth_frac, needle, question)

    # Reserve the answer budget BEFORE fitting so prompt + answer <= usable.
    prompt_ids = _fit(tok, content_fn, usable - answer_budget)
    return _probe(base_url, model, prompt_ids, value, round(depth_frac * 100),
                  needle_id, usable, answer_budget, timeout)


def _tokenizer_facts(tok, expected_sha: str | None) -> dict:
    actual = chat_template_sha(tok)
    matches = None
    if expected_sha and actual:
        matches = actual.startswith(expected_sha) or actual == expected_sha
    return {
        "tokenizer_path": str(getattr(tok, "name_or_path", None)),
        "chat_template_sha256": actual,
        "chat_template_sha256_expected": expected_sha,
        "chat_template_matches_expected": matches,
    }


def run_needle(base_url, model, tok, window, timeout, seed, expected_sha=None,
               context_len=None, reserved=0, output_tokens=512) -> dict:
    usable = min(window, context_len - reserved) if context_len else window
    flushed, detail = flush_cache(base_url, timeout)
    probes = []
    harness_error = None
    for depth_frac in DEPTHS:
        depth_pct = round(depth_frac * 100)
        value = _needle_value(seed, depth_pct)
        try:
            probes.append(_needle_probe(base_url, model, tok, usable, depth_frac, value,
                                        depth_pct, f"needle-d{depth_pct}", output_tokens, timeout))
        except (TemplateUnavailable, RuntimeError) as exc:
            harness_error = f"{type(exc).__name__}: {exc}"
            break
    return {
        "schema_version": "inference-index/longcontext-needle-v1",
        "window": window,
        "usable_window": usable,
        "engine_reserved_positions": reserved,
        "answer_budget": output_tokens,
        "seed": seed,
        "cache_reset": "flush_cache" if flushed else None,
        "cache_reset_error": None if flushed else detail,
        "harness_error": harness_error,
        "tokenizer": _tokenizer_facts(tok, expected_sha),
        "depths_pct": [round(d * 100) for d in DEPTHS],
        "all_pass": bool(probes) and harness_error is None
                    and all(p["classification"] == "pass" for p in probes),
        "classifications": [p["classification"] for p in probes],
        "probes": probes,
    }


def run_multihop(base_url, model, tok, window, timeout, seed, expected_sha=None,
                 context_len=None, reserved=0, output_tokens=512) -> dict:
    usable = min(window, context_len - reserved) if context_len else window
    flushed, detail = flush_cache(base_url, timeout)
    rng = random.Random(f"{seed}:multihop")
    n1, n2 = rng.randint(11, 89), rng.randint(11, 89)
    expected = str(n1 * n2)
    fact1 = f" Depot Kestrel received exactly {n1} pallets this cycle. "
    fact2 = f" Each pallet stored at Depot Kestrel holds exactly {n2} boxes. "
    question = ("\n\nQuestion: How many boxes are stored at Depot Kestrel in total? "
                "Reply with only the number.")

    def content_fn(char_budget):
        return _haystack(char_budget, 0.25, fact1, question, extra=(0.75, fact2))

    harness_error = None
    probe = None
    try:
        ids = _fit(tok, content_fn, usable - output_tokens)
        probe = _probe(base_url, model, ids, expected, "25/75", "multihop-25-75",
                       usable, output_tokens, timeout)
        probe["facts"] = {"n1": n1, "n2": n2}
    except (TemplateUnavailable, RuntimeError) as exc:
        harness_error = f"{type(exc).__name__}: {exc}"
    return {
        "schema_version": "inference-index/longcontext-multihop-v1",
        "window": window,
        "usable_window": usable,
        "engine_reserved_positions": reserved,
        "answer_budget": output_tokens,
        "seed": seed,
        "cache_reset": "flush_cache" if flushed else None,
        "cache_reset_error": None if flushed else detail,
        "harness_error": harness_error,
        "tokenizer": _tokenizer_facts(tok, expected_sha),
        "all_pass": bool(probe) and probe["classification"] == "pass",
        "probe": probe,
    }


def run_gate(base_url, model, tok, window, output_tokens, max_ttft_s, timeout, seed,
             expected_sha=None, context_len=None, reserved=0):
    # Reserve engine positions in the PROMPT so the full horizon decodes without
    # the engine clamping max_new_tokens (SGLang: max_new_tokens <= max_req_len -
    # input - 1, with max_req_len = context_len - 1, so `reserved` positions at
    # the ceiling are unusable). Pin input so input+output == usable_window and
    # the full output_tokens is produced; a short output is then a real failure.
    usable = min(window, context_len - reserved) if context_len else window
    pool = pool_from(tok, usable)
    flushed, detail = flush_cache(base_url, timeout)
    prompt_tokens = usable - output_tokens
    horizon = stream_completion(base_url, model, pool[:prompt_tokens], output_tokens,
                                timeout, ignore_eos=True)
    h_usage = horizon["usage"]
    h_out = h_usage.get("completion_tokens")
    h_prompt = h_usage.get("prompt_tokens")
    t0, tf, tl = horizon["t_dispatch"], horizon["t_first"], horizon["t_last"]
    timestamps_ok = bool(tf is not None and tl >= tf >= t0 and not horizon["error"])
    ttft = (tf - t0) if tf is not None else None
    finish_reason = horizon["finish_reason"]

    measurement_failures = []
    if ttft is None or ttft > max_ttft_s:
        measurement_failures.append({
            "code": "ttft_over_threshold", "cause": "unknown",
            "detail": (f"ttft {round(ttft, 3)}s > {max_ttft_s}s" if ttft is not None else "no first token"),
        })
    if not timestamps_ok:
        measurement_failures.append({
            "code": "missing_or_nonmonotonic_timestamps", "cause": "unknown",
            "detail": "client could not observe monotonic t_dispatch/t_first/t_last",
        })
    if finish_reason != "length":
        measurement_failures.append({
            "code": "finish_reason_not_length", "cause": "engine/api",
            "detail": f"finish_reason={finish_reason!r}, output_len={h_out}; ignore_eos not honoured",
        })
    if h_prompt != prompt_tokens:
        measurement_failures.append({
            "code": "prompt_token_mismatch", "cause": "engine/api",
            "detail": f"usage prompt_tokens {h_prompt} != sent {prompt_tokens} (re-tokenised/truncated)",
        })
    if h_out != output_tokens:
        measurement_failures.append({
            "code": "output_len_below_horizon" if (h_out or 0) < output_tokens else "output_len_above_horizon",
            "cause": "engine/api",
            "detail": (f"output_len {h_out} != requested horizon {output_tokens}; the "
                       f"{reserved}-position reservation did not prevent a clamp/short output"),
        })

    # Retrieval (model/prompt) check with the native local template.
    needle = None
    harness_error = None
    value = _needle_value(seed, 50)
    try:
        needle = _needle_probe(base_url, model, tok, usable, 0.50, value, 50,
                               "gate-needle-d50", output_tokens, timeout)
    except (TemplateUnavailable, RuntimeError) as exc:
        harness_error = f"{type(exc).__name__}: {exc}"
    # rc1 (measurement/preflight-invalidity): harness/template/tokenizer/engine
    # fault, or an INCONCLUSIVE retrieval (invalid probe, exhausted budget, or no
    # closed thought). rc2 is reserved for a COMPLETE answer region that is wrong.
    if harness_error is not None:
        measurement_failures.append({
            "code": "retrieval_harness_invalid", "cause": "harness/tokenizer",
            "detail": harness_error,
        })
    elif needle is not None and needle["classification"] in (
        "invalid", "output-budget-exhausted", "no-final-answer"
    ):
        measurement_failures.append({
            "code": {"invalid": "retrieval_probe_invalid",
                     "output-budget-exhausted": "output_budget_exhausted",
                     "no-final-answer": "no_final_answer"}[needle["classification"]],
            "cause": "engine/api/harness" if needle["classification"] == "invalid" else "engine/api",
            "detail": (f"needle classification={needle['classification']} "
                       f"(finish_reason={needle['finish_reason']}, "
                       f"has_boundary={needle['has_think_boundary']}, valid={needle['valid']})"),
        })

    retrieval_failure = None
    if not measurement_failures and needle is not None and needle["classification"] == "clean-miss":
        retrieval_failure = (f"needle miss: complete answer region lacked the value "
                             f"(expected {value}, answer_region={needle['answer_region']!r})")

    verdict = ("measurement-invalid" if measurement_failures
               else ("retrieval-fail" if retrieval_failure else "pass"))
    return {
        "schema_version": "inference-index/preflight-gate-v3",
        "window": window,
        "output_tokens": output_tokens,
        "max_ttft_s": max_ttft_s,
        "seed": seed,
        "tokenizer": _tokenizer_facts(tok, expected_sha),
        "cache_reset": "flush_cache" if flushed else None,
        "cache_reset_error": None if flushed else detail,
        "window_accounting": {
            "nominal_window": window,
            "usable_window": usable,
            "engine_reserved_positions": reserved,
            "api_used_input": prompt_tokens,
            "api_used_output": h_out,
            "api_used_total": prompt_tokens + (h_out or 0),
            "note": "never claim usage == nominal_window; api_used_total is the real served count",
        },
        "horizon_request": {
            "ttft_s": round(ttft, 4) if ttft is not None else None,
            "output_len": h_out,
            "finish_reason": finish_reason,
            "requested_output_tokens": output_tokens,
            "sent_prompt_tokens": prompt_tokens,
            "usage_prompt_tokens": h_prompt,
            "no_truncation": h_prompt == prompt_tokens,
            "timestamps_ok": timestamps_ok,
            "error": horizon["error"] or None,
        },
        "needle": needle,
        "harness_error": harness_error,
        "verdict": verdict,
        "passed": verdict == "pass",
        "cause": {
            "pass": None,
            "measurement-invalid": "measurement/preflight-invalidity",
            "retrieval-fail": "model/prompt-retrieval",
        }[verdict],
        "measurement_failures": measurement_failures,
        "retrieval_failure": retrieval_failure,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", required=True, choices=("gate", "needle", "multihop"))
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--model", required=True)
    parser.add_argument("--model-dir", required=True, help="mounted pinned model dir on the pod")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--window", type=int, required=True)
    parser.add_argument("--context-len", type=int, default=None,
                        help="model context ceiling; caps usable = context_len - reserved")
    parser.add_argument("--reserved-positions", type=int, default=0,
                        help="engine positions reserved at the ceiling (SGLang: 2)")
    parser.add_argument("--output-tokens", type=int, default=512)
    parser.add_argument("--max-ttft-s", type=float, default=192.0)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--trust-remote-code", action="store_true",
                        help="only for a pinned model whose tokenizer requires reviewed code")
    parser.add_argument("--expected-template-sha", default=None,
                        help="pinned chat_template sha256 (prefix ok) to assert against")
    parser.add_argument("--timeout", type=float, default=1800)
    args = parser.parse_args(argv)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    seed = args.seed if args.seed is not None else random.randint(1, 2**31 - 1)

    try:
        tok = load_tokenizer(args.model_dir, args.trust_remote_code)
    except Exception as exc:
        # A tokenizer that will not load locally is a measurement/setup invalidity.
        report = {"schema_version": "inference-index/preflight-gate-v3", "verdict": "measurement-invalid",
                  "cause": "measurement/preflight-invalidity", "passed": False,
                  "measurement_failures": [{"code": "tokenizer_load_failed", "cause": "harness/setup",
                                            "detail": f"{type(exc).__name__}: {exc}"}]}
        if args.mode == "gate":
            (args.output_dir / "preflight-failed.json").write_text(json.dumps(report, indent=2, sort_keys=True))
            print(json.dumps({"verdict": "measurement-invalid", "cause": report["cause"]}), flush=True)
            return 1
        (args.output_dir / f"{args.mode}.json").write_text(json.dumps(report, indent=2, sort_keys=True))
        print(json.dumps(report), flush=True)
        return 1

    if args.mode == "gate":
        report = run_gate(args.base_url, args.model, tok, args.window, args.output_tokens,
                          args.max_ttft_s, args.timeout, seed, args.expected_template_sha,
                          args.context_len, args.reserved_positions)
        name = {
            "pass": "preflight-ok.json",
            "measurement-invalid": "preflight-failed.json",
            "retrieval-fail": "preflight-format-failed.json",
        }[report["verdict"]]
        (args.output_dir / name).write_text(json.dumps(report, indent=2, sort_keys=True))
        print(json.dumps({"verdict": report["verdict"], "cause": report["cause"],
                          "measurement_failures": report["measurement_failures"],
                          "retrieval_failure": report["retrieval_failure"],
                          "chat_template_sha256": report["tokenizer"]["chat_template_sha256"]}), flush=True)
        # rc: 0 pass, 1 measurement/preflight-invalid, 2 model/prompt-retrieval.
        # Both nonzero => no grid, no wasted cost.
        return {"pass": 0, "measurement-invalid": 1, "retrieval-fail": 2}[report["verdict"]]
    if args.mode == "needle":
        report = run_needle(args.base_url, args.model, tok, args.window, args.timeout, seed,
                            args.expected_template_sha, args.context_len, args.reserved_positions,
                            args.output_tokens)
        (args.output_dir / "needle.json").write_text(json.dumps(report, indent=2, sort_keys=True))
        print(json.dumps({"all_pass": report["all_pass"],
                          "classifications": report["classifications"],
                          "harness_error": report["harness_error"]}), flush=True)
        return 0
    report = run_multihop(args.base_url, args.model, tok, args.window, args.timeout, seed,
                          args.expected_template_sha, args.context_len, args.reserved_positions,
                          args.output_tokens)
    (args.output_dir / "multihop.json").write_text(json.dumps(report, indent=2, sort_keys=True))
    print(json.dumps({"all_pass": report["all_pass"],
                      "classification": (report["probe"] or {}).get("classification"),
                      "harness_error": report["harness_error"]}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
