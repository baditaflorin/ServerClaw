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
        "{{ hostvars['proxmox-host'].platform_service_topology | platform_service_url('grafana', 'loki_push') }}"
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
    stat_task = next(
        task for task in tasks if task.get("name") == "Check whether extra file-scrape targets already exist"
    )
    create_task = next(task for task in tasks if task.get("name") == "Ensure missing extra file-scrape targets exist")
    env_task = next(task for task in tasks if task.get("name") == "Render Alloy environment file")
    resolve_task = next(task for task in tasks if task.get("name") == "Resolve managed extra file-scrape targets")

    resolved_paths = resolve_task["ansible.builtin.set_fact"]["loki_log_agent_managed_file_scrape_paths"]

    assert "selectattr('manage_paths', 'undefined')" in resolved_paths
    assert "rejectattr('manage_paths', 'equalto', false)" in resolved_paths
    assert stat_task["ansible.builtin.stat"]["path"] == "{{ item }}"
    assert stat_task["register"] == "loki_log_agent_file_scrape_target_stats"
    assert stat_task["loop"] == "{{ loki_log_agent_managed_file_scrape_paths }}"
    assert create_task["ansible.builtin.file"]["path"] == "{{ item.stat.path | default(item.item) }}"
    assert create_task["loop"] == "{{ loki_log_agent_file_scrape_target_stats.results }}"
    assert create_task["when"] == [
        "loki_log_agent_file_scrapes | length > 0",
        "loki_log_agent_managed_file_scrape_paths | length > 0",
        "not item.stat.exists",
    ]
    assert env_task["ansible.builtin.copy"]["dest"] == "{{ loki_log_agent_env_file }}"
    assert (
        "--server.http.listen-addr={{ loki_log_agent_http_listen_address }}"
        in env_task["ansible.builtin.copy"]["content"]
    )


def test_template_includes_postgres_audit_labels_and_metrics_pipeline() -> None:
    template = (ROLE_ROOT / "templates" / "config.alloy.j2").read_text()

    assert template.count("{% set approved_roles_pattern") == 1
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


def test_template_relabels_falco_journal_entries_by_syslog_identifier() -> None:
    template = (ROLE_ROOT / "templates" / "config.alloy.j2").read_text()

    assert 'source_labels = ["__journal_syslog_identifier"]' in template
    assert 'regex         = "falco"' in template
    assert 'target_label  = "job"' in template
    assert 'target_label  = "service"' in template
