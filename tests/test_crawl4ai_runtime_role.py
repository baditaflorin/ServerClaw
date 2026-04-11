import json
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_TASKS = REPO_ROOT / "roles" / "crawl4ai_runtime" / "tasks" / "main.yml"
ROLE_VERIFY = REPO_ROOT / "roles" / "crawl4ai_runtime" / "tasks" / "verify.yml"
ROLE_DEFAULTS = REPO_ROOT / "roles" / "crawl4ai_runtime" / "defaults" / "main.yml"
ROLE_META = REPO_ROOT / "roles" / "crawl4ai_runtime" / "meta" / "argument_specs.yml"
COMPOSE_TEMPLATE = REPO_ROOT / "roles" / "crawl4ai_runtime" / "templates" / "docker-compose.yml.j2"
CONFIG_TEMPLATE = REPO_ROOT / "roles" / "crawl4ai_runtime" / "templates" / "config.yml.j2"
PLAYBOOK_PATH = REPO_ROOT / "playbooks" / "crawl4ai.yml"
SERVICE_WRAPPER_PATH = REPO_ROOT / "playbooks" / "services" / "crawl4ai.yml"
HOST_VARS_PATH = REPO_ROOT / "inventory" / "host_vars" / "proxmox-host.yml"
WORKFLOW_CATALOG_PATH = REPO_ROOT / "config" / "workflow-catalog.json"
COMMAND_CATALOG_PATH = REPO_ROOT / "config" / "command-catalog.json"
ANSIBLE_EXECUTION_SCOPES_PATH = REPO_ROOT / "config" / "ansible-execution-scopes.yaml"


def load_yaml(path: Path) -> list[dict] | dict:
    return yaml.safe_load(path.read_text())


def test_defaults_define_private_runtime_port_and_crawl_contract() -> None:
    defaults = yaml.safe_load(ROLE_DEFAULTS.read_text())

    assert defaults["crawl4ai_runtime_site_dir"] == "/opt/crawl4ai"
    assert defaults["crawl4ai_runtime_config_dir"] == "/etc/lv3/crawl4ai"
    assert defaults["crawl4ai_runtime_container_name"] == "crawl4ai"
    assert defaults["crawl4ai_runtime_container_port"] == 11235
    assert defaults["crawl4ai_runtime_healthcheck_path"] == "/health"
    assert defaults["crawl4ai_runtime_monitor_health_path"] == "/monitor/health"
    assert defaults["crawl4ai_runtime_pull_retries"] == 4
    assert defaults["crawl4ai_runtime_pull_delay_seconds"] == 10
    assert defaults["crawl4ai_runtime_memory_limit"] == "4g"
    assert defaults["crawl4ai_runtime_cpu_limit"] == "2.0"
    assert defaults["crawl4ai_runtime_shm_size"] == "1g"
    assert defaults["crawl4ai_runtime_rate_limit"] == "120/minute"
    assert defaults["crawl4ai_runtime_verify_url"] == "https://example.com/"
    assert defaults["crawl4ai_runtime_pool_max_pages"] == 10
    assert defaults["crawl4ai_runtime_pool_idle_ttl_seconds"] == 300


def test_argument_spec_requires_runtime_urls_limits_and_verification_inputs() -> None:
    specs = yaml.safe_load(ROLE_META.read_text())
    options = specs["argument_specs"]["main"]["options"]

    assert options["crawl4ai_runtime_port"]["type"] == "int"
    assert options["crawl4ai_runtime_internal_base_url"]["type"] == "str"
    assert options["crawl4ai_runtime_local_base_url"]["type"] == "str"
    assert options["crawl4ai_runtime_monitor_health_path"]["type"] == "str"
    assert options["crawl4ai_runtime_pull_retries"]["type"] == "int"
    assert options["crawl4ai_runtime_pull_delay_seconds"]["type"] == "int"
    assert options["crawl4ai_runtime_pool_max_pages"]["type"] == "int"
    assert options["crawl4ai_runtime_pool_idle_ttl_seconds"]["type"] == "int"
    assert options["crawl4ai_runtime_memory_limit"]["type"] == "str"
    assert options["crawl4ai_runtime_cpu_limit"]["type"] == "str"
    assert options["crawl4ai_runtime_verify_url"]["type"] == "str"


