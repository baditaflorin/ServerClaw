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
UNSEAL_HELPER_TASKS_PATH = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "common"
    / "tasks"
    / "unseal_openbao_api.yml"
)
UNSEAL_HELPER_STEP_TASKS_PATH = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "common"
    / "tasks"
    / "unseal_openbao_api_key.yml"
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
    unseal_tasks = UNSEAL_HELPER_TASKS_PATH.read_text(encoding="utf-8")
    unseal_step_tasks = UNSEAL_HELPER_STEP_TASKS_PATH.read_text(encoding="utf-8")

    assert "include_tasks: ensure_local_openbao_runtime.yml" in tasks
    assert "- name: Ensure the controller-local SSH control path directory exists before OpenBao API retries" in tasks
    assert 'path: "{{ lookup(\'ansible.builtin.env\', \'ANSIBLE_SSH_CONTROL_PATH_DIR\') }}"' in tasks
    assert "- name: Record whether the local OpenBao runtime needed recovery for compose env injection" in tasks
    assert "common_openbao_compose_env_runtime_needs_recovery" in tasks
    assert "- name: Wait for the Docker daemon to answer after networking recovery" in tasks
    assert "register: common_openbao_compose_env_docker_info" in tasks
    assert "until: common_openbao_compose_env_docker_info.rc == 0" in tasks
    assert "- name: Recover the local OpenBao runtime before helper API calls" in tasks
    assert "- name: Wait for the local OpenBao API to become active" in tasks
    assert "- name: Ensure the local OpenBao API is unsealed before runtime secret injection" in tasks
    assert "include_tasks: unseal_openbao_api.yml" in tasks
    assert 'common_openbao_unseal_context: "runtime secret injection for {{ common_openbao_compose_env_service_name }}"' in tasks
    assert 'common_openbao_unseal_api_url: "http://127.0.0.1:{{ openbao_http_port }}"' in tasks
    assert "Read OpenBao seal status before" in unseal_tasks
    assert "common_openbao_unseal_completed" in unseal_tasks
    assert "include_tasks: unseal_openbao_api_key.yml" in unseal_tasks
    assert "/v1/sys/unseal" in unseal_step_tasks
    assert "common_openbao_unseal_completed" in unseal_step_tasks
    assert "register: common_openbao_compose_env_unsealed_status" in tasks
    assert "common_openbao_compose_env_unsealed_status.status == 200" in tasks
    assert "not (common_openbao_compose_env_unsealed_status.json.sealed | bool)" in tasks
    assert "- name: Assert the local OpenBao API is unsealed before runtime secret injection" in tasks
    assert "- name: Wait for the local OpenBao API to become active" in tasks
    assert "- name: Upsert the OpenBao AppRole for the runtime agent" in tasks
    assert "register: common_openbao_compose_env_approle_upsert" in tasks
    assert 'retries: "{{ common_openbao_api_operation_retries }}"' in tasks
    assert 'delay: "{{ common_openbao_api_operation_delay }}"' in tasks
    assert "until: common_openbao_compose_env_approle_upsert.status == 204" in tasks
    assert "- name: Render the bootstrap runtime env file from the managed secret payload" in tasks
    assert 'dest: "{{ common_openbao_compose_env_env_file }}"' in tasks
    assert "common_openbao_compose_env_secret_payload | dictsort" in tasks
    assert "no_log: true" in tasks
    assert "common_openbao_compose_env_agent_template_local_file" in tasks
    assert "common_openbao_compose_env_agent_template_content" in tasks
    assert "ansible.builtin.copy" in tasks
    assert "ansible.builtin.template" in tasks
    assert "- name: Probe the current runtime secret payload from OpenBao" in tasks
    assert "- name: Read the local OpenBao seal status after a transient runtime secret payload read failure" in tasks
    assert "- name: Unseal the local OpenBao API when runtime secret payload reads catch it sealed" in tasks
    assert "- name: Wait for the local OpenBao API to become active after runtime secret payload recovery" in tasks
    assert "- name: Read the current runtime secret payload from OpenBao" in tasks
    assert "until: common_openbao_compose_env_current_secret.status in [200, 404]" in tasks
    assert "register: common_openbao_compose_env_secret_upsert" in tasks
    assert "- name: Read the current OpenBao policy for the runtime AppRole" in tasks
    assert "until: common_openbao_compose_env_current_policy.status in [200, 404]" in tasks
    assert "register: common_openbao_compose_env_policy_upsert" in tasks
    assert "register: common_openbao_compose_env_approle_upsert" in tasks
    assert "until: common_openbao_compose_env_approle_upsert.status == 204" in tasks
    assert "retries: 6" in unseal_step_tasks


