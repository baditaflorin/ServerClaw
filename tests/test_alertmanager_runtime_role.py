from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_ROOT = REPO_ROOT / "collections" / "ansible_collections" / "lv3" / "platform" / "roles" / "alertmanager_runtime"
DEFAULTS_PATH = ROLE_ROOT / "defaults" / "main.yml"
TASKS_PATH = ROLE_ROOT / "tasks" / "main.yml"
VERIFY_PATH = ROLE_ROOT / "tasks" / "verify.yml"
ALERTMANAGER_CONFIG_PATH = REPO_ROOT / "config" / "alertmanager" / "alertmanager.yml"
ALERT_RULES_PATH = REPO_ROOT / "config" / "alertmanager" / "rules" / "platform.yml"
ALERTMANAGER_ENV_TEMPLATE = ROLE_ROOT / "templates" / "prometheus-alertmanager.env.j2"
RELAY_ENV_TEMPLATE = ROLE_ROOT / "templates" / "pgaudit-alert-relay.env.j2"
RELAY_SERVICE_TEMPLATE = ROLE_ROOT / "templates" / "pgaudit-alert-relay.service.j2"
RELAY_SCRIPT_TEMPLATE = ROLE_ROOT / "templates" / "pgaudit-alert-relay.py.j2"


def load_yaml(path: Path) -> list[dict] | dict:
    return yaml.safe_load(path.read_text())


def test_alertmanager_runtime_defaults_define_pgaudit_relay_contract() -> None:
    defaults = load_yaml(DEFAULTS_PATH)

    assert defaults["alertmanager_runtime_env_file"] == "/etc/default/prometheus-alertmanager"
    assert defaults["alertmanager_runtime_pgaudit_relay_enabled"] is True
    assert defaults["alertmanager_runtime_pgaudit_relay_service_name"] == "pgaudit-alert-relay"
    assert defaults["alertmanager_runtime_pgaudit_relay_nats_subject"] == "platform.security.pgaudit_unknown_role"
    assert "/.local/nats/jetstream-admin-password.txt" in defaults["alertmanager_runtime_pgaudit_relay_nats_password_local_file"]


def test_alertmanager_runtime_tasks_render_and_start_pgaudit_relay() -> None:
    tasks = load_yaml(TASKS_PATH)

    alertmanager_env_task = next(
        task for task in tasks if task.get("name") == "Render Alertmanager package environment file"
    )
    env_task = next(task for task in tasks if task.get("name") == "Render pgaudit alert relay environment file")
    script_task = next(task for task in tasks if task.get("name") == "Render pgaudit alert relay script")
    service_task = next(task for task in tasks if task.get("name") == "Render pgaudit alert relay systemd service")
    start_task = next(task for task in tasks if task.get("name") == "Enable and start pgaudit alert relay")

    assert alertmanager_env_task["ansible.builtin.template"]["src"] == "prometheus-alertmanager.env.j2"
    assert alertmanager_env_task["ansible.builtin.template"]["dest"] == "{{ alertmanager_runtime_env_file }}"
    assert env_task["ansible.builtin.template"]["src"] == "pgaudit-alert-relay.env.j2"
    assert script_task["ansible.builtin.template"]["src"] == "pgaudit-alert-relay.py.j2"
    assert service_task["ansible.builtin.template"]["src"] == "pgaudit-alert-relay.service.j2"
    assert start_task["ansible.builtin.systemd"]["name"] == "{{ alertmanager_runtime_pgaudit_relay_service_name }}"


def test_alertmanager_config_routes_unknown_role_alerts_into_the_relay() -> None:
    config = ALERTMANAGER_CONFIG_PATH.read_text()

    assert 'alertname="PostgresUnknownRoleConnection"' in config
    assert "receiver: pgaudit-unknown-role-relay" in config
    assert "url: \"{{ alertmanager_runtime_pgaudit_relay_webhook_url }}\"" in config
    assert "send_resolved: false" in config


def test_platform_alert_rules_cover_postgres_audit_anomalies() -> None:
    rules = ALERT_RULES_PATH.read_text()

    assert "name: postgres-audit" in rules
    assert "alert: PostgresPrivilegeChangeBurst" in rules
    assert "alert: PostgresUnknownRoleConnection" in rules
    assert "increase(postgres_unknown_connection_events_total" in rules
    assert "postgres_unknown_connection_events_total{job=\"postgres-audit-alloy\",component=\"pgaudit\"} offset 5m" in rules
    assert "unless" in rules


def test_alertmanager_runtime_verifies_loki_canary_rules_after_rule_copy() -> None:
    verify_tasks = load_yaml(VERIFY_PATH)
    verify_task = next(
        task for task in verify_tasks if task.get("name") == "Verify Prometheus Loki Canary rules are loaded"
    )

    assert verify_task["ansible.builtin.uri"]["url"] == "http://127.0.0.1:9090/api/v1/rules"
    assert "lv3-log-canary" in verify_task["failed_when"]
    assert "LokiCanaryTargetDown" in verify_task["failed_when"]


def test_alertmanager_runtime_verifies_pgaudit_relay_health_and_rules() -> None:
    verify_tasks = load_yaml(VERIFY_PATH)
    relay_health_task = next(
        task for task in verify_tasks if task.get("name") == "Verify pgaudit alert relay health endpoint responds"
    )
    loaded_config_task = next(
        task
        for task in verify_tasks
        if task.get("name") == "Verify the loaded Alertmanager config includes the pgaudit relay route"
    )
    verify_task = next(
        task for task in verify_tasks if task.get("name") == "Verify Prometheus PostgreSQL audit rules are loaded"
    )

    assert relay_health_task["ansible.builtin.uri"]["url"] == "{{ alertmanager_runtime_pgaudit_relay_health_url }}"
    assert loaded_config_task["ansible.builtin.uri"]["url"] == "{{ alertmanager_runtime_url }}/api/v2/status"
    assert "pgaudit-unknown-role-relay" in loaded_config_task["failed_when"]
    assert "PostgresUnknownRoleConnection" in loaded_config_task["failed_when"]
    assert verify_task["ansible.builtin.uri"]["url"] == "http://127.0.0.1:9090/api/v1/rules"
    assert "PostgresPrivilegeChangeBurst" in verify_task["failed_when"]
    assert "PostgresUnknownRoleConnection" in verify_task["failed_when"]


def test_alertmanager_package_env_template_pins_repo_managed_runtime_flags() -> None:
    env_template = ALERTMANAGER_ENV_TEMPLATE.read_text()

    assert "--config.file={{ alertmanager_runtime_config_file }}" in env_template
    assert "--storage.path={{ alertmanager_runtime_data_dir }}" in env_template
    assert "--web.listen-address=127.0.0.1:{{ alertmanager_runtime_port }}" in env_template


def test_pgaudit_relay_templates_pin_local_listener_and_nats_publication_subject() -> None:
    env_template = RELAY_ENV_TEMPLATE.read_text()
    service_template = RELAY_SERVICE_TEMPLATE.read_text()
    script_template = RELAY_SCRIPT_TEMPLATE.read_text()

    assert "PGAUDIT_RELAY_NATS_SUBJECT={{ alertmanager_runtime_pgaudit_relay_nats_subject }}" in env_template
    assert "ExecStart=/usr/bin/python3 {{ alertmanager_runtime_pgaudit_relay_script_file }}" in service_template
    assert 'NATS_SUBJECT = env("PGAUDIT_RELAY_NATS_SUBJECT", "platform.security.pgaudit_unknown_role")' in script_template
    assert 'if self.path != "/healthz":' in script_template