def test_main_tasks_render_config_compose_and_verify_runtime() -> None:
    tasks = yaml.safe_load(ROLE_TASKS.read_text())
    names = [task["name"] for task in tasks]

    assert "Render the Crawl4AI config file" in names
    assert "Render the Crawl4AI compose file" in names
    assert "Pull the Crawl4AI image" in names
    assert "Wait for the Crawl4AI health endpoint" in names
    assert "Verify the Crawl4AI runtime" in names
    pull_task = next(task for task in tasks if task["name"] == "Pull the Crawl4AI image")
    assert pull_task["retries"] == "{{ crawl4ai_runtime_pull_retries }}"
    assert pull_task["delay"] == "{{ crawl4ai_runtime_pull_delay_seconds }}"
    assert pull_task["until"] == "crawl4ai_runtime_pull.rc == 0"
    assert "Build the Crawl4AI compose startup command" in names
    startup_task = next(task for task in tasks if task["name"] == "Ensure the Crawl4AI runtime is running")
    start_command = next(task for task in startup_task["block"] if task["name"] == "Start the Crawl4AI runtime")
    rescue_names = [task["name"] for task in startup_task["rescue"]]
    recovery_fact = next(
        task
        for task in startup_task["rescue"]
        if task["name"] == "Flag stale Crawl4AI Docker bridge-network startup failures"
    )
    reset_task = next(
        task
        for task in startup_task["rescue"]
        if task["name"] == "Reset stale Crawl4AI compose resources after bridge-network startup failure"
    )
    restart_docker = next(
        task
        for task in startup_task["rescue"]
        if task["name"] == "Restart Docker to restore bridge networking before retrying Crawl4AI startup"
    )
    reassert_chains = next(
        task
        for task in startup_task["rescue"]
        if task["name"] == "Ensure Docker bridge networking chains are present before retrying Crawl4AI startup"
    )
    docker_info = next(
        task
        for task in startup_task["rescue"]
        if task["name"] == "Wait for the Docker daemon to answer after Crawl4AI bridge-network recovery"
    )
    remove_broken_container = next(
        task
        for task in startup_task["rescue"]
        if task["name"] == "Remove the broken Crawl4AI container before retrying startup"
    )
    retry_task = next(
        task
        for task in startup_task["rescue"]
        if task["name"] == "Retry Crawl4AI startup after stale bridge-network cleanup"
    )
    assert start_command["ansible.builtin.command"]["argv"] == "{{ crawl4ai_runtime_compose_up_argv }}"
    assert "Flag stale Crawl4AI Docker bridge-network startup failures" in rescue_names
    assert "Surface unexpected Crawl4AI startup failures" in rescue_names
    assert "Reset stale Crawl4AI compose resources after bridge-network startup failure" in rescue_names
    assert "Restart Docker to restore bridge networking before retrying Crawl4AI startup" in rescue_names
    assert "Ensure Docker bridge networking chains are present before retrying Crawl4AI startup" in rescue_names
    assert "Wait for the Docker daemon to answer after Crawl4AI bridge-network recovery" in rescue_names
    assert "Remove the broken Crawl4AI container before retrying startup" in rescue_names
    assert "Retry Crawl4AI startup after stale bridge-network cleanup" in rescue_names
    assert (
        "failed to set up container networking"
        in recovery_fact["ansible.builtin.set_fact"]["crawl4ai_runtime_bridge_network_missing"]
    )
    assert (
        "failed to create endpoint"
        in recovery_fact["ansible.builtin.set_fact"]["crawl4ai_runtime_bridge_network_missing"]
    )
    assert "does not exist" in recovery_fact["ansible.builtin.set_fact"]["crawl4ai_runtime_bridge_network_missing"]
    assert (
        "No chain/target/match by that name"
        in recovery_fact["ansible.builtin.set_fact"]["crawl4ai_runtime_bridge_network_missing"]
    )
    assert reset_task["ansible.builtin.command"]["argv"][-2:] == ["down", "--remove-orphans"]
    assert reset_task["failed_when"] is False
    assert restart_docker["ansible.builtin.service"] == {"name": "docker", "state": "restarted"}
    include_role = reassert_chains["ansible.builtin.include_role"]
    assert include_role["name"] == "lv3.platform.common"
    assert include_role["tasks_from"] == "docker_bridge_chains"
    assert reassert_chains["vars"]["common_docker_bridge_chains_service_name"] == "docker"
    assert reassert_chains["vars"]["common_docker_bridge_chains_require_nat_chain"] is True
    assert docker_info["ansible.builtin.command"]["argv"] == [
        "docker",
        "info",
        "--format",
        '{{ "{{.ServerVersion}}" }}',
    ]
    assert docker_info["until"] == "crawl4ai_runtime_docker_info.rc == 0"
    assert remove_broken_container["ansible.builtin.command"]["argv"] == [
        "docker",
        "rm",
        "-f",
        "{{ crawl4ai_runtime_container_name }}",
    ]
    assert remove_broken_container["failed_when"] is False
    assert retry_task["ansible.builtin.command"]["argv"][-4:] == ["up", "-d", "--force-recreate", "--remove-orphans"]
    port_check = next(
        task for task in tasks if task["name"] == "Check whether Crawl4AI publishes the expected host port"
    )
    assert port_check["ansible.builtin.command"]["argv"] == [
        "docker",
        "port",
        "{{ crawl4ai_runtime_container_name }}",
        "{{ crawl4ai_runtime_container_port }}/tcp",
    ]