def test_systemd_helper_reuses_local_openbao_recovery() -> None:
    tasks = SYSTEMD_HELPER_TASKS_PATH.read_text(encoding="utf-8")

    assert "include_tasks: ensure_local_openbao_runtime.yml" in tasks
    assert "- name: Ensure the controller-local SSH control path directory exists before OpenBao API retries" in tasks
    assert "path: \"{{ lookup('ansible.builtin.env', 'ANSIBLE_SSH_CONTROL_PATH_DIR') }}\"" in tasks
    assert "- name: Wait for the local OpenBao API to answer" in tasks
    assert "- name: Ensure the configured OpenBao API is unsealed before host-native secret delivery" in tasks
    assert "include_tasks: unseal_openbao_api.yml" in tasks
    assert "register: common_openbao_systemd_credentials_unsealed_status" in tasks
    assert "common_openbao_systemd_credentials_unsealed_status.status == 200" in tasks
    assert "not (common_openbao_systemd_credentials_unsealed_status.json.sealed | bool)" in tasks
    assert "- name: Probe the current host-native secret payload from OpenBao" in tasks
    assert "- name: Read the local OpenBao seal status after a transient host-native secret payload read failure" in tasks
    assert "- name: Unseal the local OpenBao API when host-native secret payload reads catch it sealed" in tasks
    assert "- name: Wait for the local OpenBao API to become active after host-native secret payload recovery" in tasks


def test_local_openbao_recovery_helper_recovers_compose_runtime_when_api_is_down() -> None:
    tasks = RECOVERY_TASKS_PATH.read_text(encoding="utf-8")

    assert "common_local_openbao_runtime_log_dir" in tasks
    assert "common_local_openbao_runtime_audit_log_file" in tasks
    assert "- name: Ensure the local OpenBao log directory retains managed ownership before helper API calls" in tasks
    assert "- name: Ensure the local OpenBao audit log file retains managed ownership before helper API calls" in tasks
    assert "- name: Probe whether the local OpenBao API already answers" in tasks
    assert 'path: "{{ common_local_openbao_runtime_log_dir }}"' in tasks
    assert 'path: "{{ common_local_openbao_runtime_audit_log_file }}"' in tasks
    assert "- name: Inspect current OpenBao container networks before local recovery" in tasks
    assert "- name: Inspect current OpenBao published ports before local recovery" in tasks
    assert "common_local_openbao_runtime_detached" in tasks
    assert "openbao_container_name | default('lv3-openbao')" in tasks
    assert '{{ "{{json .NetworkSettings.Ports}}" }}' in tasks
    assert "- name: Restart Docker when required chains are missing before local OpenBao recovery" in tasks
    assert "- name: Assert Docker bridge chains are present before local OpenBao recovery" in tasks
    assert "- name: Check whether the local OpenBao Compose file exists before recovery" in tasks
    assert "- name: Remove the detached OpenBao container before local recovery" in tasks
    assert "- name: Remove the stale OpenBao compose network before local recovery" in tasks
    assert "- name: Recover the local OpenBao stack when the API is unavailable" in tasks
    assert "docker" in tasks
    assert "--remove-orphans" in tasks
    assert "--force-recreate" in tasks
    assert "openbao" in tasks
