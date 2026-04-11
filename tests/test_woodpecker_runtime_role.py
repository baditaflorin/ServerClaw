from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_DEFAULTS = REPO_ROOT / "roles" / "woodpecker_runtime" / "defaults" / "main.yml"
ENV_TEMPLATE = REPO_ROOT / "roles" / "woodpecker_runtime" / "templates" / "woodpecker.env.j2"
CTMPL_TEMPLATE = REPO_ROOT / "roles" / "woodpecker_runtime" / "templates" / "woodpecker.env.ctmpl.j2"
COMPOSE_TEMPLATE = REPO_ROOT / "roles" / "woodpecker_runtime" / "templates" / "docker-compose.yml.j2"
TASK_FILE = REPO_ROOT / "roles" / "woodpecker_runtime" / "tasks" / "main.yml"
VERIFY_FILE = REPO_ROOT / "roles" / "woodpecker_runtime" / "tasks" / "verify.yml"


def test_woodpecker_runtime_defaults_bind_generated_topology_and_artifacts() -> None:
    defaults = yaml.safe_load(ROLE_DEFAULTS.read_text())

    assert defaults["woodpecker_http_port"] == "{{ woodpecker_service_topology.ports.internal }}"
    assert defaults["woodpecker_host_proxy_port"] == "{{ woodpecker_service_topology.ports.controller }}"
    assert defaults["woodpecker_public_url"] == "{{ woodpecker_service_topology.urls.public }}"
    assert defaults["woodpecker_controller_url"] == "{{ woodpecker_service_topology.urls.controller }}"
    assert defaults["woodpecker_gitea_runtime_url"] == "{{ gitea_private_base_url }}"
    assert defaults["woodpecker_local_artifact_dir"].endswith("/.local/woodpecker")
    assert defaults["woodpecker_seed_repo_full_name"] == "ops/platform"


def test_woodpecker_templates_export_gitea_oauth_and_agent_settings() -> None:
    env_template = ENV_TEMPLATE.read_text()
    ctmpl_template = CTMPL_TEMPLATE.read_text()
    compose_template = COMPOSE_TEMPLATE.read_text()

    assert "WOODPECKER_EXPERT_FORGE_OAUTH_HOST={{ woodpecker_gitea_oauth_url }}" in env_template
    assert "WOODPECKER_GITEA_URL={{ woodpecker_gitea_internal_api_url }}" in env_template
    assert "WOODPECKER_AGENT_SECRET={{ woodpecker_agent_secret }}" in env_template
    assert "[[ .Data.data.WOODPECKER_AGENT_SECRET ]]" in ctmpl_template
    assert "woodpecker-server" in compose_template
    assert "woodpecker-agent" in compose_template
    assert "{{ woodpecker_http_port }}:{{ woodpecker_http_port }}" in compose_template


def test_woodpecker_runtime_tasks_prepare_oauth_and_render_bootstrap_spec() -> None:
    task_text = TASK_FILE.read_text()
    task_data = yaml.safe_load(task_text)
    verify_text = VERIFY_FILE.read_text()
    verify_data = yaml.safe_load(verify_text)

    assert "Prepare the Gitea OAuth application for Woodpecker" in task_text
    assert "scripts/woodpecker_bootstrap.py" in task_text
    assert "Render the Woodpecker bootstrap specification locally" in task_text
    assert "name: lv3.platform.common" in task_text
    assert "Wait for the Gitea sign-in page before Woodpecker OAuth bootstrap" in task_text
    assert "Wait for the Woodpecker local health endpoint" in task_text
    assert "woodpecker_version_path" in verify_text

    gitea_wait_task = next(
        task
        for task in task_data
        if task["name"] == "Wait for the Gitea sign-in page before Woodpecker OAuth bootstrap"
    )
    local_health_task = next(
        task for task in task_data if task["name"] == "Wait for the Woodpecker local health endpoint"
    )
    verify_health_task = next(
        task for task in verify_data if task["name"] == "Verify the Woodpecker local health endpoint"
    )

    assert gitea_wait_task["ansible.builtin.uri"]["url"] == "{{ woodpecker_gitea_runtime_url }}/user/login"
    assert gitea_wait_task["retries"] == 48
    assert gitea_wait_task["until"] == "woodpecker_gitea_login_page.status == 200"
    assert local_health_task["ansible.builtin.uri"]["status_code"] == [200, 204]
    assert local_health_task["until"] == "woodpecker_health.status in [200, 204]"
    assert verify_health_task["ansible.builtin.uri"]["status_code"] == [200, 204]
    assert verify_health_task["until"] == "woodpecker_verify_health.status in [200, 204]"
