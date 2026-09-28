"""Keep the public CI entrypoint on the governed Woodpecker instance."""

from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_public_ci_uses_woodpecker_without_github_actions() -> None:
    workflow_dir = REPO_ROOT / ".github" / "workflows"
    assert not workflow_dir.exists() or not any(workflow_dir.iterdir())

    pipeline = yaml.safe_load((REPO_ROOT / ".woodpecker.yml").read_text(encoding="utf-8"))
    assert pipeline["labels"]["lv3"] == "true"
    assert "validate-woodpecker-contract" in pipeline["steps"]
