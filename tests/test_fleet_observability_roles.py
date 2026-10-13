"""Regression tests for the fleet observability roles and playbook.

The roles (node_exporter listeners and socket proxies, guest nftables, advertised Tailscale routes, the Postgres backup
stack) codify changes that were made by hand on the 0mcp, 0docker, 0database and 0own hosts. Ansible is not needed here:
the Jinja templates are rendered offline with an Ansible-compatible environment (trim_blocks, strict undefined), the
vzdump hook is executed with bash against a stub vzdump layout, and the YAML is inspected for the safety properties the
runbook relies on (explicit --limit, no secrets, no live converge by default). Nothing here contacts a host.
"""

from __future__ import annotations

import copy
import os
import re
import subprocess
from pathlib import Path
from typing import Any

import jinja2
import pytest
import yaml

import fleet_observability_render as fleet


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLES = REPO_ROOT / "collections" / "ansible_collections" / "lv3" / "platform" / "roles"
PLAYBOOK = REPO_ROOT / "playbooks" / "fleet-observability.yml"
INVENTORY = REPO_ROOT / "inventory" / "fleet-observability.yml"
NEW_ROLES = ["fleet_node_exporter", "fleet_guest_firewall", "fleet_tailscale_node", "fleet_pg_backup", "fleet_docker_prune"]

# Documentation addresses (RFC 5737 / 3849 style), never the real fleet values.
STUB_EXPORTER = {
    "fleet_node_exporter_listen_addresses": ["192.0.2.10:9100", "192.0.2.10:9102"],
    "fleet_node_exporter_textfile_dir": "/var/lib/prometheus/node-exporter/textfile",
}


def _context(role: str, **overrides: Any) -> dict[str, Any]:
    context = dict(fleet.role_defaults(role))
    context.update(overrides)
    return context


def _tasks(role: str, name: str) -> list[dict[str, Any]]:
    return yaml.safe_load((ROLES / role / "tasks" / name).read_text(encoding="utf-8"))


# ----------------------------------------------------------------------------- inventory


def test_inventory_seeds_every_fleet_and_scopes_roles_to_declared_hosts() -> None:
    groups, hostvars, all_vars = fleet.inventory_model()

    for fleet_group in ("fleet_0mcp", "fleet_0docker", "fleet_0database", "fleet_0own"):
        assert groups[fleet_group], fleet_group
    # Names are the ssh-fleet-sync aliases, one group per fleet.
    assert {"0docker_bastion", "0docker_docker", "0docker_nginx", "0docker_builder"} <= groups["fleet_0docker"]
    assert {"0database_bastion", "0database_postgres"} <= groups["fleet_0database"]
    assert {"0own_bastion", "0own_pbs", "0own_github_mirror", "0own_pyroscope_canary"} <= groups["fleet_0own"]
    assert groups["fleet_0mcp"] == {"operator-bastion", "0mcp_docker_build"}
    assert all_vars["fleet_observability_max_hosts"] == 1

    # Every host named in a role group has the variables that role requires.
    for host in groups["fleet_node_exporter_hosts"]:
        assert hostvars[host]["fleet_node_exporter_listen_addresses"], host
    for host in groups["fleet_tailscale_node_hosts"]:
        assert hostvars[host]["fleet_tailscale_node_advertise_routes"], host
    assert groups["fleet_docker_prune_hosts"] == {"0mcp_docker_build"}
    for host in groups["fleet_guest_firewall_hosts"]:
        assert hostvars[host]["fleet_guest_firewall_allowed_inbound"], host
    for host in groups["fleet_pg_backup_hosts"]:
        assert hostvars[host]["fleet_pg_backup_components"], host
    # No role group reaches beyond the hosts that had live changes.
    assert groups["fleet_guest_firewall_hosts"] == {"0own_github_mirror"}
    assert groups["fleet_tailscale_node_hosts"] == {"0docker_bastion", "0own_bastion"}


def test_hosts_that_log_in_unprivileged_use_become_and_root_hosts_do_not() -> None:
    _, hostvars, _ = fleet.inventory_model()

    assert hostvars["0docker_nginx"]["ansible_become"] is True
    assert hostvars["0own_github_mirror"]["ansible_become"] is True
    for host in ("0docker_bastion", "0database_bastion", "0own_pbs", "operator-bastion"):
        assert "ansible_become" not in hostvars[host], host


def test_tailnet_routes_are_single_host_routes_and_keep_the_pre_existing_ones() -> None:
    _, hostvars, _ = fleet.inventory_model()

    docker = hostvars["0docker_bastion"]["fleet_tailscale_node_advertise_routes"]
    own = hostvars["0own_bastion"]["fleet_tailscale_node_advertise_routes"]
    assert "10.10.10.109/32" in docker and "10.60.10.50/32" in own
    # `tailscale set --advertise-routes` replaces the list, so the older routes must still be declared.
    assert {"10.10.10.30/32", "10.10.10.106/32", "10.10.10.107/32"} <= set(docker)
    assert all(route.endswith("/32") for route in docker + own)


# ----------------------------------------------------------------------------- node_exporter


