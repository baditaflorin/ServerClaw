#!/usr/bin/env python3

from __future__ import annotations

import argparse
import ipaddress
import json
import re
from typing import Any

from controller_automation_toolkit import load_json, repo_path
from drift_lib import build_guest_ssh_command, build_host_ssh_command, drift_event_topic, load_controller_context, run_command


SERVICE_CATALOG_PATH = repo_path("config", "service-capability-catalog.json")

# Sentinel used in the internal tuple representation for a rule that carries
# no source restriction (network_policy `source: public`).
ANY_SOURCE = "any"

_LOCAL_ONLY_SOURCES = ("172.16.0.0/12", "192.168.0.0/16")

_LIVE_NFT_RULE_RE = re.compile(
    r"^\s*(?:ip saddr (?P<saddr>\S+)\s+)?"
    r"(?:(?P<proto>tcp|udp) dport \{?\s*(?P<ports>[0-9,\s-]+?)\s*\}?"
    r"|(?P<vrrp>ip protocol vrrp)"
    r"|(?P<icmp>icmp type echo-request))"
    r"\s+accept\s*;?\s*$"
)
_LIVE_FW_RULE_RE = re.compile(
    r"^IN ACCEPT(?: -source (?P<source>\S+))? -p (?P<proto>\w+)(?: -dport (?P<port>\d+))?"
    r"\s*(?:#\s*(?P<comment>.*))?$"
)
# Some .fw files carry hand-marked blocks like:
#   # BEGIN fleet-pool-fw (generated from firewall-pools.json -- edit that, not this)
#   ...
#   # END fleet-pool-fw
# confirmed live on VM120 (docker-runtime) 2026-08-26, referencing a `firewall-pools.json`
# and an `OPS.md` that do not exist anywhere in this repo or (per `gh search code`) anywhere
# in the org — the generator behind this marker is real (it's dated, described, and matches
# this file's own rendering conventions) but currently undiscovered. Until its source of
# truth is found, rules inside a marked block are treated as "externally managed" rather
# than raw drift, so a legitimate future addition there doesn't read as a critical incident.
_MANAGED_BLOCK_BEGIN_RE = re.compile(r"^#\s*BEGIN\s+(?P<name>\S+)")
_MANAGED_BLOCK_END_RE = re.compile(r"^#\s*END\s+(?P<name>\S+)")


def _guest_ip_map(host_vars: dict[str, Any]) -> dict[str, str]:
    return {guest["name"]: guest["ipv4"] for guest in host_vars["proxmox_guests"]}


def _resolve_policy(host_vars: dict[str, Any]) -> dict[str, Any]:
    """Return network_policy with its one self-referential Jinja expression resolved.

    `load_yaml()` is a plain `yaml.safe_load` (see platform/repo.py) — it does not
    render Jinja. `host_source` and `guest_management_sources` embed
    `{{ proxmox_internal_ipv4 }}`, which every other script in this repo sidesteps by
    reading `proxmox_internal_ipv4` directly instead of through network_policy. We
    can't sidestep it here since we need host_source/guest_management_sources as
    concrete CIDRs to compare against live state, so resolve the one known token.
    """
    token = "{{ proxmox_internal_ipv4 }}"
    internal_ip = str(host_vars["proxmox_internal_ipv4"])
    policy = dict(host_vars["network_policy"])
    policy["host_source"] = str(policy["host_source"]).replace(token, internal_ip)
    policy["guest_management_sources"] = [
        str(source).replace(token, internal_ip) for source in policy.get("guest_management_sources", [])
    ]
    return policy


def resolve_rule_sources(
    rule: dict[str, Any], *, policy: dict[str, Any], guest_ip_map: dict[str, str], guest_name: str
) -> list[str]:
    """Expand `rule.source` into concrete CIDRs, mirroring nftables.conf.j2 / vm.fw.j2's render macros."""
    source = rule.get("source")
    if source == "public":
        return [ANY_SOURCE]
    if source == "management":
        return list(policy.get("guest_management_sources", []))
    if source == "host":
        return [policy["host_source"]]
    if source == "all_guests":
        return [f"{ip}/32" for name, ip in sorted(guest_ip_map.items()) if name != guest_name]
    if source in guest_ip_map:
        return [f"{guest_ip_map[source]}/32"]
    return [str(source)]


