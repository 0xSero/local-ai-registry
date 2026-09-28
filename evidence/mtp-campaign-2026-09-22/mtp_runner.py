#!/usr/bin/env python3
"""MTP campaign queue runner: rent each candidate's exact card on Vast, accept, publish, commit.

    python3 runs/mtp_runner.py runs/queue-a.json

Rents only while the Vast balance is above $5 to start (then above $1.50 per further run), polling
every 10 minutes and logging each check. One recipe at a time per runner; a run is SIGTERMed after
90 minutes (validate_rented.py destroys its instance on SIGTERM), and any leftover
local-ai-validate-* instance is destroyed before and after every run. Never touches instances
without that label. After an acceptance: format, recommend, index, both plugin exports,
validate, commit (under a directory lock so two runners never commit at once).
"""
import datetime as dt
import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path("/Users/sero/local-omarchy/registry-v6")
RUNS = ROOT / "runs"
LOG = ROOT / "MTP-CAMPAIGN.log"
LOCK = RUNS / ".commit.lock"
START_BALANCE, CONTINUE_BALANCE = 5.0, 1.5
RUN_LIMIT_S = 90 * 60
GATEWAY = str(Path.home() / "local-omarchy" / "local-ai-images" / "gateway" / "gateway.py")
os.chdir(ROOT)
RUNS.mkdir(exist_ok=True)
NAME = Path(sys.argv[1]).stem
QUEUE_IDS = {i["id"] for i in json.loads(Path(sys.argv[1]).read_text())}
PIDFILE = RUNS / f"{NAME}.pid"


def log(msg):
    stamp = dt.datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M:%S%z")
    line = f"[{stamp}] [{NAME}] {msg}"
    with LOG.open("a") as f:
        f.write(line + "\n")
    print(line, flush=True)


def sh(argv, timeout=120, **kw):
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout, **kw)


def balance():
    try:
        user = json.loads(sh(["vastai", "show", "user", "--raw"], 60).stdout)
        # spendable money is .credit (prepaid) plus .balance (Sero, 2026-09-22): the > $5 rule applies to their sum
        return float(user.get("credit") or 0) + float(user.get("balance") or 0)
    except Exception as error:  # noqa: BLE001
        log(f"balance check failed: {error}")
        return None


def our_instances(rid):
    """Only the instance of the recipe this runner is running right now: two queues may list the same
    recipe, and another runner's live validation must never be touched."""
    try:
        return [i for i in json.loads(sh(["vastai", "show", "instances", "--raw"], 60).stdout)
                if str(i.get("label") or "") == f"local-ai-validate-{rid}"[:191]]
    except Exception as error:  # noqa: BLE001
        log(f"instance check failed: {error}")
        return []


def destroy_ours(rid, why):
    for inst in our_instances(rid):
        try:
            r = sh(["vastai", "destroy", "instance", str(inst["id"]), "--raw"], 90, input="y\n")
            log(f"destroyed leftover instance {inst['id']} ({inst.get('label')}) {why}: {(r.stdout or r.stderr).strip()[:120]}")
        except Exception as error:  # noqa: BLE001
            log(f"WARNING could not destroy {inst['id']}: {error}")


def wait_balance(minimum):
    while True:
        b = balance()
        log(f"vast balance {b} (need > {minimum})")
        if b is not None and b > minimum:
            return b
        time.sleep(600)


def recipe(rid):
    return json.loads((ROOT / "registry" / "recipe" / f"{rid}.json").read_text())


def publish(rid):
    while True:
        try:
            LOCK.mkdir()
            break
        except FileExistsError:
            time.sleep(5)
    try:
        steps = (["python3", "scripts/format_registry.py"], ["python3", "scripts/recommend.py"],
                 ["python3", "scripts/curate_registry.py", "--index-only"], ["python3", "scripts/format_registry.py"],
                 ["python3", "scripts/export_plugin_recipes.py", "--out", "plugin/recipes.json"],
                 ["python3", "scripts/export_plugin_v2.py", "--out", "plugin/v2/recipes.json"],
                 ["python3", "scripts/validate_registry.py"])
        for argv in steps:
            r = sh(argv, 900)
            if r.returncode != 0:
                log(f"publish step failed {' '.join(argv[1:])}: {(r.stderr or r.stdout)[-500:]}")
                return False
        flagged = bool(recipe(rid).get("recommended"))
        sh(["git", "add", "-A", "registry", "plugin"], 120)
        r = sh(["git", "commit", "-q", "-m", f"Accept {rid} on its rented card (MTP campaign)\n\n"
                "validate_rented.py on Vast; recommendation and plugin exports refreshed.\n\n"
                "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"], 120)
        if r.returncode != 0:
            log(f"git commit failed: {(r.stderr or r.stdout)[-300:]}")
            return False
        head = sh(["git", "rev-parse", "--short", "HEAD"], 30).stdout.strip()
        log(f"committed {head}: {rid} accepted{' and recommended for ' + recipe(rid)['hardware_id'] if flagged else ''}")
        return True
    finally:
        LOCK.rmdir()


