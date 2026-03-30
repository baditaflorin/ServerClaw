from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULTS_PATH = REPO_ROOT / "roles" / "plausible_runtime" / "defaults" / "main.yml"
TASKS_PATH = REPO_ROOT / "roles" / "plausible_runtime" / "tasks" / "main.yml"
VERIFY_PATH = REPO_ROOT / "roles" / "plausible_runtime" / "tasks" / "verify.yml"
COMPOSE_TEMPLATE_PATH = REPO_ROOT / "roles" / "plausible_runtime" / "templates" / "docker-compose.yml.j2"
ENV_TEMPLATE_PATH = REPO_ROOT / "roles" / "plausible_runtime" / "templates" / "plausible.env.j2"
CTMPL_TEMPLATE_PATH = REPO_ROOT / "roles" / "plausible_runtime" / "templates" / "plausible.env.ctmpl.j2"
BOOTSTRAP_TEMPLATE_PATH = REPO_ROOT / "roles" / "plausible_runtime" / "templates" / "bootstrap.eval.j2"
VERIFY_TEMPLATE_PATH = REPO_ROOT / "roles" / "plausible_runtime" / "templates" / "verify.eval.j2"
EVENT_CHECK_TEMPLATE_PATH = REPO_ROOT / "roles" / "plausible_runtime" / "templates" / "event-check.eval.j2"


def load_tasks(path: Path) -> list[dict]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_plausible_runtime_defaults_reference_service_topology_images_and_local_secrets() -> None:
    defaults = yaml.safe_load(DEFAULTS_PATH.read_text(encoding="utf-8"))

    assert defaults["plausible_service_topology"] == "{{ hostvars['proxmox_florin'].lv3_service_topology | service_topology_get('plausible') }}"
    assert defaults["plausible_internal_port"] == "{{ platform_service_topology | platform_service_port('plausible', 'internal') }}"
    assert defaults["plausible_internal_base_url"] == "{{ platform_service_topology | platform_service_url('plausible', 'internal') }}"
    assert defaults["plausible_public_base_url"] == "https://{{ plausible_service_topology.public_hostname }}"
    assert defaults["plausible_runtime_image"] == "{{ container_image_catalog.images.plausible_runtime.ref }}"
    assert defaults["plausible_postgres_image"] == "{{ container_image_catalog.images.plausible_postgres_runtime.ref }}"
    assert defaults["plausible_clickhouse_image"] == "{{ container_image_catalog.images.plausible_clickhouse_runtime.ref }}"
    assert defaults["plausible_database_password_local_file"].endswith("/.local/plausible/database-password.txt")
    assert defaults["plausible_secret_key_base_local_file"].endswith("/.local/plausible/secret-key-base.txt")
    assert defaults["plausible_bootstrap_user_password_local_file"].endswith("/.local/plausible/bootstrap-user-password.txt")
    assert defaults["plausible_mailbox_password_local_file"] == "{{ mail_platform_mailbox_password_local_file }}"
    assert defaults["plausible_site_registrations"] == "{{ hostvars['proxmox_florin'].plausible_site_registrations | default([]) }}"


