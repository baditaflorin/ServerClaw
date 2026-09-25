import json
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_ROOT = (
    REPO_ROOT / "collections" / "ansible_collections" / "lv3" / "platform" / "roles" / "fleet_build_broker_runtime"
)
PLAYBOOK_PATH = REPO_ROOT / "playbooks" / "fleet-build-broker.yml"
COLLECTION_PLAYBOOK_PATH = (
    REPO_ROOT / "collections" / "ansible_collections" / "lv3" / "platform" / "playbooks" / "fleet-build-broker.yml"
)
ENDPOINTS_PATH = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "vars"
    / "artifact_cache_registry_endpoints.yml"
)
HOST_VARS_PATH = REPO_ROOT / "inventory" / "host_vars" / "proxmox-host.yml"


def _render_compose_for_assertion(template: str) -> dict:
    replacements = {
        "{{ lookup('env', 'LV3_AGENT_SESSION') | default('operator', true) }}": "test",
        "{{ fleet_build_broker_renderer_image }}": "10.10.10.80:5002/baditaflorin/go-fleet-build-broker@sha256:"
        + "a" * 64,
        "{{ fleet_build_broker_runtime_renderer_container_name }}": "fleet-build-broker-render-runtime-secrets",
        "{{ fleet_build_broker_monitor_renderer_container_name }}": "fleet-build-broker-render-monitor-secrets",
        "{{ fleet_build_broker_container_name }}": "fleet-build-broker",
        "{{ fleet_build_broker_runtime_renderer_command | to_json }}": json.dumps(
            ["render-secrets", "--target", "runtime"]
        ),
        "{{ fleet_build_broker_monitor_renderer_command | to_json }}": json.dumps(
            ["render-secrets", "--target", "monitor"]
        ),
        "{{ fleet_build_broker_runtime_renderer_api_key_dir }}": "/etc/fleet-build-broker/renderer/runtime",
        "{{ fleet_build_broker_runtime_renderer_api_key_mount }}": "/run/broker-runtime-renderer-api-key",
        "{{ fleet_build_broker_monitor_renderer_api_key_dir }}": "/etc/fleet-build-broker/renderer/monitor",
        "{{ fleet_build_broker_monitor_renderer_api_key_mount }}": "/run/broker-monitor-renderer-api-key",
        "{{ fleet_build_broker_runtime_renderer_manifest_file }}": "/opt/fleet-build-broker/renderer-manifests/runtime.json",
        "{{ fleet_build_broker_runtime_renderer_manifest_mount }}": "/run/broker-runtime-renderer-manifest/runtime.json",
        "{{ fleet_build_broker_monitor_renderer_manifest_file }}": "/opt/fleet-build-broker/renderer-manifests/monitor.json",
        "{{ fleet_build_broker_monitor_renderer_manifest_mount }}": "/run/broker-monitor-renderer-manifest/monitor.json",
        "{{ fleet_build_broker_data_dir }}": "/var/lib/fleet-build-broker",
        "{{ fleet_build_broker_secret_dir }}": "/run/go-fleet-secrets/fleet-build-broker",
        "{{ fleet_build_broker_secret_mount }}": "/run/broker-secrets",
        "{{ fleet_build_broker_probe_secret_dir }}": "/run/go-fleet-secrets/fleet-build-broker-probe",
        "{{ fleet_build_broker_image }}": "10.10.10.80:5002/baditaflorin/go-fleet-build-broker@sha256:" + "a" * 64,
        "{{ fleet_build_broker_container_uid }}": "10001",
        "{{ fleet_build_broker_container_gid }}": "10001",
        "{{ fleet_build_broker_bind_host }}": "10.10.10.80",
        "{{ fleet_build_broker_host_port }}": "18100",
        "{{ fleet_build_broker_container_port }}": "5001",
    }
    rendered = template
    for source, target in replacements.items():
        rendered = rendered.replace(source, target)
    assert "{{" not in rendered
    return yaml.safe_load(rendered)


