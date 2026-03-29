from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
HELPER_TASKS_PATH = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "common"
    / "tasks"
    / "openbao_compose_env.yml"
)


def test_helper_unseals_restarted_openbao_before_waiting_for_health() -> None:
    tasks = HELPER_TASKS_PATH.read_text(encoding="utf-8")

    assert "- name: Inspect current OpenBao container networks" in tasks
    assert '{{ "{{json .NetworkSettings.Networks}}" }}' in tasks
    assert "- name: Inspect current OpenBao published ports" in tasks
    assert '{{ "{{json .NetworkSettings.Ports}}" }}' in tasks
    assert "- name: Record whether the local OpenBao runtime needs recovery before runtime secret injection" in tasks
    assert "common_openbao_compose_env_runtime_needs_recovery" in tasks
    assert "- name: Ensure Docker bridge networking chains are present before recovering the local OpenBao runtime" in tasks
    assert "tasks_from: docker_bridge_chains" in tasks
    assert "- name: Check whether the OpenBao compose network exists before recovery" in tasks
    assert '"{{ openbao_site_dir | basename }}_default"' in tasks
    assert "- name: Remove the detached OpenBao container before runtime secret injection recovery" in tasks
    assert "- name: Remove the stale OpenBao compose network before runtime secret injection recovery" in tasks
    assert "- name: Force-recreate the local OpenBao stack before runtime secret injection" in tasks
    assert "--force-recreate" in tasks
    assert "- name: Read the local OpenBao seal status" in tasks
    assert "/v1/sys/seal-status" in tasks
    assert "- name: Unseal the local OpenBao API when runtime secret injection finds it sealed" in tasks
    assert "/v1/sys/unseal" in tasks
    assert "keys_base64[: (openbao_init_key_threshold | default(2) | int)]" in tasks
    assert "- name: Assert the local OpenBao API is unsealed before runtime secret injection" in tasks
    assert "- name: Wait for the local OpenBao API to become active" in tasks
    assert "common_openbao_compose_env_agent_template_local_file" in tasks
    assert "common_openbao_compose_env_agent_template_content" in tasks
    assert "ansible.builtin.copy" in tasks
    assert "ansible.builtin.template" in tasks
    assert "- name: Read the current runtime secret payload from OpenBao" in tasks
    assert "until: common_openbao_compose_env_current_secret.status in [200, 404]" in tasks
    assert "- name: Read the current OpenBao policy for the runtime AppRole" in tasks
    assert "until: common_openbao_compose_env_current_policy.status in [200, 404]" in tasks
