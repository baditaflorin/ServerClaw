from pathlib import Path

import json
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK_PATH = REPO_ROOT / "playbooks" / "temporal.yml"
SERVICE_WRAPPER_PATH = REPO_ROOT / "playbooks" / "services" / "temporal.yml"
SECRET_MANIFEST_PATH = REPO_ROOT / "config" / "controller-local-secrets.json"
ANSIBLE_EXECUTION_SCOPES_PATH = REPO_ROOT / "config" / "ansible-execution-scopes.yaml"


def load_yaml(path: Path) -> list[dict] | dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_temporal_playbook_bootstraps_schema_from_localhost_and_deploys_runtime() -> None:
    plays = load_yaml(PLAYBOOK_PATH)

    postgres_play = plays[0]
    runtime_play = plays[1]
    schema_tool_task = next(
        task for task in postgres_play["post_tasks"] if task["name"] == "Ensure Temporal schema bootstrap tools are available on the schema tool host"
    )
    schema_probe_task = next(
        task for task in postgres_play["post_tasks"] if task["name"] == "Check whether the Temporal default schema version table exists"
    )
    connection_headroom_task = next(
        task for task in postgres_play["post_tasks"] if task["name"] == "Check PostgreSQL connection headroom before Temporal schema migrations"
    )
    drain_task = next(
        task
        for task in postgres_play["post_tasks"]
        if task["name"] == "Stop the Temporal runtime before schema migrations when PostgreSQL has no regular connection slots left"
    )
    schema_update_task = next(
        task for task in postgres_play["post_tasks"] if task["name"] == "Apply the Temporal default schema migrations"
    )

    assert [role["role"] for role in postgres_play["roles"]] == [
        "lv3.platform.linux_guest_firewall",
        "lv3.platform.postgres_vm",
        "lv3.platform.temporal_postgres",
    ]
    assert postgres_play["pre_tasks"][0]["vars"]["required_hosts"] == [
        "{{ playbook_execution_required_hosts.postgres[playbook_execution_env] }}",
        "{{ temporal_schema_tool_delegate_host }}",
    ]
    assert postgres_play["vars"]["temporal_controller_database_host"] == "{{ temporal_controller_database_url | urlsplit('hostname') }}"
    assert (
        postgres_play["vars"]["temporal_schema_tool_delegate_host"]
        == "{{ 'docker-runtime-staging-lv3' if (env | default('production')) == 'staging' else 'docker-runtime-lv3' }}"
    )
    assert schema_probe_task["ansible.builtin.command"]["argv"][1:4] == ["-d", "{{ temporal_database_name }}", "-Atqc"]
    assert schema_probe_task["become_user"] == "postgres"
    assert connection_headroom_task["ansible.builtin.command"]["argv"][1:4] == ["-d", "postgres", "-Atqc"]
    assert connection_headroom_task["become_user"] == "postgres"
    assert drain_task["delegate_to"] == "{{ temporal_schema_tool_delegate_host }}"
    assert drain_task["ansible.builtin.command"]["argv"] == [
        "docker",
        "compose",
        "-f",
        "{{ temporal_runtime_compose_file }}",
        "stop",
    ]
    assert schema_tool_task["delegate_to"] == "{{ temporal_schema_tool_delegate_host }}"
    assert schema_update_task["delegate_to"] == "{{ temporal_schema_tool_delegate_host }}"
    assert schema_update_task["ansible.builtin.command"]["argv"][10] == "{{ temporal_database_host }}"
    assert schema_update_task["ansible.builtin.command"]["argv"][12] == "5432"
    assert schema_update_task["ansible.builtin.command"]["argv"][5] == "{{ temporal_admin_tools_image }}"
    assert [role["role"] for role in runtime_play["roles"]] == [
        "lv3.platform.linux_guest_firewall",
        "lv3.platform.docker_runtime",
        "lv3.platform.temporal_runtime",
    ]


def test_temporal_service_wrapper_secret_manifest_and_execution_scopes_register_runtime_inputs() -> None:
    wrapper = load_yaml(SERVICE_WRAPPER_PATH)
    manifest = json.loads(SECRET_MANIFEST_PATH.read_text(encoding="utf-8"))
    scopes = yaml.safe_load(ANSIBLE_EXECUTION_SCOPES_PATH.read_text(encoding="utf-8"))

    assert wrapper == [{"import_playbook": "../temporal.yml"}]
    assert "temporal_database_password" in manifest["secrets"]
    entry = scopes["playbooks"]["playbooks/temporal.yml"]
    assert entry["playbook_id"] == "temporal"
    assert entry["canonical_service_id"] == "temporal"
