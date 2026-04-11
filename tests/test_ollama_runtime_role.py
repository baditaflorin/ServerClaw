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
    assert defaults["ollama_runtime_compose_project_name"] == "{{ ollama_runtime_site_dir | basename }}"
    assert defaults["ollama_runtime_default_model"] == "llama3.2:3b"
    assert defaults["ollama_runtime_image_pull_retries"] == 3
    assert defaults["ollama_runtime_image_pull_delay_seconds"] == 15


def test_role_retries_transient_ollama_image_pull_failures() -> None:
    tasks = load_tasks()
    pull_task = next(task for task in tasks if task.get("name") == "Pull the Ollama image")
    assert pull_task["ansible.builtin.command"]["argv"] == [
        "docker",
        "compose",
        "--file",
        "{{ ollama_runtime_compose_file }}",
        "pull",
    ]
    assert pull_task["retries"] == "{{ ollama_runtime_image_pull_retries }}"
    assert pull_task["delay"] == "{{ ollama_runtime_image_pull_delay_seconds }}"
    assert pull_task["until"] == "ollama_runtime_pull.rc == 0"


def test_role_only_pulls_missing_startup_models_inside_container() -> None:
    tasks = load_tasks()
    check_task = next(
        task for task in tasks if task.get("name") == "Check whether declared startup Ollama models are already present"
    )
    partial_find_task = next(
        task
        for task in tasks
        if task.get("name") == "Find stale Ollama partial blobs before pulling missing startup models"
    )
    partial_remove_task = next(
        task
        for task in tasks
        if task.get("name") == "Remove stale Ollama partial blobs before pulling missing startup models"
    )
    pull_task = next(
        task for task in tasks if task.get("name") == "Pull the missing startup Ollama models from inside the container"
    )
    assert check_task["ansible.builtin.command"]["argv"][-2:] == ["show", "{{ item }}"]
    assert partial_find_task["ansible.builtin.find"]["paths"] == "{{ ollama_runtime_model_dir }}/models/blobs"
    assert partial_find_task["ansible.builtin.find"]["patterns"] == "sha256-*-partial*"
    assert partial_remove_task["ansible.builtin.file"]["state"] == "absent"
    assert pull_task["ansible.builtin.command"]["argv"] == [
        "docker",
        "exec",
        "{{ ollama_runtime_container_name }}",
        "ollama",
        "pull",
        "{{ item }}",
    ]
    assert pull_task["retries"] == 3
    assert pull_task["delay"] == 10


def test_role_verifies_default_model_inside_container() -> None:
    tasks = load_tasks()
    verify_task = next(task for task in tasks if task.get("name") == "Verify the default Ollama model is present")
    assert verify_task["ansible.builtin.command"]["argv"][-2:] == ["show", "{{ ollama_runtime_default_model }}"]


def test_role_recovers_missing_docker_nat_chain_before_startup() -> None:
    tasks = load_tasks()
    precheck_task = next(
        task for task in tasks if task.get("name") == "Check whether Docker nat chain exists before Ollama startup"
    )
    assert precheck_task["ansible.builtin.command"]["argv"] == ["iptables", "-t", "nat", "-S", "DOCKER"]

    start_block = next(
        task
        for task in tasks
        if task.get("name") == "Start the Ollama runtime and recover Docker nat-chain and compose-network failures"
    )
    rescue_names = [task["name"] for task in start_block["rescue"]]
    assert "Reset stale Ollama compose resources after startup failure" in rescue_names
    assert "Restart Docker to restore nat chain before retrying Ollama startup" in rescue_names
    assert "Remove the stale Ollama compose network before retrying startup" in rescue_names
    assert "Retry Ollama startup after Docker nat-chain or compose-network recovery" in rescue_names


def test_role_force_recreates_ollama_when_port_binding_is_missing() -> None:
    tasks = load_tasks()
    port_check = next(
        task for task in tasks if task.get("name") == "Check whether Ollama publishes the expected host port"
    )
    assert port_check["ansible.builtin.command"]["argv"] == [
        "docker",
        "port",
        "{{ ollama_runtime_container_name }}",
        "{{ ollama_runtime_port }}",
    ]

    recreate_block = next(
        task
        for task in tasks
        if task.get("name")
        == "Force-recreate Ollama when the host port binding is missing and recover stale Docker networking drift"
    )
    recreate_task = next(
        task
        for task in recreate_block["block"]
        if task.get("name") == "Force-recreate Ollama when the host port binding is missing"
    )
    rescue_names = [task["name"] for task in recreate_block["rescue"]]

    assert "--force-recreate" in recreate_task["ansible.builtin.command"]["argv"]
    assert "Detect stale Docker networking drift during Ollama force-recreate" in rescue_names
    assert "Remove the stale Ollama compose network before retrying force-recreate" in rescue_names
    assert "Retry Ollama force-recreate after Docker networking recovery" in rescue_names


def test_compose_template_exposes_private_runtime_port_and_model_volume() -> None:
    template = COMPOSE_TEMPLATE.read_text()
    assert '"{{ ollama_runtime_port }}:11434"' in template
    assert "{{ ollama_runtime_model_dir }}:/root/.ollama" in template


def test_host_network_policy_allows_private_ollama_access() -> None:
    host_vars = yaml.safe_load((REPO_ROOT / "inventory" / "host_vars" / "proxmox-host.yml").read_text())
    docker_runtime_rules = host_vars["network_policy"]["guests"]["docker-runtime"]["allowed_inbound"]
    guest_rule = next(
        rule for rule in docker_runtime_rules if rule["source"] == "all_guests" and 11434 in rule["ports"]
    )
    assert 11434 in guest_rule["ports"]
