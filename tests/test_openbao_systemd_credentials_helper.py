from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
HELPER_DEFAULTS_PATH = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "common"
    / "defaults"
    / "main.yml"
)
HELPER_META_PATH = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "common"
    / "meta"
    / "argument_specs.yml"
)
HELPER_TASKS_PATH = (
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
HELPER_UNIT_TEMPLATE_PATH = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "common"
    / "templates"
    / "openbao-agent-systemd-credentials.service.j2"
)


def test_openbao_systemd_credentials_helper_supports_remote_api_targets() -> None:
    defaults = HELPER_DEFAULTS_PATH.read_text(encoding="utf-8")
    meta = HELPER_META_PATH.read_text(encoding="utf-8")
    tasks = HELPER_TASKS_PATH.read_text(encoding="utf-8")

    assert "common_openbao_systemd_credentials_manage_local_openbao_runtime: true" in defaults
    assert "common_openbao_api_operation_retries: 36" in defaults
    assert "common_openbao_api_operation_delay: 5" in defaults
    assert "common_openbao_systemd_credentials_manage_local_openbao_runtime:" in meta
    assert "common_openbao_api_operation_retries:" in meta
    assert "common_openbao_api_operation_delay:" in meta
    assert "common_openbao_systemd_credentials_api_url" in tasks
    assert "Wait for the configured OpenBao API to answer before host-native secret delivery" in tasks
    assert "common_openbao_systemd_credentials_manage_local_openbao_runtime | bool" in tasks
    assert "include_tasks: unseal_openbao_api.yml" in tasks
    assert "common_openbao_unseal_api_url: \"{{ common_openbao_systemd_credentials_api_url }}\"" in tasks
    assert "register: common_openbao_systemd_credentials_unsealed_status" in tasks
    assert "common_openbao_systemd_credentials_unsealed_status.status == 200" in tasks
    assert "not (common_openbao_systemd_credentials_unsealed_status.json.sealed | bool)" in tasks
    assert "{{ common_openbao_systemd_credentials_api_url }}/v1/auth/approle/role/{{ common_openbao_systemd_credentials_approle_name }}/secret-id" in tasks
    assert 'retries: "{{ common_openbao_api_operation_retries }}"' in tasks
    assert 'delay: "{{ common_openbao_api_operation_delay }}"' in tasks


def test_openbao_systemd_credentials_unit_waits_with_a_valid_shell_if_clause() -> None:
    template = HELPER_UNIT_TEMPLATE_PATH.read_text(encoding="utf-8")

    assert "for attempt in $(seq 1 30); do if " in template
    assert " ]; then exit 0; fi; sleep 1; done;" in template


def test_openbao_systemd_credentials_restarts_and_rechecks_when_secret_payload_changes() -> None:
    tasks = HELPER_TASKS_PATH.read_text(encoding="utf-8")

    assert "register: common_openbao_systemd_credentials_secret_write" in tasks
    assert "common_openbao_systemd_credentials_secret_write is defined and common_openbao_systemd_credentials_secret_write.changed" in tasks
    assert "Wait for the refreshed host-native credential file after OpenBao secret changes" in tasks
    assert "common_openbao_systemd_credentials_refreshed_credential_file" in tasks
