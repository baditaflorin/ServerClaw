from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULTS_PATH = REPO_ROOT / "roles" / "grafana_sso" / "defaults" / "main.yml"
TASKS_PATH = REPO_ROOT / "roles" / "grafana_sso" / "tasks" / "main.yml"


def load_yaml(path: Path) -> list[dict] | dict:
    return yaml.safe_load(path.read_text())


def test_defaults_route_grafana_logout_through_keycloak_then_shared_proxy_cleanup() -> None:
    defaults = load_yaml(DEFAULTS_PATH)

    assert defaults["grafana_sso_session_authority"] == "{{ platform_session_authority }}"
    assert defaults["grafana_sso_signout_redirect_url"] == (
        "{{ grafana_sso_session_authority.keycloak_logout_url }}"
        "?client_id={{ grafana_sso_client_id }}"
        "&post_logout_redirect_uri={{ grafana_sso_session_authority.shared_proxy_cleanup_url | urlencode }}"
    )


def test_tasks_write_the_repo_managed_signout_redirect_url() -> None:
    tasks = load_yaml(TASKS_PATH)
    oauth_task = next(task for task in tasks if task.get("name") == "Enable Generic OAuth in Grafana")
    signout_option = next(item for item in oauth_task["loop"] if item["option"] == "signout_redirect_url")

    assert signout_option["value"] == "{{ grafana_sso_signout_redirect_url }}"
