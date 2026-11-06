"""tier0-rehearsal-metrics: the slice stage of the daily rehearsal as textfile metrics (a directory that cannot start on the standby must not be visible only in a log)."""
import importlib.machinery
import importlib.util
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / "config" / "0infer" / "tier0-runner" / "bin"
SCRIPT = BIN / "tier0-rehearsal-metrics"
_loader = importlib.machinery.SourceFileLoader("tier0_rehearsal_metrics", str(SCRIPT))
_spec = importlib.util.spec_from_loader("tier0_rehearsal_metrics", _loader)
mod = importlib.util.module_from_spec(_spec)
_loader.exec_module(mod)

GOOD = """== 3) restore on 0mcp_staging_runtime at the real paths, point digest-pinned images at their local tags, validate
   76 directories validated (compose parses, images local, external networks created), 0 invalid/not restored, 0 with missing images
   ports already in use on this VM before the slice starts: none
   memory available: 6433 MiB (the slice needs about 5.6 GiB with the CI agent stopped)
"""
BAD = """   INVALID compose in /opt/services/go-pentest-nuclei: env file /etc/fleet/internal_token.env not found
   image missing for /opt/services/x: ghcr.io/baditaflorin/x:1
   73 directories validated (compose parses, images local, external networks created), 3 invalid/not restored, 1 with missing images
   ports already in use on this VM before the slice starts: 18301 18302
   memory available: 3000 MiB (the slice needs about 5.6 GiB with the CI agent stopped)
"""


def parse(text):
    out = mod.metrics(text)
    return None if out is None else dict(l.split(" ", 1) for l in out.splitlines() if l and not l.startswith("#"))


def test_a_clean_slice_stage_exports_zero_invalid_and_the_headroom():
    m = parse(GOOD)
    assert m == {"tier0_runner_slice_directories_validated": "76", "tier0_runner_slice_directories_invalid": "0", "tier0_runner_slice_images_missing_directories": "0",
                 "tier0_runner_slice_ports_busy": "0", "tier0_runner_slice_memory_available_mib": "6433"}


def test_invalid_directories_missing_images_and_busy_ports_are_counted():
    m = parse(BAD)
    assert m["tier0_runner_slice_directories_validated"] == "73" and m["tier0_runner_slice_directories_invalid"] == "3"
    assert m["tier0_runner_slice_images_missing_directories"] == "1" and m["tier0_runner_slice_ports_busy"] == "2" and m["tier0_runner_slice_memory_available_mib"] == "3000"


def test_a_log_without_the_summary_exports_nothing_so_the_last_metrics_survive(tmp_path):
    log = tmp_path / "f.log"
    log.write_text("== 1) preflight (rehearse)\nrefused: docker not usable\n")
    r = subprocess.run([sys.executable, str(SCRIPT), str(log)], capture_output=True, text=True)
    assert r.returncode == 3 and r.stdout == ""
    assert subprocess.run([sys.executable, str(SCRIPT), str(tmp_path / "missing.log")], capture_output=True, text=True).returncode == 3
    log.write_text(GOOD)
    r = subprocess.run([sys.executable, str(SCRIPT), str(log)], capture_output=True, text=True)
    assert r.returncode == 0 and "tier0_runner_slice_directories_invalid 0" in r.stdout


def test_the_summary_line_is_the_one_the_slice_script_really_prints():
    # the regex is only worth anything while tier0-slice-promote.sh prints this exact line: fleet-state holds the script, so the sentence is pinned here and in the alert text
    assert "directories validated (compose parses, images local, external networks created)" in GOOD
    assert mod.SUMMARY.search(GOOD) and mod.SUMMARY.search(BAD)


def test_the_daily_wrapper_calls_it_after_the_run_and_the_installer_ships_it():
    wrapper = (BIN / "tier0-rehearsal-daily").read_text()
    assert "/usr/local/sbin/tier0-rehearsal-metrics" in wrapper and "tier0_runner_slice.prom" in wrapper
    assert wrapper.index("tier0-failover.sh --rehearse") < wrapper.index("tier0-rehearsal-metrics")               # after the run, from its own log
    assert "tier0-rehearsal-metrics" in (ROOT / "config" / "0infer" / "tier0-runner" / "install.sh").read_text()


def test_the_alert_is_on_metrics_the_script_exports():
    doc = yaml.safe_load((ROOT / "config" / "prometheus" / "rules" / "tier0-standby.yml").read_text())
    rules = {r["alert"]: r for g in doc["groups"] for r in g["rules"] if "alert" in r}
    r = rules["Tier0SliceDirectoriesInvalid"]
    exported = set(parse(BAD))
    import re
    used = set(re.findall(r"tier0_runner_slice_\w+", r["expr"]))
    assert used and used <= exported, used - exported
    assert r["labels"]["severity"] == "warning" and r["for"] == "2h"


