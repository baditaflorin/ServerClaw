from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULTS_PATH = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "temporal_runtime"
    / "defaults"
    / "main.yml"
)
TASKS_PATH = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "temporal_runtime"
    / "tasks"
    / "main.yml"
)
VERIFY_PATH = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "temporal_runtime"
    / "tasks"
    / "verify.yml"
)
COMPOSE_TEMPLATE_PATH = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "temporal_runtime"
    / "templates"
    / "docker-compose.yml.j2"
)
ENV_TEMPLATE_PATH = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "temporal_runtime"
    / "templates"
    / "temporal.env.ctmpl.j2"
)
CONFIG_TEMPLATE_PATH = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "temporal_runtime"
    / "templates"
    / "server-config.yml.j2"
)


def load_tasks() -> list[dict]:
    return yaml.safe_load(TASKS_PATH.read_text(encoding="utf-8"))


def test_temporal_runtime_defaults_use_loopback_ports_and_private_namespace() -> None:
    defaults = yaml.safe_load(DEFAULTS_PATH.read_text(encoding="utf-8"))

    assert defaults["temporal_server_image"] == "{{ container_image_catalog.images.temporal_server_runtime.ref }}"
    assert defaults["temporal_admin_tools_image"] == "{{ container_image_catalog.images.temporal_admin_tools_runtime.ref }}"
    assert defaults["temporal_ui_image"] == "{{ container_image_catalog.images.temporal_ui_runtime.ref }}"
    assert defaults["temporal_frontend_bind_host"] == "127.0.0.1"
    assert defaults["temporal_frontend_grpc_port"] == 7233
    assert defaults["temporal_frontend_http_port"] == 7243
    assert defaults["temporal_ui_port"] == 8099
    assert defaults["temporal_default_namespace"] == "lv3"
    assert defaults["temporal_default_namespace_retention"] == "168h"
    assert defaults["temporal_default_store_max_conns"] == 5
    assert defaults["temporal_visibility_store_max_conns"] == 3


def test_temporal_runtime_bootstraps_openbao_env_and_namespace() -> None:
    tasks = load_tasks()

    secret_payload_task = next(task for task in tasks if task.get("name") == "Record the Temporal runtime secrets")
    openbao_helper = next(task for task in tasks if task.get("name") == "Prepare OpenBao agent runtime secret injection for Temporal")
    pull_task = next(task for task in tasks if task.get("name") == "Pull the Temporal compose images")
    recreate_flag_task = next(task for task in tasks if task.get("name") == "Record whether the Temporal runtime stack must be recreated")
    openbao_agent_up_task = next(task for task in tasks if task.get("name") == "Start the Temporal OpenBao agent")
    runtime_env_wait_task = next(task for task in tasks if task.get("name") == "Wait for the Temporal runtime env file")
    force_recreate_up_task = next(
        task for task in tasks if task.get("name") == "Converge the Temporal runtime stack with forced recreation when rendered inputs changed"
    )
    up_task = next(
        task
        for task in tasks
        if task.get("name") == "Converge the Temporal runtime stack" and "when" in task and "temporal_runtime_force_recreate" in task["when"]
    )
    cluster_ready_task = next(
        task for task in tasks if task.get("name") == "Wait for the Temporal cluster to become ready for namespace administration"
    )
    namespace_check_task = next(task for task in tasks if task.get("name") == "Check whether the Temporal namespace already exists")
    namespace_create_task = next(task for task in tasks if task.get("name") == "Create the repo-managed Temporal namespace when missing")
    namespace_update_task = next(task for task in tasks if task.get("name") == "Reconcile the Temporal namespace retention window")
    namespace_report_task = next(task for task in tasks if task.get("name") == "Mirror the Temporal namespace report to the control machine")

    runtime_secret_payload = secret_payload_task["ansible.builtin.set_fact"]["temporal_runtime_secret_payload"]
    assert runtime_secret_payload["TEMPORAL_DB_PASSWORD"] == "{{ lookup('ansible.builtin.file', temporal_database_password_local_file) | trim }}"
    assert openbao_helper["ansible.builtin.include_role"]["name"] == "lv3.platform.common"
    assert openbao_helper["ansible.builtin.include_role"]["tasks_from"] == "openbao_compose_env"
    assert pull_task["ansible.builtin.command"]["argv"][:4] == ["docker", "compose", "--profile", "tools"]
    assert "temporal_pull.changed" in recreate_flag_task["ansible.builtin.set_fact"]["temporal_runtime_force_recreate"]
    assert openbao_agent_up_task["ansible.builtin.command"]["argv"][-3:] == ["up", "-d", "openbao-agent"]
    assert "TEMPORAL_DB_PASSWORD" in runtime_env_wait_task["ansible.builtin.shell"]
    assert "--force-recreate" in force_recreate_up_task["ansible.builtin.command"]["argv"]
    assert force_recreate_up_task["ansible.builtin.command"]["argv"][-2:] == ["--force-recreate", "--remove-orphans"]
    assert up_task["ansible.builtin.command"]["argv"][-2:] == ["-d", "--remove-orphans"]
    assert cluster_ready_task["ansible.builtin.command"]["argv"][-3:] == ["operator", "cluster", "health"]
    assert namespace_check_task["ansible.builtin.command"]["argv"][-4:] == [
        "namespace",
        "describe",
        "--namespace",
        "{{ temporal_default_namespace }}",
    ]
    assert "--retention" in namespace_create_task["ansible.builtin.command"]["argv"]
    assert namespace_update_task["changed_when"] is False
    assert namespace_report_task["delegate_to"] == "localhost"


