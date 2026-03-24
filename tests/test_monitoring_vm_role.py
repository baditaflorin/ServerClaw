from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULTS_PATH = REPO_ROOT / "roles" / "monitoring_vm" / "defaults" / "main.yml"
TASKS_PATH = REPO_ROOT / "roles" / "monitoring_vm" / "tasks" / "main.yml"
VERIFY_PATH = REPO_ROOT / "roles" / "monitoring_vm" / "tasks" / "verify.yml"


def load_tasks(path: Path) -> list[dict]:
    return yaml.safe_load(path.read_text())


def test_defaults_define_public_grafana_url_from_service_topology() -> None:
    defaults = yaml.safe_load(DEFAULTS_PATH.read_text())
    assert defaults["monitoring_grafana_public_url"] == (
        "https://{{ hostvars[groups['proxmox_hosts'][0]].lv3_service_topology.grafana.public_hostname }}"
    )


def test_main_tasks_explicitly_disable_public_dashboards_and_embedding() -> None:
    tasks = load_tasks(TASKS_PATH)
    public_dashboards = next(task for task in tasks if task.get("name") == "Disable Grafana public dashboards")
    login_form = next(task for task in tasks if task.get("name") == "Keep the Grafana login form available for recovery")
    allow_embedding = next(task for task in tasks if task.get("name") == "Disable Grafana embedding")
    assert public_dashboards["community.general.ini_file"]["section"] == "public_dashboards"
    assert public_dashboards["community.general.ini_file"]["option"] == "enabled"
    assert public_dashboards["community.general.ini_file"]["value"] == "false"
    assert login_form["community.general.ini_file"]["section"] == "auth"
    assert login_form["community.general.ini_file"]["option"] == "disable_login_form"
    assert login_form["community.general.ini_file"]["value"] == "false"
    assert allow_embedding["community.general.ini_file"]["section"] == "security"
    assert allow_embedding["community.general.ini_file"]["option"] == "allow_embedding"
    assert allow_embedding["community.general.ini_file"]["value"] == "false"


def test_verify_tasks_check_public_dashboard_lockdown() -> None:
    tasks = load_tasks(VERIFY_PATH)
    redirect_check = next(
        task
        for task in tasks
        if task.get("name") == "Verify public Grafana dashboard URLs redirect unauthenticated viewers to login"
    )
    health_check = next(
        task for task in tasks if task.get("name") == "Verify the public Grafana health endpoint is not exposed"
    )
    headers_check = next(
        task for task in tasks if task.get("name") == "Verify Grafana version headers are stripped at the public edge"
    )
    assert redirect_check["ansible.builtin.uri"]["follow_redirects"] == "none"
    assert redirect_check["ansible.builtin.uri"]["status_code"] == 302
    assert health_check["ansible.builtin.uri"]["status_code"] == 404
    assert headers_check["ansible.builtin.command"]["argv"][0] == "curl"
