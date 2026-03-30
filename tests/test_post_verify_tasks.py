from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
TOP_LEVEL_POST_VERIFY_TASKS = REPO_ROOT / "playbooks" / "tasks" / "post-verify.yml"
COLLECTION_POST_VERIFY_TASKS = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "playbooks"
    / "tasks"
    / "post-verify.yml"
)
TOP_LEVEL_DOCKER_PUBLICATION_ASSERT_TASKS = REPO_ROOT / "playbooks" / "tasks" / "docker-publication-assert.yml"
COLLECTION_DOCKER_PUBLICATION_ASSERT_TASKS = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "playbooks"
    / "tasks"
    / "docker-publication-assert.yml"
)


def load_tasks(path: Path) -> list[dict]:
    return yaml.safe_load(path.read_text())


def test_post_verify_task_copies_stay_in_sync() -> None:
    assert load_tasks(TOP_LEVEL_POST_VERIFY_TASKS) == load_tasks(COLLECTION_POST_VERIFY_TASKS)


def test_docker_publication_assert_task_copies_stay_in_sync() -> None:
    assert load_tasks(TOP_LEVEL_DOCKER_PUBLICATION_ASSERT_TASKS) == load_tasks(COLLECTION_DOCKER_PUBLICATION_ASSERT_TASKS)


def test_post_verify_probes_run_on_service_owner_only() -> None:
    tasks = load_tasks(COLLECTION_POST_VERIFY_TASKS)
    startup_task = next(task for task in tasks if task["name"] == "Run startup verification")
    liveness_task = next(task for task in tasks if task["name"] == "Run liveness verification")
    readiness_task = next(task for task in tasks if task["name"] == "Run readiness verification")

    assert startup_task["when"] == [
        "inventory_hostname == playbook_execution_service_probe.owning_vm",
        "playbook_execution_service_probe.startup is defined",
    ]
    assert liveness_task["when"] == "inventory_hostname == playbook_execution_service_probe.owning_vm"
    assert readiness_task["when"] == "inventory_hostname == playbook_execution_service_probe.owning_vm"


def test_post_verify_repairs_docker_publication_before_readiness() -> None:
    tasks = load_tasks(COLLECTION_POST_VERIFY_TASKS)
    task_names = [task["name"] for task in tasks]
    repair_task = next(task for task in tasks if task["name"] == "Repair Docker publication before readiness verification")

    assert task_names.index("Repair Docker publication before readiness verification") < task_names.index(
        "Run readiness verification"
    )
    assert repair_task["vars"]["playbook_execution_docker_publication_contract"] == (
        "{{ playbook_execution_service_probe.readiness.docker_publication }}"
    )
    assert repair_task["when"] == [
        "inventory_hostname == playbook_execution_service_probe.owning_vm",
        "playbook_execution_service_probe.readiness is defined",
        "playbook_execution_service_probe.readiness.docker_publication is defined",
    ]


def test_docker_publication_assert_retries_empty_helper_output() -> None:
    tasks = load_tasks(COLLECTION_DOCKER_PUBLICATION_ASSERT_TASKS)
    helper_path_task = next(
        task for task in tasks if task["name"] == "Create a transient Docker publication assurance helper path"
    )
    stage_task = next(
        task for task in tasks if task["name"] == "Stage the repo-managed Docker publication assurance helper for verification"
    )
    select_command_task = next(
        task for task in tasks if task["name"] == "Select the Docker publication assurance helper command"
    )
    run_task = next(
        task for task in tasks if task["name"] == "Run Docker publication assurance before final readiness verification"
    )
    record_task = next(task for task in tasks if task["name"] == "Record the Docker publication assurance result")
    cleanup_task = next(task for task in tasks if task["name"] == "Remove the transient Docker publication assurance helper")

    assert helper_path_task["when"] == "playbook_execution_docker_publication_command is not defined"
    assert helper_path_task["changed_when"] is False
    assert stage_task["ansible.builtin.copy"]["content"] == (
        "{{ lookup('ansible.builtin.file', playbook_dir ~ '/../scripts/docker_publication_assurance.py') }}"
    )
    assert stage_task["ansible.builtin.copy"]["dest"] == "{{ playbook_execution_docker_publication_helper_tempfile.path }}"
    assert stage_task["when"] == "playbook_execution_docker_publication_command is not defined"
    assert stage_task["changed_when"] is False
    effective_command = select_command_task["ansible.builtin.set_fact"][
        "playbook_execution_docker_publication_effective_command"
    ]
    assert "playbook_execution_docker_publication_command" in effective_command
    assert "playbook_execution_docker_publication_helper_tempfile.path" in effective_command
    assert select_command_task["changed_when"] is False
    assert run_task["ansible.builtin.command"]["argv"][0] == "{{ playbook_execution_docker_publication_effective_command }}"
    assert run_task["retries"] == 6
    assert run_task["delay"] == 2
    assert "default('', true)" in run_task["until"]
    assert "default('{}', true)" in run_task["changed_when"]
    assert "default('{}', true)" in record_task["ansible.builtin.set_fact"]["playbook_execution_docker_publication_result"]
    assert cleanup_task["ansible.builtin.file"]["path"] == "{{ playbook_execution_docker_publication_helper_tempfile.path }}"
    assert cleanup_task["when"] == "playbook_execution_docker_publication_command is not defined"
    assert cleanup_task["changed_when"] is False
