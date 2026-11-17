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
    / "proxmox_network"
    / "tasks"
    / "main.yml"
)
MAKEFILE_PATH = REPO_ROOT / "Makefile"
DEFAULTS_PATH = ROLE_TASKS.parent.parent / "defaults" / "main.yml"
META_PATH = ROLE_TASKS.parent.parent / "meta" / "argument_specs.yml"
TEMPLATE_PATH = ROLE_TASKS.parent.parent / "templates" / "nftables.conf.j2"
HOST_VARS_PATH = REPO_ROOT / "inventory" / "host_vars" / "proxmox-host.yml"
PUBLIC_HOST_VARS_PATH = REPO_ROOT / "publication" / "templates" / "proxmox-host.yml"
GUEST_FIREWALL_TEMPLATE = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "proxmox_network"
    / "templates"
    / "vm.fw.j2"
)


def test_proxmox_network_renders_vm_firewall_from_active_role_path() -> None:
    tasks = yaml.safe_load(ROLE_TASKS.read_text(encoding="utf-8"))
    render_task = next(
        task for task in tasks if task["name"] == "Render per-guest Proxmox firewall policy to staging files"
    )
    template_module = render_task["ansible.builtin.template"]

    assert template_module["src"] == "vm.fw.j2"
    assert template_module["dest"] == "{{ proxmox_network_firewall_stage_dir }}/.lv3-vm-{{ guest.vmid }}.fw"


def test_proxmox_network_rejects_management_interface_aliasing_wan_bridge() -> None:
    tasks = yaml.safe_load(ROLE_TASKS.read_text(encoding="utf-8"))
    guard = next(
        task
        for task in tasks
        if task["name"] == "SAFETY GUARD — Reject a management interface that aliases the WAN bridge"
    )

    assert "management_interface != proxmox_wan_bridge" in guard["ansible.builtin.assert"]["that"]


def test_proxmox_network_defaults_define_udp_forward_contract() -> None:
    defaults = yaml.safe_load(DEFAULTS_PATH.read_text(encoding="utf-8"))

    assert defaults["proxmox_public_ingress_tcp_forwards"] == []
    assert defaults["proxmox_public_ingress_udp_forwards"] == []


def test_proxmox_network_argument_specs_accept_udp_forward_rules() -> None:
    specs = yaml.safe_load(META_PATH.read_text(encoding="utf-8"))
    options = specs["argument_specs"]["main"]["options"]

    assert options["proxmox_public_ingress_tcp_forwards"]["type"] == "list"
    assert options["proxmox_public_ingress_udp_forwards"]["type"] == "list"
    assert options["proxmox_public_ingress_udp_forwards"]["default"] == []


def test_proxmox_network_template_renders_udp_filter_and_nat_rules() -> None:
    template = TEMPLATE_PATH.read_text(encoding="utf-8")

    assert "proxmox_public_ingress_udp_forwards | default([]) | length > 0" in template
    assert "udp dport {{ forward.target_port }} accept" in template
    assert (
        "udp dport {{ forward.listen_port }} dnat ip to {{ forward.target_host }}:{{ forward.target_port }}" in template
    )


def test_proxmox_network_template_never_forwards_private_space_to_the_wan() -> None:
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    drop = (
        'oifname "{{ proxmox_wan_bridge }}" ip daddr '
        "{ 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 100.64.0.0/10, 169.254.0.0/16 } counter drop"
    )

    forward = template.split("  chain forward {", 1)[1].split("  chain output {", 1)[0]
    output = template.split("  chain output {", 1)[1].split("table ip nat", 1)[0]
    assert drop in forward and drop in output
    assert forward.index(drop) < forward.index("ct state related,established accept")
    assert forward.index(drop) < forward.index("ip saddr {{ proxmox_internal_network }} accept")


def test_private_guests_can_hairpin_public_web_names_without_open_ended_nat() -> None:
    from jinja2 import Environment, StrictUndefined

    rendered = (
        Environment(undefined=StrictUndefined)
        .from_string(TEMPLATE_PATH.read_text())
        .render(
            proxmox_wan_bridge="wan0",
            proxmox_internal_bridge="guest0",
            proxmox_internal_network="10.88.0.0/24",
            proxmox_internal_ipv4="10.88.0.1",
            proxmox_public_edge_ipv4="10.88.0.10",
            management_ipv4="203.0.113.1",
        )
    )
    assert (
        'iifname "guest0" ip saddr 10.88.0.0/24 ip daddr 203.0.113.1 tcp dport { 80, 443 } dnat ip to 10.88.0.10'
        in rendered
    )
    assert (
        'oifname "guest0" ip saddr 10.88.0.0/24 ip daddr 10.88.0.10 ct original ip daddr 203.0.113.1 tcp dport { 80, 443 } snat ip to 10.88.0.1'
        in rendered
    )


