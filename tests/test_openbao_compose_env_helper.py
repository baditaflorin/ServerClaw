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

    assert "- name: Recover the local OpenBao runtime before helper API calls" in tasks
    assert "- name: Wait for the local OpenBao API to become active" in tasks
    assert "- name: Ensure the local OpenBao API is unsealed before runtime secret injection" in tasks
    assert "include_tasks: unseal_openbao_api.yml" in tasks
    assert 'common_openbao_unseal_api_url: "http://127.0.0.1:{{ openbao_http_port }}"' in tasks
    assert "- name: Upsert the OpenBao AppRole for the runtime agent" in tasks
    assert "register: common_openbao_compose_env_approle_upsert" in tasks
    assert 'retries: "{{ common_openbao_api_operation_retries }}"' in tasks
    assert 'delay: "{{ common_openbao_api_operation_delay }}"' in tasks
    assert "until: common_openbao_compose_env_approle_upsert.status == 204" in tasks
    assert "common_openbao_compose_env_agent_template_local_file" in tasks
    assert "common_openbao_compose_env_agent_template_content" in tasks
    assert "ansible.builtin.copy" in tasks
    assert "ansible.builtin.template" in tasks
    assert "- name: Read the current runtime secret payload from OpenBao" in tasks
    assert "until: common_openbao_compose_env_current_secret.status in [200, 404]" in tasks
    assert "register: common_openbao_compose_env_secret_upsert" in tasks
    assert "- name: Read the current OpenBao policy for the runtime AppRole" in tasks
    assert "until: common_openbao_compose_env_current_policy.status in [200, 404]" in tasks
    assert "register: common_openbao_compose_env_policy_upsert" in tasks