def test_exporter_args_line_matches_the_live_formats() -> None:
    role = "fleet_node_exporter"
    # Two addresses on one host, textfile flag, single quotes and a leading space (the 0mcp hypervisor layout).
    two_addresses = _context(
        role, **STUB_EXPORTER, fleet_node_exporter_args_quote="'", fleet_node_exporter_args_prefix=" "
    )
    assert fleet._render(role, "node-exporter-args.j2", two_addresses).strip() == (
        "ARGS=' --web.listen-address=192.0.2.10:9100 --web.listen-address=192.0.2.10:9102 "
        "--collector.textfile.directory=/var/lib/prometheus/node-exporter/textfile'"
    )
    # No textfile flag, extra flags kept verbatim and after the listeners.
    plain = _context(
        role,
        fleet_node_exporter_listen_addresses=["192.0.2.20:9100"],
        fleet_node_exporter_extra_args=["--no-collector.arp", "--collector.netdev.device-exclude=^(veth.*|br-.*)$"],
    )
    assert fleet._render(role, "node-exporter-args.j2", plain).strip() == (
        'ARGS="--web.listen-address=192.0.2.20:9100 --no-collector.arp '
        '--collector.netdev.device-exclude=^(veth.*|br-.*)$"'
    )
    # The template emits exactly one line.
    assert fleet._render(role, "node-exporter-args.j2", plain).count("\n") == 1


def test_exporter_never_renders_a_wildcard_listener() -> None:
    _, hostvars, _ = fleet.inventory_model()
    groups, _, _ = fleet.inventory_model()

    for host in groups["fleet_node_exporter_hosts"]:
        for address in hostvars[host]["fleet_node_exporter_listen_addresses"]:
            assert not address.startswith(("0.0.0.0", "::", "[::]")), (host, address)
    spec = _tasks("fleet_node_exporter", "main.yml")[0]
    assert any("wildcard" in str(condition) or "0\\.0\\.0\\.0" in str(condition) for condition in spec["ansible.builtin.assert"]["that"])


def test_socket_proxy_units_match_the_live_text() -> None:
    role = "fleet_node_exporter"
    context = _context(role, fleet_node_exporter_proxyd_path="/usr/lib/systemd/systemd-socket-proxyd")
    proxy = {
        "name": "zexample-hypervisor-metrics-proxy",
        "state": "present",
        "listen_address": "192.0.2.11",
        "listen_port": 9100,
        "upstream": "198.51.100.1:9100",
        "free_bind": True,
        "socket_description": "Tailscale-only node-exporter proxy for the example hypervisor",
        "service_description": "Forward the example hypervisor node-exporter over Tailscale only",
    }

    assert fleet._render(role, "metrics-proxy.socket.j2", context, proxy) == (
        "[Unit]\n"
        "Description=Tailscale-only node-exporter proxy for the example hypervisor\n"
        "After=network-online.target tailscaled.service\n"
        "Wants=network-online.target\n"
        "Requires=tailscaled.service\n"
        "\n"
        "[Socket]\n"
        "ListenStream=192.0.2.11:9100\n"
        "NoDelay=true\n"
        "FreeBind=true\n"
        "Service=zexample-hypervisor-metrics-proxy.service\n"
        "\n"
        "[Install]\n"
        "WantedBy=sockets.target\n"
    )
    assert fleet._render(role, "metrics-proxy.service.j2", context, proxy) == (
        "[Unit]\n"
        "Description=Forward the example hypervisor node-exporter over Tailscale only\n"
        "After=network-online.target tailscaled.service\n"
        "Wants=network-online.target\n"
        "Requires=tailscaled.service zexample-hypervisor-metrics-proxy.socket\n"
        "\n"
        "[Service]\n"
        "ExecStart=/usr/lib/systemd/systemd-socket-proxyd 198.51.100.1:9100\n"
        "DynamicUser=yes\n"
        "PrivateTmp=yes\n"
    )
    without_free_bind = fleet._render(role, "metrics-proxy.socket.j2", context, {**proxy, "free_bind": False})
    assert "FreeBind" not in without_free_bind


def _port_plan(host_vars: dict[str, Any]) -> list[str]:
    """Evaluate the real port_plan.yml expression with the host's variables (Ansible's zip filter stubbed)."""
    facts = _tasks("fleet_node_exporter", "port_plan.yml")
    env = jinja2.Environment(undefined=jinja2.StrictUndefined)
    env.filters["zip"] = lambda first, second: list(zip(first, second))
    context = dict(fleet.role_defaults("fleet_node_exporter"))
    context.update(host_vars)
    for task in facts[:2]:
        for name, expression in task["ansible.builtin.set_fact"].items():
            value = env.from_string(expression).render(**context)
            context[name] = yaml.safe_load(value)
    return context["fleet_node_exporter_port_plan"]


def test_hypervisor_port_plan_has_no_collision_and_models_the_build_metrics_proxy_as_managed() -> None:
    _, hostvars, _ = fleet.inventory_model()
    host = copy.deepcopy(hostvars["operator-bastion"])
    plan = _port_plan(host)

    assert len(plan) == len(set(plan))
    assert sorted(entry.rsplit(":", 1)[1] for entry in plan) == ["9100", "9101", "9102", "9103"]
    assert not [p for p in host["fleet_node_exporter_socket_proxies"] if p["state"] == "unmanaged"]
    proxy = next(p for p in host["fleet_node_exporter_socket_proxies"] if p["name"] == "woodpecker-0exec-build-metrics-proxy")
    assert proxy["state"] == "present"
    assert (proxy["listen_address"], proxy["listen_port"], proxy["upstream"]) == ("203.0.113.6", 9103, "10.10.10.30:9100")
    assert proxy["free_bind"] is True
    assert "100.114.37.21" in proxy["consumer"]
    # The tailnet port the exporter owns (:9100) is no longer claimed by the proxy.
    assert "203.0.113.6:9100" in host["fleet_node_exporter_listen_addresses"]


