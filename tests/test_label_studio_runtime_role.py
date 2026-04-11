from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DEFAULTS_PATH = REPO_ROOT / "roles" / "label_studio_runtime" / "defaults" / "main.yml"
RUNTIME_TASKS_PATH = REPO_ROOT / "roles" / "label_studio_runtime" / "tasks" / "main.yml"
VERIFY_TASKS_PATH = REPO_ROOT / "roles" / "label_studio_runtime" / "tasks" / "verify.yml"
VERIFY_PUBLIC_TASKS_PATH = REPO_ROOT / "roles" / "label_studio_runtime" / "tasks" / "verify_public.yml"
RUNTIME_META_PATH = REPO_ROOT / "roles" / "label_studio_runtime" / "meta" / "argument_specs.yml"
COMPOSE_TEMPLATE_PATH = REPO_ROOT / "roles" / "label_studio_runtime" / "templates" / "docker-compose.yml.j2"
ENV_TEMPLATE_PATH = REPO_ROOT / "roles" / "label_studio_runtime" / "templates" / "label-studio.env.j2"
OPENBAO_ENV_TEMPLATE_PATH = REPO_ROOT / "roles" / "label_studio_runtime" / "templates" / "label-studio.env.ctmpl.j2"
PROJECT_TEMPLATE_PATH = REPO_ROOT / "roles" / "label_studio_runtime" / "templates" / "project-catalog.json.j2"
POSTGRES_DEFAULTS_PATH = REPO_ROOT / "roles" / "label_studio_postgres" / "defaults" / "main.yml"
POSTGRES_TASKS_PATH = REPO_ROOT / "roles" / "label_studio_postgres" / "tasks" / "main.yml"
POSTGRES_META_PATH = REPO_ROOT / "roles" / "label_studio_postgres" / "meta" / "argument_specs.yml"


def load_tasks(path: Path) -> list[dict]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_label_studio_runtime_defaults_reference_service_topology_image_and_local_secrets() -> None:
    defaults = yaml.safe_load(RUNTIME_DEFAULTS_PATH.read_text(encoding="utf-8"))

    assert (
        defaults["label_studio_service_topology"]
        == "{{ hostvars['proxmox-host'].lv3_service_topology | service_topology_get('label_studio') }}"
    )
    assert (
        defaults["label_studio_internal_port"]
        == "{{ platform_service_topology | platform_service_port('label_studio', 'internal') }}"
    )
    assert (
        defaults["label_studio_internal_base_url"]
        == "{{ platform_service_topology | platform_service_url('label_studio', 'internal') }}"
    )
    assert defaults["label_studio_public_base_url"] == "https://{{ label_studio_service_topology.public_hostname }}"
    assert defaults["label_studio_image"] == "{{ container_image_catalog.images.label_studio_runtime.ref }}"
    assert defaults["label_studio_database_password_local_file"].endswith("/.local/label-studio/database-password.txt")
    assert defaults["label_studio_admin_password_local_file"].endswith("/.local/label-studio/admin-password.txt")
    assert defaults["label_studio_admin_token_local_file"].endswith("/.local/label-studio/admin-token.txt")
    assert [project["id"] for project in defaults["label_studio_projects"]] == [
        "langfuse_trace_review",
        "rag_relevance_review",
        "ocr_correction_review",
    ]


def test_label_studio_runtime_argument_spec_requires_runtime_and_secret_inputs() -> None:
    specs = yaml.safe_load(RUNTIME_META_PATH.read_text(encoding="utf-8"))
    options = specs["argument_specs"]["main"]["options"]

    assert options["label_studio_site_dir"]["type"] == "path"
    assert options["label_studio_internal_port"]["type"] == "int"
    assert options["label_studio_internal_base_url"]["type"] == "str"
    assert options["label_studio_public_base_url"]["type"] == "str"
    assert options["label_studio_database_password_local_file"]["type"] == "path"
    assert options["label_studio_admin_token_local_file"]["type"] == "path"


