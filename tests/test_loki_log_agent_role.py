from pathlib import Path
import re

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_ROOT = REPO_ROOT / "collections" / "ansible_collections" / "lv3" / "platform" / "roles" / "loki_log_agent"
DEFAULTS_PATH = ROLE_ROOT / "defaults" / "main.yml"
TASKS_PATH = ROLE_ROOT / "tasks" / "main.yml"


def load_yaml(path: Path) -> list[dict] | dict:
    return yaml.safe_load(path.read_text())


def test_defaults_use_proxmox_host_service_topology_for_loki_push_url() -> None:
    defaults = load_yaml(DEFAULTS_PATH)

    assert defaults["loki_log_agent_loki_push_url"] == (
        "{{ hostvars['proxmox_florin'].platform_service_topology | platform_service_url('grafana', 'loki_push') }}"
    )


def test_validate_task_requires_the_resolved_loki_push_url() -> None:
    tasks = load_yaml(TASKS_PATH)
    validate_task = next(task for task in tasks if task.get("name") == "Validate Loki log agent inputs")

    assert "loki_log_agent_loki_push_url | length > 0" in validate_task["ansible.builtin.assert"]["that"]
    assert "loki_log_agent_http_listen_address | length > 0" in validate_task["ansible.builtin.assert"]["that"]


def test_defaults_define_managed_alloy_env_and_postgres_audit_pipeline_inputs() -> None:
    defaults = load_yaml(DEFAULTS_PATH)

    assert defaults["loki_log_agent_env_file"] == "/etc/default/alloy"
    assert defaults["loki_log_agent_http_listen_address"] == "127.0.0.1:12345"
    assert defaults["loki_log_agent_postgres_audit_paths"] == ["/var/log/postgresql/postgresql-*-main.log"]


def test_tasks_manage_alloy_env_file_and_skip_glob_touch_targets() -> None:
    tasks = load_yaml(TASKS_PATH)
    touch_task = next(task for task in tasks if task.get("name") == "Ensure extra file-scrape targets exist")
    env_task = next(task for task in tasks if task.get("name") == "Render Alloy environment file")

    assert "reject('search', '[*?\\\\[]')" in touch_task["loop"]
    assert env_task["ansible.builtin.copy"]["dest"] == "{{ loki_log_agent_env_file }}"
    assert "--server.http.listen-addr={{ loki_log_agent_http_listen_address }}" in env_task["ansible.builtin.copy"]["content"]


def test_template_includes_postgres_audit_labels_and_metrics_pipeline() -> None:
    template = (ROLE_ROOT / "templates" / "config.alloy.j2").read_text()

    assert template.count('{% set approved_roles_pattern') == 1
    assert template.count('loki.process "postgres_audit"') == 1
    assert 'loki.process "postgres_audit"' in template
    assert 'job          = "postgres-audit"' in template
    assert 'name              = "postgres_audit_events_total"' in template
    assert 'name              = "postgres_unknown_connection_events_total"' in template
    assert re.search(
        r'loki\.source\.file "postgres_audit" \{[\s\S]*?forward_to = \[loki\.process\.postgres_audit\.receiver\]\n'
        r"  file_match \{\n"
        r"    enabled = true\n"
        r"  \}\n"
        r"\}",
        template,
    )