def test_build_metrics_proxy_socket_renders_freebind_on_the_tailnet_address_and_matches_the_live_text() -> None:
    _, hostvars, all_vars = fleet.inventory_model()
    artifacts = fleet.exporter_artifacts("operator-bastion", fleet._context("fleet_node_exporter", hostvars["operator-bastion"], all_vars))
    socket_unit = next(a for a in artifacts if a.path.endswith("woodpecker-0exec-build-metrics-proxy.socket"))
    service_unit = next(a for a in artifacts if a.path.endswith("woodpecker-0exec-build-metrics-proxy.service"))

    assert socket_unit.content == (
        "[Unit]\n"
        "Description=Tailscale-only node-exporter proxy for 0mcp docker-build-lv3\n"
        "After=network-online.target tailscaled.service\n"
        "Wants=network-online.target\n"
        "Requires=tailscaled.service\n"
        "\n"
        "[Socket]\n"
        "ListenStream=203.0.113.6:9103\n"
        "NoDelay=true\n"
        "FreeBind=true\n"
        "Service=woodpecker-0exec-build-metrics-proxy.service\n"
        "\n"
        "[Install]\n"
        "WantedBy=sockets.target\n"
    )
    assert "ExecStart=/lib/systemd/systemd-socket-proxyd 10.10.10.30:9100\n" in service_unit.content


def test_every_tailnet_bound_socket_proxy_uses_freebind() -> None:
    """A socket bound to a tailnet address fails to start (or stays dead) while tailscale0 has no address."""
    _, hostvars, all_vars = fleet.inventory_model()
    for host, variables in hostvars.items():
        for proxy in variables.get("fleet_node_exporter_socket_proxies", []):
            if proxy["state"] == "present" and proxy["listen_address"].startswith("100."):
                if proxy["name"] == "zmcp-runtime-general-metrics-proxy":
                    continue  # pre-existing unit that predates this change; not modified here
                assert proxy.get("free_bind") is True, (host, proxy["name"])


def test_enabling_a_proxy_on_the_exporters_port_is_refused() -> None:
    _, hostvars, _ = fleet.inventory_model()
    host = copy.deepcopy(hostvars["operator-bastion"])
    for proxy in host["fleet_node_exporter_socket_proxies"]:
        if proxy["name"] == "woodpecker-0exec-build-metrics-proxy":
            proxy["listen_port"] = 9100

    collision = _port_plan(host)
    assert len(collision) != len(set(collision))  # the assert in port_plan.yml would fail here
    assert any(task.get("ansible.builtin.assert") for task in _tasks("fleet_node_exporter", "port_plan.yml"))


def test_stale_woodpecker_exec_proxy_on_the_0docker_hypervisor_is_modelled_as_disabled() -> None:
    _, hostvars, all_vars = fleet.inventory_model()
    docker = hostvars["0docker_bastion"]
    stale = next(p for p in docker["fleet_node_exporter_socket_proxies"] if p["name"] == "woodpecker-exec-proxy@9100")
    assert stale["state"] == "disabled"

    plan = _port_plan(docker)
    assert len(plan) == len(set(plan))
    assert "203.0.113.5:9100" in plan  # still owned once, by the managed proxy

    artifacts = fleet.exporter_artifacts("0docker_bastion", fleet._context("fleet_node_exporter", docker, all_vars))
    unit = next(a for a in artifacts if a.path == "systemd unit woodpecker-exec-proxy@9100.socket")
    assert unit.kind == "state" and unit.state == {"enabled": "disabled", "active": "inactive"}
    assert not any(a.path.endswith("woodpecker-exec-proxy@9100.socket") and a.kind == "file" for a in artifacts)

    tasks = _tasks("fleet_node_exporter", "proxies.yml")
    stop = next(t for t in tasks if t["name"] == "Keep stale socket proxies stopped and disabled")
    assert stop["ansible.builtin.systemd"]["enabled"] is False and stop["ansible.builtin.systemd"]["state"] == "stopped"
    assert stop["loop"] == "{{ fleet_node_exporter_disabled_proxies }}"
    port_plan = _tasks("fleet_node_exporter", "port_plan.yml")
    known_state = next(t for t in port_plan if t["name"] == "Assert every proxy has a known state")
    assert "fleet_node_exporter_disabled_proxies" in str(known_state) and "disabled" in known_state["ansible.builtin.assert"]["fail_msg"]