def test_plausible_runtime_tasks_manage_openbao_compose_and_port_recovery() -> None:
    tasks = load_tasks(TASKS_PATH)

    openbao_helper = next(
        task for task in tasks if task.get("name") == "Prepare OpenBao agent runtime secret injection for Plausible"
    )
    pull_task = next(task for task in tasks if task.get("name") == "Pull the Plausible images")
    up_task = next(task for task in tasks if task.get("name") == "Start the Plausible stack")
    port_check_task = next(
        task for task in tasks if task.get("name") == "Check whether Plausible publishes the expected host port"
    )
    force_recreate_task = next(
        task for task in tasks if task.get("name") == "Force-recreate Plausible when the host port binding is missing"
    )
    bootstrap_task = next(
        task for task in tasks if task.get("name") == "Reconcile the Plausible bootstrap user and site registrations"
    )
    verify_task = next(task for task in tasks if task.get("name") == "Verify the Plausible runtime")

    assert openbao_helper["ansible.builtin.include_role"]["name"] == "lv3.platform.common"
    assert openbao_helper["ansible.builtin.include_role"]["tasks_from"] == "openbao_compose_env"
    assert pull_task["ansible.builtin.command"]["argv"][-1] == "pull"
    assert up_task["ansible.builtin.command"]["argv"][-2:] == ["-d", "--remove-orphans"]
    assert port_check_task["ansible.builtin.command"]["argv"] == [
        "docker",
        "port",
        "{{ plausible_container_name }}",
        "8000/tcp",
    ]
    assert force_recreate_task["ansible.builtin.command"]["argv"][-2:] == ["--force-recreate", "--remove-orphans"]
    assert force_recreate_task["when"] == "plausible_port_binding_check.stdout | trim == \"\""
    assert bootstrap_task["ansible.builtin.command"]["argv"][:4] == ["docker", "exec", "{{ plausible_container_name }}", "bin/plausible"]
    assert verify_task["ansible.builtin.import_tasks"] == "verify.yml"


def test_plausible_verify_task_checks_tracker_and_synthetic_event_ingestion() -> None:
    tasks = load_tasks(VERIFY_PATH)

    tracker_task = next(task for task in tasks if task.get("name") == "Verify the Plausible tracker script responds locally")
    event_task = next(task for task in tasks if task.get("name") == "Post a synthetic Plausible pageview event locally")
    event_check_task = next(
        task for task in tasks if task.get("name") == "Wait for the synthetic Plausible event to reach ClickHouse"
    )

    assert tracker_task["ansible.builtin.uri"]["url"] == "{{ plausible_internal_base_url }}/js/script.js"
    assert event_task["ansible.builtin.uri"]["url"] == "{{ plausible_internal_base_url }}/api/event"
    assert event_task["ansible.builtin.uri"]["body"]["name"] == "pageview"
    assert event_task["ansible.builtin.uri"]["body"]["domain"] == "{{ plausible_verify_site_domain }}"
    assert event_check_task["ansible.builtin.command"]["argv"][:4] == [
        "docker",
        "exec",
        "{{ plausible_container_name }}",
        "bin/plausible",
    ]
    assert event_check_task["until"] == "(plausible_event_check.stdout | trim | from_json).seen"


def test_plausible_runtime_templates_render_public_urls_and_repo_managed_site_checks() -> None:
    compose_template = COMPOSE_TEMPLATE_PATH.read_text(encoding="utf-8")
    env_template = ENV_TEMPLATE_PATH.read_text(encoding="utf-8")
    ctmpl_template = CTMPL_TEMPLATE_PATH.read_text(encoding="utf-8")
    bootstrap_template = BOOTSTRAP_TEMPLATE_PATH.read_text(encoding="utf-8")
    verify_template = VERIFY_TEMPLATE_PATH.read_text(encoding="utf-8")
    event_check_template = EVENT_CHECK_TEMPLATE_PATH.read_text(encoding="utf-8")

    assert "container_name: {{ plausible_container_name }}" in compose_template
    assert '- "{{ ansible_host }}:{{ plausible_internal_port }}:8000"' in compose_template
    assert '- "127.0.0.1:{{ plausible_internal_port }}:8000"' in compose_template
    assert "BASE_URL={{ plausible_public_base_url }}" in env_template
    assert "DATABASE_URL=postgres://{{ plausible_database_user }}:{{ plausible_database_password | urlencode }}@plausible-db:5432/{{ plausible_database_name }}" in env_template
    assert '[[ with secret "kv/data/{{ plausible_openbao_secret_path }}" ]]' in ctmpl_template
    assert "Teams.get_or_create(user)" in bootstrap_template
    assert "Sites.create(user" in bootstrap_template
    assert "missing_sites" in verify_template
    assert 'path = "{{ plausible_verify_path }}"' in event_check_template
