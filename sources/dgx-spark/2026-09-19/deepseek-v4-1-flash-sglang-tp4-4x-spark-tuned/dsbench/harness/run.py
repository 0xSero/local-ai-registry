#!/usr/bin/env python3
"""Run the REPORT.md v1 benchmark protocol against an SGLang OpenAI API."""
from __future__ import annotations

import argparse
import base64
import concurrent.futures
import datetime as dt
import gzip
import json
import os
import random
import re
import shlex
import statistics
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

if __package__:
    from .common import append_jsonl, canonical_json, percentile, read_jsonl, sha256, write_json_atomic
else:
    from common import append_jsonl, canonical_json, percentile, read_jsonl, sha256, write_json_atomic

PROFILES = {
    "G0": {"thinking": False, "temperature": 0.0, "top_p": 1.0, "max_tokens": 1024},
    "S0": {"thinking": False, "temperature": 0.7, "top_p": 0.95, "max_tokens": 1024},
    # Exact bounded benchmark analogue of omp. max_tokens is benchmark-only.
    "S1-omp": {"thinking": True, "temperature": 1.0, "top_p": 1.0, "max_tokens": 2048},
}
CONTEXT_ALIASES = {"0": "0", "32768": "32k", "32k": "32k", "131072": "128k", "128k": "128k", "400000": "400k", "400k": "400k"}
LONG_CONTEXTS = {"128k", "400k"}
MEMORY_HOSTS = ["local", "sero@100.83.190.2", "valentine@10.10.10.14", "valentine@10.10.10.13"]
CATEGORY_ORDER = ["agentic", "code", "prose", "structured"]
OMP_TOOLS = [
    {"type": "function", "function": {"name": "read_file", "description": "Read a repository file", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}},
    {"type": "function", "function": {"name": "search", "description": "Search repository text", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "apply_patch", "description": "Apply a repository patch", "parameters": {"type": "object", "properties": {"patch": {"type": "string"}}, "required": ["patch"]}}},
]


def csv_list(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def http_json(url: str, body: dict[str, Any] | None = None, timeout: float = 30.0) -> Any:
    data = canonical_json(body) if body is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    with urllib.request.urlopen(urllib.request.Request(url, data, headers), timeout=timeout) as response:
        return json.load(response)


def run_command(command: str | list[str], *, timeout: float = 30.0) -> subprocess.CompletedProcess[str]:
    argv = shlex.split(command) if isinstance(command, str) else command
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False)


def docker_logs(since: float, until: float | None = None) -> str:
    argv = ["docker", "logs", "--timestamps", "--since", str(max(0, int(since) - 1))]
    if until is not None:
        argv += ["--until", str(int(until) + 2)]
    argv.append("dsv41-head")
    result = run_command(argv, timeout=60)
    return result.stdout + result.stderr


def parse_prometheus(text: str) -> dict[str, float]:
    result: dict[str, float] = {}
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        match = re.match(r"([^\s{]+)(?:\{([^}]*)\})?\s+([-+0-9.eE]+)(?:\s+\d+)?$", line)
        if not match:
            continue
        name, labels, value = match.groups()
        key = name + ("{" + labels + "}" if labels else "")
        try:
            result[key] = float(value)
        except ValueError:
            pass
    return result


def metric_sum(metrics: dict[str, float], needles: Iterable[str]) -> float | None:
    matches = [value for key, value in metrics.items() if any(needle in key.lower() for needle in needles)]
    return sum(matches) if matches else None


def fetch_metrics(base_url: str, timeout: float = 3.0) -> dict[str, float] | None:
    try:
        with urllib.request.urlopen(base_url.rstrip("/") + "/metrics", timeout=timeout) as response:
            if response.status != 200:
                return None
            return parse_prometheus(response.read().decode("utf-8", errors="replace"))
    except (urllib.error.URLError, TimeoutError, OSError):
        return None


def normalized_counters(metrics: dict[str, float] | None) -> dict[str, float | None]:
    metrics = metrics or {}
    return {
        "running": metric_sum(metrics, ("num_running_reqs", "running_requests", "requests_running")),
        "queued": metric_sum(metrics, ("num_queue_reqs", "queued_requests", "requests_waiting")),
        "generated_tokens": metric_sum(metrics, ("generation_tokens_total", "generated_tokens_total", "output_tokens_total")),
        # SGLang exposes spec_verify_calls_total (cumulative). The draft-token metrics
        # (spec_num_draft_tokens, spec_accept_length, spec_accept_rate) are gauges of the last
        # batch, so they are read as instantaneous values, never differenced.
        "verify_steps": metric_sum(metrics, ("spec_verify_calls_total", "verify_steps_total", "target_forward")),
        "draft_proposed": metric_sum(metrics, ("draft_tokens_total", "spec_proposed")),
        "draft_accepted": metric_sum(metrics, ("accepted_tokens_total", "spec_accepted")),
        "accept_length_gauge": metric_sum(metrics, ("spec_accept_length",)),
        "accept_rate_gauge": metric_sum(metrics, ("spec_accept_rate",)),
        "cache_hits": metric_sum(metrics, ("cache_hit_tokens_total", "cached_tokens_total")),
        "requests": metric_sum(metrics, ("requests_total", "request_count_total")),
    }


def metrics_support_decomposition(metrics: dict[str, float] | None) -> bool:
    counters = normalized_counters(metrics)
    # committed tokens per verify step = d(generation_tokens_total) / d(spec_verify_calls_total)
    # is the decomposition the requirement needs; draft-token totals are optional.
    return all(counters[key] is not None for key in ("running", "queued", "generated_tokens", "verify_steps"))


HEALTH_PROBE_MAX_TOKENS = 2
LOG_TS_RE = re.compile(r"\[?(\d{4}-\d\d-\d\d)[ T](\d\d:\d\d:\d\d)(?:[.,]\d+)?")