def test_build_metrics_proxy_firewall_rule_and_tailnet_grant_match_the_proxy() -> None:
    host_vars = yaml.safe_load((REPO_ROOT / "inventory" / "host_vars" / "proxmox-host.yml").read_text(encoding="utf-8"))
    rule = next(r for r in host_vars["proxmox_host_additional_tcp_rules"] if r["port"] == 9103)
    assert (rule["source"], rule["destination"]) == ("100.114.37.21/32", "203.0.113.6")

    policy = (REPO_ROOT / "config" / "tailscale" / "policy.hujson").read_text(encoding="utf-8")
    grant = re.search(r'"src": \["tag:builder-metrics-controller"\],\s*"dst": \["100\.120\.234\.7/32"\],\s*"ip":\s*\["tcp:9103"\]', policy)
    assert grant, "tailnet grant for the build-metrics proxy on :9103 is missing"
    assert '"accept": ["203.0.113.6:9103"]' in policy, "policy test for the :9103 grant is missing"


def test_retired_build_metrics_port_9100_grant_and_cluster_rule_stay_removed() -> None:
    policy = (REPO_ROOT / "config" / "tailscale" / "policy.hujson").read_text(encoding="utf-8")
    stale = re.search(r'"src": \["tag:builder-metrics-controller"\],\s*"dst": \["100\.120\.234\.7/32"\],\s*"ip":\s*\["tcp:9100"\]', policy)
    assert not stale, "the retired tag:builder-metrics-controller -> 203.0.113.6 tcp:9100 grant is back"

    host_vars = yaml.safe_load((REPO_ROOT / "inventory" / "host_vars" / "proxmox-host.yml").read_text(encoding="utf-8"))
    cluster_rules = {(r["source"], r["port"]) for r in host_vars["proxmox_cluster_additional_tcp_rules"]}
    assert ("100.114.37.21/32", 9100) not in cluster_rules, "the retired CT108 -> :9100 cluster firewall rule is back"
    assert ("203.0.113.7/32", 9102) in cluster_rules


def test_hypervisor_proxy_that_cannot_share_an_address_uses_a_distinct_address_from_the_exporter() -> None:
    _, hostvars, _ = fleet.inventory_model()
    docker = hostvars["0docker_bastion"]

    plan = _port_plan(docker)
    assert len(plan) == len(set(plan))
    # Exporter 1.5.0 binds the internal address; the proxy republishes it on the tailnet address.
    assert docker["fleet_node_exporter_listen_addresses"] == ["10.10.10.1:9100"]
    proxy = next(p for p in docker["fleet_node_exporter_socket_proxies"] if p["state"] == "present")
    assert proxy["upstream"] == "10.10.10.1:9100"
    assert proxy["listen_address"] != "10.10.10.1" and proxy["free_bind"] is True


def test_userspace_tailscaled_host_uses_tailscale_serve_not_a_socket() -> None:
    _, hostvars, _ = fleet.inventory_model()
    builder = hostvars["0docker_builder"]

    assert builder["fleet_node_exporter_tailscale_serve_tcp"] == [{"port": 9100, "target": "10.10.10.108:9100"}]
    assert "fleet_node_exporter_socket_proxies" not in builder
    serve_tasks = yaml.safe_load((ROLES / "fleet_node_exporter" / "tasks" / "tailscale_serve.yml").read_text(encoding="utf-8"))
    applied = [t for t in serve_tasks if t["name"].startswith("Apply")][0]
    assert applied["ansible.builtin.command"]["argv"][:4] == ["tailscale", "serve", "--bg", "--tcp={{ item.port }}"]
    assert "when" in applied


def test_textfile_directories_keep_the_live_ownership() -> None:
    artifacts = {
        (host, a.path): (a.owner, a.group, a.mode)
        for host in ("operator-bastion", "0docker_bastion", "0database_bastion", "0docker_nginx", "0own_pbs", "0docker_builder")
        for a in fleet.render_host(host)
        if a.kind == "dir"
    }

    assert artifacts[("operator-bastion", "/var/lib/prometheus/node-exporter/textfile")] == ("root", "root", "755")
    assert artifacts[("0docker_bastion", "/var/lib/prometheus/node-exporter/textfile")] == ("root", "root", "755")
    assert artifacts[("0database_bastion", "/var/lib/prometheus/node-exporter/textfile")] == ("root", "root", "755")
    assert artifacts[("0docker_nginx", "/var/lib/prometheus/node-exporter/textfile")] == ("prometheus", "prometheus", "755")
    assert artifacts[("0own_pbs", "/var/lib/prometheus/node-exporter/textfile")] == ("prometheus", "prometheus", "755")
    assert artifacts[("0docker_builder", "/var/lib/prometheus-node-exporter/textfile")] == ("prometheus", "prometheus", "755")


# ----------------------------------------------------------------------------- guest firewall


def test_github_mirror_firewall_only_opens_9100_to_the_monitoring_vm_on_tailscale0() -> None:
    artifacts = {a.path: a for a in fleet.render_host("0own_github_mirror")}
    nft = artifacts["/etc/nftables.conf"].content

    assert nft.startswith("flush ruleset\ntable inet filter {\n")
    assert "policy drop;" in nft
    nine_thousand = [line.strip() for line in nft.splitlines() if "9100" in line]
    assert len(nine_thousand) == 1
    assert nine_thousand[0].startswith('iifname "tailscale0" ip saddr ') and nine_thousand[0].endswith("tcp dport 9100 accept")
    assert "# Prometheus (monitoring-lv3) node_exporter scrape only" in nft
    # SSH stays reachable from the hypervisor and over tailscale0, ICMP stays accepted.
    assert re.search(r"ip saddr 10\.60\.10\.1 tcp dport \{ 22, 3000 \} accept", nft)
    assert 'iifname "tailscale0" tcp dport { 22, 443 } accept' in nft
    assert "ip protocol icmp accept" in nft and "ip6 nexthdr ipv6-icmp accept" in nft


