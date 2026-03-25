from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_TASKS = REPO_ROOT / "roles" / "n8n_runtime" / "tasks" / "main.yml"
ROLE_DEFAULTS = REPO_ROOT / "roles" / "n8n_runtime" / "defaults" / "main.yml"
COMPOSE_TEMPLATE = REPO_ROOT / "roles" / "n8n_runtime" / "templates" / "docker-compose.yml.j2"
ENV_TEMPLATE = REPO_ROOT / "roles" / "n8n_runtime" / "templates" / "n8n.env.ctmpl.j2"
POSTGRES_TASKS = REPO_ROOT / "roles" / "n8n_postgres" / "tasks" / "main.yml"


def load_tasks(path: Path) -> list[dict]:
    return yaml.safe_load(path.read_text())


def test_runtime_defaults_pin_public_hostname_and_local_artifacts() -> None:
    defaults = yaml.safe_load(ROLE_DEFAULTS.read_text())
    assert defaults["n8n_port"] == "{{ platform_service_topology | platform_service_port('n8n', 'internal') }}"
    assert defaults["n8n_owner_password_local_file"].endswith("/.local/n8n/owner-password.txt")
    assert defaults["n8n_encryption_key_local_file"].endswith("/.local/n8n/encryption-key.txt")
    assert defaults["n8n_enable_public_api"] is True


def test_runtime_bootstraps_owner_through_rest_endpoint() -> None:
    tasks = load_tasks(ROLE_TASKS)
    owner_setup = next(task for task in tasks if task.get("name") == "Bootstrap the n8n owner account when needed")
    owner_login = next(task for task in tasks if task.get("name") == "Verify n8n owner sign-in works")
    assert owner_setup["ansible.builtin.uri"]["url"] == "{{ n8n_internal_base_url }}/rest/owner/setup"
    assert owner_login["ansible.builtin.uri"]["url"] == "{{ n8n_internal_base_url }}/rest/login"
    assert owner_login["ansible.builtin.uri"]["body"]["emailOrLdapLoginId"] == "{{ n8n_owner_email }}"


def test_runtime_uses_openbao_secret_injection_for_database_password_and_encryption_key() -> None:
    template = ENV_TEMPLATE.read_text()
    assert 'kv/data/{{ n8n_openbao_secret_path }}' in template
    assert "DB_POSTGRESDB_PASSWORD" in template
    assert "N8N_ENCRYPTION_KEY" in template


def test_compose_template_exposes_n8n_port_and_data_volume() -> None:
    template = COMPOSE_TEMPLATE.read_text()
    assert '"{{ n8n_port }}:5678"' in template
    assert "{{ n8n_data_dir }}:/home/node/.n8n" in template


def test_postgres_role_provisions_named_database_and_role() -> None:
    tasks = load_tasks(POSTGRES_TASKS)
    create_role = next(task for task in tasks if task.get("name") == "Create the n8n database role")
    create_db = next(task for task in tasks if task.get("name") == "Create the n8n PostgreSQL database")
    assert "CREATE ROLE {{ n8n_database_user }} LOGIN PASSWORD" in create_role["ansible.builtin.command"]["argv"][-1]
    assert create_db["ansible.builtin.command"]["argv"][-1] == "CREATE DATABASE {{ n8n_database_name }} OWNER {{ n8n_database_user }}"


def test_host_network_policy_allows_edge_and_private_n8n_access() -> None:
    host_vars = yaml.safe_load((REPO_ROOT / "inventory" / "host_vars" / "proxmox_florin.yml").read_text())
    docker_runtime_rules = host_vars["network_policy"]["guests"]["docker-runtime-lv3"]["allowed_inbound"]
    nginx_rule = next(rule for rule in docker_runtime_rules if rule["source"] == "nginx-lv3" and 5678 in rule["ports"])
    guest_rule = next(rule for rule in docker_runtime_rules if rule["source"] == "all_guests" and 5678 in rule["ports"])
    assert nginx_rule["description"].lower().startswith("reverse proxy access")
    assert guest_rule["description"].lower().startswith("private guest-to-guest")
