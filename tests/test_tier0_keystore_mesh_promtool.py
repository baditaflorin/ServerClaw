"""The keystore-mesh alerts of the failover chain (config/prometheus/rules/tier0-standby.yml, group tier0-runner, so BOTH Prometheus instances carry them).

2026-10-18: the chain verifies keys against live keystore mesh nodes. The hourly edge-compat check exports how many nodes answer from the edge and whether the throwaway test key was used; the daily
rehearsal's metrics script exports how many keystore/vault checks failed. Pinned: the four alerts exist with the severities and delays the unit tests assume, every metric they read is one the
runner wrapper or the metrics script really writes, and (when promtool is installed) the rules pass `promtool check` and the unit tests in tests/promtool/tier0_keystore_mesh_rules_test.yml.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
RULES = REPO / "config" / "prometheus" / "rules" / "tier0-standby.yml"
BIN = REPO / "config" / "0infer" / "tier0-runner" / "bin"
requires_promtool = pytest.mark.skipif(shutil.which("promtool") is None, reason="promtool is not installed")


def _alerts():
    doc = yaml.safe_load(RULES.read_text(encoding="utf-8"))
    return {r["alert"]: (g["name"], r) for g in doc["groups"] for r in g["rules"] if "alert" in r}


@requires_promtool
def test_the_rules_pass_promtool_check_and_the_unit_tests() -> None:
    for args in (["check", "rules", str(RULES)], ["test", "rules", str(REPO / "tests" / "promtool" / "tier0_keystore_mesh_rules_test.yml")]):
        r = subprocess.run(["promtool", *args], cwd=REPO, capture_output=True, text=True, check=False)
        assert r.returncode == 0, r.stdout + r.stderr


def test_the_four_alerts_sit_in_the_runner_group_with_the_severities_and_delays_the_unit_tests_assume() -> None:
    a = _alerts()
    want = {"Tier0KeystoreMeshNodeNotAnswering": ("warning", "2h"), "Tier0KeystoreMeshAllNodesDown": ("critical", "1h"),
            "Tier0KeystoreMeshKeyUnchecked": ("warning", "6h"), "Tier0KeystoreVerifyFailing": ("warning", "1h")}
    for name, (sev, delay) in want.items():
        group, rule = a[name]
        assert group == "tier0-runner" and rule["labels"]["severity"] == sev and rule["for"] == delay, name
        assert rule["annotations"]["summary"] and rule["annotations"]["description"], name


def test_every_metric_the_alerts_read_is_written_by_the_runner_wrapper_or_the_metrics_script() -> None:
    wrapper = (BIN / "tier0-edge-compat").read_text()
    metrics = (BIN / "tier0-rehearsal-metrics").read_text()
    a = _alerts()
    for name in ("Tier0KeystoreMeshNodeNotAnswering", "Tier0KeystoreMeshAllNodesDown", "Tier0KeystoreMeshKeyUnchecked"):
        for metric in re.findall(r"tier0_runner_edge_compat_(\w+)", a[name][1]["expr"]):
            assert f'("{metric}", "{metric}")' in wrapper, (name, metric)                      # the wrapper composes tier0_runner_edge_compat_<name> from these pairs
    assert re.findall(r"tier0_runner_keystore_\w+", a["Tier0KeystoreVerifyFailing"][1]["expr"]) == ["tier0_runner_keystore_probe_failed_lines"]
    assert "tier0_runner_keystore_probe_failed_lines" in metrics
