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

    assert "- name: Read the local OpenBao seal status" in tasks
    assert "/v1/sys/seal-status" in tasks
    assert "- name: Unseal the local OpenBao API when runtime secret injection finds it sealed" in tasks
    assert "/v1/sys/unseal" in tasks
    assert "keys_base64[: (openbao_init_key_threshold | default(2) | int)]" in tasks
    assert "- name: Assert the local OpenBao API is unsealed before runtime secret injection" in tasks
    assert "- name: Wait for the local OpenBao API to become active" in tasks
    assert "- name: Upsert the OpenBao AppRole for the runtime agent" in tasks
    assert "register: common_openbao_compose_env_approle_upsert" in tasks
    assert "until: common_openbao_compose_env_approle_upsert.status == 204" in tasks
    assert "common_openbao_compose_env_agent_template_local_file" in tasks
    assert "common_openbao_compose_env_agent_template_content" in tasks
    assert "ansible.builtin.copy" in tasks
    assert "ansible.builtin.template" in tasks
    assert "- name: Read the current runtime secret payload from OpenBao" in tasks
    assert "until: common_openbao_compose_env_current_secret.status in [200, 404]" in tasks
    assert "- name: Read the current OpenBao policy for the runtime AppRole" in tasks
    assert "until: common_openbao_compose_env_current_policy.status in [200, 404]" in tasks
