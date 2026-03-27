from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
POST_VERIFY_TASKS = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "playbooks"
    / "tasks"
    / "post-verify.yml"
)


def test_post_verify_probes_run_on_service_owner_only() -> None:
    tasks = yaml.safe_load(POST_VERIFY_TASKS.read_text())
    liveness_task = next(task for task in tasks if task["name"] == "Run liveness verification")
    readiness_task = next(task for task in tasks if task["name"] == "Run readiness verification")

    assert liveness_task["when"] == "inventory_hostname == playbook_execution_service_probe.owning_vm"
    assert readiness_task["when"] == "inventory_hostname == playbook_execution_service_probe.owning_vm"
