"""Exercise early-warning, critical and missing-telemetry rules with Prometheus."""
from pathlib import Path
import shutil
import subprocess

import pytest

REPO = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(shutil.which("promtool") is None, reason="promtool is not installed")
def test_vault_standby_scratch_alerts() -> None:
    rules = REPO / "config/prometheus/rules/tier0-standby.yml"
    cases = REPO / "tests/promtool/vault_standby_scratch_rules_test.yml"
    for args in (["check", "rules", str(rules)], ["test", "rules", str(cases)]):
        result = subprocess.run(["promtool", *args], cwd=REPO, capture_output=True, text=True, check=False)
        assert result.returncode == 0, result.stdout + result.stderr