def test_host_vars_define_livekit_public_tcp_and_udp_forwards() -> None:
    host_vars = yaml.safe_load(HOST_VARS_PATH.read_text(encoding="utf-8"))

    assert host_vars["platform_port_assignments"]["livekit_signal_port"] == 7880
    assert host_vars["platform_port_assignments"]["livekit_tcp_port"] == 7881
    assert host_vars["platform_port_assignments"]["livekit_udp_port"] == 7882
    assert 7881 in host_vars["proxmox_public_ingress_tcp_ports"]
    livekit_udp_forward = next(
        forward for forward in host_vars["proxmox_public_ingress_udp_forwards"] if forward["listen_port"] == 7882
    )
    if host_vars == yaml.safe_load(PUBLIC_HOST_VARS_PATH.read_text(encoding="utf-8")):
        # The fork-ready publication template uses an example private IP.
        from ipaddress import ip_address

        assert ip_address(livekit_udp_forward["target_host"]).is_private
    else:
        assert livekit_udp_forward["target_host"] == (
            "{{ (proxmox_guests | selectattr('name', 'equalto', 'runtime-comms') | list | first).ipv4 }}"
        )
    assert livekit_udp_forward["target_port"] == 7882


def test_docker_build_allows_the_proxmox_metrics_proxy_backend() -> None:
    host_vars = yaml.safe_load(HOST_VARS_PATH.read_text(encoding="utf-8"))
    docker_build_policy = host_vars["network_policy"]["guests"]["docker-build"]

    rules = [
        rule
        for rule in docker_build_policy["allowed_inbound"]
        if rule.get("description") == "Proxmox host connection from the Tailscale metrics proxy"
    ]
    if host_vars == yaml.safe_load(PUBLIC_HOST_VARS_PATH.read_text(encoding="utf-8")):
        assert not rules  # Deployment-specific allowance is absent from the fork template.
    else:
        assert len(rules) == 1
        assert rules[0]["source"] == "host"
        assert rules[0]["protocol"] == "tcp"
        assert rules[0]["ports"] == [9100]

    template = GUEST_FIREWALL_TEMPLATE.read_text(encoding="utf-8")
    assert "{% elif rule.source == 'host' %}" in template
    assert "render_line(rule, source=policy.host_source, port=port)" in template


def test_runtime_control_preserves_nginx_minio_access() -> None:
    host_vars = yaml.safe_load(HOST_VARS_PATH.read_text(encoding="utf-8"))
    runtime_control_policy = host_vars["network_policy"]["guests"]["runtime-control"]

    nginx_rules = [rule for rule in runtime_control_policy["allowed_inbound"] if rule.get("source") == "nginx"]

    allows_minio = any(rule["protocol"] == "tcp" and 9000 in rule["ports"] for rule in nginx_rules)
    if host_vars == yaml.safe_load(PUBLIC_HOST_VARS_PATH.read_text(encoding="utf-8")):
        assert not allows_minio  # Forks configure their own cross-service access.
    else:
        assert allows_minio


def test_public_host_template_matches_the_fork_ready_network_contract(monkeypatch) -> None:
    monkeypatch.setitem(globals(), "HOST_VARS_PATH", PUBLIC_HOST_VARS_PATH)
    test_host_vars_define_livekit_public_tcp_and_udp_forwards()
    test_docker_build_allows_the_proxmox_metrics_proxy_backend()
    test_runtime_control_preserves_nginx_minio_access()


def test_guest_network_policy_target_allows_narrow_strict_converges() -> None:
    makefile = MAKEFILE_PATH.read_text(encoding="utf-8")
    target = makefile.split("converge-guest-network-policy:\n", 1)[1].split("\n\n", 1)[0]

    assert "$(EXTRA_ARGS)" in target
    assert "ANSIBLE_HOST_KEY_CHECKING=False" not in target
    assert "ANSIBLE_HOST_KEY_CHECKING=$${ANSIBLE_HOST_KEY_CHECKING:-True}" in target
