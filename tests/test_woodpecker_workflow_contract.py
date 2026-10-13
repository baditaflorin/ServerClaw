from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_primary_validation_step_filters_supported_events() -> None:
    workflow = yaml.safe_load((REPO_ROOT / ".woodpecker.yml").read_text())

    assert "when" not in workflow
    assert workflow["steps"]["validate-woodpecker-contract"]["when"] == [{"event": ["manual", "push", "pull_request"]}]