def parse_engine_log(text: str) -> dict[str, Any]:
    running: list[int] = []
    queued: list[int] = []
    accept_len: list[float] = []
    accept_rate: list[float] = []
    cap_len: list[float] = []
    generation_tps: list[float] = []
    health_probe_prefills: list[int] = []
    prefill_new_seq: list[int] = []
    prefill_new_token: list[int] = []
    cached_tokens: list[int] = []
    health_events: list[str] = []
    timestamps: list[str] = []
    relevant_lines: list[str] = []
    decode_times: list[float] = []
    for line in text.splitlines():
        if "Decode batch" in line:
            relevant_lines.append(line)
            first_field = line.split(" ", 1)[0]
            try:
                decode_times.append(dt.datetime.fromisoformat(first_field.replace("Z", "+00:00")).timestamp())
            except ValueError:
                match = LOG_TS_RE.search(line)
                if match:
                    decode_times.append(dt.datetime.fromisoformat("T".join(match.groups())).replace(tzinfo=dt.timezone.utc).timestamp())
            patterns = (
                (r"#running-req:\s*(\d+)", running, int),
                (r"#queue-req:\s*(\d+)", queued, int),
                (r"accept len:\s*([0-9.]+)", accept_len, float),
                (r"accept rate:\s*([0-9.]+)", accept_rate, float),
                (r"cap len:\s*([0-9.]+)", cap_len, float),
                (r"gen throughput \(token/s\):\s*([0-9.]+)", generation_tps, float),
            )
            for pattern, destination, converter in patterns:
                match = re.search(pattern, line)
                if match:
                    destination.append(converter(match.group(1)))
        if "Prefill batch" in line:
            # Local Studio health-probes the model every few seconds with a 1-token request.
            # Those are not benchmark prefills and must not count as foreign traffic.
            probe = re.search(r"#new-token:\s*(\d+)", line)
            if probe and int(probe.group(1)) <= HEALTH_PROBE_MAX_TOKENS:
                health_probe_prefills.append(int(probe.group(1)))
                continue
            relevant_lines.append(line)
            for pattern, destination in (
                (r"#new-seq:\s*(\d+)", prefill_new_seq),
                (r"#new-token:\s*(\d+)", prefill_new_token),
                (r"#cached-token:\s*(\d+)", cached_tokens),
            ):
                match = re.search(pattern, line)
                if match:
                    destination.append(int(match.group(1)))
        if re.search(r"\b(Xid|RoCE.*(?:retry|error)|rank.*(?:failed|unhealthy)|temperature.*thrott|NVMe.*maintenance)\b", line, re.I):
            health_events.append(line[-500:])
            if line not in relevant_lines:
                relevant_lines.append(line)
        match = LOG_TS_RE.search(line)
        if match:
            timestamps.append("T".join(match.groups()) + "Z")
    verify_mix = Counter(str(value) for value in cap_len)
    step_gaps = [right - left for left, right in zip(decode_times, decode_times[1:]) if right >= left]
    return {
        "health_probe_prefills": len(health_probe_prefills),
        "decode_steps": len(accept_len) or len(running),
        "max_running": max(running, default=0),
        "avg_running": statistics.mean(running) if running else None,
        "max_queued": max(queued, default=0),
        "prefill_batches": len(prefill_new_seq),
        "prefill_sequences": sum(prefill_new_seq),
        "prefill_tokens": sum(prefill_new_token),
        "cached_tokens": sum(cached_tokens),
        "accept_len_median": statistics.median(accept_len) if accept_len else None,
        "accept_rate_mean": statistics.mean(accept_rate) if accept_rate else None,
        "draft_proposed": sum(max(0.0, value - 1.0) for value in cap_len) if cap_len else None,
        "draft_accepted": sum(max(0.0, value - 1.0) for value in accept_len) if accept_len else None,
        "cap_len_mix": dict(sorted(verify_mix.items())),
        "generation_tps_median": statistics.median(generation_tps) if generation_tps else None,
        "health_events": health_events,
        "first_log_timestamp": timestamps[0] if timestamps else None,
        "last_log_timestamp": timestamps[-1] if timestamps else None,
        "relevant_lines": relevant_lines,
        "engine_step_gap_p50_s": percentile(step_gaps, 0.50),
        "engine_step_gap_p95_s": percentile(step_gaps, 0.95),
        "engine_step_gap_p99_s": percentile(step_gaps, 0.99),
        "engine_step_gap_max_s": max(step_gaps, default=None),
    }


def read_mem_available(host: str) -> float:
    return float(node_telemetry(host)["mem_available_gib"])


def memory_snapshot(hosts: Iterable[str] = MEMORY_HOSTS) -> dict[str, float]:
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(read_mem_available, host): host for host in hosts}
        return {host: future.result() for future, host in ((future, futures[future]) for future in futures)}


def memory_safe(snapshot: dict[str, float], minimum_gib: float = 3.0) -> bool:
    return all(value >= minimum_gib for value in snapshot.values())


NODE_QUERY = r'''awk '/MemAvailable:/{print "mem_kib="$2}' /proc/meminfo
awk '{print "load1="$1}' /proc/loadavg
printf 'cpu_count='; getconf _NPROCESSORS_ONLN
awk '$3 ~ /^nvme/ {r+=$6; w+=$10} END{print "nvme_read_sectors="r; print "nvme_write_sectors="w}' /proc/diskstats
for f in /sys/class/infiniband/*/ports/*/counters/port_rcv_packets; do [ -r "$f" ] && cat "$f"; done | awk '{s+=$1} END{print "roce_rx_packets="s}'
for f in /sys/class/infiniband/*/ports/*/counters/port_xmit_packets; do [ -r "$f" ] && cat "$f"; done | awk '{s+=$1} END{print "roce_tx_packets="s}'
for f in /sys/class/infiniband/*/ports/*/hw_counters/*retry* /sys/class/infiniband/*/ports/*/counters/symbol_error; do [ -r "$f" ] && cat "$f"; done | awk '{s+=$1} END{print "roce_retry_errors="s}'
nvidia-smi --query-gpu=utilization.gpu,clocks.sm,temperature.gpu,power.draw --format=csv,noheader,nounits 2>/dev/null | head -1 | awk -F',' '{gsub(/ /,""); print "gpu_util_pct="$1; print "sm_clock_mhz="$2; print "temperature_c="$3; print "power_w="$4}'
nvidia-smi --query-gpu=clocks_event_reasons.active --format=csv,noheader 2>/dev/null | head -1 | sed 's/^/throttle_reason=/'
'''


def node_telemetry(host: str) -> dict[str, Any]:
    if host == "local":
        argv = ["sh", "-lc", NODE_QUERY]
    else:
        remote = "sh -lc " + shlex.quote(NODE_QUERY)
        argv = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", "-o", "ControlMaster=auto", "-o", "ControlPersist=60", "-o", "ControlPath=/tmp/dsbench-ssh-%C", host, remote]
    result = run_command(argv, timeout=60)
    if result.returncode != 0:
        raise RuntimeError(f"telemetry failed on {host}: rc={result.returncode} {result.stderr.strip()}")
    output: dict[str, Any] = {"host": host}
    for line in result.stdout.splitlines():
        key, separator, value = line.partition("=")
        if not separator:
            continue
        try:
            output[key] = float(value)
        except ValueError:
            output[key] = value.strip() if key == "throttle_reason" else None
    if output.get("mem_kib") is None:
        raise RuntimeError(f"telemetry on {host} omitted MemAvailable")
    output["mem_available_gib"] = output["mem_kib"] / (1024 ** 2)
    return output


INVENTORY_QUERY = r'''printf 'hostname='; hostname
printf 'uname='; uname -a
nvidia-smi --query-gpu=name,driver_version,pci.bus_id,power.limit --format=csv,noheader 2>/dev/null | sed 's/^/gpu=/'
nvidia-smi topo -m 2>/dev/null | sed 's/^/topology=/'
rdma link show 2>/dev/null | sed 's/^/rdma=/'
ldconfig -p 2>/dev/null | grep -i nccl | sed 's/^/nccl=/'
'''


def node_inventory(host: str) -> dict[str, Any]:
    if host == "local":
        argv = ["sh", "-lc", INVENTORY_QUERY]
    else:
        argv = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", host, "sh -lc " + shlex.quote(INVENTORY_QUERY)]
    result = run_command(argv, timeout=30)
    if result.returncode != 0:
        raise RuntimeError(f"inventory failed on {host}: {result.stderr.strip()}")
    return {"host": host, "raw": result.stdout, "sha256": sha256(result.stdout)}


def cluster_inventory() -> dict[str, dict[str, Any]]:
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(node_inventory, host): host for host in MEMORY_HOSTS}
        return {host: future.result() for future, host in ((future, futures[future]) for future in futures)}


def cluster_telemetry() -> dict[str, dict[str, Any]]:
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(node_telemetry, host): host for host in MEMORY_HOSTS}
        return {host: future.result() for future, host in ((future, futures[future]) for future in futures)}


# NVML clocks_event_reasons bits. GPU_IDLE (0x1), APPLICATIONS_CLOCKS_SETTING (0x2) and SW_POWER_CAP (0x4)
# are normal on GB10 (the power cap is essentially always engaged). Only slowdown/thermal/brake bits
# invalidate a measurement.
THROTTLE_BLOCKING_MASK = 0x8 | 0x20 | 0x40 | 0x80


def throttle_blocking(value: Any) -> bool:
    text = str(value or "").strip().lower()
    if text in ("", "not active", "n/a", "[n/a]"):
        return False
    try:
        return bool(int(text, 16) & THROTTLE_BLOCKING_MASK)
    except ValueError:
        return "thermal" in text or "slowdown" in text or "brake" in text