def test_label_studio_runtime_tasks_manage_openbao_sync_and_verification_flow() -> None:
    tasks = load_tasks(RUNTIME_TASKS_PATH)

    validate_task = next(task for task in tasks if task["name"] == "Validate Label Studio runtime inputs")
    openbao_helper = next(
        task for task in tasks if task["name"] == "Prepare OpenBao agent runtime secret injection for Label Studio"
    )
    pull_task = next(task for task in tasks if task["name"] == "Pull the Label Studio image")
    force_recreate_decision = next(
        task for task in tasks if task["name"] == "Record whether the Label Studio startup needs a force recreate"
    )
    start_task = next(task for task in tasks if task["name"] == "Start the Label Studio stack")
    recreate_task = next(
        task
        for task in tasks
        if task["name"] == "Force-recreate the Label Studio stack after runtime drift or Docker recovery"
    )
    sync_task = next(
        task for task in tasks if task["name"] == "Synchronize the repo-managed Label Studio project catalog"
    )
    verify_before = next(
        task for task in tasks if task["name"] == "Verify the Label Studio runtime before project synchronization"
    )
    verify_after = next(
        task for task in tasks if task["name"] == "Verify the Label Studio runtime after project synchronization"
    )
    required_inputs = validate_task["ansible.builtin.assert"]["that"]

    assert "label_studio_database_password_local_file | length > 0" in required_inputs
    assert "label_studio_admin_password_local_file | length > 0" in required_inputs
    assert "label_studio_admin_token_local_file | length > 0" in required_inputs
    assert "label_studio_sync_script | length > 0" in required_inputs
    assert openbao_helper["ansible.builtin.include_role"]["name"] == "lv3.platform.common"
    assert openbao_helper["ansible.builtin.include_role"]["tasks_from"] == "openbao_compose_env"
    assert (
        openbao_helper["vars"]["common_openbao_compose_env_agent_template_file"]
        == "{{ label_studio_openbao_agent_dir }}/label-studio.env.ctmpl"
    )
    assert pull_task["retries"] == 5
    assert pull_task["delay"] == 5
    assert pull_task["until"] == "label_studio_pull.rc == 0"
    assert (
        "label_studio_project_catalog_template.changed"
        in force_recreate_decision["ansible.builtin.set_fact"]["label_studio_force_recreate"]
    )
    assert start_task["ansible.builtin.command"]["argv"][-3:] == ["up", "-d", "--remove-orphans"]
    assert recreate_task["ansible.builtin.command"]["argv"][-4:] == ["up", "-d", "--force-recreate", "--remove-orphans"]
    assert "{{ label_studio_sync_script }} sync" in sync_task["ansible.builtin.script"]
    assert "--token-file {{ label_studio_admin_token_remote_file }}" in sync_task["ansible.builtin.script"]
    assert "--project-catalog {{ label_studio_project_catalog_file }}" in sync_task["ansible.builtin.script"]
    assert sync_task["retries"] == 12
    assert sync_task["delay"] == 5
    assert sync_task["until"] == "label_studio_project_sync.rc == 0"
    assert verify_before["ansible.builtin.import_tasks"] == "verify.yml"
    assert verify_before["vars"]["label_studio_verify_project_catalog"] is False
    assert verify_after["ansible.builtin.import_tasks"] == "verify.yml"


def test_label_studio_verify_tasks_cover_local_runtime_public_redirects_and_project_catalog() -> None:
    verify_tasks = load_tasks(VERIFY_TASKS_PATH)
    public_tasks = load_tasks(VERIFY_PUBLIC_TASKS_PATH)

    version_task = next(task for task in verify_tasks if task["name"] == "Verify the Label Studio version endpoint")
    container_task = next(
        task for task in verify_tasks if task["name"] == "Verify the Label Studio container is running"
    )
    health_task = next(
        task for task in verify_tasks if task["name"] == "Wait for the Label Studio container health check to pass"
    )
    project_verify_task = next(
        task for task in verify_tasks if task["name"] == "Verify the repo-managed Label Studio project catalog"
    )
    ui_redirect_task = next(
        task
        for task in public_tasks
        if task["name"] == "Verify the public Label Studio UI redirects into the shared edge auth boundary"
    )
    api_redirect_task = next(
        task
        for task in public_tasks
        if task["name"] == "Verify the public Label Studio API redirects into the shared edge auth boundary"
    )
    redirect_assert = next(
        task
        for task in public_tasks
        if task["name"] == "Assert the Label Studio public redirects target the shared auth boundary"
    )

    assert container_task["ansible.builtin.command"]["argv"] == [
        "docker",
        "inspect",
        "--format",
        '{{ "{{.State.Running}}" }}',
        "{{ label_studio_container_name }}",
    ]
    assert health_task["ansible.builtin.command"]["argv"] == [
        "docker",
        "inspect",
        "--format",
        '{{ "{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}" }}',
        "{{ label_studio_container_name }}",
    ]
    assert health_task["retries"] == 36
    assert health_task["delay"] == 5
    assert health_task["until"] == "label_studio_container_health.stdout | trim == 'healthy'"
    assert (
        version_task["ansible.builtin.uri"]["url"]
        == "{{ label_studio_internal_base_url }}{{ label_studio_health_path }}"
    )
    assert version_task["retries"] == 12
    assert version_task["delay"] == 5
    assert (
        version_task["until"]
        == "label_studio_version_verify.status == 200 and (label_studio_version_verify.json.release | default('') | length) > 0"
    )
    assert "{{ label_studio_sync_script }} verify" in project_verify_task["ansible.builtin.script"]
    assert project_verify_task["when"] == "label_studio_verify_project_catalog | default(true) | bool"
    assert ui_redirect_task["ansible.builtin.uri"]["url"] == "{{ label_studio_public_base_url }}/"
    assert api_redirect_task["ansible.builtin.uri"]["url"] == "{{ label_studio_public_base_url }}/api/projects"
    assert "oauth2/(sign_in|start)" in redirect_assert["ansible.builtin.assert"]["that"][0]
    assert "oauth2/(sign_in|start)" in redirect_assert["ansible.builtin.assert"]["that"][1]


