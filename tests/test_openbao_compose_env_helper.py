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
SYSTEMD_HELPER_TASKS_PATH = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "common"
    / "tasks"
    / "openbao_systemd_credentials.yml"
)
RECOVERY_TASKS_PATH = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "common"
    / "tasks"
    / "ensure_local_openbao_runtime.yml"
)


def test_helper_unseals_restarted_openbao_before_waiting_for_health() -> None:
    tasks = HELPER_TASKS_PATH.read_text(encoding="utf-8")

    assert "include_tasks: ensure_local_openbao_runtime.yml" in tasks
    assert "- name: Ensure the controller-local SSH control path directory exists before OpenBao API retries" in tasks
    assert "path: \"{{ lookup('ansible.builtin.env', 'ANSIBLE_SSH_CONTROL_PATH_DIR') }}\"" in tasks
    assert "- name: Read the local OpenBao seal status" in tasks
    assert "/v1/sys/seal-status" in tasks
    assert "- name: Unseal the local OpenBao API when runtime secret injection finds it sealed" in tasks
    assert "/v1/sys/unseal" in tasks
    assert "keys_base64[: (openbao_init_key_threshold | default(2) | int)]" in tasks
    assert "- name: Assert the local OpenBao API is unsealed before runtime secret injection" in tasks
    assert "- name: Wait for the local OpenBao API to become active" in tasks
    assert "- name: Upsert the OpenBao AppRole for the runtime agent" in tasks
    assert "common_openbao_compose_env_agent_template_local_file" in tasks
    assert "common_openbao_compose_env_agent_template_content" in tasks
    assert "ansible.builtin.copy" in tasks
    assert "ansible.builtin.template" in tasks
    assert "- name: Read the current runtime secret payload from OpenBao" in tasks
    assert "until: common_openbao_compose_env_current_secret.status in [200, 404]" in tasks
    assert "- name: Read the current OpenBao policy for the runtime AppRole" in tasks
    assert "until: common_openbao_compose_env_current_policy.status in [200, 404]" in tasks


def test_systemd_helper_reuses_local_openbao_recovery() -> None:
    tasks = SYSTEMD_HELPER_TASKS_PATH.read_text(encoding="utf-8")

    assert "include_tasks: ensure_local_openbao_runtime.yml" in tasks
    assert "- name: Ensure the controller-local SSH control path directory exists before OpenBao API retries" in tasks
    assert "path: \"{{ lookup('ansible.builtin.env', 'ANSIBLE_SSH_CONTROL_PATH_DIR') }}\"" in tasks
    assert "- name: Wait for the local OpenBao API to answer" in tasks
    assert "- name: Unseal the local OpenBao API when host-native secret delivery finds it sealed" in tasks


def test_local_openbao_recovery_helper_recovers_compose_runtime_when_api_is_down() -> None:
    tasks = RECOVERY_TASKS_PATH.read_text(encoding="utf-8")

    assert "- name: Probe whether the local OpenBao API already answers" in tasks
    assert "- name: Inspect current OpenBao container networks before local recovery" in tasks
    assert "- name: Inspect current OpenBao published ports before local recovery" in tasks
    assert "openbao_container_name | default('lv3-openbao')" in tasks
    assert '{{ "{{json .NetworkSettings.Ports}}" }}' in tasks
    assert "- name: Restart Docker when required chains are missing before local OpenBao recovery" in tasks
    assert "- name: Assert Docker bridge chains are present before local OpenBao recovery" in tasks
    assert "- name: Remove the detached OpenBao container before local recovery" in tasks
    assert "- name: Remove the stale OpenBao compose network before local recovery" in tasks
    assert "- name: Recover the local OpenBao stack when the API is unavailable" in tasks
    assert "docker" in tasks
    assert "--remove-orphans" in tasks
    assert "--force-recreate" in tasks
    assert "openbao" in tasks