def idle_nodes_stable(samples: list[dict[str, Any]]) -> tuple[bool, list[str]]:
    if len(samples) < 3:
        return False, ["fewer_than_three_node_samples"]
    reasons = []
    recent = samples[-3:]
    for host in MEMORY_HOSTS:
        rows = [sample["nodes"].get(host, {}) for sample in recent]
        for field in ("mem_available_gib", "load1", "cpu_count", "gpu_util_pct", "sm_clock_mhz", "temperature_c", "nvme_read_sectors", "nvme_write_sectors", "roce_retry_errors"):
            if any(row.get(field) is None for row in rows):
                reasons.append(f"{host}:{field}:missing")
        if reasons and any(reason.startswith(host + ":") for reason in reasons):
            continue
        # the Local Studio health probe briefly lifts utilisation; anything above ~15% is real work
        if max(row["gpu_util_pct"] for row in rows) > 15:
            reasons.append(f"{host}:gpu_busy")
        clocks = [row["sm_clock_mhz"] for row in rows]
        if max(clocks) and (max(clocks) - min(clocks)) / max(clocks) > 0.10:
            reasons.append(f"{host}:clock_unstable")
        temperatures = [row["temperature_c"] for row in rows]
        if max(temperatures) - min(temperatures) > 5:
            reasons.append(f"{host}:temperature_unstable")
        memories = [row["mem_available_gib"] for row in rows]
        if min(memories) and (max(memories) - min(memories)) / min(memories) > 0.02:
            reasons.append(f"{host}:memory_unstable")
        if max(row["load1"] / row["cpu_count"] for row in rows) > 0.75:
            reasons.append(f"{host}:cpu_busy")
        for field in ("nvme_read_sectors", "nvme_write_sectors"):
            if rows[-1][field] - rows[0][field] > 32_768:
                reasons.append(f"{host}:nvme_busy")
        if rows[-1]["roce_retry_errors"] != rows[0]["roce_retry_errors"]:
            reasons.append(f"{host}:roce_retry")
        if any(throttle_blocking(row.get("throttle_reason")) for row in rows):
            reasons.append(f"{host}:throttle_active")
    return not reasons, reasons


def load_context_object(root: Path, row: dict[str, Any]) -> dict[str, Any]:
    path = root / row["object"]
    with gzip.open(path, "rb") as handle:
        data = handle.read()
    if sha256(data) != row["request_sha256"]:
        raise ValueError(f"context object hash mismatch: {path}")
    return json.loads(data)


def request_body(context_request: dict[str, Any], profile_name: str, seed: int, model: str, continuous: bool) -> dict[str, Any]:
    profile = PROFILES[profile_name]
    body: dict[str, Any] = {
        "model": model,
        "messages": context_request["messages"],
        "max_tokens": profile["max_tokens"],
        "temperature": profile["temperature"],
        "top_p": profile["top_p"],
        "seed": seed,
        "stream": True,
        "stream_options": {"include_usage": True},
        "chat_template_kwargs": {"thinking": profile["thinking"], "enable_thinking": profile["thinking"]},
    }
    if continuous:
        body["stream_options"]["continuous_usage_stats"] = True
    tools = context_request.get("tools")
    if profile_name == "S1-omp":
        tools = tools or OMP_TOOLS
    if tools:
        body["tools"] = tools
    return body


def loop_detected(text: str) -> bool:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) < 400:
        return False
    tail = compact[-4000:]
    for width in (32, 64, 128, 256):
        if len(tail) >= width * 5:
            suffix = tail[-width * 5:]
            if len({suffix[index * width:(index + 1) * width] for index in range(5)}) == 1:
                return True
    words = tail.split()
    if len(words) >= 120:
        grams = [tuple(words[index:index + 12]) for index in range(len(words) - 11)]
        if grams and Counter(grams).most_common(1)[0][1] >= 8:
            return True
    return False


def validate_output_shape(prompt_id: str, category: str, content: str, tool_calls: list[dict[str, Any]]) -> tuple[bool, list[str]]:
    reasons = []
    text = content.strip()
    if category == "structured":
        if prompt_id in ("structured-01", "structured-03"):
            try:
                value, _ = json.JSONDecoder().raw_decode(text)
                required = {"incident_id", "severity", "timeline", "impact", "hypotheses", "actions", "unknowns"} if prompt_id == "structured-01" else {"version", "gates", "stages", "rollback", "assumptions"}
                if not isinstance(value, dict) or not required.issubset(value):
                    reasons.append("structured_json_missing_keys")
            except (json.JSONDecodeError, TypeError):
                reasons.append("structured_json_invalid")
        elif prompt_id == "structured-02":
            lowered = text.lower()
            if not all(word in lowered for word in ("alter", "index", "rollback")):
                reasons.append("sql_migration_incomplete")
        elif prompt_id == "structured-04":
            if "```" in text or not all(re.search(rf"(?m)^{key}:\s*", text) for key in ("objective", "constraints", "daily_plan", "evidence_matrix", "stop_conditions")):
                reasons.append("yaml_shape_invalid")
    if tool_calls and any(call.get("parsed_arguments") is None for call in tool_calls):
        reasons.append("tool_arguments_invalid")
    return not reasons, reasons


