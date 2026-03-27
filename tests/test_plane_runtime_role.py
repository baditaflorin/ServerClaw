from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_DEFAULTS = REPO_ROOT / "roles" / "plane_runtime" / "defaults" / "main.yml"
ENV_TEMPLATE = REPO_ROOT / "roles" / "plane_runtime" / "templates" / "plane.env.j2"
CTMPL_TEMPLATE = REPO_ROOT / "roles" / "plane_runtime" / "templates" / "plane.env.ctmpl.j2"
COMPOSE_TEMPLATE = REPO_ROOT / "roles" / "plane_runtime" / "templates" / "docker-compose.yml.j2"


def test_plane_runtime_defaults_list_trusted_proxies() -> None:
    defaults = yaml.safe_load(ROLE_DEFAULTS.read_text())

    assert defaults["plane_gunicorn_workers"] == 2
    assert defaults["plane_healthcheck_path"] == "/api/instances/"
    assert defaults["plane_trusted_proxies"] == [
        "127.0.0.1",
        "10.10.10.10",
        "100.64.0.1",
    ]


def test_plane_env_templates_render_trusted_proxies_as_caddy_arguments() -> None:
    env_template = ENV_TEMPLATE.read_text()
    ctmpl_template = CTMPL_TEMPLATE.read_text()

    assert "TRUSTED_PROXIES={{ plane_trusted_proxies | join(' ') }}" in env_template
    assert "TRUSTED_PROXIES={{ plane_trusted_proxies | join(' ') }}" in ctmpl_template
    assert "plane_rabbitmq_password | urlencode | replace('/', '%2F')" in env_template
    assert ".Data.data.RABBITMQ_PASSWORD | urlquery" in ctmpl_template


def test_plane_env_templates_export_bucket_name_for_proxy_routing() -> None:
    env_template = ENV_TEMPLATE.read_text()
    ctmpl_template = CTMPL_TEMPLATE.read_text()

    assert "BUCKET_NAME={{ plane_s3_bucket_name }}" in env_template
    assert "BUCKET_NAME={{ plane_s3_bucket_name }}" in ctmpl_template
    assert "GUNICORN_WORKERS={{ plane_gunicorn_workers }}" in env_template
    assert "GUNICORN_WORKERS={{ plane_gunicorn_workers }}" in ctmpl_template


def test_plane_compose_template_runs_migrator_before_the_api_path() -> None:
    compose_template = COMPOSE_TEMPLATE.read_text()

    assert "container_name: {{ plane_migrator_container_name }}" in compose_template
    assert "command: ./bin/docker-entrypoint-migrator.sh" in compose_template
    assert "- {{ plane_migrator_log_dir }}:/code/plane/logs" in compose_template
    assert "migrator:\n        condition: service_started" in compose_template
    assert '  plane-redis:\n    image: {{ plane_valkey_image }}' in compose_template
    assert '      - --save\n      - ""' in compose_template
