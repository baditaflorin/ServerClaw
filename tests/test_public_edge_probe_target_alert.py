"""PublicEdgeProbeTargetBroken and the blackbox modules the probe targets need (2026-10-18).

Two probes of the public-edge-critical job (ci.example.org through the 0mcp internal gateway = the standby public edge VM110, and badita.example.com through Google DNS-over-HTTPS) were blind from
2026-10-11 03:41Z: their modules had been added by hand to the live /etc/prometheus/blackbox.yml and the next deploy of config/blackbox/blackbox.yml overwrote them, while the hand-managed file_sd targets
kept naming them, so the exporter answered 400 "Unknown module", no probe_success existed, and PublicEndpointDown never had anything to fire on. Pinned: the source file defines every module the targets
use, and the alert that makes such a gap visible exists with its delay (and, when promtool is installed, passes its unit test).
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
RULES = REPO / "config" / "prometheus" / "rules" / "public-edge-critical.yml"
requires_promtool = pytest.mark.skipif(shutil.which("promtool") is None, reason="promtool is not installed")

# the modules the live file_sd targets (public-critical-targets.yml, hand-managed on the monitoring VM) name
TARGET_MODULES = {"http_2xx_follow_redirects", "http_2xx_ci0mcp_internal", "http_2xx_dns_doh"}


def test_the_blackbox_source_file_defines_every_module_the_probe_targets_name() -> None:
    modules = yaml.safe_load((REPO / "config" / "blackbox" / "blackbox.yml").read_text(encoding="utf-8"))["modules"]
    assert TARGET_MODULES <= set(modules), sorted(TARGET_MODULES - set(modules))


def test_the_internal_gateway_module_probes_the_ci_name_through_the_edge_and_the_doh_module_needs_a_real_answer() -> None:
    modules = yaml.safe_load((REPO / "config" / "blackbox" / "blackbox.yml").read_text(encoding="utf-8"))["modules"]
    ci = modules["http_2xx_ci0mcp_internal"]["http"]
    assert ci["headers"]["Host"] == "ci.example.org" and ci["tls_config"]["server_name"] == "ci.example.org"        # the target is the edge's IP: name and SNI must be the CI host
    doh = modules["http_2xx_dns_doh"]["http"]
    assert doh["valid_status_codes"] == [200] and len(doh["fail_if_body_not_matches_regexp"]) == 2             # Status 0 AND an A answer: a 200 with an empty answer must fail


def test_the_alert_for_a_probe_target_that_produces_no_probe_success_exists_with_its_delay() -> None:
    rules = {r["alert"]: r for g in yaml.safe_load(RULES.read_text(encoding="utf-8"))["groups"] for r in g["rules"] if "alert" in r}
    r = rules["PublicEdgeProbeTargetBroken"]
    assert r["expr"] == 'up{job="public-edge-critical"} == 0' and r["for"] == "30m" and r["labels"]["severity"] == "warning"
    assert "blackbox.yml" in r["annotations"]["description"] and "Unknown module" in r["annotations"]["description"]


@requires_promtool
def test_the_rules_pass_promtool_check_and_the_unit_test() -> None:
    for args in (["check", "rules", str(RULES)], ["test", "rules", str(REPO / "tests" / "promtool" / "public_edge_probe_target_rules_test.yml")]):
        r = subprocess.run(["promtool", *args], cwd=REPO, capture_output=True, text=True, check=False)
        assert r.returncode == 0, r.stdout + r.stderr
