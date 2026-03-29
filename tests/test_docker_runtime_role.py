from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_TASKS = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "docker_runtime"
    / "tasks"
    / "main.yml"
)
ROLE_DEFAULTS = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "docker_runtime"
    / "defaults"
    / "main.yml"
)


def load_tasks() -> list[dict]:
    return yaml.safe_load(ROLE_TASKS.read_text())


def load_defaults() -> dict:
    return yaml.safe_load(ROLE_DEFAULTS.read_text())


def test_docker_runtime_patches_nftables_before_starting_docker() -> None:
    task_names = [task["name"] for task in load_tasks()]
    assert task_names.index("Reload nftables after forward compatibility patch") < task_names.index(
        "Ensure Docker service is enabled and running"
    )


def test_docker_runtime_rechecks_nat_and_forward_chains() -> None:
    tasks = load_tasks()
    task_names = {task["name"] for task in tasks}
    assert "Flush Docker handlers before chain health checks" in task_names
    assert "Check whether Docker nat chain exists" in task_names
    assert "Check whether Docker forward chain exists" in task_names
    assert "Restart Docker when required chains are missing" in task_names
    nat_recheck = next(task for task in tasks if task["name"] == "Recheck Docker nat chain after restart")
    forward_recheck = next(task for task in tasks if task["name"] == "Recheck Docker forward chain after restart")
    assert nat_recheck["retries"] == 10
    assert nat_recheck["delay"] == 2
    assert nat_recheck["until"] == "docker_runtime_nat_chain_recheck.rc == 0"
    assert forward_recheck["retries"] == 10
    assert forward_recheck["delay"] == 2
    assert forward_recheck["until"] == "docker_runtime_forward_chain_recheck.rc == 0"


def test_docker_runtime_patches_nftables_one_rule_per_cidr() -> None:
    tasks = load_tasks()
    build_rules = next(task for task in tasks if task["name"] == "Build the Docker bridge forward-compat rule block")
    patch_rules = next(task for task in tasks if task["name"] == "Patch nftables forward policy for Docker bridge egress")
    reload_rules = next(task for task in tasks if task["name"] == "Reload nftables after forward compatibility patch")

    assert "docker_runtime_container_forward_rules" in build_rules["ansible.builtin.set_fact"]
    assert patch_rules["ansible.builtin.lineinfile"]["line"] == "    {{ item }}"
    assert patch_rules["loop"] == "{{ docker_runtime_container_forward_rules }}"
    assert reload_rules["changed_when"] == "docker_runtime_nftables_forward_patch.results | selectattr('changed') | list | length > 0"


def test_docker_runtime_defaults_pin_governed_resolvers_and_registry_mirror() -> None:
    defaults = load_defaults()
    daemon_config = defaults["docker_runtime_daemon_config"]

    assert daemon_config["dns"] == ["1.1.1.1", "8.8.8.8"]
    assert daemon_config["registry-mirrors"] == ["https://mirror.gcr.io"]
