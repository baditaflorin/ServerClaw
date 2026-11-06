"""bin/tier0-edge-compat: the runner wrapper that runs the hourly standby edge check and exports it as metrics.

The stage (fleet-state) is replaced by a shim `tier0-run` that prints a RESULT_JSON line and exits with a scripted code. What matters here: the ok / could-not-run distinction the alerts depend on
(a config the edge REJECTS must never look like "could not run", or the critical alert would not fire), the previous success timestamp surviving a failed run, and the chain lock being respected.
"""
from __future__ import annotations

import fcntl
import json
import os
import shutil
import subprocess
from pathlib import Path

WRAPPER = Path(__file__).resolve().parents[1] / "config" / "0infer" / "tier0-runner" / "bin" / "tier0-edge-compat"


def run(tmp: Path, result: dict | None, rc: int, hold_lock=False, prom_text=None):
    shim = tmp / "tier0-run"
    line = f"RESULT_JSON {json.dumps(result)}\n" if result is not None else ""
    shim.write_text(f"#!/bin/bash\necho 'chain output'\nprintf '%s' '{line}'\nexit {rc}\n")
    shim.chmod(0o755)
    prom = tmp / "x.prom"
    if prom_text:
        prom.write_text(prom_text)
    lock = tmp / "chain.lock"
    fh = open(lock, "w")
    if hold_lock:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    env = dict(os.environ, TIER0_CHAIN_LOCK=str(lock), TIER0_EDGE_COMPAT_PROM=str(prom), TIER0_RUN=str(shim))
    if shutil.which("flock") is None:                                                               # macOS has no flock(1): same semantics on the fd the wrapper opened
        fl = tmp / "bin" / "flock"
        fl.parent.mkdir(exist_ok=True)
        fl.write_text("#!/usr/bin/env python3\nimport fcntl, sys\ntry:\n    fcntl.flock(int([a for a in sys.argv[1:] if a != '-n'][0]), fcntl.LOCK_EX | fcntl.LOCK_NB)\nexcept OSError:\n    sys.exit(1)\n")
        fl.chmod(0o755)
        env["PATH"] = f"{fl.parent}:{env['PATH']}"
    r = subprocess.run(["bash", str(WRAPPER)], capture_output=True, text=True, env=env, timeout=60)
    fh.close()
    return r, (prom.read_text() if prom.exists() else None)


def metric(text, name):
    for l in text.splitlines():
        if l.startswith(name + " ") or l.startswith(name + "{"):
            return l.split()[-1]
    return None


OK = {"status": "ok", "ok": True, "vhosts_selected": 355, "vhosts_skipped": 160, "snapshot_age_seconds": 900, "nginx_version": "1.26.3"}


def test_ok_run_exports_success_counts_and_version(tmp_path):
    r, prom = run(tmp_path, OK, 0)
    assert r.returncode == 0 and metric(prom, "tier0_runner_edge_compat_ok") == "1" and metric(prom, "tier0_runner_edge_compat_could_not_run") == "0"
    assert metric(prom, "tier0_runner_edge_compat_vhosts_selected") == "355" and metric(prom, "tier0_runner_edge_compat_vhosts_skipped") == "160"
    assert 'tier0_runner_edge_compat_info{nginx_version="1.26.3"} 1' in prom and metric(prom, "tier0_runner_edge_compat_last_success_timestamp_seconds") is not None


def test_a_config_the_edge_rejects_is_not_could_not_run_so_the_critical_alert_can_fire(tmp_path):
    for status in ("nginx-t-failed", "build-failed"):
        t = tmp_path / status; t.mkdir()
        r, prom = run(t, {"status": status, "ok": False, "snapshot_age_seconds": 900, "vhosts_selected": 0, "vhosts_skipped": 0}, 5)
        assert r.returncode == 5 and metric(prom, "tier0_runner_edge_compat_ok") == "0" and metric(prom, "tier0_runner_edge_compat_could_not_run") == "0", status


def test_could_not_run_is_its_own_state(tmp_path):
    for status, rc in (("no-snapshot", 6), ("no-edge", 6), ("edge-unsupported", 6)):
        t = tmp_path / status; t.mkdir()
        r, prom = run(t, {"status": status, "ok": False}, rc)
        assert metric(prom, "tier0_runner_edge_compat_ok") == "0" and metric(prom, "tier0_runner_edge_compat_could_not_run") == "1", status
    t = tmp_path / "noresult"; t.mkdir()
    r, prom = run(t, None, 1)                                                                       # the stage died without a result line
    assert metric(prom, "tier0_runner_edge_compat_could_not_run") == "1" and metric(prom, "tier0_runner_edge_compat_ok") == "0"


