from pathlib import Path
import ipaddress

from jinja2 import Template
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_TASKS = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "linux_guest_firewall"
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
    / "linux_guest_firewall"
    / "defaults"
    / "main.yml"
)
ROLE_TEMPLATE = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "linux_guest_firewall"
    / "templates"
    / "nftables.conf.j2"
)


def load_tasks() -> list[dict]:
    return yaml.safe_load(ROLE_TASKS.read_text())


def load_defaults() -> dict:
    return yaml.safe_load(ROLE_DEFAULTS.read_text())


def test_sanitized_host_template_preserves_node_exporter_guest_firewall_rules() -> None:
    host_vars = yaml.safe_load((REPO_ROOT / "publication" / "templates" / "proxmox-host.yml").read_text())
    policy = host_vars["network_policy"]["guests"]

    for guest in ("nginx", "docker-build", "runtime-control"):
        rules = [
            rule
            for rule in policy[guest]["allowed_inbound"]
            if rule.get("source") == "monitoring"
            and rule.get("protocol") == "tcp"
            and 9100 in (rule.get("ports") or [])
        ]
        assert len(rules) == 1, f"the sanitized {guest} template must preserve its node-exporter scrape rule"
        if guest != "nginx":
            assert rules[0].get("forward") is False


def test_linux_guest_firewall_reasserts_docker_bridge_chains_after_firewall_evaluation() -> None:
    tasks = load_tasks()
    task_names = [task["name"] for task in tasks]
    defaults = load_defaults()

    assert task_names.index("Inspect nftables package status on the guest") < task_names.index(
        "Record whether nftables is missing on the guest"
    )
    assert task_names.index("Record whether nftables is missing on the guest") < task_names.index(
        "Ensure nftables is installed on the guest"
    )
    assert task_names.index("Wait for guest SSH after nftables changes") < task_names.index(
        "Ensure Docker bridge networking remains available after firewall evaluation"
    )
    inspect_task = next(task for task in tasks if task["name"] == "Inspect nftables package status on the guest")
    record_missing_task = next(
        task for task in tasks if task["name"] == "Record whether nftables is missing on the guest"
    )
    ensure_nftables_task = next(task for task in tasks if task["name"] == "Ensure nftables is installed on the guest")
    ensure_task = next(
        task
        for task in tasks
        if task["name"] == "Ensure Docker bridge networking remains available after firewall evaluation"
    )
    include_role = next(
        task
        for task in ensure_task["block"]
        if task["name"] == "Assert Docker bridge chains remain available after guest firewall evaluation"
    )["ansible.builtin.include_role"]
    reset_task = next(
        task
        for task in ensure_task["rescue"]
        if task["name"] == "Reset Docker failed state before guest firewall bridge-chain recovery restart"
    )
    restart_task = next(
        task
        for task in ensure_task["rescue"]
        if task["name"] == "Restart Docker to restore bridge chains after guest firewall evaluation"
    )
    reassert_task = next(
        task
        for task in ensure_task["rescue"]
        if task["name"] == "Re-assert Docker bridge chains after guest firewall recovery restart"
    )
    fail_task = next(
        task
        for task in ensure_task["rescue"]
        if task["name"]
        == "Surface Docker bridge-chain failures after guest firewall evaluation when recovery is disabled"
    )
    assert inspect_task["ansible.builtin.command"]["argv"] == ["dpkg-query", "-W", "-f=${Status}", "nftables"]
    assert inspect_task["register"] == "linux_guest_firewall_nftables_package_status"
    assert inspect_task["changed_when"] is False
    assert inspect_task["failed_when"] is False
    assert record_missing_task["ansible.builtin.set_fact"] == {
        "linux_guest_firewall_nftables_missing": '{{ linux_guest_firewall_nftables_package_status.stdout != "install ok installed" }}'
    }
    assert ensure_nftables_task["ansible.builtin.apt"] == {"name": "nftables", "state": "present"}
    assert ensure_nftables_task["when"] == "linux_guest_firewall_nftables_missing | bool"
    assert include_role["name"] == "lv3.platform.common"
    assert include_role["tasks_from"] == "docker_bridge_chains"
    assert ensure_task["block"][0]["vars"]["common_docker_bridge_chains_service_name"] == (
        "{{ linux_guest_firewall_docker_bridge_chain_service_name }}"
    )
    assert reset_task["ansible.builtin.command"]["argv"] == [
        "systemctl",
        "reset-failed",
        "{{ linux_guest_firewall_docker_bridge_chain_service_name }}.service",
    ]
    assert reset_task["become_flags"] == "-n"
    assert reset_task["when"] == "linux_guest_firewall_recover_missing_docker_bridge_chains | bool"
    assert restart_task["ansible.builtin.service"] == {
        "name": "{{ linux_guest_firewall_docker_bridge_chain_service_name }}",
        "state": "restarted",
    }
    assert restart_task["become_flags"] == "-n"
    assert restart_task["when"] == "linux_guest_firewall_recover_missing_docker_bridge_chains | bool"
    assert reassert_task["vars"]["common_docker_bridge_chains_service_name"] == (
        "{{ linux_guest_firewall_docker_bridge_chain_service_name }}"
    )
    assert reassert_task["vars"]["common_docker_bridge_chains_retries"] == (
        "{{ linux_guest_firewall_docker_bridge_chain_recovery_retries }}"
    )
    assert reassert_task["vars"]["common_docker_bridge_chains_delay"] == (
        "{{ linux_guest_firewall_docker_bridge_chain_recovery_delay }}"
    )
    assert reassert_task["when"] == "linux_guest_firewall_recover_missing_docker_bridge_chains | bool"
    assert fail_task["when"] == "not linux_guest_firewall_recover_missing_docker_bridge_chains | bool"
    assert defaults["linux_guest_firewall_docker_bridge_chain_service_name"] == "docker"
    assert defaults["linux_guest_firewall_recover_missing_docker_bridge_chains"] is True
    assert defaults["linux_guest_firewall_docker_bridge_chain_recovery_retries"] == 30
    assert defaults["linux_guest_firewall_docker_bridge_chain_recovery_delay"] == 5