def run_one(item, first):
    rid = item["id"]
    if recipe(rid).get("status") == "validated":
        log(f"skip {rid}: already validated")
        return "done"
    wait_balance(START_BALANCE if first else CONTINUE_BALANCE)
    destroy_ours(rid, "before the run")
    argv = ["python3", "scripts/validate_rented.py", rid, "--provider", "vast",
            "--vast-min-cuda", str(item["min_cuda"]), "--disk", str(item.get("disk", 50))]
    logf = RUNS / f"{rid}.{int(time.time())}.log"
    log(f"start {rid} on {recipe(rid)['hardware_id']}: {' '.join(argv[3:])} -> runs/{logf.name}")
    env = dict(os.environ, LOCAL_AI_GATEWAY=GATEWAY)
    started = time.monotonic()
    with logf.open("w") as f:
        p = subprocess.Popen(argv, stdout=f, stderr=subprocess.STDOUT, env=env)
        try:
            rc = p.wait(timeout=RUN_LIMIT_S)
        except subprocess.TimeoutExpired:
            log(f"{rid}: exceeded 90 min; SIGTERM so the instance is destroyed")
            p.send_signal(signal.SIGTERM)
            try:
                rc = p.wait(timeout=300)
            except subprocess.TimeoutExpired:
                p.kill()
                rc = -9
    minutes = (time.monotonic() - started) / 60
    text = logf.read_text()
    destroy_ours(rid, "after the run")
    decode = re.search(r"acceptance measurements: (decode [^\n]+)", text)
    cost = re.search(r"approx cost: ([^\n]+)", text)
    gpu = re.search(r"created, [^\n]*gpu ([^\n]+)", text)
    if rc == 0 and recipe(rid).get("status") == "validated":
        log(f"ACCEPTED {rid} on {gpu.group(1) if gpu else '?'}: {decode.group(1) if decode else 'no decode line'}; "
            f"{cost.group(1) if cost else ''}; {minutes:.0f} min")
        publish(rid)
        return "done"
    lines = [l for l in text.strip().splitlines() if l.strip()]
    tail = lines[-1] if lines else "no output"
    if "no Vast offers" in text or "every Vast offer tried was already gone" in text:
        log(f"NO OFFER {rid}: {tail[:200]}")
        return "retry"
    log(f"FAILED {rid} rc={rc} after {minutes:.0f} min ({cost.group(1) if cost else 'no cost line'}): {tail[:300]}")
    return "failed"


def main():
    if PIDFILE.exists():
        try:
            os.kill(int(PIDFILE.read_text().strip()), 0)
            print(f"{NAME}: runner already alive (pid {PIDFILE.read_text().strip()}); refusing to start a duplicate", file=sys.stderr)
            return
        except (OSError, ValueError):
            pass
    PIDFILE.write_text(str(os.getpid()))
    pending = json.loads(Path(sys.argv[1]).read_text())
    log(f"runner start: {len(pending)} recipes: {[i['id'] for i in pending]}")
    first = True
    for attempt in range(1, 9):
        retry = []
        for item in pending:
            outcome = run_one(item, first)
            first = False
            if outcome == "retry":
                retry.append(item)
        pending = retry
        if not pending:
            break
        log(f"pass {attempt} done; {len(pending)} waiting for an offer: {[i['id'] for i in pending]}; retry in 60 min")
        time.sleep(3600)
    if pending:
        log(f"runner giving up on {[i['id'] for i in pending]}: no offer in {attempt} passes")
    log("runner finished")


if __name__ == "__main__":
    main()
