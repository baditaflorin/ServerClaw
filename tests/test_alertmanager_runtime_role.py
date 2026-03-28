from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
VERIFY_PATH = REPO_ROOT / "roles" / "alertmanager_runtime" / "tasks" / "verify.yml"


def test_alertmanager_runtime_verifies_loki_canary_rules_after_rule_copy() -> None:
    verify_tasks = yaml.safe_load(VERIFY_PATH.read_text())
    verify_task = next(
        task for task in verify_tasks if task.get("name") == "Verify Prometheus Loki Canary rules are loaded"
    )

    assert verify_task["ansible.builtin.uri"]["url"] == "http://127.0.0.1:9090/api/v1/rules"
    assert "lv3-log-canary" in verify_task["failed_when"]
    assert "LokiCanaryTargetDown" in verify_task["failed_when"]
