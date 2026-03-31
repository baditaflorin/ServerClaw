from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK_PATH = REPO_ROOT / "playbooks" / "services" / "guest-log-shipping.yml"
COLLECTION_PLAYBOOK_PATH = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "playbooks"
    / "services"
    / "guest-log-shipping.yml"
)
PROXMOX_HOST_VARS_PATH = REPO_ROOT / "inventory" / "host_vars" / "proxmox_florin.yml"


def load_yaml(path: Path) -> list[dict] | dict:
    return yaml.safe_load(path.read_text())


def assert_guest_log_shipping_lane_map(path: Path) -> None:
    playbook = load_yaml(path)
    pre_tasks = playbook[0]["pre_tasks"]
    derive_task = next(task for task in pre_tasks if task.get("name") == "Derive guest log shipping role and lane")
    lane_expression = derive_task["ansible.builtin.set_fact"]["monitoring_stack_guest_lane"]

    for role in (
        "nginx",
        "docker-runtime",
        "docker-build",
        "artifact-cache",
        "monitoring",
        "postgres",
        "postgres-replica",
        "artifact-cache",
        "backup",
        "coolify",
    ):
        assert f"'{role}':" in lane_expression


def test_guest_log_shipping_lane_map_covers_all_production_guest_roles() -> None:
    assert_guest_log_shipping_lane_map(PLAYBOOK_PATH)
    assert_guest_log_shipping_lane_map(COLLECTION_PLAYBOOK_PATH)

    platform_vars = load_yaml(PROXMOX_HOST_VARS_PATH)
    production_roles = {
        guest["role"]
        for guest in platform_vars["proxmox_guests"]
        if guest["name"].endswith("-lv3")
    }
    assert production_roles <= {
        "nginx",
        "docker-runtime",
        "docker-build",
        "artifact-cache",
        "monitoring",
        "postgres",
        "postgres-replica",
        "artifact-cache",
        "backup",
        "coolify",
    }


<<<<<<< HEAD
def test_guest_log_shipping_enables_postgres_audit_pipeline_from_repo_catalog() -> None:
    playbook = load_yaml(PLAYBOOK_PATH)
    role_vars = playbook[0]["roles"][0]["vars"]

    assert role_vars["loki_log_agent_postgres_audit_enabled"] == (
        "{{ monitoring_stack_guest_role == 'postgres' and inventory_hostname == 'postgres-lv3' }}"
    )
    assert "config/pgaudit/approved-roles.yaml" in role_vars["loki_log_agent_postgres_audit_approved_roles"]
    assert "ansible_host ~ ':12345'" in role_vars["loki_log_agent_http_listen_address"]


def test_guest_log_shipping_verifies_postgres_audit_scrape_after_guest_converge() -> None:
    playbook = load_yaml(PLAYBOOK_PATH)
    verify_play = playbook[1]
    assert verify_play["vars"]["monitoring_stack_postgres_audit_host"] == (
        "{{ 'postgres-staging-lv3' if (env | default('production')) == 'staging' else 'postgres-lv3' }}"
    )
    verify_task = next(
        task
        for task in verify_play["tasks"]
        if task.get("name") == "Verify Prometheus scrapes the PostgreSQL audit Alloy target after guest log shipping"
    )

    assert verify_play["hosts"] == (
        "{{ 'monitoring-staging-lv3' if (env | default('production')) == 'staging' else 'monitoring-lv3' }}"
    )
    assert verify_play["vars"]["monitoring_stack_postgres_audit_metrics_job_name"] == "postgres-audit-alloy"
    assert "monitoring_stack_postgres_audit_host" in verify_play["vars"]["monitoring_stack_postgres_audit_metrics_target"]
    assert '\\"' not in verify_task["ansible.builtin.uri"]["url"]
    assert "monitoring_stack_postgres_audit_metrics_target" in verify_task["failed_when"]

    seed_task = next(
        task
        for task in verify_play["tasks"]
        if task.get("name") == "Seed deterministic PostgreSQL audit lines after guest log shipping"
    )
    assert seed_task["delegate_to"] == "{{ monitoring_stack_postgres_audit_host }}"
    assert seed_task["become_user"] == "postgres"
    assert "CREATE ROLE {{ monitoring_stack_postgres_audit_metrics_probe_role }} NOLOGIN" in seed_task["ansible.builtin.command"]["argv"][-1]

    endpoint_task = next(
        task
        for task in verify_play["tasks"]
        if task.get("name")
        == "Verify the PostgreSQL audit Alloy endpoint exposes the expected metric families after guest log shipping"
    )
    command_argv = endpoint_task["ansible.builtin.command"]["argv"]
    command_script = command_argv[-1]

    assert command_argv[0] == "python3"
    assert endpoint_task["delegate_to"] == "{{ monitoring_stack_postgres_audit_host }}"
    assert "http://{{ monitoring_stack_postgres_audit_metrics_target }}/metrics" in command_script
    assert "# HELP loki_process_custom_postgres_audit_events_total " in command_script
    assert "# HELP loki_process_custom_postgres_connection_authorized_total " in command_script
    assert "loki_process_custom_postgres_unknown_connection_events_total" not in command_script
    assert endpoint_task["until"] == "monitoring_stack_verify_postgres_audit_metrics_endpoint.rc == 0"
    assert endpoint_task["failed_when"] == "monitoring_stack_verify_postgres_audit_metrics_endpoint.rc != 0"
