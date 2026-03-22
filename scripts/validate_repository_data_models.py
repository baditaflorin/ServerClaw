#!/usr/bin/env python3

import argparse
import datetime as dt
import ipaddress
import json
import re
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ModuleNotFoundError as exc:  # pragma: no cover - direct runtime guard
    print(
        "Missing dependency: PyYAML. Run via 'uvx --from pyyaml python ...' or 'uv run --with pyyaml ...'.",
        file=sys.stderr,
    )
    raise SystemExit(2) from exc

from live_apply_receipts import RECEIPTS_DIR, iter_receipt_paths, validate_receipts
from workflow_catalog import (
    load_secret_manifest,
    load_workflow_catalog,
    validate_secret_manifest,
    validate_workflow_catalog,
)


REPO_ROOT = Path(__file__).resolve().parent.parent
STACK_PATH = REPO_ROOT / "versions" / "stack.yaml"
HOST_VARS_PATH = REPO_ROOT / "inventory" / "host_vars" / "proxmox_florin.yml"
UPTIME_MONITORS_PATH = REPO_ROOT / "config" / "uptime-kuma" / "monitors.json"

SEMVER_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
HOSTNAME_PATTERN = re.compile(r"^[a-z0-9-]+(\.[a-z0-9-]+)*$")
IDENTIFIER_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
DNS_LABEL_PATTERN = re.compile(r"^[a-z0-9-]+$")
MAC_PATTERN = re.compile(r"^[0-9A-F]{2}(:[0-9A-F]{2}){5}$")
SERVICE_EXPOSURE_MODELS = {
    "edge-static",
    "edge-published",
    "informational-only",
    "private-only",
}
DNS_VISIBILITIES = {"public", "tailnet"}
DNS_RECORD_TYPES = {"A", "AAAA", "CNAME"}
EDGE_KINDS = {"static", "proxy"}
MONITOR_TYPES = {"http", "port"}


def load_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text())


