from __future__ import annotations

import json
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
FALCO_ROLE_DEFAULTS = REPO_ROOT / "roles" / "falco_runtime" / "defaults" / "main.yml"
FALCO_ROLE_TASKS = REPO_ROOT / "roles" / "falco_runtime" / "tasks" / "main.yml"
FALCO_ROLE_VERIFY = REPO_ROOT / "roles" / "falco_runtime" / "tasks" / "verify.yml"
FALCO_ROLE_META = REPO_ROOT / "roles" / "falco_runtime" / "meta" / "argument_specs.yml"
FALCO_ROLE_TEMPLATE = REPO_ROOT / "roles" / "falco_runtime" / "templates" / "falco-runtime.yaml.j2"
FALCO_ROLE_JOURNALD_TEMPLATE = REPO_ROOT / "roles" / "falco_runtime" / "templates" / "falco-journald.conf.j2"
BRIDGE_ROLE_DEFAULTS = REPO_ROOT / "roles" / "falco_event_bridge_runtime" / "defaults" / "main.yml"
BRIDGE_ROLE_TASKS = REPO_ROOT / "roles" / "falco_event_bridge_runtime" / "tasks" / "main.yml"
BRIDGE_ROLE_META = REPO_ROOT / "roles" / "falco_event_bridge_runtime" / "meta" / "argument_specs.yml"
PLAYBOOK_PATH = REPO_ROOT / "playbooks" / "falco.yml"
SERVICE_WRAPPER_PATH = REPO_ROOT / "playbooks" / "services" / "falco.yml"
HOST_VARS_PATH = REPO_ROOT / "inventory" / "host_vars" / "proxmox_florin.yml"
WORKFLOW_CATALOG_PATH = REPO_ROOT / "config" / "workflow-catalog.json"
COMMAND_CATALOG_PATH = REPO_ROOT / "config" / "command-catalog.json"
ANSIBLE_EXECUTION_SCOPES_PATH = REPO_ROOT / "config" / "ansible-execution-scopes.yaml"
EVENT_TAXONOMY_PATH = REPO_ROOT / "config" / "event-taxonomy.yaml"
NTFY_CONFIG_PATH = REPO_ROOT / "config" / "ntfy" / "server.yml"
FALCO_SUPPRESSIONS_PATH = REPO_ROOT / "config" / "falco" / "suppressions.yaml"
NTFY_ROLE_DEFAULTS = REPO_ROOT / "collections" / "ansible_collections" / "lv3" / "platform" / "roles" / "ntfy_runtime" / "defaults" / "main.yml"
NTFY_ROLE_TASKS = REPO_ROOT / "collections" / "ansible_collections" / "lv3" / "platform" / "roles" / "ntfy_runtime" / "tasks" / "main.yml"
NTFY_ROLE_HANDLERS = REPO_ROOT / "collections" / "ansible_collections" / "lv3" / "platform" / "roles" / "ntfy_runtime" / "handlers" / "main.yml"
NTFY_ROLE_VERIFY = REPO_ROOT / "collections" / "ansible_collections" / "lv3" / "platform" / "roles" / "ntfy_runtime" / "tasks" / "verify.yml"


def load_yaml(path: Path) -> list[dict] | dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_falco_defaults_define_private_bridge_output_and_rule_sources() -> None:
    defaults = load_yaml(FALCO_ROLE_DEFAULTS)

    assert defaults["falco_runtime_service_name"] == "falco-modern-bpf"
    assert defaults["falco_runtime_systemd_override_dir"] == "/etc/systemd/system/{{ falco_runtime_service_name }}.service.d"
    assert defaults["falco_runtime_systemd_override_file"] == "{{ falco_runtime_systemd_override_dir }}/lv3-journald.conf"
    assert defaults["falco_runtime_http_output_url"] == "http://{{ falco_runtime_bridge_host }}:{{ falco_runtime_bridge_port }}/events"
    assert defaults["falco_runtime_rule_sources"][0]["dest"].endswith("50-lv3-platform-overrides.yaml")
    assert "falcoctl-artifact-follow.service" in defaults["falco_runtime_disabled_services"]


def test_falco_argument_spec_requires_repo_and_bridge_inputs() -> None:
    specs = load_yaml(FALCO_ROLE_META)
    options = specs["argument_specs"]["main"]["options"]

    assert options["falco_runtime_repo_root"]["type"] == "path"
    assert options["falco_runtime_packages"]["elements"] == "str"
    assert options["falco_runtime_rule_sources"]["elements"] == "dict"
    assert options["falco_runtime_http_output_url"]["type"] == "str"


