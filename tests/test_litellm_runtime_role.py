from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_ROOT = REPO_ROOT / "roles" / "litellm_runtime"
ROLE_DEFAULTS = ROLE_ROOT / "defaults" / "main.yml"
ROLE_TASKS = ROLE_ROOT / "tasks" / "main.yml"
ROLE_VERIFY = ROLE_ROOT / "tasks" / "verify.yml"
ROLE_META = ROLE_ROOT / "meta" / "argument_specs.yml"
RUNTIME_TEMPLATE = ROLE_ROOT / "templates" / "runtime.env.j2"


def test_defaults_define_litellm_runtime_env_contract() -> None:
    defaults = yaml.safe_load(ROLE_DEFAULTS.read_text(encoding="utf-8"))

    assert defaults["litellm_site_dir"] == "/opt/litellm"
    assert defaults["litellm_secret_dir"] == "/etc/lv3/litellm"
    assert defaults["litellm_env_file"] == "{{ compose_runtime_secret_root }}/litellm/runtime.env"
    assert defaults["litellm_legacy_env_file"] == "{{ litellm_site_dir }}/litellm.env"
    assert defaults["litellm_local_artifact_dir"] == "{{ repo_shared_local_root }}/litellm"
    assert defaults["litellm_master_key_local_file"] == "{{ litellm_local_artifact_dir }}/master-key.txt"
    assert defaults["litellm_database_password_local_file"] == "{{ litellm_local_artifact_dir }}/database-password.txt"


def test_argument_spec_requires_runtime_paths_and_image() -> None:
    specs = yaml.safe_load(ROLE_META.read_text(encoding="utf-8"))
    options = specs["argument_specs"]["main"]["options"]

    assert options["litellm_site_dir"]["type"] == "path"
    assert options["litellm_secret_dir"]["type"] == "path"
    assert options["litellm_env_file"]["type"] == "path"
    assert options["litellm_compose_file"]["type"] == "path"
    assert options["litellm_config_file"]["type"] == "path"
    assert options["litellm_image"]["type"] == "str"
    assert options["litellm_container_name"]["type"] == "str"
    assert options["litellm_internal_port"]["type"] == "int"


def test_main_tasks_create_runtime_env_dir_before_rendering_env_file() -> None:
    tasks = yaml.safe_load(ROLE_TASKS.read_text(encoding="utf-8"))
    names = [task["name"] for task in tasks]

    assert "Ensure the LiteLLM runtime directories exist" in names
    assert "Render the LiteLLM environment file" in names
    assert "Verify the LiteLLM runtime" in names

    mkdir_task = next(task for task in tasks if task["name"] == "Ensure the LiteLLM runtime directories exist")
    loop_entries = mkdir_task["loop"]
    assert {"path": "{{ litellm_env_file | dirname }}", "mode": "0700"} in loop_entries

    verify_task = next(task for task in tasks if task["name"] == "Verify the LiteLLM runtime")
    assert verify_task["ansible.builtin.import_tasks"] == "verify.yml"


def test_main_tasks_force_recreate_when_host_publication_is_missing_and_recover_nat_chain_failures() -> None:
    tasks = yaml.safe_load(ROLE_TASKS.read_text(encoding="utf-8"))
    names = [task["name"] for task in tasks]

    assert "Check whether the Docker nat chain exists before LiteLLM startup" in names
    assert "Check whether the LiteLLM local port is already published" in names
    assert "Record whether the LiteLLM startup needs a force recreate" in names

    start_task = next(task for task in tasks if task["name"] == "Start the LiteLLM stack")
    assert start_task["when"] == "not litellm_force_recreate"

    force_task = next(
        task
        for task in tasks
        if task["name"] == "Force-recreate the LiteLLM stack and recover Docker bridge-chain failures"
    )
    assert force_task["when"] == "litellm_force_recreate"

    rescue_names = [task["name"] for task in force_task["rescue"]]
    assert "Detect Docker bridge-chain and stale compose-network failures during LiteLLM startup" in rescue_names
    assert "Ensure Docker bridge networking chains are present before retrying LiteLLM startup" in rescue_names
    assert "Retry LiteLLM startup after Docker nat-chain or compose-network recovery" in rescue_names


def test_runtime_env_template_contains_required_secret_and_log_level_lines() -> None:
    template = RUNTIME_TEMPLATE.read_text(encoding="utf-8")

    assert "LITELLM_MASTER_KEY={{ litellm_master_key }}" in template
    assert "DATABASE_URL=postgresql://" in template
    assert "ANTHROPIC_API_KEY={{ litellm_anthropic_api_key }}" in template
    assert "LITELLM_LOG_LEVEL={{ litellm_log_level }}" in template


def test_compose_template_uses_python_healthcheck_inside_the_container() -> None:
    compose_template = (ROLE_ROOT / "templates" / "docker-compose.yml.j2").read_text(encoding="utf-8")

    assert 'python -c "import urllib.request;' in compose_template
    assert "http://127.0.0.1:{{ litellm_container_port }}/health/liveliness" in compose_template
    assert "curl -sf http://localhost:{{ litellm_container_port }}/health/liveliness" not in compose_template


def test_verify_tasks_use_parameterized_common_service_health_helper() -> None:
    tasks = yaml.safe_load(ROLE_VERIFY.read_text(encoding="utf-8"))

    include_task = next(task for task in tasks if task["name"] == "Verify the LiteLLM runtime")
    include_role = include_task["ansible.builtin.include_role"]
    include_vars = include_task["vars"]

    assert include_role["name"] == "lv3.platform.common"
    assert include_role["tasks_from"] == "verify_service_health"
    assert include_vars["common_verify_service_name"] == "litellm"
