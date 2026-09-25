#!/usr/bin/env python3
"""Watch one owned Qwen server and stop it if system swap grows too far.

Example (choose a new JSONL path for each run):
  python3 monitor_memory.py --pid 12345 --output runs/qwen38/memory-watch.jsonl

The default threshold is 8192 MiB above startup swap usage, sampled every ten
seconds. Swap is a system-wide observation: growth is not attributed to this
process. ps RSS does not fully capture Metal/unified GPU allocations and is
not a measurement of the model's complete memory footprint.

Only the explicit PID owned by this user, running the known wrapper with the
original process start time and command, can receive a signal. SIGTERM is
followed by SIGKILL after ten seconds if that same process remains alive.
The monitor does not launch a server or change system memory settings.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shlex
import signal
import subprocess
import sys
import time

MIB = 1024**2
WRAPPER = "registry/asset/qwen38-mlx-vlm-serve.py"
TERMINATION_GRACE_SECONDS = 10


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def command(argv):
    return subprocess.run(argv, capture_output=True, text=True, timeout=5,
                          env={**os.environ, "LC_ALL": "C"}, check=False)


def parse_process(text):
    """Parse ps pid/uid/stat/lstart/rss/args without splitting command contents."""
    fields = text.strip().split(None, 9)
    if len(fields) != 10:
        raise ValueError("ps did not return complete process identity, RSS, and arguments")
    pid, uid, state = int(fields[0]), int(fields[1]), fields[2]
    started = " ".join(fields[3:8])
    rss_kib = int(fields[8])
    if pid < 1 or uid < 0 or rss_kib < 0:
        raise ValueError("ps returned invalid process identity or RSS")
    return {"pid": pid, "uid": uid, "state": state, "started": started,
            "rss_kib": rss_kib, "rss_bytes": rss_kib * 1024, "command": fields[9]}


def read_process(pid):
    result = command(["ps", "-ww", "-p", str(pid), "-o", "pid=", "-o", "uid=",
                      "-o", "stat=", "-o", "lstart=", "-o", "rss=", "-o", "args="])
    if result.returncode == 1 and not result.stdout.strip():
        return None
    if result.returncode != 0:
        raise RuntimeError("could not inspect target process: " + result.stderr.strip())
    if not result.stdout.strip():
        return None
    process = parse_process(result.stdout)
    return None if process["state"].startswith("Z") else process


def guard_process(process, pid, expected=None):
    if process["pid"] != pid or process["uid"] != os.geteuid():
        raise ValueError("target PID must belong to the user running this monitor")
    tokens = shlex.split(process["command"])
    # The marker must be the Python script, not a substring in an unrelated
    # process's argument or a shell/python -c command.
    script_index = 1
    while script_index < len(tokens) and tokens[script_index] in ("-B", "-u", "-I", "-E", "-s", "-S"):
        script_index += 1
    if (len(tokens) <= script_index or not Path(tokens[0]).name.lower().startswith("python")
            or not (tokens[script_index] == WRAPPER or tokens[script_index].endswith("/" + WRAPPER))):
        raise ValueError("target ps arguments do not identify the Qwen registry wrapper")
    if expected is not None and any(process[key] != expected[key] for key in ("pid", "uid", "started", "command")):
        raise ValueError("target PID identity changed; refusing to monitor or signal a replacement process")
    return process


def checked_process(pid, expected=None):
    process = read_process(pid)
    return guard_process(process, pid, expected) if process is not None else None


def public_process(process):
    # Keep complete arguments for the live identity guard, not the saved log.
    return {**{key: value for key, value in process.items() if key != "command"},
            "wrapper": WRAPPER,
            "command_sha256": hashlib.sha256(process["command"].encode()).hexdigest()}


def parse_swapusage(text):
    factors = {"": 1, "K": 1024, "M": MIB, "G": 1024**3, "T": 1024**4}
    fields = {}
    for name, value, unit in re.findall(r"\b(total|used|free)\s*=\s*([0-9]+(?:\.[0-9]+)?)\s*([KMGT]?)(?:i?B)?\b", text):
        fields[name + "_bytes"] = int(Decimal(value) * factors[unit])
    if "used_bytes" not in fields:
        raise ValueError("sysctl vm.swapusage did not contain a valid used-swap quantity")
    return fields


def parse_vm_stat(text):
    page = re.search(r"page size of ([0-9]+) bytes", text)
    return {"page_size_bytes": int(page[1]) if page else None,
            "counters": {name.strip(): int(value) for name, value in
                         re.findall(r"^([^\n:]+):\s*([0-9]+)\.?\s*$", text, re.MULTILINE)}}


def memory_observation():
    swap = command(["sysctl", "vm.swapusage"])
    vm = command(["vm_stat"])
    if swap.returncode != 0:
        raise RuntimeError("cannot measure system swap: " + swap.stderr.strip())
    return {"swap": {**parse_swapusage(swap.stdout), "raw": swap.stdout.strip()},
            "vm_stat": {**parse_vm_stat(vm.stdout), "raw": vm.stdout.strip(),
                        "returncode": vm.returncode, "stderr": vm.stderr.strip()}}


def signal_target(pid, expected, sig, record):
    # Re-read identity immediately before every signal, including escalation.
    current = checked_process(pid, expected)
    if current is None:
        record("server_exited", pid=pid)
        return False
    try:
        os.kill(pid, sig)
    except ProcessLookupError:
        record("server_exited", pid=pid)
        return False
    record("signal_sent", signal=signal.Signals(sig).name, process=public_process(current))
    return True


def terminate_target(pid, expected, record):
    if not signal_target(pid, expected, signal.SIGTERM, record):
        return
    deadline = time.monotonic() + TERMINATION_GRACE_SECONDS
    while True:
        current = checked_process(pid, expected)
        if current is None:
            record("server_exited", pid=pid)
            return
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(1, remaining))
    if not signal_target(pid, expected, signal.SIGKILL, record):
        return
    deadline = time.monotonic() + 5
    while checked_process(pid, expected) is not None:
        if time.monotonic() >= deadline:
            raise RuntimeError("same target is still visible five seconds after SIGKILL")
        time.sleep(0.25)
    record("server_exited", pid=pid)


def monitor(args, record):
    expected = checked_process(args.pid)
    if expected is None:
        record("server_exited", pid=args.pid)
        return 0
    baseline = memory_observation()
    baseline_swap = baseline["swap"]["used_bytes"]
    threshold = int(args.max_swap_growth_mib * MIB)
    record("monitor_started", process=public_process(expected), baseline=baseline,
           baseline_swap_bytes=baseline_swap, max_swap_growth_bytes=threshold,
           sample_interval_seconds=args.interval,
           scope="Swap is global; ps RSS does not fully capture unified GPU allocations.")
    while True:
        time.sleep(args.interval)
        process = checked_process(args.pid, expected)
        if process is None:
            record("server_exited", pid=args.pid)
            return 0
        memory = memory_observation()
        growth = memory["swap"]["used_bytes"] - baseline_swap
        record("sample", process=public_process(process), memory=memory,
               swap_growth_bytes=growth, swap_growth_mib=growth / MIB)
        if growth > threshold:
            record("swap_threshold_exceeded", swap_growth_bytes=growth,
                   max_swap_growth_bytes=threshold, baseline_swap_bytes=baseline_swap)
            terminate_target(args.pid, expected, record)
            return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", type=int, required=True, help="Only this owned server PID may be signaled")
    parser.add_argument("--output", type=Path, required=True, help="New JSONL file; existing files are never overwritten")
    parser.add_argument("--max-swap-growth-mib", type=float, default=8192)
    parser.add_argument("--interval", type=float, default=10, help="Seconds between samples (default: 10)")
    args = parser.parse_args()
    if args.pid <= 0 or args.pid == os.getpid():
        parser.error("--pid must identify another positive process ID")
    if any(not math.isfinite(value) or value <= 0 for value in (args.interval, args.max_swap_growth_mib)):
        parser.error("sample interval and swap-growth threshold must be finite and positive")
    if sys.platform != "darwin":
        parser.error("this monitor requires macOS sysctl, vm_stat and ps")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8", buffering=1) as output:
        def record(event, **fields):
            output.write(json.dumps({"at": utc_now(), "event": event, **fields},
                                    sort_keys=True, allow_nan=False) + "\n")
        try:
            return monitor(args, record)
        except KeyboardInterrupt:
            record("monitor_interrupted", pid=args.pid, further_server_signals=False)
            return 130
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
            record("monitor_error", pid=args.pid, error_type=type(error).__name__, error=str(error))
            print(str(error), file=sys.stderr)
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
