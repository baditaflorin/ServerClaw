from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_ROOT = REPO_ROOT / "collections" / "ansible_collections" / "lv3" / "platform" / "roles"
MEMBER_DEFAULTS = ROLE_ROOT / "nomad_cluster_member" / "defaults" / "main.yml"
MEMBER_TASKS = ROLE_ROOT / "nomad_cluster_member" / "tasks" / "main.yml"
BOOTSTRAP_DEFAULTS = ROLE_ROOT / "nomad_cluster_bootstrap" / "defaults" / "main.yml"
BOOTSTRAP_CONTROLLER_TASKS = ROLE_ROOT / "nomad_cluster_bootstrap" / "tasks" / "controller_artifacts.yml"
BOOTSTRAP_VERIFY_TASKS = ROLE_ROOT / "nomad_cluster_bootstrap" / "tasks" / "verify.yml"
MEMBER_TEMPLATE = ROLE_ROOT / "nomad_cluster_member" / "templates" / "nomad.hcl.j2"
CLI_WRAPPER_TEMPLATE = ROLE_ROOT / "nomad_cluster_member" / "templates" / "lv3-nomad.sh.j2"
SERVICE_TEMPLATE = ROLE_ROOT / "nomad_cluster_member" / "templates" / "lv3-nomad.service.j2"


def load_tasks(path: Path) -> list[dict]:
    return yaml.safe_load(path.read_text())


def test_nomad_member_defaults_follow_platform_port_and_inventory_host_patterns() -> None:
    defaults = MEMBER_DEFAULTS.read_text()
    assert "platform_port_assignments.nomad_server_port" in defaults
    assert "playbook_execution_host_patterns.monitoring[playbook_execution_env]" in defaults
    assert "hostvars[nomad_cluster_server_inventory_host].ansible_host" in defaults


def test_nomad_member_tasks_install_the_binary_and_cli_wrapper() -> None:
    tasks = load_tasks(MEMBER_TASKS)
    names = {task["name"] for task in tasks}
    assert "Install the pinned Nomad binary" in names
    assert "Render the local Nomad CLI wrapper" in names
    assert "Verify the Nomad agent" in names


def test_nomad_bootstrap_defaults_track_controller_artifacts_and_smoke_jobs() -> None:
    defaults = BOOTSTRAP_DEFAULTS.read_text()
    assert "/.local/nomad" in defaults
    assert "nomad-agent-ca-key.pem" in defaults
    assert "bootstrap-management.token" in defaults
    assert "config/nomad/jobs/lv3-nomad-smoke-service.nomad.hcl" in defaults
    assert "config/nomad/jobs/lv3-nomad-smoke-batch.nomad.hcl" in defaults


def test_nomad_bootstrap_controller_tasks_generate_ca_server_and_client_material() -> None:
    tasks = load_tasks(BOOTSTRAP_CONTROLLER_TASKS)
    names = {task["name"] for task in tasks}
    assert "Generate the Nomad TLS certificate authority when missing" in names
    assert "Render the Nomad server OpenSSL profile" in names
    assert "Render the Nomad client OpenSSL profile" in names
    assert "Generate the Nomad server TLS certificate when missing" in names
    assert "Generate the Nomad client TLS certificate when missing" in names


def test_nomad_bootstrap_verify_checks_service_and_batch_paths() -> None:
    tasks = load_tasks(BOOTSTRAP_VERIFY_TASKS)
    delegate_task = next(task for task in tasks if task["name"] == "Verify the smoke service content from the build host")
    assert delegate_task["delegate_to"] == "{{ nomad_cluster_bootstrap_build_host }}"

    log_task = next(task for task in tasks if task["name"] == "Read the smoke batch allocation logs")
    assert log_task["ansible.builtin.command"]["argv"][:3] == ["/usr/local/bin/lv3-nomad", "alloc", "logs"]


def test_nomad_templates_enable_acl_tls_and_client_docker_plugin() -> None:
    config_template = MEMBER_TEMPLATE.read_text()
    cli_wrapper = CLI_WRAPPER_TEMPLATE.read_text()
    service_template = SERVICE_TEMPLATE.read_text()

    assert "verify_server_hostname = true" in config_template
    assert "plugin \"docker\"" in config_template
    assert "NOMAD_ADDR" in cli_wrapper
    assert "NOMAD_CACERT" in cli_wrapper
    assert "User={{ nomad_cluster_service_user }}" in service_template
    assert "Group={{ nomad_cluster_service_group }}" in service_template


def test_nomad_member_defaults_run_the_agent_as_root_for_tls_and_docker_access() -> None:
    defaults = MEMBER_DEFAULTS.read_text()
    assert "nomad_cluster_service_user: root" in defaults
    assert "nomad_cluster_service_group: root" in defaults