=======
def test_guest_log_shipping_enables_postgres_audit_pipeline_from_repo_catalog() -> None:
    playbook = load_yaml(PLAYBOOK_PATH)
    role_vars = playbook[0]["roles"][0]["vars"]

    assert role_vars["loki_log_agent_postgres_audit_enabled"] == (
        "{{ monitoring_stack_guest_role == 'postgres' and inventory_hostname == 'postgres-lv3' }}"
    )
    assert "config/pgaudit/approved-roles.yaml" in role_vars["loki_log_agent_postgres_audit_approved_roles"]
    assert "ansible_host ~ ':12345'" in role_vars["loki_log_agent_http_listen_address"]


def test_guest_log_shipping_verifies_postgres_audit_scrape_after_guest_converge() -> None:
    playbook = load_yaml(PLAYBOOK_PATH)
    verify_play = playbook[1]
    assert verify_play["vars"]["monitoring_stack_postgres_audit_host"] == (
        "{{ 'postgres-staging-lv3' if (env | default('production')) == 'staging' else 'postgres-lv3' }}"
    )
    verify_task = next(
        task
        for task in verify_play["tasks"]
        if task.get("name") == "Verify Prometheus scrapes the PostgreSQL audit Alloy target after guest log shipping"
    )

    assert verify_play["hosts"] == (
        "{{ 'monitoring-staging-lv3' if (env | default('production')) == 'staging' else 'monitoring-lv3' }}"
    )
    assert verify_play["vars"]["monitoring_stack_postgres_audit_metrics_job_name"] == "postgres-audit-alloy"
    assert "monitoring_stack_postgres_audit_host" in verify_play["vars"]["monitoring_stack_postgres_audit_metrics_target"]
    assert '\\"' not in verify_task["ansible.builtin.uri"]["url"]
    assert "monitoring_stack_postgres_audit_metrics_target" in verify_task["failed_when"]

    seed_task = next(
        task
        for task in verify_play["tasks"]
        if task.get("name") == "Seed deterministic PostgreSQL audit lines after guest log shipping"
    )
    assert seed_task["delegate_to"] == "{{ monitoring_stack_postgres_audit_host }}"
    assert seed_task["become_user"] == "postgres"
    assert (
        "CREATE ROLE {{ monitoring_stack_postgres_audit_metrics_probe_role }} NOLOGIN"
        in seed_task["ansible.builtin.command"]["argv"][-1]
    )

    endpoint_task = next(
        task
        for task in verify_play["tasks"]
        if task.get("name")
        == "Verify the PostgreSQL audit Alloy endpoint exposes the expected metric families after guest log shipping"
    )
    command_argv = endpoint_task["ansible.builtin.command"]["argv"]
    command_script = command_argv[-1]

    assert command_argv[0] == "python3"
    assert endpoint_task["delegate_to"] == "{{ monitoring_stack_postgres_audit_host }}"
    assert "http://{{ monitoring_stack_postgres_audit_metrics_target }}/metrics" in command_script
    assert "# HELP loki_process_custom_postgres_audit_events_total " in command_script
    assert "# HELP loki_process_custom_postgres_connection_authorized_total " in command_script
    assert "loki_process_custom_postgres_unknown_connection_events_total" not in command_script
    assert endpoint_task["until"] == "monitoring_stack_verify_postgres_audit_metrics_endpoint.rc == 0"
    assert endpoint_task["failed_when"] == "monitoring_stack_verify_postgres_audit_metrics_endpoint.rc != 0"


def test_openbao_audit_scrape_does_not_manage_service_owned_paths() -> None:
    playbook = load_yaml(PLAYBOOK_PATH)
    role_vars = playbook[0]["roles"][0]["vars"]
    file_scrapes_expression = role_vars["loki_log_agent_file_scrapes"]

    assert "'name': 'openbao_audit'" in file_scrapes_expression
    assert "'manage_paths': false" in file_scrapes_expression
>>>>>>> ae8e2d665 ([loki] Stop clobbering OpenBao audit paths during log shipping)
