from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_TASKS = REPO_ROOT / "roles" / "rag_context_runtime" / "tasks" / "main.yml"
COMPOSE_TEMPLATE = REPO_ROOT / "roles" / "rag_context_runtime" / "templates" / "docker-compose.yml.j2"


def load_tasks() -> list[dict]:
    return yaml.safe_load(ROLE_TASKS.read_text())


def test_pull_task_only_targets_external_qdrant_image() -> None:
    tasks = load_tasks()
    pull_task = next(task for task in tasks if task.get("name") == "Pull the platform context images")
    assert pull_task["ansible.builtin.command"]["argv"][-2:] == ["pull", "qdrant"]


def test_compose_template_build_uses_host_network() -> None:
    assert "network: host" in COMPOSE_TEMPLATE.read_text()


def test_host_network_policy_allows_platform_context_proxy_port() -> None:
    host_vars = yaml.safe_load(
        (REPO_ROOT / "inventory" / "host_vars" / "proxmox_florin.yml").read_text()
    )
    docker_runtime_rules = host_vars["network_policy"]["guests"]["docker-runtime-lv3"]["allowed_inbound"]
    host_rule = next(rule for rule in docker_runtime_rules if rule["source"] == "host")
    assert 8010 in host_rule["ports"]