def test_label_studio_templates_bind_private_port_and_render_expected_env_contract() -> None:
    compose_template = COMPOSE_TEMPLATE_PATH.read_text(encoding="utf-8")
    env_template = ENV_TEMPLATE_PATH.read_text(encoding="utf-8")
    openbao_env_template = OPENBAO_ENV_TEMPLATE_PATH.read_text(encoding="utf-8")
    project_template = PROJECT_TEMPLATE_PATH.read_text(encoding="utf-8")

    assert "image: {{ label_studio_openbao_agent_image }}" in compose_template
    assert "container_name: {{ label_studio_container_name }}" in compose_template
    assert '"{{ ansible_host }}:{{ label_studio_internal_port }}:{{ label_studio_container_port }}"' in compose_template
    assert '"127.0.0.1:{{ label_studio_internal_port }}:{{ label_studio_container_port }}"' in compose_template
    assert "- label-studio" in compose_template
    assert "- --init" in compose_template
    assert "HOST={{ label_studio_public_base_url }}" in env_template
    assert "JSON_LOG=true" in env_template
    assert "DISABLE_SIGNUP_WITHOUT_LINK=true" in env_template
    assert "LABEL_STUDIO_ENABLE_LEGACY_API_TOKEN=true" in env_template
    assert "POSTGRE_PASSWORD={{ label_studio_database_password }}" in env_template
    assert "USER_TOKEN={{ label_studio_admin_token }}" in env_template
    assert (
        'POSTGRE_PASSWORD=[[ with secret "kv/data/{{ label_studio_openbao_secret_path }}" ]][[ .Data.data.POSTGRE_PASSWORD ]][[ end ]]'
        in openbao_env_template
    )
    assert (
        'USER_TOKEN=[[ with secret "kv/data/{{ label_studio_openbao_secret_path }}" ]][[ .Data.data.USER_TOKEN ]][[ end ]]'
        in openbao_env_template
    )
    assert "{% for project in label_studio_projects %}" in project_template


def test_label_studio_postgres_role_defaults_specs_and_tasks_cover_database_setup() -> None:
    defaults = yaml.safe_load(POSTGRES_DEFAULTS_PATH.read_text(encoding="utf-8"))
    specs = yaml.safe_load(POSTGRES_META_PATH.read_text(encoding="utf-8"))
    tasks = load_tasks(POSTGRES_TASKS_PATH)
    options = specs["argument_specs"]["main"]["options"]
    names = [task["name"] for task in tasks]

    assert defaults["label_studio_database_name"] == "label_studio"
    assert defaults["label_studio_database_user"] == "label_studio"
    assert defaults["label_studio_database_password_local_file"].endswith("/.local/label-studio/database-password.txt")
    assert options["label_studio_database_name"]["type"] == "str"
    assert options["label_studio_postgres_password_file"]["type"] == "path"
    assert "Generate the Label Studio database password" in names
    assert "Create the Label Studio role" in names
    assert "Create the Label Studio PostgreSQL database" in names
