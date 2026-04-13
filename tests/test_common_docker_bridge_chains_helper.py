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
    initial_forward = next(task for task in tasks if task["name"] == "Check whether Docker forward chain exists")
    expect_forward = next(
        task for task in tasks if task["name"] == "Decide whether Docker forward-chain enforcement is required"
    )
    reset_connection = next(
        task for task in tasks if task["name"] == "Reset SSH connection before Docker bridge-chain recovery checks"
    )
    wait_for_ssh = next(
        task for task in tasks if task["name"] == "Wait for SSH before Docker bridge-chain recovery checks"
    )
    nat_verify = next(task for task in tasks if task["name"] == "Verify Docker nat chain after retry loop")
    forward_verify = next(task for task in tasks if task["name"] == "Verify Docker forward chain after retry loop")
    nat_final = next(task for task in tasks if task["name"] == "Capture final Docker nat chain state after retry loop")
    forward_final = next(
        task for task in tasks if task["name"] == "Capture final Docker forward chain state after retry loop"
    )
    nat_assert = next(
        task for task in tasks if task["name"] == "Assert Docker nat chain is present after health evaluation"
    )
    forward_assert = next(
        task for task in tasks if task["name"] == "Assert Docker forward chain is present after health evaluation"
    )

    assert "common_docker_bridge_chains_expect_forward_chain" in expect_forward["ansible.builtin.set_fact"]
    assert "Restart Docker when required bridge chains are missing" not in task_names
    assert "Restart Docker when required bridge chains are still missing after the retry loop" not in task_names
    assert "iptables -t filter -S DOCKER-FORWARD" in initial_forward["ansible.builtin.shell"]
    assert "iptables -t filter -S DOCKER >/dev/null 2>&1" in initial_forward["ansible.builtin.shell"]
    assert "iptables -t filter -S FORWARD" in initial_forward["ansible.builtin.shell"]
    assert reset_connection["ansible.builtin.include_tasks"] == "docker_bridge_chains_reset_connection.yml"
    assert wait_for_ssh["ansible.builtin.wait_for_connection"]["connect_timeout"] == 5
    assert wait_for_ssh["ansible.builtin.wait_for_connection"]["connect_timeout"] == 5
    assert nat_verify["register"] == "common_docker_bridge_chains_nat_verify"
    assert forward_verify["register"] == "common_docker_bridge_chains_forward_verify"
    assert nat_verify["retries"] == "{{ common_docker_bridge_chains_retries }}"
    assert nat_verify["delay"] == "{{ common_docker_bridge_chains_delay }}"
    assert nat_verify["until"] == "common_docker_bridge_chains_nat_verify.rc == 0"
    assert forward_verify["retries"] == "{{ common_docker_bridge_chains_retries }}"
    assert forward_verify["delay"] == "{{ common_docker_bridge_chains_delay }}"
    assert forward_verify["until"] == "common_docker_bridge_chains_forward_verify.rc == 0"
    assert nat_final["ansible.builtin.set_fact"]["common_docker_bridge_chains_nat_final"] == (
        "{{ common_docker_bridge_chains_nat_verify }}"
    )
    assert forward_final["ansible.builtin.set_fact"]["common_docker_bridge_chains_forward_final"] == (
        "{{ common_docker_bridge_chains_forward_verify }}"
    )
    assert forward_verify["when"] == [
        "common_docker_bridge_chains_active_state.rc == 0",
        "common_docker_bridge_chains_expect_forward_chain | default(false)",
    ]
    assert nat_assert["ansible.builtin.assert"]["that"] == ["common_docker_bridge_chains_nat_final.rc == 0"]
    assert forward_assert["ansible.builtin.assert"]["that"] == ["common_docker_bridge_chains_forward_final.rc == 0"]
    assert "equivalent Docker-managed FORWARD bridge rules" in forward_assert["ansible.builtin.assert"]["fail_msg"]
    assert "legacy filter DOCKER chain" in forward_assert["ansible.builtin.assert"]["fail_msg"]
    assert forward_assert["when"] == [
        "common_docker_bridge_chains_active_state.rc == 0",
        "common_docker_bridge_chains_expect_forward_chain | default(false)",
    ]