def require_mapping(value: Any, path: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be a mapping")
    return value


def require_list(value: Any, path: str) -> list:
    if not isinstance(value, list):
        raise ValueError(f"{path} must be a list")
    return value


def require_str(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path} must be a non-empty string")
    return value


def require_bool(value: Any, path: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{path} must be a boolean")
    return value


def require_int(value: Any, path: str, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{path} must be an integer")
    if minimum is not None and value < minimum:
        raise ValueError(f"{path} must be >= {minimum}")
    return value


def require_semver(value: Any, path: str) -> str:
    value = require_str(value, path)
    if not SEMVER_PATTERN.match(value):
        raise ValueError(f"{path} must use semantic version format")
    return value


def require_date(value: Any, path: str) -> str:
    if isinstance(value, dt.date):
        return value.isoformat()
    value = require_str(value, path)
    if not DATE_PATTERN.match(value):
        raise ValueError(f"{path} must use YYYY-MM-DD format")
    return value


def require_hostname(value: Any, path: str) -> str:
    value = require_str(value, path)
    if not HOSTNAME_PATTERN.match(value):
        raise ValueError(f"{path} must be a lowercase hostname or label")
    return value


def require_identifier(value: Any, path: str) -> str:
    value = require_str(value, path)
    if not IDENTIFIER_PATTERN.match(value):
        raise ValueError(f"{path} must use lowercase letters, numbers, hyphens, or underscores")
    return value


def require_ipv4(value: Any, path: str) -> str:
    value = require_str(value, path)
    try:
        ipaddress.IPv4Address(value)
    except ipaddress.AddressValueError as exc:
        raise ValueError(f"{path} must be a valid IPv4 address") from exc
    return value


def require_network(value: Any, path: str) -> str:
    value = require_str(value, path)
    try:
        ipaddress.ip_network(value, strict=False)
    except ValueError as exc:
        raise ValueError(f"{path} must be a valid network or CIDR") from exc
    return value


def require_string_list(value: Any, path: str) -> list[str]:
    items = require_list(value, path)
    result = []
    for index, item in enumerate(items):
        result.append(require_str(item, f"{path}[{index}]"))
    return result


def require_int_list(value: Any, path: str, minimum: int = 1) -> list[int]:
    items = require_list(value, path)
    result = []
    for index, item in enumerate(items):
        result.append(require_int(item, f"{path}[{index}]", minimum))
    return result


def require_enum(value: Any, path: str, allowed: set[str]) -> str:
    value = require_str(value, path)
    if value not in allowed:
        raise ValueError(f"{path} must be one of {sorted(allowed)}")
    return value


def guest_plan_key(role: str) -> str:
    return f"{role.replace('-', '_')}_vm"


def validate_proxmox_guest(guest: Any, path: str) -> tuple[int, str, str]:
    guest = require_mapping(guest, path)
    vmid = require_int(guest.get("vmid"), f"{path}.vmid", 1)
    name = require_hostname(guest.get("name"), f"{path}.name")
    require_identifier(guest.get("role"), f"{path}.role")
    ipv4 = require_ipv4(guest.get("ipv4"), f"{path}.ipv4")
    require_int(guest.get("cidr"), f"{path}.cidr", 1)
    require_ipv4(guest.get("gateway4"), f"{path}.gateway4")
    require_int(guest.get("cores"), f"{path}.cores", 1)
    require_int(guest.get("memory_mb"), f"{path}.memory_mb", 1)
    require_int(guest.get("disk_gb"), f"{path}.disk_gb", 1)
    require_string_list(guest.get("tags"), f"{path}.tags")
    require_string_list(guest.get("packages"), f"{path}.packages")

    macaddr = guest.get("macaddr")
    if macaddr is not None:
        macaddr = require_str(macaddr, f"{path}.macaddr")
        if not MAC_PATTERN.match(macaddr):
            raise ValueError(f"{path}.macaddr must use uppercase colon-separated MAC format")

    extra_disks = guest.get("extra_disks", [])
    for index, disk in enumerate(require_list(extra_disks, f"{path}.extra_disks")):
        disk = require_mapping(disk, f"{path}.extra_disks[{index}]")
        require_str(disk.get("interface"), f"{path}.extra_disks[{index}].interface")
        require_str(disk.get("storage"), f"{path}.extra_disks[{index}].storage")
        require_int(disk.get("size_gb"), f"{path}.extra_disks[{index}].size_gb", 1)

    return vmid, name, ipv4


def validate_service_topology_entry(
    service_id: str,
    service: Any,
    guest_names: set[str],
    host_id: str,
) -> tuple[str, str | None]:
    service = require_mapping(service, f"lv3_service_topology.{service_id}")
    require_identifier(service_id, f"lv3_service_topology key '{service_id}'")
    service_name = require_identifier(
        service.get("service_name"), f"lv3_service_topology.{service_id}.service_name"
    )
    owning_vm = require_identifier(
        service.get("owning_vm"), f"lv3_service_topology.{service_id}.owning_vm"
    )
    if owning_vm not in guest_names and owning_vm != host_id:
        raise ValueError(
            f"lv3_service_topology.{service_id}.owning_vm must reference a known guest or host id"
        )

    require_str(service.get("private_ip"), f"lv3_service_topology.{service_id}.private_ip")
    require_enum(
        service.get("exposure_model"),
        f"lv3_service_topology.{service_id}.exposure_model",
        SERVICE_EXPOSURE_MODELS,
    )

    public_hostname = service.get("public_hostname")
    if public_hostname is not None:
        public_hostname = require_hostname(
            public_hostname, f"lv3_service_topology.{service_id}.public_hostname"
        )

    observability = require_mapping(
        service.get("observability"), f"lv3_service_topology.{service_id}.observability"
    )
    require_bool(
        observability.get("guest_dashboard"),
        f"lv3_service_topology.{service_id}.observability.guest_dashboard",
    )
    require_bool(
        observability.get("service_telemetry"),
        f"lv3_service_topology.{service_id}.observability.service_telemetry",
    )

    dns = service.get("dns")
    if dns is not None:
        dns = require_mapping(dns, f"lv3_service_topology.{service_id}.dns")
        managed = require_bool(dns.get("managed"), f"lv3_service_topology.{service_id}.dns.managed")
        if managed:
            require_enum(
                dns.get("visibility"),
                f"lv3_service_topology.{service_id}.dns.visibility",
                DNS_VISIBILITIES,
            )
            name = require_hostname(dns.get("name"), f"lv3_service_topology.{service_id}.dns.name")
            if not DNS_LABEL_PATTERN.match(name):
                raise ValueError(f"lv3_service_topology.{service_id}.dns.name must be a single DNS label")
            require_enum(
                dns.get("type"),
                f"lv3_service_topology.{service_id}.dns.type",
                DNS_RECORD_TYPES,
            )
            require_str(dns.get("target"), f"lv3_service_topology.{service_id}.dns.target")
            require_int(dns.get("ttl"), f"lv3_service_topology.{service_id}.dns.ttl", 1)

    edge = service.get("edge")
    if edge is not None:
        edge = require_mapping(edge, f"lv3_service_topology.{service_id}.edge")
        enabled = require_bool(edge.get("enabled"), f"lv3_service_topology.{service_id}.edge.enabled")
        if enabled:
            if public_hostname is None:
                raise ValueError(f"lv3_service_topology.{service_id} enables edge without public_hostname")
            require_bool(edge.get("tls"), f"lv3_service_topology.{service_id}.edge.tls")
            kind = require_enum(
                edge.get("kind"), f"lv3_service_topology.{service_id}.edge.kind", EDGE_KINDS
            )
            if kind == "static":
                require_hostname(edge.get("slug"), f"lv3_service_topology.{service_id}.edge.slug")
                require_str(edge.get("title"), f"lv3_service_topology.{service_id}.edge.title")
                require_str(
                    edge.get("description"),
                    f"lv3_service_topology.{service_id}.edge.description",
                )
                require_str(edge.get("meta"), f"lv3_service_topology.{service_id}.edge.meta")
                if "action_url" in edge:
                    require_str(edge.get("action_url"), f"lv3_service_topology.{service_id}.edge.action_url")
                if "action_label" in edge:
                    require_str(
                        edge.get("action_label"),
                        f"lv3_service_topology.{service_id}.edge.action_label",
                    )
            if kind == "proxy":
                require_str(edge.get("upstream"), f"lv3_service_topology.{service_id}.edge.upstream")

    return service_name, public_hostname


def validate_host_vars() -> dict[str, Any]:
    host_vars = require_mapping(load_yaml(HOST_VARS_PATH), str(HOST_VARS_PATH))
    host_id = require_identifier(HOST_VARS_PATH.stem, "host_vars host id")
    require_ipv4(host_vars.get("management_ipv4"), "host_vars.management_ipv4")
    require_ipv4(host_vars.get("management_tailscale_ipv4"), "host_vars.management_tailscale_ipv4")
    require_int_list(
        host_vars.get("proxmox_public_ingress_tcp_ports"),
        "host_vars.proxmox_public_ingress_tcp_ports",
    )

    proxmox_guests = require_list(host_vars.get("proxmox_guests"), "host_vars.proxmox_guests")
    guest_vmids: set[int] = set()
    guest_names: set[str] = set()
    guest_ips: set[str] = set()
    guest_plan_keys: set[str] = set()
    guest_vmids_by_key: dict[str, int] = {}
    guest_ips_by_key: dict[str, str] = {}
    backup_guest_key: str | None = None
    for index, guest in enumerate(proxmox_guests):
        vmid, name, ipv4 = validate_proxmox_guest(guest, f"host_vars.proxmox_guests[{index}]")
        role = guest_plan_key(require_identifier(guest.get("role"), f"host_vars.proxmox_guests[{index}].role"))
        if vmid in guest_vmids:
            raise ValueError(f"duplicate proxmox guest vmid: {vmid}")
        if name in guest_names:
            raise ValueError(f"duplicate proxmox guest name: {name}")
        if ipv4 in guest_ips:
            raise ValueError(f"duplicate proxmox guest ipv4: {ipv4}")
        if role in guest_plan_keys:
            raise ValueError(f"duplicate proxmox guest role key: {role}")
        guest_vmids.add(vmid)
        guest_names.add(name)
        guest_ips.add(ipv4)
        guest_plan_keys.add(role)
        guest_vmids_by_key[role] = vmid
        guest_ips_by_key[role] = ipv4
        if role == "backup_vm":
            backup_guest_key = role

    if backup_guest_key is None:
        raise ValueError("host_vars.proxmox_guests must include a backup guest with role key backup_vm")

    if require_int(host_vars.get("backup_vm_vmid"), "host_vars.backup_vm_vmid", 1) != guest_vmids_by_key["backup_vm"]:
        raise ValueError("host_vars.backup_vm_vmid must match the backup guest vmid")
    backup_vm_name = require_hostname(host_vars.get("backup_vm_name"), "host_vars.backup_vm_name")
    if backup_vm_name not in guest_names:
        raise ValueError("host_vars.backup_vm_name must match a managed guest name")
    if require_ipv4(host_vars.get("backup_vm_ipv4"), "host_vars.backup_vm_ipv4") != guest_ips_by_key["backup_vm"]:
        raise ValueError("host_vars.backup_vm_ipv4 must match the backup guest IPv4")

    proxies = require_list(host_vars.get("proxmox_tailscale_tcp_proxies"), "host_vars.proxmox_tailscale_tcp_proxies")
    for index, proxy in enumerate(proxies):
        proxy = require_mapping(proxy, f"host_vars.proxmox_tailscale_tcp_proxies[{index}]")
        require_hostname(proxy.get("name"), f"host_vars.proxmox_tailscale_tcp_proxies[{index}].name")
        require_str(proxy.get("listen_address"), f"host_vars.proxmox_tailscale_tcp_proxies[{index}].listen_address")
        require_int(proxy.get("listen_port"), f"host_vars.proxmox_tailscale_tcp_proxies[{index}].listen_port", 1)
        require_ipv4(proxy.get("upstream_host"), f"host_vars.proxmox_tailscale_tcp_proxies[{index}].upstream_host")
        require_int(proxy.get("upstream_port"), f"host_vars.proxmox_tailscale_tcp_proxies[{index}].upstream_port", 1)

    topology = require_mapping(host_vars.get("lv3_service_topology"), "host_vars.lv3_service_topology")
    if not topology:
        raise ValueError("host_vars.lv3_service_topology must not be empty")

    service_names: set[str] = set()
    public_hostnames: set[str] = set()
    for service_id, service in topology.items():
        service_name, public_hostname = validate_service_topology_entry(
            service_id, service, guest_names, host_id
        )
        if service_name in service_names:
            raise ValueError(f"duplicate service_name in service topology: {service_name}")
        service_names.add(service_name)
        if public_hostname is not None:
            if public_hostname in public_hostnames:
                raise ValueError(f"duplicate public_hostname in service topology: {public_hostname}")
            public_hostnames.add(public_hostname)

    return {
        "host_id": host_id,
        "guest_names": guest_names,
        "guest_plan_keys": guest_plan_keys,
        "guest_vmids_by_key": guest_vmids_by_key,
        "guest_ips_by_key": guest_ips_by_key,
    }


def validate_monitor(monitor: Any, path: str) -> str:
    monitor = require_mapping(monitor, path)
    name = require_str(monitor.get("name"), f"{path}.name")
    monitor_type = require_enum(monitor.get("type"), f"{path}.type", MONITOR_TYPES)
    require_str(monitor.get("description"), f"{path}.description")
    require_int(monitor.get("interval"), f"{path}.interval", 1)
    require_int(monitor.get("retryInterval"), f"{path}.retryInterval", 1)
    require_int(monitor.get("maxretries"), f"{path}.maxretries", 0)
    accepted = require_string_list(monitor.get("accepted_statuscodes"), f"{path}.accepted_statuscodes")
    if not accepted:
        raise ValueError(f"{path}.accepted_statuscodes must not be empty")

    if monitor_type == "http":
        url = require_str(monitor.get("url"), f"{path}.url")
        if not (url.startswith("http://") or url.startswith("https://")):
            raise ValueError(f"{path}.url must start with http:// or https://")
        require_int(monitor.get("maxredirects"), f"{path}.maxredirects", 0)

    if monitor_type == "port":
        require_str(monitor.get("hostname"), f"{path}.hostname")
        require_int(monitor.get("port"), f"{path}.port", 1)

    return name


def validate_uptime_monitors() -> None:
    monitors = require_list(json.loads(UPTIME_MONITORS_PATH.read_text()), str(UPTIME_MONITORS_PATH))
    if not monitors:
        raise ValueError("config/uptime-kuma/monitors.json must not be empty")
    names: set[str] = set()
    for index, monitor in enumerate(monitors):
        name = validate_monitor(monitor, f"config/uptime-kuma/monitors.json[{index}]")
        if name in names:
            raise ValueError(f"duplicate monitor name in config/uptime-kuma/monitors.json: {name}")
        names.add(name)


def validate_versions_stack(host_vars_context: dict[str, Any]) -> None:
    stack = require_mapping(load_yaml(STACK_PATH), str(STACK_PATH))
    repo_version = require_semver(stack.get("repo_version"), "versions/stack.yaml.repo_version")
    platform_version = require_semver(
        stack.get("platform_version"), "versions/stack.yaml.platform_version"
    )
    require_semver(stack.get("schema_version"), "versions/stack.yaml.schema_version")

    receipt_ids = {path.stem for path in iter_receipt_paths()}
    evidence = require_mapping(stack.get("live_apply_evidence"), "versions/stack.yaml.live_apply_evidence")
    receipt_dir = require_str(evidence.get("receipt_dir"), "versions/stack.yaml.live_apply_evidence.receipt_dir")
    if receipt_dir != "receipts/live-applies":
        raise ValueError("versions/stack.yaml.live_apply_evidence.receipt_dir must be receipts/live-applies")
    if (REPO_ROOT / receipt_dir) != RECEIPTS_DIR:
        raise ValueError("versions/stack.yaml.live_apply_evidence.receipt_dir must point at the receipt directory")
    latest_receipts = require_mapping(
        evidence.get("latest_receipts"), "versions/stack.yaml.live_apply_evidence.latest_receipts"
    )
    for key, value in latest_receipts.items():
        require_identifier(key, f"versions/stack.yaml.live_apply_evidence.latest_receipts.{key}")
        value = require_str(value, f"versions/stack.yaml.live_apply_evidence.latest_receipts.{key}")
        if value not in receipt_ids:
            raise ValueError(f"versions/stack.yaml.latest_receipts references unknown receipt '{value}'")

    desired_state = require_mapping(stack.get("desired_state"), "versions/stack.yaml.desired_state")
    if (
        require_identifier(desired_state.get("host_id"), "versions/stack.yaml.desired_state.host_id")
        != host_vars_context["host_id"]
    ):
        raise ValueError("versions/stack.yaml.desired_state.host_id must match the canonical host vars id")
    require_identifier(desired_state.get("provider"), "versions/stack.yaml.desired_state.provider")
    require_ipv4(desired_state.get("management_ipv4"), "versions/stack.yaml.desired_state.management_ipv4")

    base_os = require_mapping(desired_state.get("base_os"), "versions/stack.yaml.desired_state.base_os")
    require_hostname(base_os.get("family"), "versions/stack.yaml.desired_state.base_os.family")
    require_int(base_os.get("major"), "versions/stack.yaml.desired_state.base_os.major", 1)
    require_hostname(base_os.get("codename"), "versions/stack.yaml.desired_state.base_os.codename")

    proxmox = require_mapping(desired_state.get("proxmox"), "versions/stack.yaml.desired_state.proxmox")
    require_int(proxmox.get("major"), "versions/stack.yaml.desired_state.proxmox.major", 1)
    require_hostname(proxmox.get("channel"), "versions/stack.yaml.desired_state.proxmox.channel")
    require_bool(proxmox.get("installed"), "versions/stack.yaml.desired_state.proxmox.installed")

    network = require_mapping(desired_state.get("network"), "versions/stack.yaml.desired_state.network")
    require_hostname(network.get("wan_bridge"), "versions/stack.yaml.desired_state.network.wan_bridge")
    require_hostname(network.get("internal_bridge"), "versions/stack.yaml.desired_state.network.internal_bridge")
    require_network(
        network.get("internal_ipv4_gateway"),
        "versions/stack.yaml.desired_state.network.internal_ipv4_gateway",
    )
    require_network(network.get("internal_subnet"), "versions/stack.yaml.desired_state.network.internal_subnet")
    require_bool(network.get("outbound_nat"), "versions/stack.yaml.desired_state.network.outbound_nat")

    guest_network_plan = require_mapping(
        desired_state.get("guest_network_plan"), "versions/stack.yaml.desired_state.guest_network_plan"
    )
    guest_vmids = require_mapping(
        require_mapping(
            desired_state.get("guest_provisioning"), "versions/stack.yaml.desired_state.guest_provisioning"
        ).get("guest_vmids"),
        "versions/stack.yaml.desired_state.guest_provisioning.guest_vmids",
    )
    if set(guest_network_plan.keys()) != host_vars_context["guest_plan_keys"]:
        raise ValueError("versions/stack.yaml.desired_state.guest_network_plan keys must match the managed guest fleet")
    if set(guest_vmids.keys()) != host_vars_context["guest_plan_keys"]:
        raise ValueError("versions/stack.yaml.desired_state.guest_provisioning.guest_vmids keys must match the managed guest fleet")
    for key in host_vars_context["guest_plan_keys"]:
        if (
            require_ipv4(guest_network_plan.get(key), f"versions/stack.yaml.desired_state.guest_network_plan.{key}")
            != host_vars_context["guest_ips_by_key"][key]
        ):
            raise ValueError(
                f"versions/stack.yaml.desired_state.guest_network_plan.{key} must match inventory/host_vars/proxmox_florin.yml"
            )
        if (
            require_int(
                guest_vmids.get(key),
                f"versions/stack.yaml.desired_state.guest_provisioning.guest_vmids.{key}",
                1,
            )
            != host_vars_context["guest_vmids_by_key"][key]
        ):
            raise ValueError(
                f"versions/stack.yaml.desired_state.guest_provisioning.guest_vmids.{key} must match inventory/host_vars/proxmox_florin.yml"
            )

    guest_provisioning = require_mapping(
        desired_state.get("guest_provisioning"), "versions/stack.yaml.desired_state.guest_provisioning"
    )
    require_int(
        guest_provisioning.get("template_vmid"),
        "versions/stack.yaml.desired_state.guest_provisioning.template_vmid",
        1,
    )
    require_str(
        guest_provisioning.get("template_name"),
        "versions/stack.yaml.desired_state.guest_provisioning.template_name",
    )

    traffic_model = require_mapping(
        desired_state.get("traffic_model"), "versions/stack.yaml.desired_state.traffic_model"
    )
    require_ipv4(
        traffic_model.get("guest_default_gateway"),
        "versions/stack.yaml.desired_state.traffic_model.guest_default_gateway",
    )
    require_bool(
        traffic_model.get("guest_outbound_via_host_nat"),
        "versions/stack.yaml.desired_state.traffic_model.guest_outbound_via_host_nat",
    )
    require_ipv4(
        traffic_model.get("public_edge_vm"), "versions/stack.yaml.desired_state.traffic_model.public_edge_vm"
    )
    require_bool(
        traffic_model.get("public_edge_forwarding_enabled"),
        "versions/stack.yaml.desired_state.traffic_model.public_edge_forwarding_enabled",
    )
    require_int_list(
        traffic_model.get("public_ingress_ports"),
        "versions/stack.yaml.desired_state.traffic_model.public_ingress_ports",
    )

    operator_access = require_mapping(
        desired_state.get("operator_access"), "versions/stack.yaml.desired_state.operator_access"
    )
    require_str(
        operator_access.get("bootstrap_method"),
        "versions/stack.yaml.desired_state.operator_access.bootstrap_method",
    )
    require_str(
        operator_access.get("steady_state_host_method"),
        "versions/stack.yaml.desired_state.operator_access.steady_state_host_method",
    )
    require_ipv4(
        operator_access.get("steady_state_host_target"),
        "versions/stack.yaml.desired_state.operator_access.steady_state_host_target",
    )
    require_str(
        operator_access.get("private_guest_access_method"),
        "versions/stack.yaml.desired_state.operator_access.private_guest_access_method",
    )
    require_ipv4(
        operator_access.get("private_build_vm"),
        "versions/stack.yaml.desired_state.operator_access.private_build_vm",
    )

    automation_access = require_mapping(
        desired_state.get("automation_access"), "versions/stack.yaml.desired_state.automation_access"
    )
    require_str(
        automation_access.get("proxmox_api_user"),
        "versions/stack.yaml.desired_state.automation_access.proxmox_api_user",
    )
    require_str(
        automation_access.get("proxmox_api_token_id"),
        "versions/stack.yaml.desired_state.automation_access.proxmox_api_token_id",
    )
    require_str(
        automation_access.get("proxmox_api_role"),
        "versions/stack.yaml.desired_state.automation_access.proxmox_api_role",
    )
    require_bool(
        automation_access.get("proxmox_api_privilege_separation"),
        "versions/stack.yaml.desired_state.automation_access.proxmox_api_privilege_separation",
    )
    require_str(
        automation_access.get("proxmox_api_secret_storage"),
        "versions/stack.yaml.desired_state.automation_access.proxmox_api_secret_storage",
    )

    security = require_mapping(desired_state.get("security"), "versions/stack.yaml.desired_state.security")
    for index, source in enumerate(require_string_list(security.get("management_sources"), "versions/stack.yaml.desired_state.security.management_sources")):
        require_network(source, f"versions/stack.yaml.desired_state.security.management_sources[{index}]")
    require_str(
        security.get("proxmox_tfa_user"), "versions/stack.yaml.desired_state.security.proxmox_tfa_user"
    )
    require_hostname(
        security.get("proxmox_tls_hostname"),
        "versions/stack.yaml.desired_state.security.proxmox_tls_hostname",
    )
    require_str(
        security.get("notifications_email"),
        "versions/stack.yaml.desired_state.security.notifications_email",
    )

    dns = require_mapping(desired_state.get("dns"), "versions/stack.yaml.desired_state.dns")
    require_hostname(dns.get("zone"), "versions/stack.yaml.desired_state.dns.zone")
    require_ipv4(dns.get("public_ipv4_target"), "versions/stack.yaml.desired_state.dns.public_ipv4_target")
    for index, hostname in enumerate(require_string_list(dns.get("initial_subdomains"), "versions/stack.yaml.desired_state.dns.initial_subdomains")):
        require_hostname(hostname, f"versions/stack.yaml.desired_state.dns.initial_subdomains[{index}]")
    require_bool(
        dns.get("publish_aaaa_initially"),
        "versions/stack.yaml.desired_state.dns.publish_aaaa_initially",
    )

    public_publication = require_mapping(
        desired_state.get("public_publication"), "versions/stack.yaml.desired_state.public_publication"
    )
    require_ipv4(
        public_publication.get("edge_vm"),
        "versions/stack.yaml.desired_state.public_publication.edge_vm",
    )
    require_str(
        public_publication.get("tls_termination"),
        "versions/stack.yaml.desired_state.public_publication.tls_termination",
    )
    for index, hostname in enumerate(require_string_list(public_publication.get("published_hostnames"), "versions/stack.yaml.desired_state.public_publication.published_hostnames")):
        require_hostname(hostname, f"versions/stack.yaml.desired_state.public_publication.published_hostnames[{index}]")

    observed_state = require_mapping(stack.get("observed_state"), "versions/stack.yaml.observed_state")
    require_date(observed_state.get("checked_at"), "versions/stack.yaml.observed_state.checked_at")

    access = require_mapping(observed_state.get("access"), "versions/stack.yaml.observed_state.access")
    for field in (
        "ssh_bootstrap_key_working",
        "host_ops_user_working",
        "host_ops_user_working_via_tailscale",
        "guest_ops_user_working_via_proxmox_jump",
        "guest_root_ssh_disabled",
        "guest_ssh_password_authentication",
        "proxmox_ops_pam_tfa_enabled",
        "proxmox_api_token_verified",
    ):
        require_bool(access.get(field), f"versions/stack.yaml.observed_state.access.{field}")

    os_state = require_mapping(observed_state.get("os"), "versions/stack.yaml.observed_state.os")
    require_str(os_state.get("banner"), "versions/stack.yaml.observed_state.os.banner")
    require_str(os_state.get("kernel"), "versions/stack.yaml.observed_state.os.kernel")
    require_str(os_state.get("distribution"), "versions/stack.yaml.observed_state.os.distribution")
    require_int(os_state.get("major"), "versions/stack.yaml.observed_state.os.major", 1)
    require_str(os_state.get("codename"), "versions/stack.yaml.observed_state.os.codename")

    proxmox_state = require_mapping(observed_state.get("proxmox"), "versions/stack.yaml.observed_state.proxmox")
    require_bool(proxmox_state.get("installed"), "versions/stack.yaml.observed_state.proxmox.installed")
    require_str(proxmox_state.get("version"), "versions/stack.yaml.observed_state.proxmox.version")
    require_str(proxmox_state.get("ve_version"), "versions/stack.yaml.observed_state.proxmox.ve_version")
    require_int(proxmox_state.get("api_ui_port"), "versions/stack.yaml.observed_state.proxmox.api_ui_port", 1)
    require_hostname(
        proxmox_state.get("tls_hostname"), "versions/stack.yaml.observed_state.proxmox.tls_hostname"
    )

    network_state = require_mapping(observed_state.get("network"), "versions/stack.yaml.observed_state.network")
    require_hostname(network_state.get("wan_bridge"), "versions/stack.yaml.observed_state.network.wan_bridge")
    require_bool(network_state.get("wan_bridge_active"), "versions/stack.yaml.observed_state.network.wan_bridge_active")
    require_hostname(network_state.get("internal_bridge"), "versions/stack.yaml.observed_state.network.internal_bridge")
    require_bool(
        network_state.get("internal_bridge_active"),
        "versions/stack.yaml.observed_state.network.internal_bridge_active",
    )
    require_network(
        network_state.get("internal_ipv4_gateway"),
        "versions/stack.yaml.observed_state.network.internal_ipv4_gateway",
    )
    require_bool(network_state.get("ipv4_forwarding"), "versions/stack.yaml.observed_state.network.ipv4_forwarding")
    require_bool(network_state.get("outbound_nat"), "versions/stack.yaml.observed_state.network.outbound_nat")
    require_ipv4(network_state.get("public_edge_ipv4"), "versions/stack.yaml.observed_state.network.public_edge_ipv4")
    require_bool(
        network_state.get("public_ingress_forwarding_enabled"),
        "versions/stack.yaml.observed_state.network.public_ingress_forwarding_enabled",
    )
    require_int_list(
        network_state.get("public_ingress_forwarded_ports"),
        "versions/stack.yaml.observed_state.network.public_ingress_forwarded_ports",
    )
    for index, source in enumerate(require_string_list(network_state.get("management_sources"), "versions/stack.yaml.observed_state.network.management_sources")):
        require_network(source, f"versions/stack.yaml.observed_state.network.management_sources[{index}]")
    require_bool(
        network_state.get("tailscale_host_admin_path_working"),
        "versions/stack.yaml.observed_state.network.tailscale_host_admin_path_working",
    )
    require_ipv4(
        network_state.get("tailscale_tail_ipv4"), "versions/stack.yaml.observed_state.network.tailscale_tail_ipv4"
    )

    guests_state = require_mapping(observed_state.get("guests"), "versions/stack.yaml.observed_state.guests")
    template = require_mapping(guests_state.get("template"), "versions/stack.yaml.observed_state.guests.template")
    require_int(template.get("vmid"), "versions/stack.yaml.observed_state.guests.template.vmid", 1)
    require_str(template.get("name"), "versions/stack.yaml.observed_state.guests.template.name")
    require_bool(template.get("exists"), "versions/stack.yaml.observed_state.guests.template.exists")

    instances = require_list(guests_state.get("instances"), "versions/stack.yaml.observed_state.guests.instances")
    instance_names: set[str] = set()
    for index, guest in enumerate(instances):
        guest = require_mapping(guest, f"versions/stack.yaml.observed_state.guests.instances[{index}]")
        require_int(guest.get("vmid"), f"versions/stack.yaml.observed_state.guests.instances[{index}].vmid", 1)
        name = require_hostname(
            guest.get("name"), f"versions/stack.yaml.observed_state.guests.instances[{index}].name"
        )
        require_ipv4(
            guest.get("ipv4"), f"versions/stack.yaml.observed_state.guests.instances[{index}].ipv4"
        )
        require_bool(
            guest.get("running"), f"versions/stack.yaml.observed_state.guests.instances[{index}].running"
        )
        instance_names.add(name)
    if instance_names != host_vars_context["guest_names"]:
        raise ValueError("versions/stack.yaml.observed_state.guests.instances must contain the managed guest fleet")

    monitoring = require_mapping(observed_state.get("monitoring"), "versions/stack.yaml.observed_state.monitoring")
    require_ipv4(monitoring.get("vm"), "versions/stack.yaml.observed_state.monitoring.vm")
    require_bool(monitoring.get("grafana_running"), "versions/stack.yaml.observed_state.monitoring.grafana_running")
    require_str(monitoring.get("grafana_version"), "versions/stack.yaml.observed_state.monitoring.grafana_version")
    dashboards = require_list(
        monitoring.get("grafana_dashboards"), "versions/stack.yaml.observed_state.monitoring.grafana_dashboards"
    )
    for index, dashboard in enumerate(dashboards):
        dashboard = require_mapping(
            dashboard, f"versions/stack.yaml.observed_state.monitoring.grafana_dashboards[{index}]"
        )
        require_str(
            dashboard.get("uid"),
            f"versions/stack.yaml.observed_state.monitoring.grafana_dashboards[{index}].uid",
        )
        require_str(
            dashboard.get("title"),
            f"versions/stack.yaml.observed_state.monitoring.grafana_dashboards[{index}].title",
        )
        require_int(
            dashboard.get("panels"),
            f"versions/stack.yaml.observed_state.monitoring.grafana_dashboards[{index}].panels",
            1,
        )

    docker_runtime = require_mapping(
        observed_state.get("docker_runtime"), "versions/stack.yaml.observed_state.docker_runtime"
    )
    require_ipv4(docker_runtime.get("vm"), "versions/stack.yaml.observed_state.docker_runtime.vm")
    require_bool(
        docker_runtime.get("docker_engine_running"),
        "versions/stack.yaml.observed_state.docker_runtime.docker_engine_running",
    )
    require_str(
        docker_runtime.get("docker_engine_version"),
        "versions/stack.yaml.observed_state.docker_runtime.docker_engine_version",
    )
    require_str(
        docker_runtime.get("docker_compose_plugin_version"),
        "versions/stack.yaml.observed_state.docker_runtime.docker_compose_plugin_version",
    )

    uptime_kuma = require_mapping(
        observed_state.get("uptime_kuma"), "versions/stack.yaml.observed_state.uptime_kuma"
    )
    require_ipv4(uptime_kuma.get("vm"), "versions/stack.yaml.observed_state.uptime_kuma.vm")
    require_str(uptime_kuma.get("public_url"), "versions/stack.yaml.observed_state.uptime_kuma.public_url")
    require_bool(
        uptime_kuma.get("container_running"),
        "versions/stack.yaml.observed_state.uptime_kuma.container_running",
    )
    require_bool(
        uptime_kuma.get("local_auth_bootstrapped"),
        "versions/stack.yaml.observed_state.uptime_kuma.local_auth_bootstrapped",
    )
    require_int(
        uptime_kuma.get("seeded_monitors"),
        "versions/stack.yaml.observed_state.uptime_kuma.seeded_monitors",
        1,
    )

    publication_state = require_mapping(
        observed_state.get("public_publication"),
        "versions/stack.yaml.observed_state.public_publication",
    )
    require_bool(
        publication_state.get("edge_configured"),
        "versions/stack.yaml.observed_state.public_publication.edge_configured",
    )
    for index, hostname in enumerate(require_string_list(publication_state.get("published_hostnames"), "versions/stack.yaml.observed_state.public_publication.published_hostnames")):
        require_hostname(hostname, f"versions/stack.yaml.observed_state.public_publication.published_hostnames[{index}]")

    postgres = require_mapping(observed_state.get("postgres"), "versions/stack.yaml.observed_state.postgres")
    require_ipv4(postgres.get("vm"), "versions/stack.yaml.observed_state.postgres.vm")
    require_bool(postgres.get("service_running"), "versions/stack.yaml.observed_state.postgres.service_running")
    require_bool(
        postgres.get("guest_firewall_enabled"),
        "versions/stack.yaml.observed_state.postgres.guest_firewall_enabled",
    )
    require_str(
        postgres.get("tailscale_proxy_host"),
        "versions/stack.yaml.observed_state.postgres.tailscale_proxy_host",
    )
    require_hostname(postgres.get("dns_name"), "versions/stack.yaml.observed_state.postgres.dns_name")

    backups = require_mapping(observed_state.get("backups"), "versions/stack.yaml.observed_state.backups")
    require_bool(backups.get("configured"), "versions/stack.yaml.observed_state.backups.configured")
    if backups["configured"]:
        require_str(backups.get("mode"), "versions/stack.yaml.observed_state.backups.mode")
        require_str(backups.get("storage_id"), "versions/stack.yaml.observed_state.backups.storage_id")
        require_bool(
            backups.get("legacy_external_cifs_path_blocked"),
            "versions/stack.yaml.observed_state.backups.legacy_external_cifs_path_blocked",
        )
    else:
        require_str(backups.get("blocker"), "versions/stack.yaml.observed_state.backups.blocker")

    release_tracks = require_mapping(stack.get("release_tracks"), "versions/stack.yaml.release_tracks")
    delivery_model = require_mapping(
        release_tracks.get("delivery_model"), "versions/stack.yaml.release_tracks.delivery_model"
    )
    require_str(delivery_model.get("mode"), "versions/stack.yaml.release_tracks.delivery_model.mode")
    require_str(
        delivery_model.get("branch_prefix"),
        "versions/stack.yaml.release_tracks.delivery_model.branch_prefix",
    )
    repo_versioning = require_mapping(
        release_tracks.get("repo_versioning"), "versions/stack.yaml.release_tracks.repo_versioning"
    )
    if require_semver(
        repo_versioning.get("current"), "versions/stack.yaml.release_tracks.repo_versioning.current"
    ) != repo_version:
        raise ValueError("versions/stack.yaml.release_tracks.repo_versioning.current must match repo_version")
    platform_versioning = require_mapping(
        release_tracks.get("platform_versioning"),
        "versions/stack.yaml.release_tracks.platform_versioning",
    )
    if require_semver(
        platform_versioning.get("current"),
        "versions/stack.yaml.release_tracks.platform_versioning.current",
    ) != platform_version:
        raise ValueError(
            "versions/stack.yaml.release_tracks.platform_versioning.current must match platform_version"
        )


def validate_repository_data_models() -> int:
    secret_manifest = load_secret_manifest()
    validate_secret_manifest(secret_manifest)
    workflow_catalog = load_workflow_catalog()
    validate_workflow_catalog(workflow_catalog, secret_manifest)
    validate_receipts()
    validate_uptime_monitors()
    host_vars_context = validate_host_vars()
    validate_versions_stack(host_vars_context)
    print("Repository data models OK")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate the repository's canonical machine-readable data models."
    )
    parser.add_argument("--validate", action="store_true", help="Validate the repository data models.")
    args = parser.parse_args()

    if not args.validate:
        parser.print_help()
        return 0

    try:
        return validate_repository_data_models()
    except (OSError, json.JSONDecodeError, ValueError, yaml.YAMLError) as exc:
        print(f"Repository data model error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