def test_broker_defaults_require_cache_only_image_and_two_principal_renderer_contract() -> None:
    defaults = yaml.safe_load((ROLE_ROOT / "defaults" / "main.yml").read_text())

    assert defaults["fleet_build_broker_image"] == ""
    assert defaults["fleet_build_broker_renderer_image"] == "{{ fleet_build_broker_image }}"
    assert defaults["fleet_build_broker_image_mirror"] == "127.0.0.1:5005"
    assert defaults["fleet_build_broker_secret_dir"] == "/run/go-fleet-secrets/fleet-build-broker"
    assert defaults["fleet_build_broker_probe_secret_dir"] == "/run/go-fleet-secrets/fleet-build-broker-probe"
    assert defaults["fleet_build_broker_runtime_renderer_api_key_file"] == (
        "{{ fleet_build_broker_runtime_renderer_api_key_dir }}/api-key"
    )
    assert defaults["fleet_build_broker_monitor_renderer_api_key_file"] == (
        "{{ fleet_build_broker_monitor_renderer_api_key_dir }}/api-key"
    )
    assert defaults["fleet_build_broker_runtime_renderer_manifest_mount"] == (
        "/run/broker-runtime-renderer-manifest/runtime.json"
    )
    assert defaults["fleet_build_broker_monitor_renderer_manifest_mount"] == (
        "/run/broker-monitor-renderer-manifest/monitor.json"
    )
    assert defaults["fleet_build_broker_host_port"] == 18100
    assert defaults["fleet_build_broker_container_port"] == 5001
    assert defaults["fleet_build_broker_container_uid"] == 10001
    assert defaults["fleet_build_broker_container_gid"] == 10001
    assert defaults["fleet_build_broker_secret_dir_mode"] == "0750"
    assert defaults["fleet_build_broker_secret_file_mode"] == "0440"
    assert defaults["fleet_build_broker_probe_secret_dir_mode"] == "0700"
    assert defaults["fleet_build_broker_probe_secret_file_mode"] == "0400"
    assert defaults["fleet_build_broker_renderer_api_key_dir_mode"] == "0700"
    assert defaults["fleet_build_broker_renderer_api_key_file_mode"] == "0400"

    assert defaults["fleet_build_broker_required_secret_files"] == [
        "server.crt",
        "server.key",
        "client-ca.crt",
        "github-app-id",
        "github-app-installation-id",
        "github-app-private-key.pem",
        "github-pat-fallback",
    ]
    assert defaults["fleet_build_broker_required_probe_secret_files"] == [
        "server-ca.crt",
        "monitor.crt",
        "monitor.key",
    ]
    assert set(defaults["fleet_build_broker_runtime_secret_manifest"].values()) == set(
        defaults["fleet_build_broker_required_secret_files"]
    )
    assert set(defaults["fleet_build_broker_monitor_secret_manifest"].values()) == set(
        defaults["fleet_build_broker_required_probe_secret_files"]
    )

    assert defaults["fleet_build_broker_runtime_renderer_command"] == [
        "render-secrets",
        "--target",
        "runtime",
        "--manifest",
        "/run/broker-runtime-renderer-manifest/runtime.json",
        "--api-key-file",
        "/run/broker-runtime-renderer-api-key/api-key",
        "--vault-url",
        "https://fleet-secrets.0exec.com",
        "--output-dir",
        "/run/broker-secrets",
        "--directory-gid",
        "10001",
        "--directory-mode",
        "0750",
        "--file-uid",
        "0",
        "--file-gid",
        "10001",
        "--file-mode",
        "0440",
    ]
    assert defaults["fleet_build_broker_monitor_renderer_command"] == [
        "render-secrets",
        "--target",
        "monitor",
        "--manifest",
        "/run/broker-monitor-renderer-manifest/monitor.json",
        "--api-key-file",
        "/run/broker-monitor-renderer-api-key/api-key",
        "--vault-url",
        "https://fleet-secrets.0exec.com",
        "--output-dir",
        "/run/broker-probe-secrets",
    ]