def test_firewall_template_table_mode_replaces_only_the_inet_filter_table() -> None:
    role = "fleet_guest_firewall"
    context = _context(
        role,
        fleet_guest_firewall_flush_mode="table",
        fleet_guest_firewall_allowed_inbound=[{"protocol": "tcp", "ports": [22]}, {"protocol": "tcp", "ports": [9100], "source": "192.0.2.5"}],
    )

    rendered = fleet._render(role, "nftables.conf.j2", context)
    assert rendered.startswith("destroy table inet filter\n")
    assert "flush ruleset" not in rendered
    assert "ip saddr 192.0.2.5 tcp dport 9100 accept" in rendered


def test_firewall_role_guards_against_a_lockout_and_validates_before_replacing() -> None:
    tasks = _tasks("fleet_guest_firewall", "main.yml")
    guard = tasks[0]["ansible.builtin.assert"]
    assert any("select('equalto', 22)" in condition for condition in guard["that"])
    template = [t for t in tasks if "ansible.builtin.template" in t][0]["ansible.builtin.template"]
    assert template["validate"] == "/usr/sbin/nft -c -f %s"
    reload_task = [t for t in tasks if t["name"].startswith("Reload the nftables")][0]
    assert reload_task["when"] == "fleet_guest_firewall_config is changed"
    assert any(t["name"].startswith("Wait for SSH") for t in tasks)


# ----------------------------------------------------------------------------- tailscale node


def test_tailscale_role_only_sets_routes_and_refuses_wider_routes() -> None:
    tasks = _tasks("fleet_tailscale_node", "main.yml")
    commands = [t["ansible.builtin.command"]["argv"] for t in tasks if "ansible.builtin.command" in t]

    assert commands[0] == ["tailscale", "debug", "prefs"]
    assert commands[1][:2] == ["tailscale", "set"]
    assert all(arg not in ("up", "login") for argv in commands for arg in argv)
    assert not any(a.startswith(("--ssh", "--accept", "--advertise-tags", "--exit-node")) for argv in commands for a in argv)
    guard = " ".join(tasks[0]["ansible.builtin.assert"]["that"])
    assert "/32" in guard and fleet.role_defaults("fleet_tailscale_node")["fleet_tailscale_node_allow_wider_routes"] is False


# ----------------------------------------------------------------------------- vzdump hook


HOOK_LOG = """\
2026-10-12 02:30:04 INFO: starting new backup job: vzdump 100 --storage own-pbs-0database
2026-10-12 02:53:58 INFO: backup was done incrementally, reused 540.64 GiB (90%)
2026-10-12 02:53:58 INFO: transferred 134.09 GiB in 1434 seconds (95.8 MiB/s)
2026-10-12 02:53:58 INFO: Finished Backup of VM 100 (00:23:55)
"""


def _hook(tmp_path: Path) -> tuple[Path, dict[str, Path]]:
    paths = {
        "state": tmp_path / "state",
        "textfile": tmp_path / "textfile",
        "logs": tmp_path / "vzdump-logs",
    }
    for directory in paths.values():
        directory.mkdir()
    context = _context(
        "fleet_pg_backup",
        fleet_pg_backup_state_dir=str(paths["state"]),
        fleet_pg_backup_hook_textfile_dir=str(paths["textfile"]),
        fleet_pg_backup_hook_vzdump_log_dir=str(paths["logs"]),
    )
    script = tmp_path / "hook.sh"
    script.write_text(fleet._render("fleet_pg_backup", "vzdump-pg-metrics-hook.j2", context), encoding="utf-8")
    script.chmod(0o755)
    return script, paths


def _run_hook(script: Path, phase: str, env: dict[str, str] | None = None, mode: str = "snapshot", vmid: str = "100") -> None:
    environment = {"PATH": os.environ["PATH"], **(env or {})}
    subprocess.run([str(script), phase, mode, vmid], env=environment, check=True, capture_output=True, text=True)


def _metrics(textfile: Path) -> dict[str, float]:
    values: dict[str, float] = {}
    for line in (textfile / "pg_backup_vzdump.prom").read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#"):
            name, value = line.rsplit(" ", 1)
            values[name.split("{", 1)[0]] = float(value)
    return values


def test_hook_records_size_and_duration_for_a_pbs_target_where_vzdump_sets_no_logfile(tmp_path: Path) -> None:
    script, paths = _hook(tmp_path)
    (paths["logs"] / "qemu-100.log").write_text(HOOK_LOG, encoding="utf-8")
    pbs_env = {"VMTYPE": "qemu", "STOREID": "own-pbs-0database", "HOSTNAME": "pg-primary"}  # no LOGFILE, as for PBS

    for phase in ("backup-start", "backup-end", "log-end"):
        _run_hook(script, phase, pbs_env)

    metrics = _metrics(paths["textfile"])
    assert metrics["pg_backup_last_status"] == 1
    assert metrics["pg_backup_size_bytes"] == round(134.09 * 1024**3)
    assert metrics["pg_backup_duration_seconds"] == 1434
    assert metrics["pg_backup_last_success_timestamp_seconds"] > 0
    assert 'vmid="100"' in (paths["textfile"] / "pg_backup_vzdump.prom").read_text(encoding="utf-8")