def test_falco_tasks_install_render_rules_and_verify_service() -> None:
    tasks = load_yaml(FALCO_ROLE_TASKS)
    names = [task["name"] for task in tasks]

    assert "Install the Falco runtime packages" in names
    assert "Ensure the Falco systemd override directory exists" in names
    assert "Render the Falco journald systemd override" in names
    assert "Render the Falco runtime override config" in names
    assert "Sync the repo-managed Falco rule files" in names
    assert "Ensure the Falco runtime service is enabled and started" in names
    assert "Verify the Falco runtime" in names

    verify_tasks = load_yaml(FALCO_ROLE_VERIFY)
    verify_names = [task["name"] for task in verify_tasks]
    assert "Verify the Falco runtime service is active" in verify_names
    assert "Verify the managed Falco smoke rule is present" in verify_names


def test_falco_template_enables_json_stdout_and_http_output() -> None:
    template = FALCO_ROLE_TEMPLATE.read_text(encoding="utf-8")
    journald_template = FALCO_ROLE_JOURNALD_TEMPLATE.read_text(encoding="utf-8")

    assert "json_output: true" in template
    assert "stdout_output:" in template
    assert "http_output:" in template
    assert "{{ falco_runtime_http_output_url }}" in template
    assert "StandardOutput=journal" in journald_template
    assert "StandardError=journal" in journald_template


def test_falco_suppressions_narrowly_allow_semgrep_drop_and_execute_noise() -> None:
    suppressions = load_yaml(FALCO_SUPPRESSIONS_PATH)
    semgrep_suppression = next(
        entry for entry in suppressions if entry.get("macro") == "known_drop_and_execute_activities"
    )

    assert semgrep_suppression["override"] == {"condition": "append"}
    assert 'container.image.repository = "registry.lv3.org/check-runner/python"' in semgrep_suppression["condition"]
    assert 'proc.name = "semgrep-core"' in semgrep_suppression["condition"]
    assert 'proc.exepath contains "/site-packages/semgrep/bin/semgrep-core"' in semgrep_suppression["condition"]


def test_bridge_defaults_reuse_private_nats_and_ntfy_contracts() -> None:
    defaults = load_yaml(BRIDGE_ROLE_DEFAULTS)

    assert defaults["falco_event_bridge_service_name"] == "lv3-falco-event-bridge"
    assert defaults["falco_event_bridge_listen_port"] == "{{ hostvars['proxmox_florin'].platform_port_assignments.falco_event_bridge_port }}"
    assert defaults["falco_event_bridge_nats_subject"] == "platform.security.falco"
    assert defaults["falco_event_bridge_ntfy_topic"] == "platform-security-critical"


def test_bridge_role_reads_controller_local_credentials_and_starts_systemd_service() -> None:
    tasks = load_yaml(BRIDGE_ROLE_TASKS)
    names = [task["name"] for task in tasks]

    assert "Read the controller-local NATS admin password for the Falco bridge" in names
    assert "Read the controller-local ntfy password for the Falco bridge" in names
    assert "Render the Falco event bridge systemd unit" in names
    assert "Ensure the Falco event bridge service is enabled and running" in names

    specs = load_yaml(BRIDGE_ROLE_META)
    options = specs["argument_specs"]["main"]["options"]
    assert options["falco_event_bridge_listen_port"]["type"] == "int"
    assert options["falco_event_bridge_script_sources"]["elements"] == "dict"


def test_playbook_converges_bridge_then_falco_runtime_across_hosts() -> None:
    playbook = load_yaml(PLAYBOOK_PATH)

    assert len(playbook) == 2
    first_roles = [role["role"] for role in playbook[0]["roles"]]
    second_roles = [role["role"] for role in playbook[1]["roles"]]
    assert playbook[0]["hosts"] == "docker-runtime-lv3"
    assert playbook[1]["hosts"] == "docker-runtime-lv3:docker-build-lv3:monitoring-lv3:postgres-lv3"
    assert "lv3.platform.ntfy_runtime" in first_roles
    assert first_roles[-1] == "lv3.platform.falco_event_bridge_runtime"
    assert second_roles[-1] == "lv3.platform.falco_runtime"

    wrapper = load_yaml(SERVICE_WRAPPER_PATH)
    assert wrapper == [{"import_playbook": "../falco.yml"}]


def test_inventory_exposes_private_bridge_port_and_guest_access_rules() -> None:
    host_vars = load_yaml(HOST_VARS_PATH)

    assert host_vars["platform_port_assignments"]["falco_event_bridge_port"] == 18084
    docker_runtime_rules = host_vars["network_policy"]["guests"]["docker-runtime-lv3"]["allowed_inbound"]
    build_rule = next(rule for rule in docker_runtime_rules if rule["source"] == "docker-build-lv3" and 18084 in rule["ports"])
    monitoring_rule = next(rule for rule in docker_runtime_rules if rule["source"] == "monitoring-lv3" and 18084 in rule["ports"])
    postgres_rule = next(rule for rule in docker_runtime_rules if rule["source"] == "postgres-lv3")
    assert 18084 in build_rule["ports"]
    assert 18084 in monitoring_rule["ports"]
    assert 18084 in postgres_rule["ports"]


