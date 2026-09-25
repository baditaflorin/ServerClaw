from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_ROOT = REPO_ROOT / "collections" / "ansible_collections" / "lv3" / "platform" / "roles" / "artifact_cache_runtime"
HOST_VARS_PATH = REPO_ROOT / "inventory" / "host_vars" / "proxmox-host.yml"
PROXMOX_NETWORK_TEMPLATE_ROOT = (
    REPO_ROOT / "collections" / "ansible_collections" / "lv3" / "platform" / "roles" / "proxmox_network" / "templates"
)


def test_artifact_cache_defaults_define_four_upstream_mirrors() -> None:
    defaults = yaml.safe_load((ROLE_ROOT / "defaults" / "main.yml").read_text())
    mirrors = defaults["artifact_cache_registry_mirrors"]
    assert defaults["artifact_cache_state"] == "present"
    assert defaults["artifact_cache_network_mode"] == "host"
    assert list(mirrors.keys()) == ["docker_io", "ghcr_io", "artifacts_plane_so", "docker_n8n_io"]
    assert mirrors["docker_io"]["upstream_registry"] == "https://registry-1.docker.io"
    assert mirrors["ghcr_io"]["bind_port"] == 5002
    assert mirrors["docker_io"]["mirror_registry"] == "{{ artifact_cache_bind_host }}:5001"


def test_private_ghcr_upstream_auth_is_opt_in_and_cache_only() -> None:
    defaults = yaml.safe_load((ROLE_ROOT / "defaults" / "main.yml").read_text())
    argument_specs = yaml.safe_load((ROLE_ROOT / "meta" / "argument_specs.yml").read_text())

    assert defaults["artifact_cache_ghcr_private_packages_enabled"] is False
    assert defaults["artifact_cache_ghcr_private_proxy_config_file"] == "/etc/artifact-cache/ghcr-proxy/config.yml"
    assert defaults["artifact_cache_ghcr_private_proxy_config_parent_dirs"] == [
        "/etc/artifact-cache",
        "/etc/artifact-cache/ghcr-proxy",
    ]
    assert defaults["artifact_cache_ghcr_private_listener_host"] == "127.0.0.1"
    assert defaults["artifact_cache_ghcr_private_listener_port"] == 5005
    assert defaults["artifact_cache_ghcr_private_storage_path"] == "{{ artifact_cache_data_root }}/ghcr-private"
    options = argument_specs["argument_specs"]["main"]["options"]
    assert options["artifact_cache_ghcr_private_packages_enabled"]["type"] == "bool"
    assert options["artifact_cache_ghcr_private_proxy_config_file"]["type"] == "path"
    assert options["artifact_cache_ghcr_private_listener_host"]["type"] == "str"
    assert options["artifact_cache_ghcr_private_listener_port"]["type"] == "int"
    assert options["artifact_cache_ghcr_private_storage_path"]["type"] == "path"


def test_artifact_cache_tasks_render_seed_plan_then_warm_images() -> None:
    tasks = yaml.safe_load((ROLE_ROOT / "tasks" / "main.yml").read_text())
    task_names = [task["name"] for task in tasks]
    assert "Stop the artifact cache stack when state=absent" in task_names
    assert "Wait for artifact cache listeners to stop when state=absent" in task_names
    assert "Wait for the private GHCR loopback listener to stop when state=absent" in task_names
    assert "Generate the artifact cache seed plan from repo catalogs" in task_names
    assert "Persist the artifact cache seed plan on the guest" in task_names
    assert "Warm the mirrored image set through the cache endpoints" in task_names


def test_private_ghcr_auth_fails_closed_without_a_root_only_regular_file() -> None:
    tasks = yaml.safe_load((ROLE_ROOT / "tasks" / "main.yml").read_text())
    by_name = {task["name"]: task for task in tasks}

    boundary = by_name["Validate the private GHCR cache boundary when enabled"]
    assert boundary["when"] == [
        "artifact_cache_state == 'present'",
        "artifact_cache_ghcr_private_packages_enabled | bool",
    ]
    assert (
        "artifact_cache_registry_mirrors.ghcr_io.service_name == 'ghcr'" in boundary["ansible.builtin.assert"]["that"]
    )
    assert "artifact_cache_registry_mirrors.ghcr_io.bind_port == 5002" in boundary["ansible.builtin.assert"]["that"]
    assert "artifact_cache_ghcr_private_listener_host == '127.0.0.1'" in boundary["ansible.builtin.assert"]["that"]
    assert "artifact_cache_ghcr_private_listener_port | int == 5005" in boundary["ansible.builtin.assert"]["that"]
    assert (
        "artifact_cache_ghcr_private_storage_path == (artifact_cache_data_root ~ '/ghcr-private')"
        in boundary["ansible.builtin.assert"]["that"]
    )

    inspect = by_name["Inspect the cache-owned rendered GHCR proxy configuration"]
    inspect_parents = by_name["Inspect the fixed parent directories for the private GHCR configuration"]
    require_parents = by_name["Require root-only non-symlink parent directories for private GHCR configuration"]
    require = by_name["Require a root-only regular GHCR proxy configuration"]
    assert inspect["no_log"] is True
    assert require["no_log"] is True
    required_checks = require["ansible.builtin.assert"]["that"]
    assert "artifact_cache_ghcr_private_proxy_config_stat.stat.isreg" in required_checks
    assert "not artifact_cache_ghcr_private_proxy_config_stat.stat.islnk" in required_checks
    assert "artifact_cache_ghcr_private_proxy_config_stat.stat.uid == 0" in required_checks
    assert "artifact_cache_ghcr_private_proxy_config_stat.stat.gid == 0" in required_checks
    assert "artifact_cache_ghcr_private_proxy_config_stat.stat.mode == '0400'" in required_checks
    assert inspect_parents["loop"] == "{{ artifact_cache_ghcr_private_proxy_config_parent_dirs }}"
    assert require_parents["loop"] == "{{ artifact_cache_ghcr_private_proxy_parent_stats.results }}"
    parent_checks = require_parents["ansible.builtin.assert"]["that"]
    assert "item.stat.isdir" in parent_checks
    assert "not item.stat.islnk" in parent_checks
    assert "item.stat.uid == 0" in parent_checks
    assert "item.stat.gid == 0" in parent_checks
    assert "item.stat.mode == '0700'" in parent_checks

    private_storage = by_name["Ensure private GHCR cache storage is root-only"]
    assert private_storage["ansible.builtin.file"]["path"] == "{{ artifact_cache_ghcr_private_storage_path }}"
    assert private_storage["ansible.builtin.file"]["mode"] == "0700"