def _normalize_ports(rule: dict[str, Any]) -> list[int | None]:
    if rule.get("protocol") in {"vrrp", "icmp"}:
        return [None]
    ports: list[int | None] = []
    for port in rule.get("ports", []):
        text = str(port)
        if ":" in text:
            start, end = (int(part) for part in text.split(":", 1))
            ports.extend(range(start, end + 1))
        else:
            ports.append(int(text))
    return ports


def declared_guest_rules(
    policy: dict[str, Any], guest_ip_map: dict[str, str], guest_name: str
) -> set[tuple[str, str, int | None]]:
    """Declared (source, protocol, port) tuples for the in-guest nftables `input` chain."""
    guest_policy = policy["guests"][guest_name]
    declared: set[tuple[str, str, int | None]] = set()
    for rule in guest_policy.get("allowed_inbound", []):
        for source in resolve_rule_sources(rule, policy=policy, guest_ip_map=guest_ip_map, guest_name=guest_name):
            for port in _normalize_ports(rule):
                declared.add((source, rule["protocol"], port))
    return declared


def declared_proxmox_rules(
    policy: dict[str, Any], guest_ip_map: dict[str, str], guest_name: str
) -> set[tuple[str, str, int | None]]:
    """Declared (source, protocol, port) tuples for the Proxmox-level `<vmid>.fw`.

    Mirrors vm.fw.j2's carve-out: local-only-CIDR rules are dropped from this layer
    when `allow_container_forwarding` is set, because the guest's own nftables policy
    already enforces them (see the comment in vm.fw.j2 next to `guest_local_only_sources`).
    """
    guest_policy = policy["guests"][guest_name]
    allow_forwarding = bool(guest_policy.get("allow_container_forwarding", False))
    declared: set[tuple[str, str, int | None]] = set()
    for rule in guest_policy.get("allowed_inbound", []):
        raw_source = rule.get("source")
        if allow_forwarding and raw_source in _LOCAL_ONLY_SOURCES:
            continue
        for source in resolve_rule_sources(rule, policy=policy, guest_ip_map=guest_ip_map, guest_name=guest_name):
            for port in _normalize_ports(rule):
                declared.add((source, rule["protocol"], port))
    return declared


def parse_live_nftables(ruleset_text: str) -> tuple[set[tuple[str, str, int | None]], list[str]]:
    """Parse `nft list ruleset` text output into (source, protocol, port) tuples.

    Returns (parsed_tuples, unparsed_lines) — unparsed lines are surfaced rather than
    silently dropped, since a parser gap here would otherwise look like "no drift".
    """
    live: set[tuple[str, str, int | None]] = set()
    unparsed: list[str] = []
    in_input_chain = False
    for raw_line in ruleset_text.splitlines():
        line = raw_line.strip()
        if line.startswith("chain input"):
            in_input_chain = True
            continue
        if in_input_chain and line == "}":
            in_input_chain = False
            continue
        if not in_input_chain or not line or line.startswith(("type filter", "policy", "iifname", "ct state")):
            continue
        match = _LIVE_NFT_RULE_RE.match(line)
        if not match:
            unparsed.append(raw_line)
            continue
        source = match.group("saddr") or ANY_SOURCE
        if match.group("vrrp"):
            live.add((source, "vrrp", None))
        elif match.group("icmp"):
            live.add((source, "icmp", None))
        else:
            proto = match.group("proto")
            for port_text in match.group("ports").split(","):
                live.add((source, proto, int(port_text.strip())))
    return live, unparsed