def test_the_previous_success_survives_a_failed_run(tmp_path):
    prev = "tier0_runner_edge_compat_last_success_timestamp_seconds 1790000000\n"
    r, prom = run(tmp_path, {"status": "nginx-t-failed", "ok": False}, 5, prom_text=prev)
    assert metric(prom, "tier0_runner_edge_compat_last_success_timestamp_seconds") == "1790000000"


def test_a_busy_chain_lock_skips_the_run_and_keeps_the_last_metrics(tmp_path):
    prev = "tier0_runner_edge_compat_ok 1\n"
    r, prom = run(tmp_path, OK, 0, hold_lock=True, prom_text=prev)
    assert r.returncode == 0 and "skipping this run" in r.stdout and prom == prev                      # a rehearsal in progress: nothing overwritten


def test_the_alert_expressions_match_the_exported_metric_names():
    rules = (Path(__file__).resolve().parents[1] / "config" / "prometheus" / "rules" / "tier0-standby.yml").read_text()
    exported = set(__import__("re").findall(r"tier0_runner_edge_compat_\w+", WRAPPER.read_text()))
    used = set(__import__("re").findall(r"tier0_runner_edge_compat_\w+", rules))
    assert used and used <= exported | {"tier0_runner_edge_compat_vhosts_selected", "tier0_runner_edge_compat_vhosts_skipped", "tier0_runner_edge_compat_backends_closed",
                                              "tier0_runner_edge_compat_keystore_mesh_nodes", "tier0_runner_edge_compat_keystore_mesh_nodes_ok", "tier0_runner_edge_compat_keystore_mesh_key_checked"}, used - exported     # an alert on a metric the wrapper never writes would never fire


def test_the_dark_names_alert_is_on_a_metric_the_wrapper_exports_and_sits_above_what_the_slice_refresh_leaves():
    import yaml
    doc = yaml.safe_load((Path(__file__).resolve().parents[1] / "config" / "prometheus" / "rules" / "tier0-standby.yml").read_text())
    rules = {r["alert"]: r for g in doc["groups"] for r in g["rules"] if "alert" in r}
    r = rules["Tier0StandbyDarkNames"]
    assert r["expr"] == "max(tier0_runner_edge_compat_vhosts_skipped) > 80" and r["labels"]["severity"] == "warning"
    assert '("vhosts_skipped", "vhosts_skipped")' in WRAPPER.read_text()                                 # the wrapper exports it (name composed from the prefix); 56 names stay dark after the refresh by design: the threshold sits above that, below the 121 it was


def test_the_wrapper_exports_the_backend_reachability_counts_and_the_alerts_use_them():
    import yaml
    assert '("backends_total", "backends_total"), ("backends_closed", "backends_closed")' in WRAPPER.read_text()
    doc = yaml.safe_load((Path(__file__).resolve().parents[1] / "config" / "prometheus" / "rules" / "tier0-standby.yml").read_text())
    rules = {r["alert"]: r for g in doc["groups"] for r in g["rules"] if "alert" in r}
    assert rules["Tier0EdgeBackendPortsClosed"]["expr"] == "max(tier0_runner_edge_compat_backends_closed) > 0" and rules["Tier0EdgeBackendPortsClosed"]["labels"]["severity"] == "warning"
    assert rules["Tier0StandbyNamesNotAnswering"]["expr"] == "max(tier0_runner_standby_names_failing) > 5"
    rehearsal = (Path(__file__).resolve().parents[1] / "config" / "0infer" / "tier0-runner" / "bin" / "tier0-rehearsal-metrics").read_text()
    assert "tier0_runner_standby_names_failing" in rehearsal                                                      # the probe metric the second alert reads is written by the metrics script


def streaks(prom):
    import re
    return {(m.group(1), m.group(2)): int(m.group(3)) for m in re.finditer(r'^tier0_runner_edge_backend_closed_streak\{backend_ip="([^"]+)",backend_port="(\d+)"\} (\d+)', prom or "", re.M)}