def test_linux_guest_firewall_only_resets_ssh_when_the_rendered_policy_changes() -> None:
    tasks = load_tasks()

    reset_task = next(
        task for task in tasks if task["name"] == "Reset SSH connection after guest nftables policy evaluation"
    )
    wait_task = next(task for task in tasks if task["name"] == "Wait for guest SSH after nftables changes")
    post_bridge_reset_task = next(
        task
        for task in tasks
        if task["name"] == "Reset SSH connection after post-bridge guest nftables policy evaluation"
    )
    post_bridge_wait_task = next(
        task for task in tasks if task["name"] == "Wait for guest SSH after post-bridge nftables changes"
    )

    assert reset_task["ansible.builtin.include_tasks"] == "reset_connection.yml"
    assert reset_task["when"] == "linux_guest_firewall_config.changed"
    assert wait_task["when"] == "linux_guest_firewall_config.changed"
    assert post_bridge_reset_task["ansible.builtin.include_tasks"] == "reset_connection.yml"
    assert post_bridge_reset_task["when"] == "linux_guest_firewall_post_bridge_config.changed"
    assert post_bridge_wait_task["when"] == "linux_guest_firewall_post_bridge_config.changed"


def test_linux_guest_firewall_replaces_only_its_owned_nftables_table() -> None:
    template = ROLE_TEMPLATE.read_text()

    assert "destroy table inet filter" in template
    assert "flush ruleset" not in template


HOST_VARS_PATH = REPO_ROOT / "inventory" / "host_vars" / "proxmox-host.yml"
SNAT_FIXTURE_PATH = REPO_ROOT / "tests" / "fixtures" / "linux_guest_firewall_snat_policy.yml"
TEMPLATE_PATH = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "linux_guest_firewall"
    / "templates"
    / "nftables.conf.j2"
)


def test_container_forwarding_guests_use_the_source_only_forward_path() -> None:
    template = TEMPLATE_PATH.read_text()

    assert "guest_policy.allow_container_forwarding | default(false)" in template
    assert "docker_runtime_container_forward_source_cidrs" in template
    assert "linux_guest_firewall_container_forward_source_cidrs" in template