PROBE_LINE = "PROBE_ALL total=459 probed=374 answering=191 reached=91 failing=92 slice_dependent=85 seconds=17\n"


def test_the_all_names_probe_summary_is_exported_next_to_the_slice_metrics():
    m = parse(GOOD + PROBE_LINE)
    assert m["tier0_runner_standby_names_total"] == "459" and m["tier0_runner_standby_names_probed"] == "374"
    assert m["tier0_runner_standby_names_answering"] == "191" and m["tier0_runner_standby_names_reached"] == "91"
    assert m["tier0_runner_standby_names_failing"] == "92" and m["tier0_runner_standby_names_slice_dependent"] == "85" and m["tier0_runner_standby_probe_seconds"] == "17"
    assert m["tier0_runner_slice_directories_validated"] == "76"                                                  # both stages in one log: both families


def test_either_stage_alone_is_enough_and_neither_exports_nothing():
    only_probe = parse(PROBE_LINE)
    assert only_probe["tier0_runner_standby_names_failing"] == "92" and "tier0_runner_slice_directories_invalid" not in only_probe
    only_slice = parse(GOOD)
    assert "tier0_runner_standby_names_failing" not in only_slice and only_slice["tier0_runner_slice_directories_invalid"] == "0"
    assert parse("nothing useful here\n") is None


KEY_GOOD = """   KEYSTORE_MESH from=0mcp_docker_build url=http://10.10.10.91:18021 version=0.10.2 valid=200 wrong_scope=401 bogus=401 key=yes ok=1
   KEYSTORE_VAULT from=0mcp_docker_build url=http://10.10.10.30:18142 health=200 read=200 value=match bogus=401 nokey=401 key=yes ok=1
   KEYSTORE_MESH from=0mcp_nginx url=http://100.64.0.24:18021 version=0.10.2 valid=200 wrong_scope=401 bogus=401 key=yes ok=1
   KEYSTORE_EDGE_VHOST name=fleet-secrets-rehearsal.0exec.com health=200 nokey=401 bogus=401 ok=1
   KEYSTORE_VERIFY mode=mesh result=ok
   KEYSTORE_EDGE_GATEWAY name=a11y-quick.0crawl.com nokey=401 bogus=401 ok=1
   KEYSTORE_VERIFY mode=mesh stage=gateway result=ok
"""
KEY_BAD = KEY_GOOD.replace("version=0.10.2 valid=200 wrong_scope=401 bogus=401 key=yes ok=1\n   KEYSTORE_EDGE_VHOST", "version=none valid=000 wrong_scope=000 bogus=000 key=yes ok=0\n   KEYSTORE_EDGE_VHOST", 1).replace(
    "KEYSTORE_VERIFY mode=mesh result=ok", "KEYSTORE_VERIFY mode=mesh result=FAILED")


def test_the_keystore_checks_of_a_passing_rehearsal_export_their_count_zero_failures_and_both_verdicts():
    out = mod.metrics(KEY_GOOD)
    m = dict(l.split(" ", 1) for l in out.splitlines() if l and not l.startswith("#"))
    assert m["tier0_runner_keystore_probe_lines"] == "5" and m["tier0_runner_keystore_probe_failed_lines"] == "0"
    assert m['tier0_runner_keystore_verify_ok{stage="vault"}'] == "1" and m['tier0_runner_keystore_verify_ok{stage="gateway"}'] == "1"      # the vault stage prints no stage=


def test_a_failing_keystore_check_is_counted_and_the_stage_verdict_is_zero():
    m = dict(l.split(" ", 1) for l in mod.metrics(KEY_BAD).splitlines() if l and not l.startswith("#"))
    assert m["tier0_runner_keystore_probe_failed_lines"] == "1" and m['tier0_runner_keystore_verify_ok{stage="vault"}'] == "0" and m['tier0_runner_keystore_verify_ok{stage="gateway"}'] == "1"


def test_a_log_without_keystore_lines_exports_nothing_about_the_keystore_and_a_probe_error_counts_as_failed():
    assert "keystore" not in (mod.metrics(GOOD) or "")
    m = dict(l.split(" ", 1) for l in mod.metrics("KEYSTORE_PROBE from=0mcp_nginx url=http://10.10.10.91:18021 error=host-unreachable ok=0\n").splitlines() if l and not l.startswith("#"))
    assert m["tier0_runner_keystore_probe_lines"] == "1" and m["tier0_runner_keystore_probe_failed_lines"] == "1"

