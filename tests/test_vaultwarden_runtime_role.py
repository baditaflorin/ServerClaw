from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULTS_PATH = REPO_ROOT / "roles" / "vaultwarden_runtime" / "defaults" / "main.yml"
TASKS_PATH = REPO_ROOT / "roles" / "vaultwarden_runtime" / "tasks" / "main.yml"
VERIFY_PATH = REPO_ROOT / "roles" / "vaultwarden_runtime" / "tasks" / "verify.yml"
COMPOSE_TEMPLATE = REPO_ROOT / "roles" / "vaultwarden_runtime" / "templates" / "docker-compose.yml.j2"


def load_yaml(path: Path) -> list[dict] | dict:
    return yaml.safe_load(path.read_text())


def test_defaults_use_private_service_topology_and_local_bootstrap_artifacts() -> None:
    defaults = load_yaml(DEFAULTS_PATH)
    assert defaults["vaultwarden_https_port"] == "{{ hostvars['proxmox_florin'].platform_service_topology | platform_service_port('vaultwarden', 'internal') }}"
    assert defaults["vaultwarden_controller_url"] == "{{ hostvars['proxmox_florin'].platform_service_topology | platform_service_url('vaultwarden', 'controller') }}"
    assert defaults["vaultwarden_database_inventory_host"] == "{{ 'postgres-staging-lv3' if (env | default('production')) == 'staging' else 'postgres-lv3' }}"
    assert defaults["vaultwarden_database_host"] == "{{ hostvars[vaultwarden_database_inventory_host].ansible_host }}"
    assert defaults["vaultwarden_local_health_url"] == "{{ vaultwarden_internal_base_url }}"
    assert defaults["vaultwarden_admin_token_local_file"] == "{{ vaultwarden_local_artifact_dir }}/admin-token.txt"
    assert defaults["vaultwarden_admin_token_hash_local_file"] == "{{ vaultwarden_local_artifact_dir }}/admin-token-argon2.txt"
    assert defaults["vaultwarden_tls_server_sans"][1] == "{{ hostvars['proxmox_florin'].platform_host.management.tailscale_ipv4 }}"


def test_role_generates_hash_with_the_vaultwarden_binary_when_missing() -> None:
    tasks = load_yaml(TASKS_PATH)
    missing_fact = next(task for task in tasks if task.get("name") == "Record whether the Vaultwarden admin token hash must be generated")
    hash_task = next(task for task in tasks if task.get("name") == "Generate the Vaultwarden admin token hash on the runtime host when missing")
    assert "vaultwarden_admin_token_hash_local.stat.size" in missing_fact["ansible.builtin.set_fact"]["vaultwarden_admin_token_hash_missing"]
    command = hash_task["ansible.builtin.shell"]
    assert "script -qec" in command
    assert "docker run --rm -it" in command
    assert "/vaultwarden hash" in command
    assert "tr -d '\\r'" in command
    assert "sed -n \"s/.*ADMIN_TOKEN=" in command


