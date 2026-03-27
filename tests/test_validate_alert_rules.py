from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import validate_alert_rules


def test_validate_alert_rules_accepts_repo_rules():
    errors = validate_alert_rules.validate_rule_files(
        Path(__file__).resolve().parents[1] / "config" / "alertmanager" / "rules"
    )
    assert errors == []


def test_validate_alert_rules_rejects_missing_runbook(tmp_path: Path):
    rules_dir = tmp_path / "rules"
    rules_dir.mkdir()
    (rules_dir / "broken.yml").write_text(
        """
groups:
  - name: broken
    rules:
      - alert: BrokenAlert
        expr: up == 0
        labels:
          severity: critical
          service: grafana
        annotations:
          summary: Broken
""".strip()
        + "\n",
        encoding="utf-8",
    )

    errors = validate_alert_rules.validate_rule_files(rules_dir)
    assert len(errors) == 1
    assert "runbook_url" in errors[0]