def test_broker_role_fails_closed_and_renders_two_scopes_before_starting() -> None:
    tasks = yaml.safe_load((ROLE_ROOT / "tasks" / "main.yml").read_text())
    names = [task["name"] for task in tasks]

    assert names.index("Validate fleet build broker runtime inputs") < names.index(
        "Verify the cache-owned GHCR listener is reachable before broker pull"
    )
    assert names.index("Require the root-only runtime renderer API-key file") < names.index(
        "Render the non-secret runtime renderer manifest"
    )
    assert names.index("Require the root-only monitor renderer API-key file") < names.index(
        "Render the non-secret monitor renderer manifest"
    )
    assert names.index("Remove the prior root-only broker secret renderer executions") < names.index(
        "Converge the fleet build broker stack after root-only secret rendering"
    )
    assert names.index("Converge the fleet build broker stack after root-only secret rendering") < names.index(
        "Inspect required root-rendered broker runtime secret files after rendering"
    )

    validate = tasks[0]["ansible.builtin.assert"]["that"]
    assert "fleet_build_broker_image_mirror == '127.0.0.1:5005'" in validate
    assert any("baditaflorin/go-fleet-build-broker@sha256" in clause for clause in validate)
    assert any("fleet_build_broker_renderer_image == fleet_build_broker_image" == clause for clause in validate)
    assert any("fleet_build_broker_host_port | int == 18100" == clause for clause in validate)
    assert any("fleet_build_broker_container_port | int == 5001" == clause for clause in validate)
    assert any("fleet_build_broker_container_uid | int == 10001" == clause for clause in validate)
    assert any("fleet_build_broker_secret_file_mode == '0440'" == clause for clause in validate)
    assert any("fleet_build_broker_probe_secret_file_mode == '0400'" == clause for clause in validate)
    assert any("fleet_build_broker_runtime_renderer_command" in clause for clause in validate)
    assert any("fleet_build_broker_monitor_renderer_command" in clause for clause in validate)

    runtime_key_assert = next(
        task for task in tasks if task["name"] == "Require the root-only runtime renderer API-key file"
    )
    monitor_key_assert = next(
        task for task in tasks if task["name"] == "Require the root-only monitor renderer API-key file"
    )
    runtime_secret_assert = next(
        task
        for task in tasks
        if task["name"] == "Require group-readable-only broker runtime secret files after rendering"
    )
    probe_secret_assert = next(
        task for task in tasks if task["name"] == "Require root-only broker monitor probe secret files after rendering"
    )
    assert runtime_key_assert["no_log"] is True
    assert monitor_key_assert["no_log"] is True
    assert runtime_secret_assert["no_log"] is True
    assert probe_secret_assert["no_log"] is True
    assert (
        "item.stat.gid | int == fleet_build_broker_container_gid | int"
        in runtime_secret_assert["ansible.builtin.assert"]["that"]
    )
    assert "item.stat.gid | int == 0" in probe_secret_assert["ansible.builtin.assert"]["that"]


def test_broker_compose_keeps_renderer_credentials_and_monitor_material_scoped() -> None:
    template = (ROLE_ROOT / "templates" / "docker-compose.yml.j2").read_text()

    assert "render-runtime-secrets:" in template
    assert "render-monitor-secrets:" in template
    assert "image: {{ fleet_build_broker_renderer_image }}" in template
    assert template.count('user: "0:0"') == 2
    assert template.count('restart: "no"') == 2
    assert "command: {{ fleet_build_broker_runtime_renderer_command | to_json }}" in template
    assert "command: {{ fleet_build_broker_monitor_renderer_command | to_json }}" in template
    assert (
        "{{ fleet_build_broker_runtime_renderer_api_key_dir }}:{{ fleet_build_broker_runtime_renderer_api_key_mount }}:ro"
        in template
    )
    assert (
        "{{ fleet_build_broker_monitor_renderer_api_key_dir }}:{{ fleet_build_broker_monitor_renderer_api_key_mount }}:ro"
        in template
    )
    assert (
        "{{ fleet_build_broker_runtime_renderer_manifest_file }}:{{ fleet_build_broker_runtime_renderer_manifest_mount }}:ro"
        in template
    )
    assert (
        "{{ fleet_build_broker_monitor_renderer_manifest_file }}:{{ fleet_build_broker_monitor_renderer_manifest_mount }}:ro"
        in template
    )

    runtime_renderer = template.split("  render-runtime-secrets:\n", maxsplit=1)[1].split(
        "  render-monitor-secrets:\n", maxsplit=1
    )[0]
    monitor_renderer = template.split("  render-monitor-secrets:\n", maxsplit=1)[1].split(
        "  fleet-build-broker:\n", maxsplit=1
    )[0]
    broker_section = template.split("  fleet-build-broker:\n", maxsplit=1)[1]
    assert "{{ fleet_build_broker_secret_dir }}:{{ fleet_build_broker_secret_mount }}:rw" in runtime_renderer
    assert "{{ fleet_build_broker_probe_secret_dir }}" not in runtime_renderer
    assert "{{ fleet_build_broker_monitor_renderer_manifest_file }}" not in runtime_renderer
    assert "{{ fleet_build_broker_probe_secret_dir }}:/run/broker-probe-secrets:rw" in monitor_renderer
    assert "{{ fleet_build_broker_secret_dir }}" not in monitor_renderer
    assert "{{ fleet_build_broker_runtime_renderer_manifest_file }}" not in monitor_renderer
    assert "/run/broker-runtime-renderer-api-key" not in monitor_renderer
    assert "/run/broker-monitor-renderer-api-key" not in runtime_renderer
    assert "cap_drop:\n      - ALL\n    cap_add:\n      - CHOWN" in runtime_renderer
    assert "cap_drop:\n      - ALL\n    cap_add:\n      - CHOWN" in monitor_renderer
    assert runtime_renderer.count("cap_add:") == 1
    assert monitor_renderer.count("cap_add:") == 1

    assert "condition: service_completed_successfully" in template
    assert 'user: "{{ fleet_build_broker_container_uid }}:{{ fleet_build_broker_container_gid }}"' in template
    assert "read_only: true" in template
    assert "cap_drop:" in template and "- ALL" in template
    assert "no-new-privileges:true" in template
    assert "pids_limit: 128" in template
    assert "mem_limit: 512m" in template
    assert 'cpus: "0.50"' in template
    assert (
        '"{{ fleet_build_broker_bind_host }}:{{ fleet_build_broker_host_port }}:{{ fleet_build_broker_container_port }}"'
        in template
    )
    assert "{{ fleet_build_broker_secret_dir }}:{{ fleet_build_broker_secret_mount }}:ro" in broker_section
    assert 'test: ["CMD", "/fleet-build-broker", "healthcheck"]' in broker_section
    assert "monitor.crt" not in broker_section
    assert "monitor.key" not in broker_section
    assert "server-ca.crt" not in broker_section
    assert "/run/broker-probe-secrets" not in broker_section
    assert "cap_add:" not in broker_section