def test_container_snat_is_opt_in_and_limited_to_explicit_flows() -> None:
    template = TEMPLATE_PATH.read_text()
    host_vars = yaml.safe_load(HOST_VARS_PATH.read_text())
    source_guest_policies = host_vars["network_policy"]["guests"]
    source_coolify_policy = source_guest_policies.get("coolify", {})

    assert "guest_policy.allow_container_private_edge_https_snat | default(false)" in template
    assert all(
        not policy.get("allow_container_private_edge_https_snat", False) and not policy.get("container_snat_rules", [])
        for guest, policy in source_guest_policies.items()
        if guest != "coolify"
    )

    # Production inventory can opt in only for narrow bridge networks and
    # host-specific flows. The separate fixture below keeps renderer coverage
    # stable when publication replaces deployment inventory with fork defaults.
    if source_coolify_policy.get("allow_container_private_edge_https_snat", False):
        source_cidrs = source_coolify_policy.get("container_private_edge_https_snat_source_cidrs", [])
        source_rules = source_coolify_policy.get("container_snat_rules", [])
        assert source_cidrs
        assert source_rules
        assert all(ipaddress.ip_network(cidr, strict=False).prefixlen >= 24 for cidr in source_cidrs)
        assert all(ipaddress.ip_network(rule["source"], strict=False).prefixlen >= 32 for rule in source_rules)

    fixture = yaml.safe_load(SNAT_FIXTURE_PATH.read_text())
    policy = dict(host_vars["network_policy"])
    policy["guests"] = dict(policy["guests"])
    policy["guests"]["coolify"] = {
        **policy["guests"].get("coolify", {}),
        **fixture["coolify_snat_policy"],
    }

    guest_ip_map = {guest["name"]: guest["ipv4"] for guest in host_vars["proxmox_guests"]}
    guest_role_map = {guest["name"]: guest["role"] for guest in host_vars["proxmox_guests"]}
    rendered = Template(template).render(
        inventory_hostname="coolify",
        linux_guest_firewall_host_id="proxmox-host",
        linux_guest_firewall_policy=policy,
        linux_guest_firewall_guest_ip_map=guest_ip_map,
        linux_guest_firewall_guest_role_map=guest_role_map,
        linux_guest_firewall_container_forward_source_cidrs=["172.16.0.0/12", "192.168.0.0/16", "10.200.0.0/16"],
        hostvars={"proxmox-host": host_vars},
    )

    edge_ip = host_vars["proxmox_public_edge_ipv4"]
    coolify_ip = guest_ip_map["coolify"]
    for cidr in fixture["coolify_snat_policy"]["container_private_edge_https_snat_source_cidrs"]:
        assert f"ip saddr {cidr} ip daddr {edge_ip} tcp dport 443 snat to {coolify_ip}" in rendered
    assert "table ip lv3_container_snat" in rendered
    for rule in fixture["coolify_snat_policy"]["container_snat_rules"]:
        destination = guest_ip_map.get(rule["destination"], rule["destination"])
        ports = ", ".join(str(port) for port in rule["ports"])
        assert (
            f"ip saddr {rule['source']} ip daddr {destination} {rule['protocol']} "
            f"dport {{ {ports} }} snat to {coolify_ip}"
        ) in rendered
    assert "destroy table ip coolify_egress" in rendered
    assert "destroy table ip coolify_dns_egress" in rendered
    monitoring_ip = guest_ip_map["monitoring"]
    assert f"ip saddr {monitoring_ip}/32 tcp dport {{ 9100 }} accept" in rendered
    forward_chain = rendered.split("chain forward {", maxsplit=1)[1].split("chain output {", maxsplit=1)[0]
    assert f"{monitoring_ip}/32" not in forward_chain
    for broad_cidr in ("172.16.0.0/12", "192.168.0.0/16", "10.200.0.0/16"):
        assert f"ip saddr {broad_cidr} ip daddr {edge_ip} tcp dport 443" not in rendered
    assert f"ip daddr {edge_ip} tcp dport {{ 80, 443 }}" not in rendered

    non_coolify_render = Template(template).render(
        inventory_hostname="docker-runtime",
        linux_guest_firewall_host_id="proxmox-host",
        linux_guest_firewall_policy=policy,
        linux_guest_firewall_guest_ip_map=guest_ip_map,
        linux_guest_firewall_guest_role_map=guest_role_map,
        linux_guest_firewall_container_forward_source_cidrs=["172.16.0.0/12", "192.168.0.0/16", "10.200.0.0/16"],
        hostvars={"proxmox-host": host_vars},
    )
    assert "destroy table ip coolify_egress" not in non_coolify_render
    assert "destroy table ip coolify_dns_egress" not in non_coolify_render


def test_linux_guest_firewall_defaults_cover_all_governed_docker_bridge_cidrs() -> None:
    defaults = load_defaults()

    assert defaults["linux_guest_firewall_container_forward_source_cidrs"] == [
        "172.16.0.0/12",
        "192.168.0.0/16",
        "10.200.0.0/16",
    ]


def test_coolify_guest_policy_enables_container_forwarding_for_published_ports() -> None:
    host_vars = yaml.safe_load(HOST_VARS_PATH.read_text())
    coolify_policy = host_vars["network_policy"]["guests"]["coolify"]

    assert coolify_policy["allow_container_forwarding"] is True

    published_sources = {
        rule["source"]: tuple(rule["ports"]) for rule in coolify_policy["allowed_inbound"] if rule["source"] == "nginx"
    }
    assert published_sources["nginx"] == (80, 443, 8000, 8096)


def test_livekit_guest_policy_allows_edge_signalling_and_public_media_ingress() -> None:
    host_vars = yaml.safe_load(HOST_VARS_PATH.read_text())
    docker_runtime_rules = host_vars["network_policy"]["guests"]["docker-runtime"]["allowed_inbound"]

    assert any(
        rule["source"] == "nginx" and rule["protocol"] == "tcp" and 7880 in rule["ports"]
        for rule in docker_runtime_rules
    )
    assert any(
        rule["source"] == "public" and rule["protocol"] == "tcp" and 7881 in rule["ports"]
        for rule in docker_runtime_rules
    )
    assert any(
        rule["source"] == "public" and rule["protocol"] == "udp" and 7882 in rule["ports"]
        for rule in docker_runtime_rules
    )