def test_role_recovers_missing_docker_bridge_chains_before_startup() -> None:
    tasks = load_yaml(TASKS_PATH)

    inspect_networks = next(
        task for task in tasks if task.get("name") == "Inspect current Vaultwarden container networks"
    )
    inspect_ports = next(
        task for task in tasks if task.get("name") == "Inspect current Vaultwarden container published ports"
    )
    recreate_fact = next(
        task for task in tasks if task.get("name") == "Record whether Vaultwarden must be force recreated before startup"
    )
    startup_command = next(task for task in tasks if task.get("name") == "Build the Vaultwarden startup command")
    nat_check = next(
        task for task in tasks if task.get("name") == "Check whether the Docker nat chain exists before Vaultwarden startup"
    )
    forward_check = next(
        task for task in tasks if task.get("name") == "Check whether the Docker forward chain exists before Vaultwarden startup"
    )
    restart = next(
        task
        for task in tasks
        if task.get("name") == "Restart Docker when the nat or forward chain is missing before Vaultwarden startup"
    )
    assert_task = next(
        task for task in tasks if task.get("name") == "Assert Docker bridge chains are present before Vaultwarden startup"
    )
    startup = next(
        task for task in tasks if task.get("name") == "Start the Vaultwarden stack and recover Docker bridge-chain failures"
    )

    assert inspect_networks["ansible.builtin.command"]["argv"][:3] == ["docker", "inspect", "{{ vaultwarden_container_name }}"]
    assert inspect_networks["ansible.builtin.command"]["argv"][-1] == '{{ "{{json .NetworkSettings.Networks}}" }}'
    assert inspect_ports["ansible.builtin.command"]["argv"][-1] == '{{ "{{json .NetworkSettings.Ports}}" }}'
    assert "vaultwarden_container_networks.stdout" in recreate_fact["ansible.builtin.set_fact"]["vaultwarden_force_recreate"]
    assert "vaultwarden_container_ports.stdout" in recreate_fact["ansible.builtin.set_fact"]["vaultwarden_force_recreate"]
    assert "vaultwarden_compose_up_argv" in startup_command["ansible.builtin.set_fact"]
    assert "--force-recreate" in startup_command["ansible.builtin.set_fact"]["vaultwarden_compose_up_argv"]
    assert nat_check["ansible.builtin.command"]["argv"] == ["iptables", "-t", "nat", "-S", "DOCKER"]
    assert forward_check["ansible.builtin.command"]["argv"] == ["iptables", "-S", "DOCKER-FORWARD"]
    assert restart["when"] == (
        "vaultwarden_docker_nat_chain_check.rc == 1 or vaultwarden_docker_forward_chain_check.rc == 1"
    )
    assert assert_task["ansible.builtin.assert"]["that"] == [
        "vaultwarden_docker_nat_chain_recheck.rc == 0",
        "vaultwarden_docker_forward_chain_recheck.rc == 0",
    ]

    start_task = next(task for task in startup["block"] if task.get("name") == "Start the Vaultwarden stack")
    rescue_fact = next(
        task for task in startup["rescue"] if task.get("name") == "Flag Docker bridge-chain failures during Vaultwarden startup"
    )
    network_reset = next(
        task
        for task in startup["rescue"]
        if task.get("name") == "Reset stale Vaultwarden compose resources before retrying startup"
    )
    retry_task = next(
        task for task in startup["rescue"] if task.get("name") == "Retry Vaultwarden startup after Docker bridge-chain recovery"
    )

    assert start_task["ansible.builtin.command"]["argv"] == "{{ vaultwarden_compose_up_argv }}"
    assert "No chain/target/match by that name" in rescue_fact["ansible.builtin.set_fact"][
        "vaultwarden_docker_bridge_chain_missing"
    ]
    assert "Unable to enable ACCEPT OUTGOING rule" in rescue_fact["ansible.builtin.set_fact"][
        "vaultwarden_docker_bridge_chain_missing"
    ]
    assert "failed to create endpoint" in rescue_fact["ansible.builtin.set_fact"]["vaultwarden_docker_network_missing"]
    assert network_reset["ansible.builtin.command"]["argv"][-2:] == ["down", "--remove-orphans"]
    assert network_reset["when"] == "vaultwarden_docker_network_missing"
    assert "--force-recreate" in retry_task["ansible.builtin.command"]["argv"]
    assert retry_task["when"] == "vaultwarden_docker_bridge_chain_missing or vaultwarden_docker_network_missing"


def test_compose_template_uses_postgres_tls_and_hashed_admin_token() -> None:
    template = COMPOSE_TEMPLATE.read_text()
    assert "DATABASE_URL: postgresql://" in template
    assert "vaultwarden_database_password | urlencode | replace('/', '%2F')" in template
    assert "ADMIN_TOKEN: '{{ vaultwarden_admin_token_hash | replace(\"$\", \"$$\") }}'" in template
    assert '- "{{ ansible_host }}:{{ vaultwarden_https_port }}:{{ vaultwarden_https_port }}"' in template
    assert 'ROCKET_TLS: \'{certs="{{ vaultwarden_tls_server_cert_file }}",key="{{ vaultwarden_tls_server_key_file }}"}\'' in template


def test_verify_checks_controller_liveness_and_local_bootstrap_state() -> None:
    verify = load_yaml(VERIFY_PATH)
    resolution_task = next(task for task in verify if task.get("name") == "Check whether the Vaultwarden controller hostname resolves locally")
    probe_task = next(task for task in verify if task.get("name") == "Select the Vaultwarden controller probe target")
    bind_task = next(task for task in verify if task.get("name") == "Discover the local Tailscale IPv4 address for fallback controller probes")
    controller_task = next(task for task in verify if task.get("name") == "Verify Vaultwarden is reachable through the controller URL")
    fallback_task = next(task for task in verify if task.get("name") == "Verify Vaultwarden is reachable through the controller proxy fallback")
    bootstrap_stat = next(task for task in verify if task.get("name") == "Assert the Vaultwarden bootstrap state file exists locally")
    assert resolution_task["ansible.builtin.command"]["argv"][-1] == "{{ vaultwarden_controller_url | urlsplit('hostname') }}"
    assert "vaultwarden_service_topology.dns.target" in probe_task["ansible.builtin.set_fact"]["vaultwarden_controller_probe_url"]
    assert "vaultwarden_controller_url | urlsplit('port')" in probe_task["ansible.builtin.set_fact"]["vaultwarden_controller_probe_url"]
    assert "ifconfig | awk '/inet 100\\./" in bind_task["ansible.builtin.shell"]
    assert controller_task["ansible.builtin.uri"]["url"] == "{{ vaultwarden_controller_probe_url }}/alive"
    assert controller_task["ansible.builtin.uri"]["headers"] == "{{ vaultwarden_controller_probe_headers }}"
    assert "--interface \"{{ vaultwarden_controller_probe_bind_address.stdout | trim }}\"" in fallback_task["ansible.builtin.shell"]
    assert "--header 'Host: {{ vaultwarden_controller_url | urlsplit('hostname') }}'" in fallback_task["ansible.builtin.shell"]
    assert bootstrap_stat["ansible.builtin.stat"]["path"] == "{{ vaultwarden_bootstrap_state_local_file }}"
