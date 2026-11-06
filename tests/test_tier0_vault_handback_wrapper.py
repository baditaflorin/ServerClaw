"""bin/tier0-vault-handback-rehearsal: the runner wrapper that runs the daily vault handback rehearsal and exports it as metrics.

The stage (fleet-state tier0-vault-handback.sh) is replaced by a shim `tier0-run` that prints a RESULT_JSON line and exits with a scripted code. What matters here: "failed" (the real vault refused the
merged database, or a decision was wrong) stays distinct from "could not run" so the failure alert can fire and a missing replica does not raise it, the previous success time survives a failed run,
the chain lock is WAITED for (a daily job must not be skipped because a simulation was running), and every metric an alert uses is one the wrapper writes.
"""
from __future__ import annotations

import fcntl
import json
import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "config" / "0infer" / "tier0-runner" / "bin" / "tier0-vault-handback-rehearsal"
RULES = ROOT / "config" / "prometheus" / "rules" / "tier0-standby.yml"

OK = {"status": "ok", "startup_rows": 1391, "startup_verify_failed": 0, "merged_rows": 1391}


def run(tmp: Path, result: dict | None, rc: int, hold_lock_seconds=0.0, wait="900", prom_text=None):
    shim = tmp / "tier0-run"
    line = f"RESULT_JSON {json.dumps(result)}\n" if result is not None else ""
    (tmp / "result.txt").write_text(line)                                            # a file, not a quoted string: the error text has apostrophes
    shim.write_text(f"#!/bin/bash\necho \"args: $*\"\ncat '{tmp}/result.txt'\nexit {rc}\n")
    shim.chmod(0o755)
    prom = tmp / "x.prom"
    if prom_text:
        prom.write_text(prom_text)
    lock = tmp / "chain.lock"
    env = dict(os.environ, TIER0_CHAIN_LOCK=str(lock), TIER0_HB_PROM=str(prom), TIER0_RUN=str(shim), TIER0_HB_LOCK_WAIT=wait)
    if shutil.which("flock") is None:                                                # macOS: a flock(1) with the same semantics on the fd the wrapper opened (-w SECONDS supported)
        fl = tmp / "bin" / "flock"
        fl.parent.mkdir(exist_ok=True)
        fl.write_text("#!/usr/bin/env python3\nimport fcntl, sys, time\na = sys.argv[1:]\nwait = 0.0\nif '-w' in a:\n    i = a.index('-w'); wait = float(a[i + 1]); del a[i:i + 2]\n"
                      "a = [x for x in a if x != '-n']\nend = time.time() + wait\nwhile True:\n    try:\n        fcntl.flock(int(a[0]), fcntl.LOCK_EX | fcntl.LOCK_NB); sys.exit(0)\n"
                      "    except OSError:\n        if time.time() >= end: sys.exit(1)\n        time.sleep(0.05)\n")
        fl.chmod(0o755)
        env["PATH"] = f"{fl.parent}:{env['PATH']}"
    holder = open(lock, "w")
    if hold_lock_seconds:
        fcntl.flock(holder, fcntl.LOCK_EX | fcntl.LOCK_NB)
        threading.Timer(hold_lock_seconds, lambda: (fcntl.flock(holder, fcntl.LOCK_UN), holder.close())).start()
    r = subprocess.run(["bash", str(WRAPPER)], capture_output=True, text=True, env=env, timeout=60)
    if not hold_lock_seconds:
        holder.close()
    return r, (prom.read_text() if prom.exists() else None)


def metric(text, name):
    for l in text.splitlines():
        if l.startswith("tier0_runner_vault_handback_rehearsal_" + name + " "):
            return l.split()[-1]
    return None


def test_a_passing_rehearsal_exports_success_and_what_the_real_vault_verified(tmp_path):
    r, prom = run(tmp_path, OK, 0)
    assert r.returncode == 0 and "args: tier0-vault-handback.sh --rehearse" in r.stdout
    assert metric(prom, "ok") == "1" and metric(prom, "could_not_run") == "0" and metric(prom, "rows_verified") == "1391" and metric(prom, "rows_failed_verification") == "0"
    assert metric(prom, "last_success_timestamp_seconds") is not None and metric(prom, "last_exit_code") == "0"


def test_a_failed_rehearsal_is_not_could_not_run_so_the_failure_alert_can_fire(tmp_path):
    r, prom = run(tmp_path, {"status": "failed", "error": "3 rows fail the vault's own verification", "startup_rows": 1391, "startup_verify_failed": 3}, 5)
    assert r.returncode == 5 and metric(prom, "ok") == "0" and metric(prom, "could_not_run") == "0" and metric(prom, "rows_failed_verification") == "3"


def test_could_not_run_is_its_own_state_including_a_run_that_printed_no_result(tmp_path):
    r, prom = run(tmp_path, {"status": "could-not-run", "message": "standby unreachable"}, 3)
    assert metric(prom, "ok") == "0" and metric(prom, "could_not_run") == "1" and metric(prom, "rows_verified") is None
    t = tmp_path / "noresult"; t.mkdir()
    r, prom = run(t, None, 1)
    assert metric(prom, "could_not_run") == "1" and metric(prom, "ok") == "0"


def test_the_previous_success_survives_a_failed_run(tmp_path):
    prev = "tier0_runner_vault_handback_rehearsal_last_success_timestamp_seconds 1790000000\n"
    r, prom = run(tmp_path, {"status": "failed", "error": "x"}, 5, prom_text=prev)
    assert metric(prom, "last_success_timestamp_seconds") == "1790000000"


def test_a_busy_chain_lock_is_waited_for_not_skipped(tmp_path):
    r, prom = run(tmp_path, OK, 0, hold_lock_seconds=1.0, wait="20")
    assert r.returncode == 0 and "skipping" not in r.stdout and metric(prom, "ok") == "1"                 # the simulation finished, the rehearsal ran


def test_a_lock_that_stays_busy_for_the_whole_wait_skips_and_leaves_the_metrics_alone(tmp_path):
    prev = "tier0_runner_vault_handback_rehearsal_ok 1\n"
    r, prom = run(tmp_path, OK, 0, hold_lock_seconds=3.0, wait="1", prom_text=prev)
    assert r.returncode == 0 and "skipping this run" in r.stdout and prom == prev
    time.sleep(2.2)                                                                                         # let the lock-holder thread finish before the next test


def test_the_alert_expressions_only_use_metrics_the_wrapper_writes():
    rules = RULES.read_text()
    exported = set(re.findall(r"tier0_runner_vault_handback_rehearsal_\w+", WRAPPER.read_text())) | {"tier0_runner_vault_handback_rehearsal_" + n for n in
                                                                                                    ("rows_verified", "rows_failed_verification", "merged_rows")}
    used = set(re.findall(r"tier0_runner_vault_handback_rehearsal_\w+", rules))
    assert used and used <= exported, used - exported                                                      # an alert on a metric nobody writes would never fire
