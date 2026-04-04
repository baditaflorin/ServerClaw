from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
HELPER_TASKS = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "common"
    / "tasks"
    / "docker_bridge_chains.yml"
)


def load_tasks() -> list[dict]:
    return yaml.safe_load(HELPER_TASKS.read_text())


def test_docker_bridge_chain_helper_asserts_on_retry_task_success_state() -> None:
    tasks = load_tasks()
    task_names = {task["name"] for task in tasks}
    expect_forward = next(task for task in tasks if task["name"] == "Decide whether Docker forward-chain enforcement is required")
    needs_recovery = next(task for task in tasks if task["name"] == "Decide whether Docker bridge-chain recovery checks are required")
    reset_connection = next(task for task in tasks if task["name"] == "Reset SSH connection before Docker bridge-chain recovery checks")
    wait_for_ssh = next(task for task in tasks if task["name"] == "Wait for SSH before Docker bridge-chain recovery checks")
    nat_assert = next(task for task in tasks if task["name"] == "Assert Docker nat chain is present after health evaluation")
    forward_assert = next(
        task for task in tasks if task["name"] == "Assert Docker forward chain is present after health evaluation"
    )

    assert "common_docker_bridge_chains_expect_forward_chain" in expect_forward["ansible.builtin.set_fact"]
    assert "common_docker_bridge_chains_needs_recovery_check" in needs_recovery["ansible.builtin.set_fact"]
    assert "Restart Docker when required bridge chains are missing" not in task_names
    assert "Restart Docker when required bridge chains are still missing after the retry loop" not in task_names
    assert "Verify Docker nat chain after retry loop" not in task_names
    assert "Verify Docker forward chain after retry loop" not in task_names
    assert "Capture final Docker nat chain state after retry loop" not in task_names
    assert "Capture final Docker forward chain state after retry loop" not in task_names
    assert reset_connection["when"] == [
        "common_docker_bridge_chains_active_state.rc == 0",
        "common_docker_bridge_chains_needs_recovery_check | default(false)",
    ]
    assert reset_connection["ansible.builtin.include_tasks"] == "docker_bridge_chains_reset_connection.yml"
    assert wait_for_ssh["ansible.builtin.wait_for_connection"]["connect_timeout"] == 5
    assert wait_for_ssh["ansible.builtin.wait_for_connection"]["connect_timeout"] == 5
    assert wait_for_ssh["when"] == [
        "common_docker_bridge_chains_active_state.rc == 0",
        "common_docker_bridge_chains_needs_recovery_check | default(false)",
    ]
    assert "common_docker_bridge_chains_nat_recheck is defined" in nat_assert["ansible.builtin.assert"]["that"][0]
    assert "common_docker_bridge_chains_nat_check" in nat_assert["ansible.builtin.assert"]["that"][0]
    assert nat_assert["ansible.builtin.assert"]["that"][0].strip().endswith("== 0")
    assert "common_docker_bridge_chains_forward_recheck is defined" in forward_assert["ansible.builtin.assert"]["that"][0]
    assert "common_docker_bridge_chains_forward_check" in forward_assert["ansible.builtin.assert"]["that"][0]
    assert forward_assert["ansible.builtin.assert"]["that"][0].strip().endswith("== 0")
    assert forward_assert["when"] == [
        "common_docker_bridge_chains_active_state.rc == 0",
        "common_docker_bridge_chains_expect_forward_chain | default(false)",
    ]