def test_temporal_verify_task_checks_ui_cluster_health_and_namespace() -> None:
    tasks = yaml.safe_load(VERIFY_PATH.read_text(encoding="utf-8"))

    ui_task = next(task for task in tasks if task.get("name") == "Verify the Temporal UI responds on the loopback diagnostic endpoint")
    cluster_task = next(task for task in tasks if task.get("name") == "Verify Temporal cluster health through the repo-managed admin-tools profile")
    namespace_task = next(task for task in tasks if task.get("name") == "Verify the repo-managed Temporal namespace exists")
    assert_task = next(task for task in tasks if task.get("name") == "Assert Temporal UI, cluster health, and namespace verification are working")

    assert ui_task["ansible.builtin.uri"]["url"] == "http://127.0.0.1:{{ temporal_ui_port }}"
    assert cluster_task["ansible.builtin.command"]["argv"][-3:] == ["operator", "cluster", "health"]
    assert namespace_task["ansible.builtin.command"]["argv"][-4:] == [
        "namespace",
        "describe",
        "--namespace",
        "{{ temporal_default_namespace }}",
    ]
    assert "temporal_default_namespace in temporal_verify_namespace.stdout" in assert_task["ansible.builtin.assert"]["that"]


def test_temporal_compose_and_config_templates_use_loopback_publication_and_password_placeholder() -> None:
    compose_template = COMPOSE_TEMPLATE_PATH.read_text(encoding="utf-8")
    env_template = ENV_TEMPLATE_PATH.read_text(encoding="utf-8")
    config_template = CONFIG_TEMPLATE_PATH.read_text(encoding="utf-8")

    assert "  openbao-agent:" in compose_template
    assert '      - "{{ temporal_frontend_bind_host }}:{{ temporal_frontend_grpc_port }}:{{ temporal_frontend_grpc_port }}"' in compose_template
    assert '      - "{{ temporal_ui_bind_host }}:{{ temporal_ui_port }}:{{ temporal_ui_container_port }}"' in compose_template
    assert "profiles:" in compose_template
    assert "temporal-admin-tools" in compose_template
    assert "/etc/temporal/config/history.yml.tpl" in compose_template
    assert "temporal-server --config-file /tmp/temporal-history.yml start --service=history" in compose_template
    assert "temporal-server --config-file /tmp/temporal-matching.yml start --service=matching" in compose_template
    assert "temporal-server --config-file /tmp/temporal-frontend.yml start --service=frontend" in compose_template
    assert "temporal-server --config-file /tmp/temporal-worker.yml start --service=worker" in compose_template
    assert '__TEMPORAL_DB_PASSWORD__' in compose_template
    assert 'TEMPORAL_DB_PASSWORD=[[ with secret "kv/data/{{ temporal_openbao_secret_path }}" ]]' in env_template
    assert '[[ .Data.data.TEMPORAL_DB_PASSWORD ]]' in env_template
    assert 'password: "__TEMPORAL_DB_PASSWORD__"' in config_template
    assert "maxConns: {{ temporal_default_store_max_conns }}" in config_template
    assert "maxConns: {{ temporal_visibility_store_max_conns }}" in config_template
    assert 'rpcAddress: "{{ temporal_public_frontend_address }}"' in config_template
    assert 'broadcastAddress: "__TEMPORAL_BROADCAST_ADDRESS__"' in config_template
    assert "TEMPORAL_BROADCAST_ADDRESS=$$(hostname -i | awk '{print $$1}')" in compose_template
    assert '__TEMPORAL_BROADCAST_ADDRESS__' in compose_template
    assert "namespaceDefaults:" not in config_template
