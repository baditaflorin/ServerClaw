from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_DEFAULTS = REPO_ROOT / "roles" / "searxng_runtime" / "defaults" / "main.yml"
ROLE_TASKS = REPO_ROOT / "roles" / "searxng_runtime" / "tasks" / "main.yml"
VERIFY_TASKS = REPO_ROOT / "roles" / "searxng_runtime" / "tasks" / "verify.yml"
SETTINGS_TEMPLATE = REPO_ROOT / "roles" / "searxng_runtime" / "templates" / "settings.yml.j2"
COMPOSE_TEMPLATE = REPO_ROOT / "roles" / "searxng_runtime" / "templates" / "docker-compose.yml.j2"
LIMITER_TEMPLATE = REPO_ROOT / "roles" / "searxng_runtime" / "templates" / "limiter.toml.j2"


def load_tasks(path: Path) -> list[dict]:
    return yaml.safe_load(path.read_text())


def test_role_defaults_pin_expected_runtime_paths() -> None:
    defaults = yaml.safe_load(ROLE_DEFAULTS.read_text())
    assert defaults["searxng_runtime_site_dir"] == "/opt/searxng"
    assert defaults["searxng_runtime_config_dir"] == "/etc/searxng"
    assert defaults["searxng_runtime_cache_dir"] == "/data/searxng/cache"
    assert defaults["searxng_runtime_limiter_file"] == "{{ searxng_runtime_config_dir }}/limiter.toml"
    assert (
        defaults["searxng_runtime_public_base_url"]
        == "{{ platform_service_topology.searxng.urls.public | default(searxng_runtime_controller_url) }}"
    )


def test_role_generates_and_mirrors_stable_secret_key() -> None:
    tasks = load_tasks(ROLE_TASKS)
    generate_task = next(task for task in tasks if task.get("name") == "Generate the SearXNG secret key")
    mirror_task = next(
        task for task in tasks if task.get("name") == "Mirror the SearXNG secret key to the control machine"
    )
    assert "openssl rand -hex 32" in generate_task["ansible.builtin.shell"]
    assert mirror_task["ansible.builtin.copy"]["dest"] == "{{ searxng_runtime_secret_key_local_file }}"


def test_settings_template_enables_json_search_and_valkey_backing() -> None:
    template = SETTINGS_TEMPLATE.read_text()
    assert "limiter: {{ searxng_runtime_enable_limiter | bool | lower }}" in template
    assert "- json" in template
    assert "valkey://valkey:6379/0" in template
    assert 'instance_name: "{{ searxng_runtime_instance_name }}"' in template


def test_compose_template_runs_valkey_sidecar_and_private_http_port() -> None:
    template = COMPOSE_TEMPLATE.read_text()
    assert "image: {{ searxng_runtime_valkey_image }}" in template
    assert "container_name: {{ searxng_runtime_valkey_container_name }}" in template
    assert "valkey-cli" in template
    assert "condition: service_healthy" in template
    assert '"{{ searxng_runtime_port }}:8080"' in template
    assert "{{ searxng_runtime_config_dir }}:/etc/searxng" in template


def test_limiter_template_passlists_private_networks() -> None:
    template = LIMITER_TEMPLATE.read_text()
    assert "trusted_proxies = [" in template
    assert "pass_ip = [" in template
    assert "searxng_runtime_pass_ip_ranges" in template
    assert "100.64.0.0/10" in yaml.safe_load(ROLE_DEFAULTS.read_text())["searxng_runtime_pass_ip_ranges"]


def test_verify_tasks_hit_root_and_json_search_endpoints() -> None:
    verify_tasks = load_tasks(VERIFY_TASKS)
    root_task = next(task for task in verify_tasks if task.get("name") == "Verify the SearXNG root page responds")
    search_task = next(
        task for task in verify_tasks if task.get("name") == "Verify the SearXNG JSON search endpoint responds"
    )
    assert root_task["ansible.builtin.uri"]["url"] == "{{ searxng_runtime_internal_base_url }}"
    assert "format=json" in search_task["ansible.builtin.uri"]["url"]


def test_host_network_policy_allows_private_searxng_access() -> None:
    host_vars = yaml.safe_load((REPO_ROOT / "inventory" / "host_vars" / "proxmox_florin.yml").read_text())
    docker_runtime_rules = host_vars["network_policy"]["guests"]["docker-runtime-lv3"]["allowed_inbound"]
    host_rule = next(rule for rule in docker_runtime_rules if rule["source"] == "host")
    guest_rule = next(rule for rule in docker_runtime_rules if rule["source"] == "all_guests" and 8881 in rule["ports"])
    assert 8881 in host_rule["ports"]
    assert 8881 in guest_rule["ports"]