def test_workflow_and_command_catalogs_register_falco_converge_entrypoint() -> None:
    workflow_catalog = json.loads(WORKFLOW_CATALOG_PATH.read_text(encoding="utf-8"))
    command_catalog = json.loads(COMMAND_CATALOG_PATH.read_text(encoding="utf-8"))

    workflow = workflow_catalog["workflows"]["converge-falco"]
    command = command_catalog["commands"]["converge-falco"]

    assert workflow["preferred_entrypoint"] == {
        "kind": "make_target",
        "target": "converge-falco",
        "command": "make converge-falco",
    }
    assert "syntax-check-falco" in workflow["validation_targets"]
    assert workflow["owner_runbook"] == "docs/runbooks/configure-falco-runtime.md"
    assert command["workflow_id"] == "converge-falco"
    assert command["approval_policy"] == "sensitive_live_change"
    assert command["evidence"]["live_apply_receipt_required"] is True


def test_ansible_scopes_taxonomy_ntfy_and_mutation_audit_cover_falco() -> None:
    scopes = load_yaml(ANSIBLE_EXECUTION_SCOPES_PATH)
    entry = scopes["playbooks"]["playbooks/falco.yml"]
    assert entry["playbook_id"] == "falco"
    assert entry["mutation_scope"] == "platform"
    assert "security:falco-runtime" in entry["shared_surfaces"]

    taxonomy = load_yaml(EVENT_TAXONOMY_PATH)
    security_topics = {topic["name"]: topic for topic in taxonomy["domains"]["security"]["topics"]}
    assert "platform.security.falco" in security_topics
    assert security_topics["platform.security.falco"]["payload"]["required"] == [
        "event",
        "host",
        "rule",
        "priority",
        "time",
    ]

    ntfy_config = NTFY_CONFIG_PATH.read_text(encoding="utf-8")
    assert "{{ ntfy_runtime_username }}:platform-security-critical:rw" in ntfy_config


def test_ntfy_runtime_restarts_container_when_auth_config_changes() -> None:
    defaults = load_yaml(NTFY_ROLE_DEFAULTS)
    tasks = load_yaml(NTFY_ROLE_TASKS)
    handlers = load_yaml(NTFY_ROLE_HANDLERS)
    verify_tasks = load_yaml(NTFY_ROLE_VERIFY)

    render_config = next(task for task in tasks if task["name"] == "Render ntfy server config")
    render_compose = next(task for task in tasks if task["name"] == "Render ntfy compose file")
    ensure_bridge_chains = next(
        task for task in tasks if task["name"] == "Ensure Docker bridge networking chains are ready before ntfy startup"
    )
    startup_recovery = next(
        task for task in tasks if task["name"] == "Start the ntfy stack and recover Docker bridge-chain failures"
    )
    snapshot_acl = next(task for task in tasks if task["name"] == "Snapshot provisioned ntfy ACL state")
    repair_acl = next(task for task in tasks if task["name"] == "Force-recreate the ntfy stack when provisioned ACL entries are stale")
    restart_handler = next(task for task in handlers if task["name"] == "Restart ntfy stack")
    verify_acl = next(
        task
        for task in verify_tasks
        if task["name"] == "Verify provisioned ntfy ACL topics are writable for the managed publisher"
    )

    assert defaults["ntfy_runtime_image"] == "binwiederhier/ntfy:v2.21.0"
    assert defaults["ntfy_runtime_expected_write_topics"] == [
        "platform-alerts",
        "platform-alerts-sbom-verify",
        "platform-slo-warn",
        "platform-security-critical",
    ]
    assert ensure_bridge_chains["ansible.builtin.include_role"]["tasks_from"] == "docker_bridge_chains"
    assert ensure_bridge_chains["vars"]["common_docker_bridge_chains_service_name"] == "docker"
    assert ensure_bridge_chains["vars"]["common_docker_bridge_chains_require_nat_chain"] is True
    startup_rescue_names = [task["name"] for task in startup_recovery["rescue"]]
    assert startup_recovery["block"][0]["name"] == "Start the ntfy stack"
    assert "Flag Docker bridge-chain failures during ntfy startup" in startup_rescue_names
    assert "Reset stale ntfy compose resources after startup failure" in startup_rescue_names
    assert "Ensure Docker bridge networking chains are present before retrying ntfy startup" in startup_rescue_names
    assert "Retry ntfy startup after Docker bridge-chain recovery" in startup_rescue_names
    assert render_config["notify"] == "Restart ntfy stack"
    assert render_compose["notify"] == "Restart ntfy stack"
    assert snapshot_acl["environment"]["NTFY_RUNTIME_EXPECTED_TOPICS"] == "{{ ntfy_runtime_expected_write_topics | to_json }}"
    assert repair_acl["when"] == "ntfy_runtime_acl_state.rc != 0"
    assert "--force-recreate" in restart_handler["ansible.builtin.command"]["argv"]
    assert verify_acl["environment"]["NTFY_RUNTIME_EXPECTED_TOPICS"] == "{{ ntfy_runtime_expected_write_topics | to_json }}"