def test_hook_still_honours_logfile_when_vzdump_provides_it_and_takes_the_vmid_from_its_argument(tmp_path: Path) -> None:
    script, paths = _hook(tmp_path)
    logfile = tmp_path / "dir-target.log"
    logfile.write_text(HOOK_LOG.replace("1434 seconds", "99 seconds"), encoding="utf-8")

    for phase in ("backup-start", "backup-end"):
        _run_hook(script, phase, vmid="105")
    _run_hook(script, "log-end", {"LOGFILE": str(logfile), "VMTYPE": "qemu"}, vmid="105")

    metrics = _metrics(paths["textfile"])
    assert metrics["pg_backup_duration_seconds"] == 99
    assert 'vmid="105"' in (paths["textfile"] / "pg_backup_vzdump.prom").read_text(encoding="utf-8")


def test_hook_does_not_publish_a_stale_log_as_the_size_of_a_failed_run(tmp_path: Path) -> None:
    script, paths = _hook(tmp_path)
    (paths["logs"] / "qemu-100.log").write_text(HOOK_LOG, encoding="utf-8")

    for phase in ("backup-start", "backup-abort", "log-end"):
        _run_hook(script, phase, {"VMTYPE": "qemu"})

    metrics = _metrics(paths["textfile"])
    assert metrics["pg_backup_last_status"] == 0
    assert metrics["pg_backup_size_bytes"] == 0
    assert metrics["pg_backup_last_attempt_timestamp_seconds"] > 0


def test_hook_falls_back_to_the_measured_duration_when_the_log_is_unreadable(tmp_path: Path) -> None:
    script, paths = _hook(tmp_path)

    for phase in ("backup-start", "backup-end", "log-end"):
        _run_hook(script, phase, {"VMTYPE": "qemu"})

    metrics = _metrics(paths["textfile"])
    assert metrics["pg_backup_last_status"] == 1
    assert metrics["pg_backup_duration_seconds"] >= 0
    assert metrics["pg_backup_size_bytes"] == 0  # unknown, not invented


def test_hook_ignores_job_level_phases(tmp_path: Path) -> None:
    script, paths = _hook(tmp_path)

    subprocess.run([str(script), "job-start"], check=True, capture_output=True, text=True)

    assert not (paths["textfile"] / "pg_backup_vzdump.prom").exists()


# ----------------------------------------------------------------------------- pgBackRest, PBS, secrets


def test_pgbackrest_config_stays_dormant_and_free_of_secrets() -> None:
    artifacts = {a.path: a for a in fleet.render_host("0database_postgres") if a.kind == "file"}
    conf = artifacts["/etc/pgbackrest/pgbackrest.conf"].content
    service = artifacts["/root/pgbackrest-prepared/pgbackrest-daily.service"].content
    timer = artifacts["/root/pgbackrest-prepared/pgbackrest-daily.timer"].content
    wrapper = artifacts["/usr/local/sbin/pgbackrest-daily"].content

    assert "# repo1-type=sftp" in conf and not re.search(r"^repo1-(type|path|sftp)", conf, re.MULTILINE)
    assert "cipher" not in re.sub(r"^#.*$", "", conf, flags=re.MULTILINE)
    assert "[main]" in conf and "pg1-path=/var/lib/postgresql/18/main" in conf
    assert 'STANZA="${STANZA:-main}"' in wrapper  # was "prod": a stanza the config does not define
    assert "OnCalendar=" in timer and "ExecStart=/usr/local/sbin/pgbackrest-daily" in service
    # The units are only prepared: nothing renders into /etc/systemd/system unless the timer is explicitly enabled.
    assert all(not path.startswith("/etc/systemd/system") for path in artifacts)
    defaults = fleet.role_defaults("fleet_pg_backup")
    assert defaults["fleet_pg_backup_pgbackrest_timer_enabled"] is False
    assert defaults["fleet_pg_backup_pgbackrest_repo"] == {}


def test_pgbackrest_role_never_changes_postgres_or_reads_the_passphrase() -> None:
    text = "\n".join(path.read_text(encoding="utf-8") for path in (ROLES / "fleet_pg_backup" / "tasks").glob("*.yml"))
    commands = re.findall(r"^\s+- (?:psql|ALTER SYSTEM)", text, re.MULTILINE)

    assert not commands and "archive_mode" not in re.sub(r"#.*", "", text)
    for secret_task in ("slurp", "lookup('ansible.builtin.file'", "lookup('file'"):
        assert secret_task not in text
    stat_tasks = [t for t in _tasks("fleet_pg_backup", "pgbackrest.yml") if "ansible.builtin.stat" in t]
    assert [t["ansible.builtin.stat"]["path"] for t in stat_tasks] == ["{{ fleet_pg_backup_pgbackrest_conf_dir }}/{{ fleet_pg_backup_pgbackrest_cipher_file }}"]
    guard = " ".join(_tasks("fleet_pg_backup", "pgbackrest.yml")[0]["ansible.builtin.assert"]["that"])
    assert "timer_enabled" in guard and "fleet_node_exporter_textfile_dir" in guard


