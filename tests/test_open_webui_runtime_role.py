from pathlib import Path

import json
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_DEFAULTS = REPO_ROOT / "roles" / "open_webui_runtime" / "defaults" / "main.yml"
ROLE_TASKS = REPO_ROOT / "roles" / "open_webui_runtime" / "tasks" / "main.yml"
ROLE_VERIFY_TASKS = REPO_ROOT / "roles" / "open_webui_runtime" / "tasks" / "verify.yml"
COMPOSE_TEMPLATE = REPO_ROOT / "roles" / "open_webui_runtime" / "templates" / "docker-compose.yml.j2"
ENV_TEMPLATE = REPO_ROOT / "roles" / "open_webui_runtime" / "templates" / "open-webui.env.j2"
CTMPL_TEMPLATE = REPO_ROOT / "roles" / "open_webui_runtime" / "templates" / "open-webui.env.ctmpl.j2"
HEALTH_PROBE_CATALOG = REPO_ROOT / "config" / "health-probe-catalog.json"


def load_tasks() -> list[dict]:
    return yaml.safe_load(ROLE_TASKS.read_text())


def load_verify_tasks() -> list[dict]:
    return yaml.safe_load(ROLE_VERIFY_TASKS.read_text())


def load_health_probes() -> dict:
    return json.loads(HEALTH_PROBE_CATALOG.read_text())["services"]


def test_defaults_expose_public_oidc_runtime_inputs() -> None:
    defaults = yaml.safe_load(ROLE_DEFAULTS.read_text())

    assert defaults["open_webui_webui_name"] == "Open WebUI"
    assert defaults["open_webui_oidc_provider_name"] == "Keycloak"
    assert defaults["open_webui_oidc_scopes"] == "openid email profile"
    assert defaults["open_webui_oidc_redirect_uri"] == "{{ open_webui_webui_url }}/oauth/oidc/callback"
    assert defaults["open_webui_enable_openbao_agent"] is True
    assert defaults["open_webui_enable_login_form"] == "{{ not (open_webui_enable_oidc | bool) }}"
    assert defaults["open_webui_enable_password_auth"] == "{{ not (open_webui_enable_oidc | bool) }}"
    assert defaults["open_webui_default_user_role"] == "pending"
    assert defaults["open_webui_session_cookie_secure"] is False
    assert defaults["open_webui_auth_cookie_secure"] is False


def test_env_template_wires_public_runtime_identity_and_oidc_fields() -> None:
    template = ENV_TEMPLATE.read_text()

    assert "WEBUI_NAME={{ open_webui_webui_name }}" in template
    assert "ENABLE_LOGIN_FORM={{ 'True' if open_webui_enable_login_form | bool else 'False' }}" in template
    assert "ENABLE_PASSWORD_AUTH={{ 'True' if open_webui_enable_password_auth | bool else 'False' }}" in template
    assert "DEFAULT_USER_ROLE={{ open_webui_default_user_role }}" in template
    assert "WEBUI_SESSION_COOKIE_SAME_SITE={{ open_webui_session_cookie_same_site }}" in template
    assert "WEBUI_AUTH_COOKIE_SAME_SITE={{ open_webui_auth_cookie_same_site }}" in template
    assert "WEBUI_SESSION_COOKIE_SECURE={{ 'True' if open_webui_session_cookie_secure | bool else 'False' }}" in template
    assert "WEBUI_AUTH_COOKIE_SECURE={{ 'True' if open_webui_auth_cookie_secure | bool else 'False' }}" in template
    assert "OAUTH_PROVIDER_NAME={{ open_webui_oidc_provider_name }}" in template
    assert "OPENID_REDIRECT_URI={{ open_webui_oidc_redirect_uri }}" in template


def test_ctmpl_template_reads_oidc_secret_from_openbao() -> None:
    template = CTMPL_TEMPLATE.read_text()

    assert "WEBUI_NAME={{ open_webui_webui_name }}" in template
    assert 'OAUTH_CLIENT_SECRET=[[ with secret "kv/data/{{ open_webui_openbao_secret_path }}" ]][[ .Data.data.OAUTH_CLIENT_SECRET ]][[ end ]]' in template
    assert '[[ with secret "kv/data/{{ open_webui_openbao_secret_path }}" ]][[ .Data.data.PROVIDER_ENV_BLOCK ]][[ end ]]' in template


def test_tasks_only_prepare_openbao_when_the_sidecar_is_enabled() -> None:
    tasks = load_tasks()

    helper_task = next(task for task in tasks if task.get("name") == "Prepare OpenBao agent runtime secret injection for Open WebUI")
    assert helper_task["when"] == "open_webui_enable_openbao_agent | bool"


def test_compose_template_only_depends_on_openbao_agent_when_enabled() -> None:
    template = COMPOSE_TEMPLATE.read_text()

    assert "{% if open_webui_enable_openbao_agent | bool %}" in template
    assert "  openbao-agent:" in template
    assert "      openbao-agent:" in template


def test_verify_tasks_skip_password_signin_when_password_auth_is_disabled() -> None:
    tasks = load_verify_tasks()

    signin_task = next(task for task in tasks if task.get("name") == "Verify Open WebUI admin sign-in works")
    assert_task = next(task for task in tasks if task.get("name") == "Assert Open WebUI sign-in returned the expected account")

    assert signin_task["when"] == "open_webui_enable_password_auth | bool"
    assert assert_task["when"] == "open_webui_enable_password_auth | bool"


def test_open_webui_and_serverclaw_probes_match_their_runtime_contracts() -> None:
    probes = load_health_probes()

    open_webui_startup = probes["open_webui"]["startup"]
    open_webui_readiness = probes["open_webui"]["readiness"]

    assert open_webui_startup["method"] == "POST"
    assert open_webui_startup["url"] == "http://127.0.0.1:8088/api/v1/auths/signin"
    assert "body" not in open_webui_startup
    assert "body_format" not in open_webui_startup

    assert open_webui_readiness["method"] == "POST"
    assert open_webui_readiness["url"] == "http://127.0.0.1:8088/api/v1/auths/signin"
    assert "body" not in open_webui_readiness
    assert "body_format" not in open_webui_readiness

    serverclaw_startup = probes["serverclaw"]["startup"]
    serverclaw_readiness = probes["serverclaw"]["readiness"]

    assert serverclaw_startup["method"] == "GET"
    assert serverclaw_startup["url"] == "http://127.0.0.1:8096"
    assert "body" not in serverclaw_startup
    assert "body_format" not in serverclaw_startup

    assert serverclaw_readiness["method"] == "GET"
    assert serverclaw_readiness["url"] == "http://127.0.0.1:8096"
    assert "body" not in serverclaw_readiness
    assert "body_format" not in serverclaw_readiness
