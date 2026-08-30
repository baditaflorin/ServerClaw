from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_root_workflow_filter_allows_pull_requests() -> None:
    workflow = yaml.safe_load((REPO_ROOT / ".woodpecker.yml").read_text())

    assert workflow["when"] == {
        "event": ["manual", "push", "pull_request"],
    }