def test_a_closed_pair_counts_the_hourly_runs_it_has_been_closed_in_a_row_and_disappears_when_it_opens(tmp_path):
    base = dict(OK, backends_total=292, backends_closed=2)
    prom = None
    for expected in (1, 2, 3):
        t = tmp_path / f"run{expected}"; t.mkdir()
        r, prom = run(t, dict(base, backends_closed_pairs=["100.64.0.24:8999", "100.102.176.103:8331"]), 0, prom_text=prom)
        assert streaks(prom) == {("100.64.0.24", "8999"): expected, ("100.102.176.103", "8331"): expected}, prom
    t = tmp_path / "opens"; t.mkdir()
    r, prom = run(t, dict(base, backends_closed=1, backends_closed_pairs=["100.64.0.24:8999"]), 0, prom_text=prom)
    assert streaks(prom) == {("100.64.0.24", "8999"): 4}                                               # the other one opened: its series is gone, the first keeps counting
    t = tmp_path / "all_open"; t.mkdir()
    r, prom = run(t, dict(base, backends_closed=0, backends_closed_pairs=[]), 0, prom_text=prom)
    assert streaks(prom) == {} and "tier0_runner_edge_backend_closed_streak" not in prom


def test_a_run_that_could_not_look_or_an_older_stage_without_the_list_keeps_what_was_known(tmp_path):
    known = 'tier0_runner_edge_backend_closed_streak{backend_ip="100.64.0.24",backend_port="8999"} 5\n'
    t = tmp_path / "failed"; t.mkdir()
    r, prom = run(t, {"status": "no-edge", "ok": False}, 6, prom_text=known)
    assert streaks(prom) == {("100.64.0.24", "8999"): 5}                                               # the edge was unreachable: nothing is learned, nothing is forgotten
    t = tmp_path / "old"; t.mkdir()
    r, prom = run(t, dict(OK), 0, prom_text=known)                                                        # an ok run from a stage that does not list the pairs yet
    assert streaks(prom) == {("100.64.0.24", "8999"): 5}


def test_a_malformed_pair_in_the_result_is_ignored_not_fatal(tmp_path):
    r, prom = run(tmp_path, dict(OK, backends_closed_pairs=["nonsense", "100.1.1.1:abc", "100.2.2.2:8100"]), 0)
    assert r.returncode == 0 and streaks(prom) == {("100.2.2.2", "8100"): 1}


def test_the_wrapper_exports_the_keystore_mesh_state_the_chain_depends_on(tmp_path):
    r, prom = run(tmp_path, dict(OK, keystore_mesh_nodes=2, keystore_mesh_nodes_ok=1, keystore_mesh_key_checked=1), 0)
    assert metric(prom, "tier0_runner_edge_compat_keystore_mesh_nodes") == "2" and metric(prom, "tier0_runner_edge_compat_keystore_mesh_nodes_ok") == "1"
    assert metric(prom, "tier0_runner_edge_compat_keystore_mesh_key_checked") == "1"
    t = tmp_path / "older"; t.mkdir()
    r, prom = run(t, OK, 0)                                                                                 # an older stage that does not report the mesh: nothing is invented
    assert metric(prom, "tier0_runner_edge_compat_keystore_mesh_nodes") is None and metric(prom, "tier0_runner_edge_compat_keystore_mesh_key_checked") is None
    t = tmp_path / "unchecked"; t.mkdir()
    r, prom = run(t, dict(OK, keystore_mesh_nodes=2, keystore_mesh_nodes_ok=2, keystore_mesh_key_checked=0), 0)
    assert metric(prom, "tier0_runner_edge_compat_keystore_mesh_key_checked") == "0"                          # the key file is missing: the alert Tier0KeystoreMeshKeyUnchecked reads this


def test_the_keystore_mesh_alerts_read_what_the_wrapper_and_the_metrics_script_write():
    import yaml
    doc = yaml.safe_load((Path(__file__).resolve().parents[1] / "config" / "prometheus" / "rules" / "tier0-standby.yml").read_text())
    rules = {r["alert"]: r for g in doc["groups"] for r in g["rules"] if "alert" in r}
    assert rules["Tier0KeystoreMeshNodeNotAnswering"]["expr"] == "max(tier0_runner_edge_compat_keystore_mesh_nodes) - max(tier0_runner_edge_compat_keystore_mesh_nodes_ok) > 0"
    assert rules["Tier0KeystoreMeshAllNodesDown"]["labels"]["severity"] == "critical"
    assert rules["Tier0KeystoreMeshKeyUnchecked"]["expr"] == "min(tier0_runner_edge_compat_keystore_mesh_key_checked) == 0"