def parse_live_proxmox_fw(
    fw_text: str,
) -> tuple[set[tuple[str, str, int | None]], list[str], dict[tuple[str, str, int | None], str]]:
    """Returns (live_tuples, unparsed_lines, managed_block_by_tuple).

    `managed_block_by_tuple` maps a live tuple to the name of the `# BEGIN <name>`
    block it was found inside, for rules that live inside a hand-marked, apparently
    externally-generated block rather than being emitted by this repo's own
    proxmox_network/vm.fw.j2 rendering.
    """
    live: set[tuple[str, str, int | None]] = set()
    unparsed: list[str] = []
    managed_block_by_tuple: dict[tuple[str, str, int | None], str] = {}
    in_rules = False
    current_block: str | None = None
    for raw_line in fw_text.splitlines():
        line = raw_line.strip()
        if line == "[RULES]":
            in_rules = True
            continue
        if line.startswith("[") and line != "[RULES]":
            in_rules = False
            continue
        if not in_rules:
            continue
        if line.startswith("#"):
            begin_match = _MANAGED_BLOCK_BEGIN_RE.match(line)
            end_match = _MANAGED_BLOCK_END_RE.match(line)
            if begin_match:
                current_block = begin_match.group("name")
            elif end_match:
                current_block = None
            continue
        if not line:
            continue
        match = _LIVE_FW_RULE_RE.match(line)
        if not match:
            unparsed.append(raw_line)
            continue
        source = match.group("source") or ANY_SOURCE
        port = int(match.group("port")) if match.group("port") else None
        tup = (source, match.group("proto"), port)
        live.add(tup)
        if current_block:
            managed_block_by_tuple[tup] = current_block
    return live, unparsed, managed_block_by_tuple


def _diff_records(
    *,
    layer: str,
    guest_name: str,
    declared: set[tuple[str, str, int | None]],
    live: set[tuple[str, str, int | None]],
    managed_block_by_tuple: dict[tuple[str, str, int | None], str] | None = None,
) -> list[dict[str, Any]]:
    managed_block_by_tuple = managed_block_by_tuple or {}
    records: list[dict[str, Any]] = []
    for source, proto, port in sorted(live - declared, key=str):
        managed_by = managed_block_by_tuple.get((source, proto, port))
        if managed_by:
            records.append(
                {
                    "source": "firewall",
                    "layer": layer,
                    "event": drift_event_topic("warn"),
                    "severity": "warn",
                    "resource": guest_name,
                    "detail": (
                        f"{layer}: live rule for {source} {proto}"
                        f"{f'/{port}' if port is not None else ''} on {guest_name} is managed by the "
                        f"'{managed_by}' block, not by network_policy — not yet mirrored into the declared "
                        "source of truth (see ADR 0489)"
                    ),
                    "rule": {"source": source, "protocol": proto, "port": port},
                    "managed_by": managed_by,
                    "shared_surfaces": [guest_name],
                }
            )
            continue
        records.append(
            {
                "source": "firewall",
                "layer": layer,
                "event": drift_event_topic("critical"),
                "severity": "critical",
                "resource": guest_name,
                "detail": (
                    f"{layer}: live rule allows {source} {proto}"
                    f"{f'/{port}' if port is not None else ''} on {guest_name} "
                    "with no matching declaration in network_policy — likely applied out-of-band"
                ),
                "rule": {"source": source, "protocol": proto, "port": port},
                "shared_surfaces": [guest_name],
            }
        )
    for source, proto, port in sorted(declared - live, key=str):
        records.append(
            {
                "source": "firewall",
                "layer": layer,
                "event": drift_event_topic("warn"),
                "severity": "warn",
                "resource": guest_name,
                "detail": (
                    f"{layer}: declared rule for {source} {proto}"
                    f"{f'/{port}' if port is not None else ''} on {guest_name} "
                    "is not present live — apply is pending"
                ),
                "rule": {"source": source, "protocol": proto, "port": port},
                "shared_surfaces": [guest_name],
            }
        )
    return records