def test_verify_tasks_cover_health_monitor_playground_and_markdown_smoke() -> None:
    verify = yaml.safe_load(ROLE_VERIFY.read_text())
    names = [task["name"] for task in verify]

    assert "Verify the Crawl4AI health endpoint responds locally" in names
    assert "Verify the Crawl4AI monitoring endpoint reports an active browser pool" in names
    assert "Verify the Crawl4AI playground responds locally" in names
    assert "Verify the Crawl4AI markdown endpoint returns cleaned content for the runbook smoke URL" in names
    markdown_task = next(
        task
        for task in verify
        if task["name"] == "Verify the Crawl4AI markdown endpoint returns cleaned content for the runbook smoke URL"
    )
    assert markdown_task["ansible.builtin.uri"]["url"] == "{{ crawl4ai_runtime_local_base_url }}/md"
    assert markdown_task["ansible.builtin.uri"]["body"] == {"url": "{{ crawl4ai_runtime_verify_url }}"}


def test_compose_template_publishes_private_port_mounts_config_and_sets_shm() -> None:
    template = COMPOSE_TEMPLATE.read_text()

    assert "network_mode: bridge" not in template
    assert "networks:" in template
    assert "- runtime" in template
    assert "driver: bridge" in template
    assert '"{{ crawl4ai_runtime_port }}:{{ crawl4ai_runtime_container_port }}"' in template
    assert "{{ crawl4ai_runtime_config_file }}:/app/config.yml:ro" in template
    assert "shm_size: {{ crawl4ai_runtime_shm_size }}" in template
    assert "mem_limit: {{ crawl4ai_runtime_memory_limit }}" in template
    assert 'cpus: "{{ crawl4ai_runtime_cpu_limit }}"' in template


def test_config_template_enables_rate_limiting_and_observability() -> None:
    template = CONFIG_TEMPLATE.read_text()

    assert 'host: "0.0.0.0"' in template
    assert 'provider: "openai/gpt-4o-mini"' in template
    assert "pool:" in template
    assert "max_pages: {{ crawl4ai_runtime_pool_max_pages }}" in template
    assert "idle_ttl_sec: {{ crawl4ai_runtime_pool_idle_ttl_seconds }}" in template
    assert "browser:" in template
    assert "headless: true" in template
    assert 'default_limit: "{{ crawl4ai_runtime_rate_limit }}"' in template
    assert 'storage_uri: "memory://"' in template
    assert 'endpoint: "/metrics"' in template
    assert 'endpoint: "{{ crawl4ai_runtime_healthcheck_path }}"' in template
    assert "memory_threshold_percent" in template


def test_playbook_converges_runtime_without_api_gateway_route() -> None:
    playbook = load_yaml(PLAYBOOK_PATH)

    assert len(playbook) == 1
    play = playbook[0]
    assert play["hosts"] == "docker-runtime"
    roles = [role["role"] for role in play["roles"]]
    assert roles == [
        "lv3.platform.linux_guest_firewall",
        "lv3.platform.docker_runtime",
        "lv3.platform.crawl4ai_runtime",
    ]


def test_service_wrapper_imports_the_canonical_playbook() -> None:
    wrapper = load_yaml(SERVICE_WRAPPER_PATH)
    assert wrapper == [{"import_playbook": "../crawl4ai.yml"}]


def test_inventory_opens_the_private_crawl_port_to_guest_and_docker_callers() -> None:
    host_vars = yaml.safe_load(HOST_VARS_PATH.read_text())

    assert host_vars["platform_port_assignments"]["crawl4ai_port"] == 11235
    docker_runtime_rules = host_vars["network_policy"]["guests"]["docker-runtime"]["allowed_inbound"]
    guest_rule = next(
        rule for rule in docker_runtime_rules if rule["source"] == "all_guests" and 11235 in rule["ports"]
    )
    assert 11235 in guest_rule["ports"]
    docker_rule = next(
        rule for rule in docker_runtime_rules if rule["source"] == "172.16.0.0/12" and 11235 in rule["ports"]
    )
    assert 11235 in docker_rule["ports"]


def test_workflow_and_command_catalogs_declare_converge_entrypoint() -> None:
    workflow_catalog = json.loads(WORKFLOW_CATALOG_PATH.read_text())
    command_catalog = json.loads(COMMAND_CATALOG_PATH.read_text())

    workflow = workflow_catalog["workflows"]["converge-crawl4ai"]
    command = command_catalog["commands"]["converge-crawl4ai"]

    assert workflow["preferred_entrypoint"] == {
        "kind": "make_target",
        "target": "converge-crawl4ai",
        "command": "make converge-crawl4ai",
    }
    assert "syntax-check-crawl4ai" in workflow["validation_targets"]
    assert workflow["owner_runbook"] == "docs/runbooks/configure-crawl4ai.md"
    assert command["workflow_id"] == "converge-crawl4ai"
    assert command["approval_policy"] == "sensitive_live_change"
    assert command["evidence"]["live_apply_receipt_required"] is True


def test_ansible_execution_scopes_registers_the_direct_crawl4ai_playbook() -> None:
    scopes = yaml.safe_load(ANSIBLE_EXECUTION_SCOPES_PATH.read_text())
    entry = scopes["playbooks"]["playbooks/crawl4ai.yml"]

    assert entry["playbook_id"] == "crawl4ai"
    assert entry["mutation_scope"] == "host"
    assert "service:crawl4ai" in entry["shared_surfaces"]