def stream_request(
    base_url: str,
    body: dict[str, Any],
    barrier: threading.Barrier,
    cancel: threading.Event,
    timeout: float,
    active_responses: set[Any] | None = None,
    active_lock: threading.Lock | None = None,
) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    content_parts: list[str] = []
    reasoning_parts: list[str] = []
    tool_parts: list[str] = []
    tool_accumulator: dict[int, dict[str, str]] = {}
    usage: dict[str, Any] | None = None
    finish_reason: str | None = None
    first_ns = answer_ns = last_ns = sent_ns = None
    first_event_token_count = None
    error = None
    barrier.wait(timeout=30)
    sent_ns = time.monotonic_ns()
    wall_start = time.time()
    request = urllib.request.Request(
        base_url.rstrip("/") + "/v1/chat/completions",
        canonical_json(body),
        {"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            if active_responses is not None and active_lock is not None:
                with active_lock:
                    active_responses.add(response)
            try:
                for raw in response:
                    if cancel.is_set():
                        raise RuntimeError("cancelled by memory guard")
                    now = time.monotonic_ns()
                    line = raw.decode("utf-8", errors="replace").strip()
                    if not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        events.append({"monotonic_ns": now, "kind": "done"})
                        continue
                    event = json.loads(payload)
                    if event.get("usage"):
                        usage = event["usage"]
                    pieces = []
                    for choice in event.get("choices") or []:
                        if choice.get("finish_reason"):
                            finish_reason = choice["finish_reason"]
                        delta = choice.get("delta") or {}
                        reasoning = delta.get("reasoning_content") or delta.get("reasoning") or ""
                        content = delta.get("content") or ""
                        calls = delta.get("tool_calls") or []
                        if reasoning:
                            reasoning_parts.append(reasoning)
                            pieces.append("reasoning")
                        if content:
                            content_parts.append(content)
                            pieces.append("content")
                            answer_ns = answer_ns or now
                        if calls:
                            serialized = json.dumps(calls, sort_keys=True, ensure_ascii=False)
                            tool_parts.append(serialized)
                            for call in calls:
                                index = int(call.get("index", 0))
                                accumulator = tool_accumulator.setdefault(index, {"id": "", "name": "", "arguments": ""})
                                accumulator["id"] += str(call.get("id") or "")
                                function = call.get("function") or {}
                                accumulator["name"] += str(function.get("name") or "")
                                accumulator["arguments"] += str(function.get("arguments") or "")
                            pieces.append("tool_calls")
                            answer_ns = answer_ns or now
                    if pieces:
                        first_ns = first_ns or now
                        if first_event_token_count is None:
                            event_completion = (event.get("usage") or {}).get("completion_tokens")
                            first_event_token_count = event_completion if isinstance(event_completion, int) and event_completion > 0 else 1
                        last_ns = now
                    events.append({"monotonic_ns": now, "kind": "+".join(pieces) or "metadata", "data": event})
            finally:
                if active_responses is not None and active_lock is not None:
                    with active_lock:
                        active_responses.discard(response)
    except Exception as exc:  # retained in receipt; caller validates
        error = f"{type(exc).__name__}: {exc}"
    end_ns = time.monotonic_ns()
    parsed_tools = []
    tools_valid = True
    for index, call in sorted(tool_accumulator.items()):
        try:
            arguments = json.loads(call["arguments"]) if call["arguments"] else {}
        except json.JSONDecodeError:
            arguments = None
            tools_valid = False
        parsed_tools.append({"index": index, **call, "parsed_arguments": arguments})
    return {
        "finish_reason": finish_reason,
        "sent_monotonic_ns": sent_ns,
        "first_event_monotonic_ns": first_ns,
        "first_answer_monotonic_ns": answer_ns,
        "last_token_monotonic_ns": last_ns,
        "first_event_token_count": first_event_token_count,
        "first_event_token_count_source": "continuous_usage" if first_event_token_count not in (None, 1) else "one_token_fallback",
        "end_monotonic_ns": end_ns,
        "wall_start_unix": wall_start,
        "wall_end_unix": time.time(),
        "events": events,
        "usage": usage,
        "content": "".join(content_parts),
        "reasoning": "".join(reasoning_parts),
        "tool_calls_text": "".join(tool_parts),
        "tool_calls": parsed_tools,
        "tool_calls_valid": tools_valid,
        "error": error,
    }


def derive_request_metrics(result: dict[str, Any]) -> dict[str, Any]:
    sent = result.get("sent_monotonic_ns")
    first = result.get("first_event_monotonic_ns")
    answer = result.get("first_answer_monotonic_ns")
    last = result.get("last_token_monotonic_ns")
    usage = result.get("usage") or {}
    completion = usage.get("completion_tokens")
    first_count = result.get("first_event_token_count") or 1
    timestamps = [event["monotonic_ns"] for event in result.get("events", []) if event.get("kind") not in ("metadata", "done")]
    gaps = [(right - left) / 1e9 for left, right in zip(timestamps, timestamps[1:])]
    decode_tps = None
    if completion is not None and first is not None and last is not None and last > first and completion > first_count:
        decode_tps = (completion - first_count) / ((last - first) / 1e9)
    details = usage.get("completion_tokens_details") or {}
    reasoning_tokens = details.get("reasoning_tokens")
    return {
        "ttft_s": (first - sent) / 1e9 if sent and first else None,
        "ttfa_s": (answer - sent) / 1e9 if sent and answer else None,
        "latency_s": (result["end_monotonic_ns"] - sent) / 1e9 if sent else None,
        "decode_tps": decode_tps,
        "end_to_end_tps": completion / ((result["end_monotonic_ns"] - sent) / 1e9) if sent and completion else None,
        "completion_tokens": completion,
        "first_event_token_count": first_count,
        "decode_tokens": completion - first_count if isinstance(completion, int) else None,
        "prompt_tokens": usage.get("prompt_tokens"),
        "reasoning_tokens": reasoning_tokens,
        "answer_tokens": completion - reasoning_tokens if isinstance(completion, int) and isinstance(reasoning_tokens, int) else None,
        "inter_event_gap_p50_s": percentile(gaps, 0.50),
        "inter_event_gap_p95_s": percentile(gaps, 0.95),
        "inter_event_gap_p99_s": percentile(gaps, 0.99),
        "inter_event_gap_max_s": max(gaps, default=None),
        "event_count": len(timestamps),
        "loop_detected": loop_detected(result.get("content", "") + result.get("reasoning", "")),
    }


def overlap_fraction(requests: list[dict[str, Any]]) -> float:
    windows = [(row.get("first_event_monotonic_ns"), row.get("last_token_monotonic_ns")) for row in requests]
    if any(start is None or end is None for start, end in windows):
        return 0.0
    intersection = max(0, min(end for _, end in windows) - max(start for start, _ in windows))
    union = max(end for _, end in windows) - min(start for start, _ in windows)
    return intersection / union if union > 0 else 0.0


def counter_delta(before: dict[str, float | None], after: dict[str, float | None]) -> dict[str, float | None]:
    result = {}
    for key in before:
        left, right = before[key], after.get(key)
        result[key] = right - left if left is not None and right is not None and right >= left else None
    return result


def prompt_tokens_mismatch(actual: Any, expected: Any) -> bool:
    """The chat template and tool rendering add a few tokens that /tokenize does not reproduce
    exactly, so compare with a tolerance of 8 tokens or 0.5%, whichever is larger."""
    if actual is None or expected is None:
        return False
    tolerance = max(24.0, 0.005 * float(expected))
    return abs(float(actual) - float(expected)) > tolerance


def validate_cell(cell: dict[str, Any], concurrency: int) -> list[str]:
    reasons: list[str] = []
    requests = cell["requests"]
    if len(requests) != concurrency:
        reasons.append("fewer_than_C_receipts")
    if any(row.get("error") for row in requests):
        reasons.append("request_error")
    if any((row.get("metrics") or {}).get("loop_detected") for row in requests):
        reasons.append("loop_detected")
    if any((row.get("metrics") or {}).get("completion_tokens") in (None, 0) for row in requests):
        reasons.append("missing_usage")
    if any(row.get("output_corrupt") for row in requests):
        reasons.append("output_corruption")
    # Output-shape deviations (e.g. JSON followed by prose) are a quality signal, not contamination:
    # they are counted and reported as a guardrail rate, and do not discard the speed measurement.
    if any(row.get("prompt_token_mismatch") for row in requests):
        reasons.append("prompt_token_mismatch")
    # overlap is reported, never fatal: a mixed real workload finishes streams at different times
    log = cell.get("engine_log") or {}
    if (log.get("max_running") or 0) > concurrency:
        reasons.append("effective_concurrency_or_foreign_request")
    if (log.get("max_queued") or 0) > max(0, concurrency - 1):
        reasons.append("queue_beyond_barrier_admission")
    # Chunked prefill logs one "#new-seq: 1" line per chunk, so a long prompt looks like many
    # sequences. Compare prefilled token volume with what the requests actually consumed instead.
    expected_prompt_tokens = sum((row.get("metrics") or {}).get("prompt_tokens") or 0 for row in requests)
    prefilled = log.get("prefill_tokens") or 0
    if expected_prompt_tokens:
        if prefilled < 0.85 * expected_prompt_tokens:
            reasons.append("missing_prefill_tokens")
        elif prefilled > 1.25 * expected_prompt_tokens + 4096:
            reasons.append("foreign_prefill_tokens")
    elif log.get("prefill_sequences", 0) > concurrency:
        reasons.append("foreign_or_missing_prefill")
    if log.get("cached_tokens", 0) > 0:
        reasons.append("cold_prefix_cache_hit")
    # SGLang logs a decode line every decode_log_interval (40) steps, so a short answer
    # (e.g. a tool call) legitimately produces none. Only demand log evidence when the
    # wave generated enough tokens that at least one line must have been written.
    generated = sum((row.get("metrics") or {}).get("completion_tokens") or 0 for row in requests)
    expect_log_steps = generated >= 40 * 2 * max(1, concurrency)
    if not log.get("decode_steps") and expect_log_steps:
        reasons.append("missing_engine_steps")
    if log.get("accept_len_median") is None and expect_log_steps:
        reasons.append("missing_spec_metrics")
    if log.get("health_events"):
        reasons.append("rank_fabric_or_health_event")
    if cell.get("memory_guard_failed"):
        reasons.append("memory_below_3_gib")
    before, after = cell.get("counter_before", {}), cell.get("counter_after", {})
    # gauges (instantaneous last-batch values) legitimately go down; only totals must be monotonic
    gauges = {"running", "queued", "accept_length_gauge", "accept_rate_gauge"}
    if any(key not in gauges and before.get(key) is not None and after.get(key) is not None and after[key] < before[key] for key in before):
        reasons.append("non_monotonic_counter")
    telemetry = cell.get("telemetry_samples") or []
    if not telemetry or any(sample.get("node_telemetry_error") for sample in telemetry):
        reasons.append("missing_four_node_telemetry")
    # A barrier start necessarily queues the other C-1 requests while the first one prefills;
    # only queueing beyond that means the server admitted foreign work.
    if any((sample.get("queued") or 0) > max(0, concurrency - 1) for sample in telemetry):
        reasons.append("queue_beyond_barrier_admission")
    for sample in telemetry:
        for node in (sample.get("nodes") or {}).values():
            if throttle_blocking(node.get("throttle_reason")):
                reasons.append("temperature_or_clock_throttle")
    for node in (cell.get("node_telemetry_summary") or {}).values():
        if (node.get("roce_retry_errors") or {}).get("delta", 0) != 0:
            reasons.append("roce_retry")
    return sorted(set(reasons))


def summarize_node_telemetry(samples: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    fields = ("mem_available_gib", "load1", "gpu_util_pct", "sm_clock_mhz", "temperature_c", "power_w", "nvme_read_sectors", "nvme_write_sectors", "roce_rx_packets", "roce_tx_packets", "roce_retry_errors")
    for host in MEMORY_HOSTS:
        rows = [sample.get("nodes", {}).get(host, {}) for sample in samples if sample.get("nodes", {}).get(host)]
        host_result = {}
        for field in fields:
            values = [float(row[field]) for row in rows if row.get(field) is not None]
            if values:
                host_result[field] = {"min": min(values), "median": statistics.median(values), "max": max(values), "delta": values[-1] - values[0]}
        result[host] = host_result
    return result


def derive_cell_metrics(requests: list[dict[str, Any]], log: dict[str, Any], deltas: dict[str, Any], counter_window_s: float | None = None) -> dict[str, Any]:
    valid = [row for row in requests if row.get("metrics", {}).get("decode_tps") is not None]
    firsts = [row["first_event_monotonic_ns"] for row in valid]
    lasts = [row["last_token_monotonic_ns"] for row in valid]
    tokens = [row["metrics"]["decode_tokens"] for row in valid]
    window = (max(lasts) - min(firsts)) / 1e9 if firsts and max(lasts) > min(firsts) else None
    aggregate = sum(tokens) / window if window else None
    steps = deltas.get("verify_steps") or log.get("decode_steps")
    committed = deltas.get("generated_tokens") or sum(max(0, token) for token in tokens)
    decomposition_window = counter_window_s if deltas.get("verify_steps") is not None and counter_window_s else window
    step_window = (log.get("last_log_timestamp"), log.get("first_log_timestamp"))
    return {
        "median_stream_tps": statistics.median(row["metrics"]["decode_tps"] for row in valid) if valid else None,
        "p10_stream_tps": percentile([row["metrics"]["decode_tps"] for row in valid], 0.10),
        "aggregate_wave_tps": aggregate,
        "decode_window_s": window,
        "counter_window_s": counter_window_s,
        "steady_server_tps": (deltas.get("generated_tokens") / counter_window_s) if counter_window_s and deltas.get("generated_tokens") is not None else log.get("generation_tps_median"),
        "verify_steps": steps,
        "steps_per_s": steps / decomposition_window if steps and decomposition_window else None,
        "committed_tokens": committed,
        "committed_tokens_per_step": committed / steps if steps else None,
        "draft_proposed": deltas.get("draft_proposed") if deltas.get("draft_proposed") is not None else log.get("draft_proposed"),
        "draft_accepted": deltas.get("draft_accepted") if deltas.get("draft_accepted") is not None else log.get("draft_accepted"),
        "acceptance_ratio": deltas.get("draft_accepted") / deltas.get("draft_proposed") if deltas.get("draft_proposed") else log.get("accept_rate_mean"),
        "verify_length_mix": log.get("cap_len_mix", {}),
        "engine_step_gap_p95_s": log.get("engine_step_gap_p95_s"),
        "step_window_log_timestamps": step_window,
    }


def context_index(path: Path) -> tuple[Path, dict[tuple[str, int, int, str, str, int, int], dict[str, Any]]]:
    rows = read_jsonl(path)
    index = {(row["prompt_id"], int(row["replicate"]), int(row["stream"]), row["context"], row.get("profile", "G0"), int(row.get("variant", 0)), int(row.get("concurrency", 1))): row for row in rows}
    return path.parent, index


def prompt_waves(prompts: list[dict[str, Any]], concurrency: int, tier: str, block: int, rng: random.Random) -> list[list[dict[str, Any]]]:
    ordered = sorted(prompts, key=lambda prompt: (CATEGORY_ORDER.index(prompt["category"]), prompt["id"]))
    if tier == "gate":
        if concurrency == 1:
            return [[ordered[block % len(ordered)]]]
        offset = block % len(ordered)
        rotated = ordered[offset:] + ordered[:offset]
        chosen = []
        for index in range(concurrency):
            category = CATEGORY_ORDER[index % len(CATEGORY_ORDER)]
            candidates = [prompt for prompt in rotated if prompt["category"] == category and prompt not in chosen]
            chosen.append(candidates[(index // len(CATEGORY_ORDER)) % len(candidates)])
        shift = block % concurrency
        return [chosen[shift:] + chosen[:shift]]
    # Full: all 16 prompts at C1; category-balanced rotations at C4/C8.
    if concurrency == 1:
        return [[prompt] for prompt in ordered]
    categories = {category: [prompt for prompt in ordered if prompt["category"] == category] for category in CATEGORY_ORDER}
    waves = []
    count = 4 if concurrency == 4 else 2
    for wave in range(count):
        selected = []
        per_category = concurrency // 4
        for category_index, category in enumerate(CATEGORY_ORDER):
            for slot in range(per_category):
                selected.append(categories[category][wave * per_category + slot])
        shift = block % concurrency
        waves.append(selected[shift:] + selected[:shift])
    return waves


def tier_cells(tier: str, profiles: list[str], contexts: list[str], concurrencies: list[int], rng: random.Random) -> list[tuple[str, str, int]]:
    if tier == "gate":
        defaults = [(profile, context, concurrency) for profile in ("S1-omp", "S0") for context in ("0", "32k") for concurrency in (1, 4, 8)]
        defaults.append(("S1-omp", "128k", 1))
        cells = [cell for cell in defaults if cell[0] in profiles and cell[1] in contexts and cell[2] in concurrencies]
    else:
        cells = [(profile, context, concurrency) for profile in profiles for context in contexts for concurrency in concurrencies]
    rng.shuffle(cells)
    return cells


def flush_prefix_cache(base_url: str) -> str:
    """Drop the radix/prefix cache so a cold-prefix cell cannot inherit an earlier run's blocks.
    The endpoint returns 400 while requests are in flight, so call it only when idle."""
    try:
        request = urllib.request.Request(base_url.rstrip("/") + "/flush_cache", method="POST")
        with urllib.request.urlopen(request, timeout=30) as response:
            return f"ok:{response.status}"
    except Exception as exc:
        return f"skipped:{type(exc).__name__}"


def wait_for_idle(base_url: str, seconds: float, timeout: float) -> dict[str, Any]:
    start = time.monotonic()
    idle_since = None
    mode = "metrics"
    node_samples: list[dict[str, Any]] = []
    last_nodes = 0.0
    last_stability_reasons: list[str] = []
    while time.monotonic() - start < timeout:
        metrics = fetch_metrics(base_url)
        counters = normalized_counters(metrics)
        if counters["running"] is None or counters["queued"] is None:
            mode = "engine_log"
            recent = docker_logs(time.time() - 2)
            busy = [
                line for line in recent.splitlines()
                if ("Decode batch" in line or "Prefill batch" in line)
                and not (
                    "Prefill batch" in line
                    and (lambda m: bool(m) and int(m.group(1)) <= HEALTH_PROBE_MAX_TOKENS)(re.search(r"#new-token:\s*(\d+)", line))
                )
            ]
            idle = not busy
        else:
            idle = counters["running"] == 0 and counters["queued"] == 0
        if time.monotonic() - last_nodes >= 2.0:
            # nvidia-smi can stall while the GPUs are saturated; retry before giving up on the whole run
            for attempt in range(3):
                try:
                    nodes = cluster_telemetry()
                    break
                except Exception as exc:
                    if attempt == 2:
                        raise
                    time.sleep(2.0)
            if not memory_safe({host: row["mem_available_gib"] for host, row in nodes.items()}):
                raise RuntimeError(f"idle gate memory below 3 GiB: {nodes}")
            node_samples.append({"monotonic_ns": time.monotonic_ns(), "nodes": nodes})
            last_nodes = time.monotonic()
        if idle:
            idle_since = idle_since or time.monotonic()
            if time.monotonic() - idle_since >= seconds:
                stable, reasons = idle_nodes_stable(node_samples)
                if stable:
                    return {"mode": mode, "idle_seconds": seconds, "wait_seconds": time.monotonic() - start, "node_samples": node_samples, "stability": "passed"}
                last_stability_reasons = reasons
                idle_since = None
        else:
            idle_since = None
        time.sleep(0.5)
    raise TimeoutError(f"server did not remain idle/stable for {seconds}s within {timeout}s; stability={last_stability_reasons}")


def telemetry_loop(base_url: str, stop: threading.Event, cancel: threading.Event, long_context: bool, samples: list[dict[str, Any]]) -> None:
    while not stop.is_set():
        metrics = normalized_counters(fetch_metrics(base_url))
        sample: dict[str, Any] = {"monotonic_ns": time.monotonic_ns(), **metrics}
        try:
            nodes = cluster_telemetry()
            sample["nodes"] = nodes
            memory = {host: row["mem_available_gib"] for host, row in nodes.items()}
            if long_context and not memory_safe(memory):
                cancel.set()
        except Exception as exc:
            sample["node_telemetry_error"] = str(exc)
            if long_context:
                cancel.set()
        samples.append(sample)
        stop.wait(2.0)


def run_wave(
    args: argparse.Namespace,
    run_dir: Path,
    root: Path,
    index: dict[tuple[str, int, int, str, str, int, int], dict[str, Any]],
    prompts: list[dict[str, Any]],
    profile: str,
    context: str,
    concurrency: int,
    block_id: str,
    replicate_number: int,
    wave_number: int,
    continuous: bool,
    variant: int,
) -> dict[str, Any]:
    replicate = replicate_number
    entries = []
    bodies = []
    for stream, prompt in enumerate(prompts):
        key = (prompt["id"], replicate, stream, context, profile, variant, concurrency)
        if key not in index:
            raise KeyError(f"missing built context {key}; rebuild contexts with enough replicates/streams")
        entry = index[key]
        context_request = load_context_object(root, entry)
        seed = int(sha256(f"{args.pair_id}|{block_id}|{prompt['id']}|{stream}")[:8], 16)
        entries.append((prompt, entry, seed))
        bodies.append(request_body(context_request, profile, seed, args.model, continuous))
    idle = wait_for_idle(args.base_url, args.idle_seconds, args.idle_timeout)
    idle["flush_cache"] = flush_prefix_cache(args.base_url)
    initial_memory = memory_snapshot() if context in LONG_CONTEXTS else None
    if initial_memory is not None and not memory_safe(initial_memory):
        raise RuntimeError(f"memory guard: below 3 GiB before cell: {initial_memory}")
    before_metrics_raw = fetch_metrics(args.base_url)
    before = normalized_counters(before_metrics_raw)
    start_wall = time.time()
    barrier = threading.Barrier(concurrency)
    cancel = threading.Event()
    stop = threading.Event()
    telemetry: list[dict[str, Any]] = []
    monitor = threading.Thread(target=telemetry_loop, args=(args.base_url, stop, cancel, context in LONG_CONTEXTS, telemetry), daemon=True)
    monitor.start()
    active_responses: set[Any] = set()
    active_lock = threading.Lock()
    def cancel_open_responses() -> None:
        cancel.wait()
        with active_lock:
            responses = list(active_responses)
        for response in responses:
            try:
                response.close()
            except OSError:
                pass
    cancel_watcher = threading.Thread(target=cancel_open_responses, daemon=True)
    cancel_watcher.start()
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [pool.submit(stream_request, args.base_url, body, barrier, cancel, args.request_timeout, active_responses, active_lock) for body in bodies]
        results = [future.result() for future in futures]
    memory_guard_failed = cancel.is_set()
    cancel.set()  # release the response-cancellation watcher after normal completion
    cancel_watcher.join(timeout=2)
    stop.set()
    monitor.join(timeout=5)
    end_wall = time.time()
    after_metrics_raw = fetch_metrics(args.base_url)
    after = normalized_counters(after_metrics_raw)
    log_text = docker_logs(start_wall, end_wall)
    log = parse_engine_log(log_text)
    deltas = counter_delta(before, after)
    request_receipts = []
    cell_id = f"{block_id}-{profile}-{context}-c{concurrency}-w{wave_number}-a{uuid.uuid4().hex[:8]}"
    for stream, ((prompt, entry, seed), body, result) in enumerate(zip(entries, bodies, results)):
        metrics = derive_request_metrics(result)
        correctness_valid, correctness_reasons = validate_output_shape(prompt["id"], prompt["category"], result.get("content", ""), result.get("tool_calls", []))
        if not correctness_valid and result.get("finish_reason") == "tool_calls" and result.get("tool_calls") and result.get("tool_calls_valid", True):
            # omp sends tools on every request; answering with a well-formed tool call is valid for any category
            correctness_valid, correctness_reasons = True, ["answered_with_tool_calls"]
        if not correctness_valid and result.get("finish_reason") == "length":
            # truncated by the benchmark-only max_tokens cap: shape cannot be judged
            correctness_valid, correctness_reasons = True, ["truncated_by_benchmark_cap"]
        receipt = {
            "schema": "dsbench.request.v1",
            "run_id": args.run_id,
            "cell_id": cell_id,
            "model": args.model,
            "label": args.label,
            "arm": args.arm,
            "pair_id": args.pair_id,
            "boot_id": args.boot_id,
            "block_id": block_id,
            "profile": profile,
            "context": context,
            "concurrency": concurrency,
            "wave": wave_number,
            "context_variant": variant,
            "stream": stream,
            "prompt_id": prompt["id"],
            "category": prompt["category"],
            "context_request_sha256": entry["request_sha256"],
            "serialized_request_sha256": sha256(canonical_json(body)),
            "prompt_tokens_verified": entry["prompt_tokens"],
            "sampling": {key: body[key] for key in ("temperature", "top_p", "seed", "max_tokens")},
            "thinking": body["chat_template_kwargs"]["thinking"],
            "benchmark_output_cap_notice": "max_tokens is benchmark-only; production omp sends no output cap",
            **result,
            "metrics": metrics,
            "output_corrupt": not (result.get("content") or result.get("reasoning") or result.get("tool_calls_text")) or not result.get("tool_calls_valid", True),
            "prompt_token_mismatch": prompt_tokens_mismatch(metrics.get("prompt_tokens"), entry["prompt_tokens"]),
            "correctness_valid": correctness_valid,
            "correctness_reasons": correctness_reasons,
        }
        append_jsonl(run_dir / "requests.jsonl", receipt)
        request_receipts.append(receipt)
    overlap = overlap_fraction(request_receipts)
    cell = {
        "schema": "dsbench.cell.v1",
        "run_id": args.run_id,
        "cell_id": cell_id,
        "label": args.label,
        "arm": args.arm,
        "pair_id": args.pair_id,
        "boot_id": args.boot_id,
        "block_id": block_id,
        "profile": profile,
        "context": context,
        "concurrency": concurrency,
        "wave": wave_number,
        "context_variant": variant,
        "idle_gate": idle,
        "initial_mem_available_gib": initial_memory,
        "memory_guard_failed": memory_guard_failed,
        "counter_source": "prometheus" if metrics_support_decomposition(before_metrics_raw) and metrics_support_decomposition(after_metrics_raw) else "engine_log",
        "counter_before": before,
        "counter_after": after,
        "counter_before_raw": before_metrics_raw,
        "counter_after_raw": after_metrics_raw,
        "counter_delta": deltas,
        "engine_log": log,
        "engine_log_sha256": sha256(log_text),
        "telemetry_samples": telemetry,
        "node_telemetry_summary": summarize_node_telemetry(telemetry),
        "overlap_fraction": overlap,
        "request_ids": [row["prompt_id"] + f":s{row['stream']}" for row in request_receipts],
        "context_request_hashes": [row["context_request_sha256"] for row in request_receipts],
        "requests": request_receipts,
    }
    cell["metrics"] = derive_cell_metrics(request_receipts, log, deltas, end_wall - start_wall)
    cell["metrics"]["correctness_failures"] = sum(1 for row in request_receipts if row.get("correctness_valid") is False)
    cell["metrics"]["correctness_reasons"] = sorted({reason for row in request_receipts for reason in (row.get("correctness_reasons") or []) if reason != "answered_with_tool_calls"})
    cell["invalid_reasons"] = validate_cell(cell, concurrency)
    cell["valid"] = not cell["invalid_reasons"]
    append_jsonl(run_dir / "cells.jsonl", {key: value for key, value in cell.items() if key != "requests"})
    return cell


def smoke_tests(args: argparse.Namespace) -> dict[str, Any]:
    models = http_json(args.base_url.rstrip("/") + "/v1/models", timeout=20)
    ids = [row.get("id") for row in models.get("data", [])]
    if args.model not in ids:
        raise RuntimeError(f"model {args.model!r} not advertised: {ids}")
    base = {"model": args.model, "max_tokens": 32, "temperature": 0, "stream": False, "chat_template_kwargs": {"thinking": False, "enable_thinking": False}}
    checks = {}
    checks["identity"] = ids
    checks["correctness"] = http_json(args.base_url.rstrip("/") + "/v1/chat/completions", {**base, "messages": [{"role": "user", "content": "Reply with exactly BENCH_OK."}]}, 120)
    tool_body = {**base, "max_tokens": 256, "chat_template_kwargs": {"thinking": True, "enable_thinking": True}, "messages": [{"role": "user", "content": "Call read_file for README.md."}], "tools": [OMP_TOOLS[0]], "tool_choice": "auto"}
    checks["tool"] = http_json(args.base_url.rstrip("/") + "/v1/chat/completions", tool_body, 120)
    pixel = base64.b64encode(base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=")).decode()
    vision_body = {**base, "messages": [{"role": "user", "content": [{"type": "text", "text": "Describe the image briefly."}, {"type": "image_url", "image_url": {"url": "data:image/png;base64," + pixel}}]}]}
    checks["vision"] = http_json(args.base_url.rstrip("/") + "/v1/chat/completions", vision_body, 120)
    correctness_message = ((checks["correctness"].get("choices") or [{}])[0].get("message") or {})
    tool_message = ((checks["tool"].get("choices") or [{}])[0].get("message") or {})
    vision_message = ((checks["vision"].get("choices") or [{}])[0].get("message") or {})
    result = {
        "models": ids,
        "correctness_ok": str(correctness_message.get("content") or "").strip() == "BENCH_OK",
        "tool_ok": bool(tool_message.get("tool_calls")),
        "vision_ok": bool(str(vision_message.get("content") or "").strip()),
    }
    if not all(result[key] for key in ("correctness_ok", "tool_ok", "vision_ok")):
        raise RuntimeError(f"identity/vision/tool/correctness smoke failed: {result}")
    return result


def probe_continuous_usage(args: argparse.Namespace) -> bool:
    body = request_body({"messages": [{"role": "user", "content": "Reply OK."}]}, "G0", 1, args.model, True)
    body["max_tokens"] = 2
    barrier = threading.Barrier(1)
    result = stream_request(args.base_url, body, barrier, threading.Event(), 120)
    if not result["error"]:
        return True
    if "400" in result["error"] or "422" in result["error"]:
        return False
    raise RuntimeError(f"continuous usage probe failed unexpectedly: {result['error']}")


def capture_manifest(args: argparse.Namespace, prompts_path: Path, contexts_path: Path) -> dict[str, Any]:
    inspect = run_command(["docker", "inspect", "dsv41-head"], timeout=30)
    image_id = args.image_id
    env: dict[str, str] = {}
    container_command = None
    if inspect.returncode == 0:
        try:
            item = json.loads(inspect.stdout)[0]
            image_id = image_id or item.get("Image")
            container_command = {"entrypoint": item.get("Config", {}).get("Entrypoint"), "cmd": item.get("Config", {}).get("Cmd")}
            for assignment in item.get("Config", {}).get("Env", []):
                name, _, value = assignment.partition("=")
                env[name] = "<redacted>" if re.search(r"TOKEN|PASS|KEY|SECRET|CREDENTIAL|AUTH", name, re.I) else value
        except (ValueError, KeyError, IndexError):
            pass
    head = docker_logs(time.time() - args.manifest_log_hours * 3600)
    server_args: Any = None
    matches = re.findall(r"server_args\s*=\s*(.+)", head)
    if matches:
        server_args = matches[-1][-20000:]
    elif container_command:
        server_args = {"source": "docker-inspect-command", **container_command}
    prompt_rows = read_jsonl(prompts_path)
    return {
        "schema": "dsbench.manifest.v1",
        "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "run_id": args.run_id,
        "label": args.label,
        "arm": args.arm,
        "pair_id": args.pair_id,
        "boot_id": args.boot_id,
        "model_id": args.model,
        "model_revision": args.model_revision,
        "tokenizer_hash": args.tokenizer_hash,
        "chat_template_hash": args.chat_template_hash,
        "engine_commit": args.engine_commit,
        "image_id": image_id,
        "server_args": server_args,
        "container_command": container_command,
        "engine_environment": env,
        "git_commits": dict(item.split("=", 1) for item in args.git),
        "harness_commit": args.harness_commit,
        "prompts_path": str(prompts_path),
        "prompts_sha256": sha256(prompts_path.read_bytes()),
        "prompt_request_hashes": {row["id"]: sha256(canonical_json(row)) for row in prompt_rows},
        "contexts_path": str(contexts_path),
        "contexts_index_sha256": sha256(contexts_path.read_bytes()),
        "profiles": {name: PROFILES[name] for name in args.profile_names},
        "tier": args.tier,
        "blocks": args.blocks,
        "block_offset": args.block_offset,
        "replicate_offset": args.replicate_offset,
        "contexts": args.context_names,
        "concurrencies": args.concurrency_values,
        "warmup_waves": 0 if args.skip_warmup else args.warmup_waves,
        "smoke_skipped": args.skip_smoke,
        "output_caps_benchmark_only": True,
        "clock_sources": {"client_events": "time.monotonic_ns", "receipts": "time.time", "engine_log": "UTC container timestamps"},
        "host": os.uname().nodename,
        "cluster_inventory": cluster_inventory(),
        "python": sys.version,
    }


def run_hook(command: str | None, name: str) -> None:
    if not command:
        return
    result = run_command(command, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(f"{name} hook failed ({result.returncode}): {result.stderr.strip()}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://10.10.10.12:8888")
    parser.add_argument("--model", default="deepseek-v4.1-flash")
    parser.add_argument("--prompts", type=Path, default=Path(__file__).parent / "prompts/prompts-v1.jsonl")
    parser.add_argument("--contexts-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("runs"))
    parser.add_argument("--tier", choices=("gate", "full"), default="gate")
    parser.add_argument("--profiles", help="default: S1-omp,S0 for gate; G0,S0,S1-omp for full")
    parser.add_argument("--contexts", default="0,32k,128k,400k")
    parser.add_argument("--concurrencies", default="1,4,8")
    parser.add_argument("--blocks", type=int, default=1)
    parser.add_argument("--block-offset", type=int, default=0, help="global paired block number for the first local block")
    parser.add_argument("--context-replicates", type=int, default=0, help="0: infer from context index")
    parser.add_argument("--replicate-offset", type=int, default=0, help="first context replicate for this boot/day")
    parser.add_argument("--label", required=True)
    parser.add_argument("--arm", default="single")
    parser.add_argument("--pair-id", default="unpaired")
    parser.add_argument("--boot-id", required=True)
    parser.add_argument("--model-revision", required=True)
    parser.add_argument("--tokenizer-hash", required=True)
    parser.add_argument("--chat-template-hash", required=True)
    parser.add_argument("--engine-commit", required=True)
    parser.add_argument("--image-id")
    parser.add_argument("--harness-commit", default="working-tree")
    parser.add_argument("--git", action="append", default=[], metavar="NAME=COMMIT")
    parser.add_argument("--pause-cmd")
    parser.add_argument("--resume-cmd")
    parser.add_argument("--idle-seconds", type=float, default=10.0)
    parser.add_argument("--idle-timeout", type=float, default=300.0)
    parser.add_argument("--request-timeout", type=float, default=1800.0)
    parser.add_argument("--attempts", type=int, choices=(3,), default=3)
    parser.add_argument("--warmup-waves", type=int, default=2)
    parser.add_argument("--manifest-log-hours", type=float, default=24.0)
    parser.add_argument("--skip-smoke", action="store_true", help="development/mock only")
    parser.add_argument("--skip-warmup", action="store_true", help="development/mock only")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if bool(args.pause_cmd) != bool(args.resume_cmd):
        raise SystemExit("--pause-cmd and --resume-cmd must be supplied together")
    if args.block_offset < 0:
        raise SystemExit("--block-offset must be non-negative")
    if args.warmup_waves < 2:
        raise SystemExit("--warmup-waves must be at least 2")
    args.profile_names = csv_list(args.profiles or ("S1-omp,S0" if args.tier == "gate" else "G0,S0,S1-omp"))
    if unknown := set(args.profile_names) - PROFILES.keys():
        raise SystemExit(f"unknown profiles: {sorted(unknown)}")
    args.context_names = [CONTEXT_ALIASES.get(item, item) for item in csv_list(args.contexts)]
    if unknown := set(args.context_names) - set(CONTEXT_ALIASES.values()):
        raise SystemExit(f"unknown contexts: {sorted(unknown)}")
    args.concurrency_values = [int(item) for item in csv_list(args.concurrencies)]
    if any("=" not in item for item in args.git):
        raise SystemExit("--git must be NAME=COMMIT")
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    args.run_id = f"{stamp}-{args.label}-{uuid.uuid4().hex[:8]}"
    run_dir = args.output / args.run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    context_root, contexts = context_index(args.contexts_file)
    available_replicates = sorted({key[1] for key in contexts})
    if available_replicates != list(range(len(available_replicates))):
        raise SystemExit(f"context replicate IDs must be contiguous from zero: {available_replicates}")
    if args.context_replicates == 0:
        args.context_replicates = len(available_replicates)
    if args.context_replicates > len(available_replicates):
        raise SystemExit(f"--context-replicates={args.context_replicates} exceeds {len(available_replicates)} in index")
    if args.replicate_offset < 0 or args.replicate_offset + args.blocks > args.context_replicates:
        raise SystemExit(f"replicate offset {args.replicate_offset} plus {args.blocks} blocks exceeds {args.context_replicates} distinct contexts")
    available_variants = sorted({key[5] for key in contexts})
    required_variants = args.warmup_waves + args.attempts
    if available_variants != list(range(len(available_variants))) or len(available_variants) < required_variants:
        raise SystemExit(f"context variants must be contiguous from zero and include {required_variants} entries: {available_variants}")
    prompts = read_jsonl(args.prompts)
    manifest = capture_manifest(args, args.prompts, args.contexts_file)
    write_json_atomic(run_dir / "manifest.preflight.json", manifest)
    resumed = False
    try:
        run_hook(args.pause_cmd, "pause")
        resumed = bool(args.pause_cmd)
        continuous = probe_continuous_usage(args)
        manifest["continuous_usage_stats_supported"] = continuous
        manifest["metrics_available"] = metrics_support_decomposition(fetch_metrics(args.base_url))
        if not args.skip_smoke:
            manifest["smoke"] = smoke_tests(args)
        write_json_atomic(run_dir / "manifest.json", manifest)
        rng = random.Random(int(sha256(args.pair_id)[:16], 16))
        cells = tier_cells(args.tier, args.profile_names, args.context_names, args.concurrency_values, rng)
        # Warm the exact selected graph shapes with bounded discarded waves.
        if not args.skip_warmup:
            for profile, context, concurrency in cells:
                warm_prompts = prompt_waves(prompts, concurrency, "gate", 0, rng)[0]
                for warm in range(args.warmup_waves):
                    result = run_wave(args, run_dir, context_root, contexts, warm_prompts, profile, context, concurrency, "warmup", args.replicate_offset, warm, continuous, warm)
                    append_jsonl(run_dir / "warmups.jsonl", {"cell_id": result["cell_id"], "valid": result["valid"], "discarded": True})
                    if not result["valid"]:
                        print(f"warmup validation notes (discarded, continuing): {result['invalid_reasons']}", flush=True)
        for local_block in range(args.blocks):
            block_number = args.block_offset + local_block
            replicate_number = args.replicate_offset + local_block
            block_id = f"b{block_number:03d}"
            block_cells = list(cells)
            rng.shuffle(block_cells)
            for profile, context, concurrency in block_cells:
                waves = prompt_waves(prompts, concurrency, args.tier, block_number, rng)
                for wave_number, wave_prompts in enumerate(waves):
                    final = None
                    for attempt in range(1, args.attempts + 1):
                        variant = args.warmup_waves + attempt - 1
                        try:
                            final = run_wave(args, run_dir, context_root, contexts, wave_prompts, profile, context, concurrency, block_id, replicate_number, wave_number, continuous, variant)
                        except (RuntimeError, TimeoutError, subprocess.TimeoutExpired, urllib.error.URLError) as exc:
                            reason = "memory_below_3_gib" if "memory" in str(exc).lower() else "harness_exception"
                            final = {
                                "schema": "dsbench.cell.v1", "run_id": args.run_id,
                                "cell_id": f"{block_id}-{profile}-{context}-c{concurrency}-w{wave_number}-a{uuid.uuid4().hex[:8]}",
                                "label": args.label, "arm": args.arm, "pair_id": args.pair_id,
                                "boot_id": args.boot_id, "block_id": block_id, "profile": profile,
                                "context": context, "concurrency": concurrency, "wave": wave_number,
                                "context_variant": variant, "valid": False,
                                "invalid_reasons": [reason], "exception": f"{type(exc).__name__}: {exc}",
                                "metrics": {}, "engine_log": {}, "counter_before": {}, "counter_after": {},
                            }
                            append_jsonl(run_dir / "cells.jsonl", final)
                        print(f"{block_id} {profile} {context} C{concurrency} w{wave_number} attempt {attempt}: {'valid' if final['valid'] else ','.join(final['invalid_reasons'])}", flush=True)
                        if final["valid"]:
                            break
                    if final and not final["valid"]:
                        append_jsonl(run_dir / "blocked.jsonl", {"run_id": args.run_id, "label": args.label, "arm": args.arm, "pair_id": args.pair_id, "boot_id": args.boot_id, "block_id": block_id, "profile": profile, "context": context, "concurrency": concurrency, "wave": wave_number, "reason": final["invalid_reasons"]})
        write_json_atomic(run_dir / "complete.json", {"run_id": args.run_id, "completed_utc": dt.datetime.now(dt.timezone.utc).isoformat()})
    finally:
        if resumed:
            run_hook(args.resume_cmd, "resume")
    print(run_dir)


if __name__ == "__main__":
    main()