def test_pve_backup_references_the_storage_secret_without_reading_it() -> None:
    _, hostvars, _ = fleet.inventory_model()
    storage = hostvars["0database_bastion"]["fleet_pg_backup_pve_storage"]
    job = hostvars["0database_bastion"]["fleet_pg_backup_pve_jobs"][0]

    assert storage["password_file"] == "/etc/pve/priv/storage/own-pbs-0database.pw"
    assert "password" not in {key for key in storage if key != "password_file"}
    assert (job["id"], job["vmid"], job["schedule"], job["bwlimit"], job["mode"], job["enabled"]) == (
        "pg-primary-daily-pbs",
        "100",
        "02:30",
        100000,
        "snapshot",
        True,
    )
    assert job["notes_template"] == "{{guestname}} {{vmid}} daily crash-consistent"
    text = (ROLES / "fleet_pg_backup" / "tasks" / "pve_backup.yml").read_text(encoding="utf-8")
    assert "slurp" not in text and "--password" not in text and "pvesm" not in text.replace("`pvesm add pbs`", "")


def test_pbs_side_only_verifies_namespace_and_token_and_never_generates_secrets() -> None:
    text = (ROLES / "fleet_pg_backup" / "tasks" / "pbs_server.yml").read_text(encoding="utf-8")

    assert "generate-token" not in re.sub(r"fail_msg:.*?(?=\n- name:|\Z)", "", text, flags=re.DOTALL)
    assert "namespace create" not in text and "ns/" in text
    argv_lines = re.findall(r"^\s+- (user|acl|prune-job|create|update|list|list-tokens)$", text, re.MULTILINE)
    assert "delete" not in text.lower().replace("deleted", "")
    assert argv_lines  # reads and additive writes only
    _, hostvars, _ = fleet.inventory_model()
    acls = hostvars["0own_pbs"]["fleet_pg_backup_pbs_acls"]
    assert {a["path"] for a in acls} == {"/datastore/own-pbs/0database"}
    assert {a["role"] for a in acls} == {"DatastoreBackup", "DatastoreAudit"}


def test_no_secret_values_in_the_new_files() -> None:
    files = [INVENTORY, PLAYBOOK, REPO_ROOT / "scripts" / "fleet_observability_render.py", REPO_ROOT / "docs" / "runbooks" / "fleet-observability.md"]
    for role in NEW_ROLES:
        files += [path for path in (ROLES / role).rglob("*") if path.is_file()]
    # A variable that looks like a secret and carries a long literal value. File references (*_file) and names
    # (*_name) are fine; they point at a secret or label one.
    secret_assignment = re.compile(
        r"(?im)^\s*(repo\d-cipher-pass|[a-z_]*(?:password|passphrase|secret|token)[a-z_]*(?<!_file)(?<!_name))\s*[:=]\s*['\"]?[A-Za-z0-9+=_-]{12,}"
    )
    key_material = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----|tskey-[A-Za-z0-9-]+|[A-Za-z0-9]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")

    for path in files:
        text = path.read_text(encoding="utf-8")
        assert not secret_assignment.search(text), path
        assert not key_material.search(text), path


# ----------------------------------------------------------------------------- playbook safety and wiring


def test_playbook_refuses_to_run_without_a_limit_and_is_not_wired_anywhere_by_default() -> None:
    plays = yaml.safe_load(PLAYBOOK.read_text(encoding="utf-8"))
    guard = plays[0]

    assert guard["hosts"] == "all" and guard["run_once"] is True and guard["gather_facts"] is False
    conditions = " ".join(guard["tasks"][0]["ansible.builtin.assert"]["that"])
    assert "ansible_limit is defined" in conditions
    assert "'all'" in conditions and "'*'" in conditions
    assert "ansible_play_hosts_all | length <= (fleet_observability_max_hosts | default(1) | int)" in conditions
    for play in plays[1:]:
        assert play["serial"] == 1
        assert play["hosts"].startswith("fleet_") and play["hosts"].endswith("_hosts")
        assert play["tags"]
    assert [play["roles"][0]["role"] for play in plays[1:]] == [
        "lv3.platform.fleet_node_exporter",
        "lv3.platform.fleet_tailscale_node",
        "lv3.platform.fleet_guest_firewall",
        "lv3.platform.fleet_pg_backup",
        "lv3.platform.fleet_docker_prune",
    ]

    for wired in ("playbooks/site.yml", "Makefile", ".woodpecker.yml", "ansible.cfg"):
        path = REPO_ROOT / wired
        if path.exists():
            assert "fleet-observability" not in path.read_text(encoding="utf-8"), wired
    assert "fleet-observability" not in (REPO_ROOT / "ansible.cfg").read_text(encoding="utf-8")
    assert "inventory/hosts.yml" in (REPO_ROOT / "ansible.cfg").read_text(encoding="utf-8")


