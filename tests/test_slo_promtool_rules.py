"""Run the promtool unit tests for the generated SLO and HTTPS/TLS rules (skipped when promtool is not installed)."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import generate_https_tls_assurance  # noqa: E402

PROMTOOL_DIR = REPO_ROOT / "tests" / "promtool"
RULES_DIR = REPO_ROOT / "config" / "prometheus" / "rules"

requires_promtool = pytest.mark.skipif(shutil.which("promtool") is None, reason="promtool is not installed")


def run_promtool(*args: str, cwd: Path) -> None:
    result = subprocess.run(["promtool", *args], cwd=cwd, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr


@requires_promtool
def test_generated_slo_rules_pass_promtool_check_and_unit_tests() -> None:
    run_promtool("check", "rules", str(RULES_DIR / "slo_rules.yml"), str(RULES_DIR / "slo_alerts.yml"), cwd=REPO_ROOT)
    run_promtool("test", "rules", str(PROMTOOL_DIR / "slo_rules_test.yml"), cwd=REPO_ROOT)


@requires_promtool
def test_generated_tls_rules_pass_promtool_check_and_unit_tests(tmp_path: Path) -> None:
    rules = tmp_path / "rules"
    rules.mkdir()
    targets = generate_https_tls_assurance.discover_https_tls_targets()
    (rules / "https_tls_alerts.yml").write_text(
        generate_https_tls_assurance.build_alerts_text_with_markers(targets), encoding="utf-8"
    )
    (tmp_path / "https_tls_rules_test.yml").write_text(
        (PROMTOOL_DIR / "https_tls_rules_test.yml").read_text(encoding="utf-8"), encoding="utf-8"
    )
    run_promtool("check", "rules", str(rules / "https_tls_alerts.yml"), cwd=tmp_path)
    run_promtool("test", "rules", "https_tls_rules_test.yml", cwd=tmp_path)


def test_promtool_test_files_are_valid_yaml_and_reference_generated_rules() -> None:
    slo_tests = yaml.safe_load((PROMTOOL_DIR / "slo_rules_test.yml").read_text(encoding="utf-8"))
    assert [Path(item).name for item in slo_tests["rule_files"]] == ["slo_rules.yml", "slo_alerts.yml"]
    names = {case["name"] for case in slo_tests["tests"]}
    assert len(names) == 4
    for rule_file in slo_tests["rule_files"]:
        assert (PROMTOOL_DIR / rule_file).resolve().is_file()
    tls_tests = yaml.safe_load((PROMTOOL_DIR / "https_tls_rules_test.yml").read_text(encoding="utf-8"))
    assert tls_tests["rule_files"] == ["rules/https_tls_alerts.yml"]
