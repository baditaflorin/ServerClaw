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

    assert "- name: Ensure the local OpenBao API answers before runtime secret injection" in tasks
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


def test_helper_recovers_local_openbao_publication_drift() -> None:
    tasks = HELPER_TASKS_PATH.read_text(encoding="utf-8")
    systemd_helper_tasks = (
        REPO_ROOT
        / "collections"
        / "ansible_collections"
        / "lv3"
        / "platform"
        / "roles"
        / "common"
        / "tasks"
        / "openbao_systemd_credentials.yml"
    ).read_text(encoding="utf-8")

    assert "- name: Force-recreate the OpenBao service when the local API publication is missing before runtime secret injection" in tasks
    assert "--force-recreate" in tasks
    assert "- name: Wait for the local OpenBao loopback port after runtime secret injection recovery" in tasks
    assert "connection refused" in tasks
    assert "- name: Force-recreate the OpenBao service when the local API publication is missing before host-native secret delivery" in systemd_helper_tasks
    assert "- name: Wait for the local OpenBao loopback port after host-native secret delivery recovery" in systemd_helper_tasks