def test_new_roles_follow_the_repo_role_conventions() -> None:
    config = yaml.safe_load((REPO_ROOT / "config" / "ansible-role-idempotency.yml").read_text(encoding="utf-8"))

    for role in NEW_ROLES:
        root = ROLES / role
        assert (root / "README.md").is_file() and (root / "tasks" / "main.yml").is_file(), role
        spec = yaml.safe_load((root / "meta" / "argument_specs.yml").read_text(encoding="utf-8"))
        options = spec["argument_specs"]["main"]["options"]
        defaults = fleet.role_defaults(role)
        assert set(defaults) <= set(options), (role, set(defaults) - set(options))
        for task_file in (root / "tasks").glob("*.yml"):
            text = task_file.read_text(encoding="utf-8")
            assert text.startswith("---\n"), task_file
            if task_file.name != "main.yml" or role != "fleet_tailscale_node":
                assert "# Purpose:" in text or task_file.name in {"pve_backup_job.yml"} or text.splitlines()[1].startswith("- name:"), task_file
            yaml.safe_load(text)
        assert role in config["roles"] and config["roles"][role]["policy"] == "tracked"


def test_checks_never_apply_changes_in_check_mode_reads_are_marked() -> None:
    """Read-only probes must run in --check --diff so the drift report is real."""
    probes = {
        "fleet_node_exporter": ("tailscale_serve.yml", "Read the current tailscale serve configuration"),
        "fleet_tailscale_node": ("main.yml", "Read the live tailscale preferences"),
        "fleet_pg_backup": ("pve_backup.yml", "Read the live PBS storage entry"),
    }
    for role, (file_name, task_name) in probes.items():
        task = [t for t in _tasks(role, file_name) if t["name"] == task_name][0]
        assert task["check_mode"] is False and task["changed_when"] is False, (role, task_name)


def test_every_mutating_command_is_guarded_by_a_drift_condition() -> None:
    for role in NEW_ROLES:
        for task_file in (ROLES / role / "tasks").glob("*.yml"):
            for task in yaml.safe_load(task_file.read_text(encoding="utf-8")):
                command = task.get("ansible.builtin.command")
                if not command:
                    continue
                argv = command.get("argv", []) if isinstance(command, dict) else []
                mutating = (
                    argv[:2] == ["tailscale", "set"]
                    or argv[:2] == ["tailscale", "serve"] and "--bg" in argv
                    or argv[:2] == ["pvesh", "set"]
                    or argv[:2] == ["pvesh", "create"]
                    or argv[:1] == ["proxmox-backup-manager"] and any(a in argv for a in ("create", "update"))
                    or argv[:2] == ["nft", "-f"]
                )
                if mutating:
                    assert "when" in task, (role, task_file.name, task["name"])


# ----------------------------------------------------------------------------- syntax


def _strings(node: Any) -> list[str]:
    if isinstance(node, str):
        return [node]
    if isinstance(node, list):
        return [text for item in node for text in _strings(item)]
    if isinstance(node, dict):
        return [text for key, value in node.items() for text in _strings(key) + _strings(value)]
    return []


def test_every_task_expression_and_template_parses_as_jinja() -> None:
    """Ansible is not installed here, so at least prove that no expression or template has a syntax error."""
    env = jinja2.Environment()
    parsed = 0
    for role in NEW_ROLES:
        for task_file in (ROLES / role / "tasks").glob("*.yml"):
            for text in _strings(yaml.safe_load(task_file.read_text(encoding="utf-8"))):
                if "{{" in text or "{%" in text:
                    env.parse(text)
                    parsed += 1
        for template in (ROLES / role / "templates").glob("*.j2"):
            env.parse(template.read_text(encoding="utf-8"))
            parsed += 1
        for handler in (ROLES / role / "handlers").glob("*.yml"):
            yaml.safe_load(handler.read_text(encoding="utf-8"))
    for text in _strings(yaml.safe_load(PLAYBOOK.read_text(encoding="utf-8"))):
        if "{{" in text or "{%" in text:
            env.parse(text)
            parsed += 1
    assert parsed > 100


def test_tasks_only_use_fully_qualified_builtin_modules() -> None:
    allowed = {
        "ansible.builtin.apt", "ansible.builtin.assert", "ansible.builtin.command", "ansible.builtin.copy",
        "ansible.builtin.debug", "ansible.builtin.file", "ansible.builtin.include_tasks", "ansible.builtin.lineinfile",
        "ansible.builtin.meta", "ansible.builtin.set_fact", "ansible.builtin.stat", "ansible.builtin.systemd",
        "ansible.builtin.template", "ansible.builtin.wait_for_connection",
    }
    keywords = {
        "name", "when", "loop", "loop_control", "register", "changed_when", "failed_when", "check_mode", "notify",
        "block", "vars", "delegate_to", "tags", "become", "no_log", "run_once", "listen",
    }

    def walk(tasks: list[dict[str, Any]], origin: str) -> None:
        for task in tasks:
            if "block" in task:
                walk(task["block"], origin)
            modules = set(task) - keywords
            assert modules <= allowed, (origin, task.get("name"), modules - allowed)
            assert len(modules) <= 1, (origin, task.get("name"))

    for role in NEW_ROLES:
        for task_file in (ROLES / role / "tasks").glob("*.yml"):
            walk(yaml.safe_load(task_file.read_text(encoding="utf-8")), f"{role}/{task_file.name}")
    walk(yaml.safe_load(PLAYBOOK.read_text(encoding="utf-8"))[0]["tasks"], "playbook")
