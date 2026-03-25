from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULTS_PATH = REPO_ROOT / "roles" / "vaultwarden_runtime" / "defaults" / "main.yml"
TASKS_PATH = REPO_ROOT / "roles" / "vaultwarden_runtime" / "tasks" / "main.yml"
VERIFY_PATH = REPO_ROOT / "roles" / "vaultwarden_runtime" / "tasks" / "verify.yml"
COMPOSE_TEMPLATE = REPO_ROOT / "roles" / "vaultwarden_runtime" / "templates" / "docker-compose.yml.j2"


def load_yaml(path: Path) -> list[dict] | dict:
    return yaml.safe_load(path.read_text())


def test_defaults_use_private_service_topology_and_local_bootstrap_artifacts() -> None:
    defaults = load_yaml(DEFAULTS_PATH)
    assert defaults["vaultwarden_https_port"] == "{{ platform_service_topology | platform_service_port('vaultwarden', 'internal') }}"
    assert defaults["vaultwarden_controller_url"] == "{{ platform_service_topology | platform_service_url('vaultwarden', 'controller') }}"
    assert defaults["vaultwarden_admin_token_local_file"] == "{{ vaultwarden_local_artifact_dir }}/admin-token.txt"
    assert defaults["vaultwarden_admin_token_hash_local_file"] == "{{ vaultwarden_local_artifact_dir }}/admin-token-argon2.txt"


def test_role_generates_hash_with_the_vaultwarden_binary_when_missing() -> None:
    tasks = load_yaml(TASKS_PATH)
    hash_task = next(task for task in tasks if task.get("name") == "Generate the Vaultwarden admin token hash on the runtime host when missing")
    command = hash_task["ansible.builtin.shell"]
    assert "docker run --rm -i" in command
    assert "/vaultwarden hash" in command


def test_compose_template_uses_postgres_tls_and_hashed_admin_token() -> None:
    template = COMPOSE_TEMPLATE.read_text()
    assert "DATABASE_URL: postgresql://" in template
    assert "ADMIN_TOKEN: {{ vaultwarden_admin_token_hash }}" in template
    assert 'ROCKET_TLS: \'{certs="{{ vaultwarden_tls_server_cert_file }}",key="{{ vaultwarden_tls_server_key_file }}"}\'' in template


def test_verify_checks_controller_liveness_and_local_bootstrap_state() -> None:
    verify = load_yaml(VERIFY_PATH)
    controller_task = next(task for task in verify if task.get("name") == "Verify Vaultwarden is reachable through the controller URL")
    bootstrap_stat = next(task for task in verify if task.get("name") == "Assert the Vaultwarden bootstrap state file exists locally")
    assert controller_task["ansible.builtin.uri"]["url"] == "{{ vaultwarden_controller_url }}/alive"
    assert bootstrap_stat["ansible.builtin.stat"]["path"] == "{{ vaultwarden_bootstrap_state_local_file }}"
