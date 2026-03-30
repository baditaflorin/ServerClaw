from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_ROOT = REPO_ROOT / "roles" / "minio_runtime"
DEFAULTS_PATH = ROLE_ROOT / "defaults" / "main.yml"
TASKS_PATH = ROLE_ROOT / "tasks" / "main.yml"
VERIFY_PATH = ROLE_ROOT / "tasks" / "verify.yml"
COMPOSE_TEMPLATE = ROLE_ROOT / "templates" / "docker-compose.yml.j2"
ENV_TEMPLATE = ROLE_ROOT / "templates" / "runtime.env.j2"
ENV_CTEMPLATE = ROLE_ROOT / "templates" / "runtime.env.ctmpl.j2"


def load_yaml(path: Path) -> list[dict]:
    return yaml.safe_load(path.read_text())


def test_defaults_define_shared_bucket_contracts() -> None:
    defaults = DEFAULTS_PATH.read_text()
    assert "container_image_catalog.images.minio_runtime.ref" in defaults
    assert "minio_langfuse_bucket_name: langfuse-exports" in defaults
    assert "minio_langfuse_cors_smoke_object_name: __lv3-langfuse-cors-smoke.txt" in defaults
    assert "minio_gitea_bucket_name: gitea-lfs" in defaults
    assert "minio_loki_bucket_name: loki-chunks" in defaults
    assert "minio_platform_context_bucket_name: rag-staging" in defaults
    assert "minio_platform_context_retention_days: 14" in defaults


def test_tasks_install_mc_and_manage_buckets_policies_and_lifecycle() -> None:
    tasks = load_yaml(TASKS_PATH)
    names = {task["name"] for task in tasks}
    tasks_text = TASKS_PATH.read_text()

    assert "Install the pinned MinIO client" in names
    assert "Resolve the managed MinIO consumer contracts" in names
    assert "Generate the MinIO root password when missing" in names
    assert "Generate the MinIO consumer secret keys when missing" in names
    assert "Render the MinIO bucket policy documents" in names
    assert "Ensure the RAG staging bucket lifecycle rule exists" in names
    assert "Verify the MinIO runtime" in names
    assert "minio_managed_consumers_resolved" in tasks_text
    assert "minio_consumer_secret_generation.stdout" in tasks_text


def test_templates_publish_public_server_and_console_urls() -> None:
    compose = COMPOSE_TEMPLATE.read_text()
    env_template = ENV_TEMPLATE.read_text()
    env_ctemplate = ENV_CTEMPLATE.read_text()

    assert '"{{ minio_api_port }}:9000"' in compose
    assert '"{{ minio_console_port }}:9001"' in compose
    assert "--console-address" in compose
    assert "MINIO_SERVER_URL={{ minio_public_base_url }}" in env_template
    assert "MINIO_BROWSER_REDIRECT_URL={{ minio_console_public_url }}" in env_template
    assert 'MINIO_ROOT_PASSWORD=[[ with secret ' in env_ctemplate


def test_verify_tasks_probe_health_buckets_cors_and_lifecycle() -> None:
    tasks = load_yaml(VERIFY_PATH)
    names = {task["name"] for task in tasks}
    verify_text = VERIFY_PATH.read_text()

    assert "Verify the MinIO live health endpoint responds locally" in names
    assert "Verify the MinIO ready health endpoint responds locally" in names
    assert "Verify the managed MinIO buckets are reachable" in names
    assert "Verify the Langfuse bucket default CORS behavior" in names
    assert "Verify the RAG staging bucket lifecycle rule" in names
    assert "minio_managed_consumers_resolved" in verify_text
    assert "share download --json --expire 5m" in verify_text
    assert "access-control-allow-origin" in verify_text
