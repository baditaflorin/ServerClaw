from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_DEFAULTS = REPO_ROOT / "roles" / "open_webui_runtime" / "defaults" / "main.yml"
ROLE_VERIFY_TASKS = REPO_ROOT / "roles" / "open_webui_runtime" / "tasks" / "verify.yml"
ENV_TEMPLATE = REPO_ROOT / "roles" / "open_webui_runtime" / "templates" / "open-webui.env.j2"
CTMPL_TEMPLATE = REPO_ROOT / "roles" / "open_webui_runtime" / "templates" / "open-webui.env.ctmpl.j2"


def load_verify_tasks() -> list[dict]:
    return yaml.safe_load(ROLE_VERIFY_TASKS.read_text())


def test_defaults_expose_public_oidc_runtime_inputs() -> None:
    defaults = yaml.safe_load(ROLE_DEFAULTS.read_text())

    assert defaults["open_webui_webui_name"] == "Open WebUI"
    assert defaults["open_webui_oidc_provider_name"] == "Keycloak"
    assert defaults["open_webui_oidc_scopes"] == "openid email profile"
    assert defaults["open_webui_oidc_redirect_uri"] == "{{ open_webui_webui_url }}/oauth/oidc/callback"
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


def test_verify_tasks_skip_password_signin_when_password_auth_is_disabled() -> None:
    tasks = load_verify_tasks()

    signin_task = next(task for task in tasks if task.get("name") == "Verify Open WebUI admin sign-in works")
    assert_task = next(task for task in tasks if task.get("name") == "Assert Open WebUI sign-in returned the expected account")

    assert signin_task["when"] == "open_webui_enable_password_auth | bool"
    assert assert_task["when"] == "open_webui_enable_password_auth | bool"
