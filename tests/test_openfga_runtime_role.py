from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULTS_PATH = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "openfga_runtime"
    / "defaults"
    / "main.yml"
)
TASKS_PATH = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "openfga_runtime"
    / "tasks"
    / "main.yml"
)
VERIFY_PATH = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "openfga_runtime"
    / "tasks"
    / "verify.yml"
)
COMPOSE_TEMPLATE_PATH = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "openfga_runtime"
    / "templates"
    / "docker-compose.yml.j2"
)
PLAYBOOK_PATH = REPO_ROOT / "playbooks" / "openfga.yml"


def load_tasks() -> list[dict]:
    return yaml.safe_load(TASKS_PATH.read_text(encoding="utf-8"))


def test_openfga_runtime_defaults_use_private_controller_url() -> None:
    defaults = yaml.safe_load(DEFAULTS_PATH.read_text(encoding="utf-8"))

    assert defaults["openfga_image"] == "{{ container_image_catalog.images.openfga_runtime.ref }}"
    assert defaults["openfga_controller_url"].startswith("http://{{ hostvars['proxmox_florin'].management_tailscale_ipv4 }}")
    assert "openfga_host_proxy_port" in defaults["openfga_controller_url"]
    assert defaults["openfga_preshared_key_local_file"].endswith("/.local/openfga/preshared-key.txt")


def test_openfga_runtime_bootstraps_openbao_env_and_migrations() -> None:
    tasks = load_tasks()

    openbao_helper = next(task for task in tasks if task.get("name") == "Prepare OpenBao agent runtime secret injection for OpenFGA")
    migrate_task = next(task for task in tasks if task.get("name") == "Run OpenFGA database migrations")
    up_task = next(task for task in tasks if task.get("name") == "Converge the OpenFGA runtime stack")

    assert openbao_helper["ansible.builtin.include_role"]["name"] == "lv3.platform.common"
    assert openbao_helper["ansible.builtin.include_role"]["tasks_from"] == "openbao_compose_env"
    assert migrate_task["ansible.builtin.command"]["argv"][-4:] == [
        "--datastore-engine",
        "postgres",
        "--datastore-uri",
        "{{ openfga_datastore_uri }}",
    ]
    assert up_task["ansible.builtin.command"]["argv"][-2:] == ["-d", "--remove-orphans"]


def test_openfga_verify_task_checks_health_and_authenticated_api() -> None:
    tasks = yaml.safe_load(VERIFY_PATH.read_text(encoding="utf-8"))

    health_task = next(task for task in tasks if task.get("name") == "Verify OpenFGA responds on the local health endpoint")
    api_task = next(task for task in tasks if task.get("name") == "Verify the OpenFGA API enforces the repo-managed preshared key")

    assert health_task["ansible.builtin.uri"]["url"] == "{{ openfga_local_url }}/healthz"
    assert api_task["ansible.builtin.uri"]["headers"]["Authorization"] == "Bearer {{ openfga_preshared_key }}"


def test_openfga_compose_template_uses_openbao_agent_and_runtime_env() -> None:
    template = COMPOSE_TEMPLATE_PATH.read_text(encoding="utf-8")

    assert "  openbao-agent:" in template
    assert "    env_file:" in template
    assert "      - {{ openfga_env_file }}" in template
    assert "--authn-method=preshared" in template


def test_openfga_playbook_bootstraps_serverclaw_authz_from_localhost() -> None:
    plays = yaml.safe_load(PLAYBOOK_PATH.read_text(encoding="utf-8"))

    bootstrap_play = next(play for play in plays if play["name"] == "Bootstrap the ServerClaw delegated authorization graph from the controller")
    task = bootstrap_play["tasks"][0]

    assert task["name"] == "Bootstrap the ServerClaw authorization store, model, and tuples"
    assert task["ansible.builtin.command"]["argv"][0] == "python3"
    assert task["ansible.builtin.command"]["argv"][1] == "{{ openfga_bootstrap_script }}"
    assert "--openfga-preshared-key-file" in task["ansible.builtin.command"]["argv"]
