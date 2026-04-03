from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_ROOT = REPO_ROOT / "roles" / "langfuse_runtime"
DEFAULTS_PATH = ROLE_ROOT / "defaults" / "main.yml"
TASKS_PATH = ROLE_ROOT / "tasks" / "main.yml"
VERIFY_TASKS_PATH = ROLE_ROOT / "tasks" / "verify.yml"
COMPOSE_TEMPLATE = ROLE_ROOT / "templates" / "docker-compose.yml.j2"
ENV_TEMPLATE = ROLE_ROOT / "templates" / "langfuse.env.j2"
ENV_CTEMPLATE = ROLE_ROOT / "templates" / "langfuse.env.ctmpl.j2"


def load_tasks() -> list[dict]:
    return yaml.safe_load(TASKS_PATH.read_text())


def load_verify_tasks() -> list[dict]:
    return yaml.safe_load(VERIFY_TASKS_PATH.read_text())


def test_defaults_use_shared_minio_contract() -> None:
    defaults = DEFAULTS_PATH.read_text()
    assert "langfuse_minio_secret_key_local_file" in defaults
    assert "langfuse_minio_access_key_id: langfuseapp" in defaults
    assert "langfuse_minio_bucket_name: langfuse-exports" in defaults
    assert "platform_service_url('minio', 'internal')" in defaults
    assert "platform_service_url('minio', 'public')" in defaults
    assert "langfuse_minio_root_password" not in defaults
    assert "langfuse_minio_image" not in defaults


def test_tasks_require_minio_secret_and_record_shared_s3_secret() -> None:
    tasks = load_tasks()
    names = {task["name"] for task in tasks}

    assert "Check whether the Langfuse MinIO secret key exists on the control machine" in names
    assert "Fail if the Langfuse MinIO secret key is missing locally" in names

    record_task = next(task for task in tasks if task.get("name") == "Record the Langfuse runtime secrets")
    assert "LANGFUSE_S3_SECRET_ACCESS_KEY" in record_task["ansible.builtin.set_fact"]["langfuse_runtime_secret_payload"]


def test_env_templates_use_shared_minio_for_event_and_media_uploads() -> None:
    template = ENV_TEMPLATE.read_text()
    ctemplate = ENV_CTEMPLATE.read_text()

    assert "LANGFUSE_S3_EVENT_UPLOAD_BUCKET={{ langfuse_minio_bucket_name }}" in template
    assert "LANGFUSE_S3_EVENT_UPLOAD_ENDPOINT={{ langfuse_minio_private_endpoint }}" in template
    assert "LANGFUSE_S3_MEDIA_UPLOAD_ENDPOINT={{ langfuse_minio_public_endpoint }}" in template
    assert "LANGFUSE_S3_SECRET_ACCESS_KEY" not in template
    assert "MINIO_ROOT_USER" not in template

    assert "LANGFUSE_S3_SECRET_ACCESS_KEY" in ctemplate
    assert "LANGFUSE_S3_MEDIA_UPLOAD_ENDPOINT={{ langfuse_minio_public_endpoint }}" in ctemplate
    assert "MINIO_ROOT_PASSWORD" not in ctemplate


def test_compose_template_no_longer_embeds_local_minio_sidecar() -> None:
    template = COMPOSE_TEMPLATE.read_text()
    assert "\n  minio:\n" not in template
    assert "langfuse-minio" not in template


def test_tasks_recover_stale_compose_network_during_langfuse_startup() -> None:
    tasks = load_tasks()
    start_block = next(
        task
        for task in tasks
        if task.get("name") == "Start the Langfuse stack and recover stale compose-network failures"
    )
    rescue_names = [task["name"] for task in start_block["rescue"]]

    assert "Flag stale Langfuse compose-network failures during startup" in rescue_names
    assert "Reset stale Langfuse compose resources before retrying startup" in rescue_names
    assert "Retry Langfuse stack startup after compose-network recovery" in rescue_names


def test_tasks_force_recreate_langfuse_when_network_attachment_is_missing() -> None:
    tasks = load_tasks()
    network_check = next(
        task for task in tasks if task.get("name") == "Check whether Langfuse has an attached Docker network"
    )
    recovery_block = next(
        task for task in tasks if task.get("name") == "Force-recreate Langfuse when Docker network attachment is missing"
    )
    network_cleanup = next(
        task
        for task in recovery_block["block"]
        if task.get("name") == "Remove the stale Langfuse compose network before retrying startup"
    )
    retry_up = next(
        task
        for task in recovery_block["block"]
        if task.get("name") == "Force-recreate Langfuse after local network attachment recovery"
    )
    network_recheck = next(
        task for task in tasks if task.get("name") == "Recheck Langfuse Docker network attachment"
    )

    assert "{{json .NetworkSettings.Networks}}" in network_check["ansible.builtin.shell"]
    assert recovery_block["when"] == "langfuse_network_attachment_check.stdout | trim in ['', '{}', 'null']"
    assert "^{{ langfuse_site_dir | basename }}_default$" in network_cleanup["ansible.builtin.shell"]
    assert retry_up["ansible.builtin.command"]["argv"][-4:] == ["up", "-d", "--force-recreate", "--remove-orphans"]
    assert network_recheck["until"] == "langfuse_network_attachment_recheck.stdout | trim not in ['', '{}', 'null']"


def test_verify_retries_bootstrap_project_api_until_langfuse_db_recovers() -> None:
    verify_tasks = load_verify_tasks()
    verify_task = next(
        task
        for task in verify_tasks
        if task.get("name") == "Verify the Langfuse bootstrap project API is reachable"
    )

    assert verify_task["retries"] == 30
    assert verify_task["delay"] == 5
    assert verify_task["until"] == "(langfuse_verify_project.status | default(0)) == 200"
    assert verify_task["failed_when"] is False