def collect_drift(context: dict[str, Any] | None = None, *, guests: list[str] | None = None) -> list[dict[str, Any]]:
    context = context or load_controller_context()
    host_vars = context["host_vars"]
    policy = _resolve_policy(host_vars)
    guest_ip_map = _guest_ip_map(host_vars)
    guest_names = guests or sorted(policy["guests"].keys())

    guest_by_name = {g["name"]: g for g in host_vars["proxmox_guests"]}
    records: list[dict[str, Any]] = []

    for guest_name in guest_names:
        if guest_name not in policy["guests"]:
            continue

        nft_result = run_command(build_guest_ssh_command(context, guest_name, "sudo -n nft list ruleset 2>/dev/null || nft list ruleset"))
        if nft_result.returncode != 0:
            records.append(
                {
                    "source": "firewall",
                    "layer": "guest-nftables",
                    "event": drift_event_topic("unreachable"),
                    "severity": "warn",
                    "resource": guest_name,
                    "detail": f"could not collect live nftables state: {nft_result.stderr or nft_result.stdout}",
                    "shared_surfaces": [guest_name],
                }
            )
        else:
            live, unparsed = parse_live_nftables(nft_result.stdout)
            declared = declared_guest_rules(policy, guest_ip_map, guest_name)
            records.extend(_diff_records(layer="guest-nftables", guest_name=guest_name, declared=declared, live=live))
            for line in unparsed:
                records.append(
                    {
                        "source": "firewall",
                        "layer": "guest-nftables",
                        "event": drift_event_topic("warn"),
                        "severity": "warn",
                        "resource": guest_name,
                        "detail": f"unparsed live nftables line (not compared, may hide drift): {line.strip()!r}",
                        "shared_surfaces": [guest_name],
                    }
                )

        vmid = guest_by_name.get(guest_name, {}).get("vmid")
        if vmid is None:
            continue
        fw_result = run_command(build_host_ssh_command(context, f"cat /etc/pve/firewall/{vmid}.fw 2>/dev/null"))
        if fw_result.returncode != 0 or not fw_result.stdout.strip():
            continue
        live_fw, unparsed_fw, managed_fw = parse_live_proxmox_fw(fw_result.stdout)
        declared_fw = declared_proxmox_rules(policy, guest_ip_map, guest_name)
        records.extend(
            _diff_records(
                layer="proxmox-fw",
                guest_name=guest_name,
                declared=declared_fw,
                live=live_fw,
                managed_block_by_tuple=managed_fw,
            )
        )
        for line in unparsed_fw:
            records.append(
                {
                    "source": "firewall",
                    "layer": "proxmox-fw",
                    "event": drift_event_topic("warn"),
                    "severity": "warn",
                    "resource": guest_name,
                    "detail": f"unparsed live proxmox .fw line (not compared, may hide drift): {line.strip()!r}",
                    "shared_surfaces": [guest_name],
                }
            )

    return records


def _service_map() -> dict[str, dict[str, Any]]:
    payload = load_json(SERVICE_CATALOG_PATH)
    return {service["id"]: service for service in payload.get("services", [])}


def _port_from_internal_url(service: dict[str, Any]) -> int | None:
    url = service.get("internal_url")
    if not isinstance(url, str) or ":" not in url.rsplit("/", 1)[-1]:
        return None
    try:
        return int(url.rsplit(":", 1)[-1].split("/", 1)[0])
    except ValueError:
        return None