def test_rendered_broker_compose_limits_chown_to_one_shot_renderers() -> None:
    compose = _render_compose_for_assertion((ROLE_ROOT / "templates" / "docker-compose.yml.j2").read_text())
    services = compose["services"]

    assert services["render-runtime-secrets"]["cap_drop"] == ["ALL"]
    assert services["render-runtime-secrets"]["cap_add"] == ["CHOWN"]
    assert services["render-monitor-secrets"]["cap_drop"] == ["ALL"]
    assert services["render-monitor-secrets"]["cap_add"] == ["CHOWN"]
    assert "cap_add" not in services["fleet-build-broker"]
    assert (
        "/opt/fleet-build-broker/renderer-manifests/runtime.json:/run/broker-runtime-renderer-manifest/runtime.json:ro"
        in services["render-runtime-secrets"]["volumes"]
    )
    assert (
        "/opt/fleet-build-broker/renderer-manifests/monitor.json:/run/broker-monitor-renderer-manifest/monitor.json:ro"
        in services["render-monitor-secrets"]["volumes"]
    )
    assert all("monitor.json" not in volume for volume in services["render-runtime-secrets"]["volumes"])
    assert all("runtime.json" not in volume for volume in services["render-monitor-secrets"]["volumes"])


def test_artifact_cache_firewall_allows_only_declared_builders_to_broker_port() -> None:
    host_vars = yaml.safe_load(HOST_VARS_PATH.read_text())
    rules = host_vars["network_policy"]["guests"]["artifact-cache"]["allowed_inbound"]
    broker_rules = [rule for rule in rules if rule["protocol"] == "tcp" and rule.get("ports") == [18100]]

    assert {rule["source"] for rule in broker_rules} == {"10.10.10.30/32", "10.10.10.108/32"}
    assert all("fleet build broker" in rule["description"].lower() for rule in broker_rules)


def test_broker_playbook_targets_only_artifact_cache_and_the_ghcr_listener() -> None:
    wrapper = yaml.safe_load(PLAYBOOK_PATH.read_text())
    assert wrapper == [
        {"import_playbook": "../collections/ansible_collections/lv3/platform/playbooks/fleet-build-broker.yml"}
    ]

    playbook = yaml.safe_load(COLLECTION_PLAYBOOK_PATH.read_text())
    play = playbook[0]
    assert play["name"] == "Converge the private fleet build broker on artifact-cache"
    assert play["hosts"] == "artifact-cache"
    assert play["vars_files"] == ["../vars/artifact_cache_registry_endpoints.yml"]
    assert (
        play["vars"]["docker_runtime_insecure_registries"] == "{{ artifact_cache_docker_runtime_insecure_registries }}"
    )
    endpoints = yaml.safe_load(ENDPOINTS_PATH.read_text())
    assert endpoints["artifact_cache_docker_runtime_insecure_registries"][-1] == "127.0.0.1:5005"
    assert [role["role"] for role in play["roles"]] == [
        "lv3.platform.linux_guest_firewall",
        "lv3.platform.docker_runtime",
        "lv3.platform.fleet_build_broker_runtime",
    ]
