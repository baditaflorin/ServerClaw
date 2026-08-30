import re
from pathlib import Path

import yaml


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
SERVICE_REGISTRY_PATH = REPO_ROOT / "inventory" / "group_vars" / "all" / "platform_services.yml"
GROUP_VARS_MAIN_PATH = REPO_ROOT / "inventory" / "group_vars" / "all" / "main.yml"
HOST_VARS_PATH = REPO_ROOT / "inventory" / "host_vars" / "proxmox-host.yml"


def test_compose_helper_uses_narrow_provisioner_and_fails_closed() -> None:
    tasks = HELPER_TASKS_PATH.read_text(encoding="utf-8")
    defaults = (REPO_ROOT / "roles" / "common" / "defaults" / "main.yml").read_text(encoding="utf-8")

    assert 'common_openbao_compose_env_openbao_address: ""' in defaults
    assert "common_openbao_compose_env_manage_local_openbao_runtime: false" in defaults
    assert "common_openbao_compose_env_provisioner_credential_file:" in defaults
    assert "common_openbao_compose_env_provisioner_approle_name: runtime-secret-provisioner" in defaults
    assert "common_openbao_compose_env_provisioner_policy_name:" in defaults
    assert "common_openbao_compose_env_require_fresh_agent_render: true" in defaults
    assert "common_openbao_compose_env_api_url" in tasks
    assert "- name: Resolve the caller against registered needs_openbao Compose services" in tasks
    assert "item.value.needs_openbao | default(true) | bool" in tasks
    assert "- name: Enforce the registered OpenBao service boundary" in tasks
    assert "common_openbao_compose_env_protected_approle_names" in tasks
    assert "- name: Login with the runtime-secret provisioner AppRole" in tasks
    assert "common_openbao_compose_env_provisioner_credential.role_id" in tasks
    assert "common_openbao_compose_env_provisioner_credential.secret_id" in tasks
    assert "- name: Read the provisioner token's effective capabilities" in tasks
    assert "- name: Require the provisioner to be denied policy and protected-AppRole management" in tasks
    assert "sys/capabilities-self" in tasks
    assert "auth/approle/role/controller-automation/secret-id" in tasks
    assert "- name: Fail closed when OpenBao is sealed or not initialized" in tasks
    assert "never restarts or unseals the shared secret authority" in tasks
    assert "- name: Read the pre-created service AppRole role ID" in tasks
    assert "- name: Generate a service AppRole secret ID when the on-disk credential is absent or stale" in tasks
    assert "- name: Verify the existing service AppRole secret ID" in tasks
    assert "- name: Require the service AppRole to receive only its generated policy" in tasks
    assert "- name: Require a read-only exact-path service AppRole capability set" in tasks
    assert "__contract_probe__" in tasks
    assert 'retries: "{{ common_openbao_api_operation_retries }}"' in tasks
    assert 'delay: "{{ common_openbao_api_operation_delay }}"' in tasks
    assert "- name: Render the transient env through a one-shot OpenBao Agent" in tasks
    assert "-exit-after-auth" in tasks
    assert "- name: Require a fresh root-only OpenBao Agent env" in tasks
    assert "common_openbao_compose_env_fresh_env.stat.mode == '0600'" in tasks
    assert "common_openbao_compose_env_fresh_env.stat.uid | int == 0" in tasks
    assert "- name: Render the bootstrap runtime env file from the managed secret payload" not in tasks
    assert 'path: "{{ common_openbao_compose_env_env_file }}"' in tasks
    assert "no_log: true" in tasks
    assert "common_openbao_compose_env_agent_template_local_file" in tasks
    assert "common_openbao_compose_env_agent_template_content" in tasks
    assert "ansible.builtin.copy" in tasks
    assert "ansible.builtin.template" in tasks
    assert "- name: Read the current registered runtime secret payload from OpenBao" in tasks
    assert "until: common_openbao_compose_env_current_secret.status in [200, 404]" in tasks
    assert "register: common_openbao_compose_env_secret_upsert" in tasks
    assert "openbao_init_local_file" not in tasks
    assert "root_token" not in tasks
    assert "include_tasks: unseal_openbao_api.yml" not in tasks
    assert "include_tasks: ensure_local_openbao_runtime.yml" not in tasks
    assert "/v1/sys/unseal" not in tasks
    assert "method: PUT" not in tasks
    assert "Upsert the OpenBao AppRole" not in tasks


def test_compose_api_operations_delegate_to_the_topology_owner() -> None:
    group_vars = yaml.safe_load(GROUP_VARS_MAIN_PATH.read_text(encoding="utf-8"))
    assert group_vars["common_openbao_compose_env_api_host"] == (
        "{{ hostvars[platform_topology_host].platform_service_topology.openbao.owning_vm }}"
    )


def test_docker_runtime_agents_have_an_exact_openbao_automation_path() -> None:
    host_vars = yaml.safe_load(HOST_VARS_PATH.read_text(encoding="utf-8"))
    runtime_control_rules = host_vars["network_policy"]["guests"]["runtime-control"]["allowed_inbound"]

    matching_rules = [
        rule for rule in runtime_control_rules if rule["source"] == "docker-runtime" and 8201 in rule["ports"]
    ]

    assert matching_rules == [
        {
            "source": "docker-runtime",
            "protocol": "tcp",
            "ports": [8201],
            "description": "Private OpenBao Agent secret delivery to registered services on docker-runtime",
        }
    ]


def test_every_registered_openbao_compose_service_resolves_to_one_helper_caller() -> None:
    registry = yaml.safe_load(SERVICE_REGISTRY_PATH.read_text(encoding="utf-8"))["platform_service_registry"]
    group_vars = yaml.safe_load(GROUP_VARS_MAIN_PATH.read_text(encoding="utf-8"))
    overrides = group_vars["openbao_runtime_secret_namespace_overrides"]
    contracts = {
        key: {
            key,
            overrides.get(key, key),
            Path(service.get("site_dir", f"/opt/{key}")).name,
        }
        for key, service in registry.items()
        if service.get("service_type") == "docker_compose" and service.get("needs_openbao", True)
    }

    resolved_callers: dict[str, str] = {}
    for tasks_path in (REPO_ROOT / "roles").glob("*/tasks/main.yml"):
        tasks = tasks_path.read_text(encoding="utf-8")
        if "tasks_from: openbao_compose_env" not in tasks:
            continue
        match = re.search(r"common_openbao_compose_env_service_name:\s*([^\n]+)", tasks)
        assert match is not None, tasks_path
        caller = match.group(1).strip().strip("\"'")
        matches = [key for key, aliases in contracts.items() if caller in aliases]
        assert len(matches) == 1, (tasks_path, caller, matches)
        assert matches[0] not in resolved_callers, (tasks_path, caller, matches[0])
        resolved_callers[matches[0]] = caller

    assert set(resolved_callers) == set(contracts)


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
    assert (
        "- name: Read the local OpenBao seal status after a transient host-native secret payload read failure" in tasks
    )
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