def collect_dependency_gaps(host_vars: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Cross-reference service-capability-catalog `depends_on` against declared network_policy.

    Static declared-vs-declared check (no SSH) — catches "the rule was never added at
    all" even before any live drift run. This is the check that would have caught the
    gitea -> MinIO port-9010 gap ahead of the outage it caused.
    """
    host_vars = host_vars or load_controller_context()["host_vars"]
    policy = _resolve_policy(host_vars)
    guest_ip_map = _guest_ip_map(host_vars)
    services = _service_map()
    records: list[dict[str, Any]] = []

    for service in services.values():
        depender_vm = service.get("vm")
        for dep_id in service.get("depends_on", []):
            dependency = services.get(dep_id)
            if dependency is None:
                records.append(
                    {
                        "source": "firewall-dependency",
                        "event": drift_event_topic("warn"),
                        "severity": "warn",
                        "service": service["id"],
                        "detail": f"{service['id']} declares depends_on '{dep_id}' which is not a known service id",
                        "shared_surfaces": [service["id"]],
                    }
                )
                continue
            target_vm = dependency.get("vm")
            port = _port_from_internal_url(dependency)
            if not depender_vm or not target_vm or port is None:
                records.append(
                    {
                        "source": "firewall-dependency",
                        "event": drift_event_topic("warn"),
                        "severity": "warn",
                        "service": service["id"],
                        "detail": (
                            f"cannot verify {service['id']} -> {dep_id}: missing vm or a parseable port "
                            "in the service catalog"
                        ),
                        "shared_surfaces": [service["id"], dep_id],
                    }
                )
                continue
            if target_vm not in policy.get("guests", {}):
                continue
            declared = declared_guest_rules(policy, guest_ip_map, target_vm)
            permitted = any(
                proto in {"tcp", "udp"} and rule_port == port and _source_covers(source, depender_vm, guest_ip_map)
                for source, proto, rule_port in declared
            )
            if not permitted:
                records.append(
                    {
                        "source": "firewall-dependency",
                        "event": drift_event_topic("critical"),
                        "severity": "critical",
                        "service": service["id"],
                        "resource": target_vm,
                        "detail": (
                            f"{service['id']} ({depender_vm}) depends on {dep_id} ({target_vm}:{port}) "
                            f"but no network_policy rule on {target_vm} permits {depender_vm} on port {port}"
                        ),
                        "shared_surfaces": [service["id"], dep_id, target_vm],
                    }
                )
    return records


def _source_covers(declared_source: str, depender_vm: str, guest_ip_map: dict[str, str]) -> bool:
    if declared_source == ANY_SOURCE:
        return True
    if depender_vm not in guest_ip_map:
        return False
    depender_ip = guest_ip_map[depender_vm]
    try:
        return ipaddress.ip_address(depender_ip) in ipaddress.ip_network(declared_source, strict=False)
    except ValueError:
        return False


def explain(*, target_guest: str, port: int, source_guest: str, host_vars: dict[str, Any] | None = None) -> dict[str, Any]:
    """Answer: can `source_guest` reach `target_guest` on `port`, and why (or why not)?"""
    host_vars = host_vars or load_controller_context()["host_vars"]
    policy = _resolve_policy(host_vars)
    guest_ip_map = _guest_ip_map(host_vars)
    if target_guest not in policy.get("guests", {}):
        return {"reachable": False, "reason": f"'{target_guest}' has no network_policy.guests entry"}

    guest_policy = policy["guests"][target_guest]
    for rule in guest_policy.get("allowed_inbound", []):
        if rule.get("protocol") not in {"tcp", "udp"}:
            continue
        if port not in [p for p in _normalize_ports(rule) if p is not None]:
            continue
        for source in resolve_rule_sources(rule, policy=policy, guest_ip_map=guest_ip_map, guest_name=target_guest):
            if _source_covers(source, source_guest, guest_ip_map):
                return {
                    "reachable": True,
                    "matched_rule": rule,
                    "declared_source_expr": rule.get("source"),
                    "resolved_source": source,
                    "description": rule.get("description"),
                    "provenance": rule.get("provenance"),
                    "owner": (rule.get("provenance") or {}).get("owner", "unset — see inventory/host_vars/proxmox-host.yml git blame"),
                }
    return {
        "reachable": False,
        "reason": f"no allowed_inbound rule on '{target_guest}' permits {source_guest} on port {port}",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Detect firewall drift and dependency gaps against network_policy.")
    sub = parser.add_subparsers(dest="mode")

    drift_parser = sub.add_parser("drift", help="Diff declared network_policy against live host/guest state (default).")
    drift_parser.add_argument("--guest", action="append", dest="guests", help="Limit to this guest (repeatable).")

    deps_parser = sub.add_parser("deps", help="Static check: service depends_on vs declared network_policy.")
    del deps_parser

    explain_parser = sub.add_parser("explain", help="Can <source> reach <target> on <port>, and why?")
    explain_parser.add_argument("target_guest")
    explain_parser.add_argument("port", type=int)
    explain_parser.add_argument("source_guest")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    mode = args.mode or "drift"
    if mode == "drift":
        print(json.dumps(collect_drift(guests=getattr(args, "guests", None)), indent=2))
    elif mode == "deps":
        print(json.dumps(collect_dependency_gaps(), indent=2))
    elif mode == "explain":
        print(json.dumps(explain(target_guest=args.target_guest, port=args.port, source_guest=args.source_guest), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
