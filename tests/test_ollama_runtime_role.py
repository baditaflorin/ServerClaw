from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_TASKS = REPO_ROOT / "roles" / "ollama_runtime" / "tasks" / "main.yml"
ROLE_DEFAULTS = REPO_ROOT / "roles" / "ollama_runtime" / "defaults" / "main.yml"
COMPOSE_TEMPLATE = REPO_ROOT / "roles" / "ollama_runtime" / "templates" / "docker-compose.yml.j2"


def load_tasks() -> list[dict]:
    return yaml.safe_load(ROLE_TASKS.read_text())


def test_role_defaults_pin_private_model_storage() -> None:
    defaults = yaml.safe_load(ROLE_DEFAULTS.read_text())
    assert defaults["ollama_runtime_model_dir"] == "{{ ollama_runtime_data_dir }}/models"
    assert defaults["ollama_runtime_default_model"] == "llama3.2:3b"


def test_role_pulls_declared_startup_models_via_api() -> None:
    tasks = load_tasks()
    pull_task = next(task for task in tasks if task.get("name") == "Pull the declared startup Ollama models")
    assert pull_task["ansible.builtin.uri"]["url"] == "{{ ollama_runtime_base_url }}/api/pull"
    assert pull_task["ansible.builtin.uri"]["body"]["model"] == "{{ item }}"


def test_role_verifies_default_model_inside_container() -> None:
    tasks = load_tasks()
    verify_task = next(task for task in tasks if task.get("name") == "Verify the default Ollama model is present")
    assert verify_task["ansible.builtin.command"]["argv"][-2:] == ["show", "{{ ollama_runtime_default_model }}"]


def test_compose_template_exposes_private_runtime_port_and_model_volume() -> None:
    template = COMPOSE_TEMPLATE.read_text()
    assert '"{{ ollama_runtime_port }}:11434"' in template
    assert "{{ ollama_runtime_model_dir }}:/root/.ollama" in template


def test_host_network_policy_allows_private_ollama_access() -> None:
    host_vars = yaml.safe_load((REPO_ROOT / "inventory" / "host_vars" / "proxmox_florin.yml").read_text())
    docker_runtime_rules = host_vars["network_policy"]["guests"]["docker-runtime-lv3"]["allowed_inbound"]
    guest_rule = next(rule for rule in docker_runtime_rules if rule["source"] == "all_guests")
    assert 11434 in guest_rule["ports"]