def test_artifact_cache_compose_template_exposes_proxy_remote_urls() -> None:
    template = (ROLE_ROOT / "templates" / "docker-compose.yml.j2").read_text()
    assert "REGISTRY_PROXY_REMOTEURL" in template
    assert "network_mode: {{ artifact_cache_network_mode }}" in template
    assert (
        "REGISTRY_HTTP_ADDR: 0.0.0.0:{{ (artifact_cache_network_mode == 'host') | ternary(mirror.bind_port, 5000) }}"
        in template
    )
    assert "{% if artifact_cache_network_mode != 'host' %}" in template
    assert "{{ mirror.storage_path }}:/var/lib/registry" in template


def test_private_ghcr_auth_mount_is_read_only_and_exclusive_to_a_loopback_only_service() -> None:
    template = (ROLE_ROOT / "templates" / "docker-compose.yml.j2").read_text()

    public_adapter, private_adapter = template.split(
        "{% if artifact_cache_ghcr_private_packages_enabled | bool %}", maxsplit=1
    )
    assert "artifact-cache-ghcr-private" not in public_adapter
    assert "artifact_cache_ghcr_private_proxy_config_file" not in public_adapter
    assert "artifact-cache-ghcr-private" in private_adapter
    assert "network_mode:" not in private_adapter
    assert (
        '"{{ artifact_cache_ghcr_private_listener_host }}:{{ artifact_cache_ghcr_private_listener_port }}:5000"'
        in private_adapter
    )
    assert "{{ artifact_cache_ghcr_private_storage_path }}:/var/lib/registry" in private_adapter
    assert "{{ artifact_cache_ghcr_private_proxy_config_file }}:/etc/docker/registry/config.yml:ro" in template
    assert "io.lv3.platform.ghcr-private-proxy-config-mtime" in template
    assert "REGISTRY_PROXY_USERNAME" not in template
    assert "REGISTRY_PROXY_PASSWORD" not in template


def test_private_ghcr_docs_require_atomic_cache_only_vault_delivery() -> None:
    role_readme = (ROLE_ROOT / "README.md").read_text()
    runbook = (REPO_ROOT / "docs" / "runbooks" / "artifact-cache-runtime.md").read_text()

    for document in (role_readme, runbook):
        assert "artifact-cache-ghcr-renderer" in document
        assert "artifact_cache_ghcr_proxy_config" in document
        assert "no api key" in document.lower()
    assert "atomically replaces" in runbook
    assert "proxy.remoteurl: https://ghcr.io" in runbook
    assert "password: <cache-only-package-read-secret>" in runbook


def test_artifact_cache_network_policy_allows_runtime_consumers() -> None:
    host_vars = yaml.safe_load(HOST_VARS_PATH.read_text())
    artifact_cache_rules = host_vars["network_policy"]["guests"]["artifact-cache"]["allowed_inbound"]
    cache_sources = {
        rule["source"] for rule in artifact_cache_rules if {5001, 5002, 5003, 5004} & set(rule.get("ports", []))
    }

    assert {"docker-runtime", "172.16.0.0/12", "192.168.0.0/16"} <= cache_sources
    assert all(5005 not in rule.get("ports", []) for rule in artifact_cache_rules)


def test_proxmox_vm_firewall_renders_cache_ports_for_concrete_guest_sources_only() -> None:
    template = (PROXMOX_NETWORK_TEMPLATE_ROOT / "vm.fw.j2").read_text()

    assert "guest_local_only_sources = ['172.16.0.0/12', '192.168.0.0/16']" in template
    assert (
        "not (guest_policy.allow_container_forwarding | default(false) and rule.source in guest_local_only_sources)"
        in template
    )
