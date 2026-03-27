#!/usr/bin/env python3

import argparse
import datetime as dt
import ipaddress
import json
import re
import subprocess
import sys
from typing import Any

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if "platform" in sys.modules and not hasattr(sys.modules["platform"], "__path__"):
    del sys.modules["platform"]

from command_catalog import load_command_catalog, validate_command_catalog
from api_gateway_catalog import load_api_gateway_catalog, validate_api_gateway_catalog
from api_publication import load_api_publication_catalog, validate_api_publication_catalog
from capacity_report import load_capacity_model
from canonical_errors import ErrorRegistry
from container_image_policy import load_image_catalog, validate_image_catalog as validate_container_image_catalog
from changelog_redaction import load_redaction_policy, validate_redaction_policy
from controller_automation_toolkit import emit_cli_error, load_json, load_yaml, repo_path
from control_plane_lanes import load_lane_catalog
from data_catalog import load_data_catalog, validate_data_catalog
from dependency_graph import load_dependency_graph
from data_catalog import load_data_catalog, validate_data_catalog
from live_apply_receipts import RECEIPTS_DIR, iter_receipt_paths, validate_receipts
from platform.circuit import load_circuit_policies
from generate_platform_vars import PLATFORM_VARS_PATH, PORT_KEYS, build_platform_vars
from mutation_audit import load_mutation_audit_schema, validate_mutation_audit_schema
from operator_manager import ROSTER_PATH, validate_operator_roster
from platform.execution_lanes import load_execution_lane_catalog
from promotion_pipeline import validate_promotion_receipts
from public_surface_scan import load_public_surface_scan_policy
from validate_ephemeral_vmid import validate_ephemeral_vmid_ranges
from generate_slo_rules import outputs_match as slo_outputs_match
from slo_tracking import (
    GRAFANA_DASHBOARD_PATH,
    PROMETHEUS_ALERTS_PATH,
    PROMETHEUS_RULES_PATH,
    PROMETHEUS_TARGETS_PATH,
    SLO_CATALOG_PATH,
    load_slo_catalog,
)
from service_completeness import load_context as load_service_completeness_context
from workflow_catalog import (
    load_secret_manifest,
    load_workflow_catalog,
    validate_secret_manifest,
    validate_workflow_catalog,
)
from platform.config_merge import validate_merge_eligible_catalog


STACK_PATH = repo_path("versions", "stack.yaml")
GLOBAL_VARS_PATH = repo_path("inventory", "group_vars", "all.yml")
HOST_VARS_PATH = repo_path("inventory", "host_vars", "proxmox_florin.yml")
UPTIME_MONITORS_PATH = repo_path("config", "uptime-kuma", "monitors.json")
HEALTH_PROBE_CATALOG_PATH = repo_path("config", "health-probe-catalog.json")
CERTIFICATE_CATALOG_PATH = repo_path("config", "certificate-catalog.json")
SECRET_CATALOG_PATH = repo_path("config", "secret-catalog.json")
TOKEN_POLICY_PATH = repo_path("config", "token-policy.yaml")
TOKEN_INVENTORY_PATH = repo_path("config", "token-inventory.yaml")
IMAGE_CATALOG_PATH = repo_path("config", "image-catalog.json")
ERROR_REGISTRY_PATH = repo_path("config", "error-codes.yaml")
PLATFORM_FINDING_SCHEMA_PATH = repo_path("docs", "schema", "platform-finding.json")
MAINTENANCE_WINDOW_SCHEMA_PATH = repo_path("docs", "schema", "maintenance-window.json")
VM_TEMPLATE_MANIFEST_PATH = repo_path("config", "vm-template-manifest.json")
CAPACITY_MODEL_PATH = repo_path("config", "capacity-model.json")
CAPACITY_MODEL_SCHEMA_PATH = repo_path("docs", "schema", "capacity-model.schema.json")
VERSION_SEMANTICS_PATH = repo_path("config", "version-semantics.json")
WORKSTREAMS_PATH = repo_path("workstreams.yaml")
TRIAGE_RULES_PATH = repo_path("config", "triage-rules.yaml")
TRIAGE_AUTO_CHECK_ALLOWLIST_PATH = repo_path("config", "triage-auto-check-allowlist.yaml")
CHANGELOG_REDACTION_PATH = repo_path("config", "changelog-redaction.yaml")
AGENT_POLICIES_PATH = repo_path("config", "agent-policies.yaml")
CIRCUIT_POLICIES_PATH = repo_path("config", "circuit-policies.yaml")
MERGE_ELIGIBLE_FILES_PATH = repo_path("config", "merge-eligible-files.yaml")

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
EXTRA_DNS_RECORD_TYPES = {"A", "AAAA", "CNAME", "MX", "TXT"}
EDGE_KINDS = {"static", "proxy"}
MONITOR_TYPES = {"http", "port"}
PROBE_KINDS = {"http", "tcp", "command", "systemd"}
HTTP_METHODS = {"DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"}
IDENTITY_CLASSES = {"human_operator", "service", "agent", "break_glass"}
AGENT_POLICY_IDENTITY_CLASSES = {"operator-agent", "service-agent"}
TRUST_TIERS = {"T1", "T2", "T3", "T4"}
NETWORK_POLICY_PROTOCOLS = {"tcp", "udp", "vrrp"}
IMAGE_SOURCE_KINDS = {"upstream", "local_build"}
IMAGE_PIN_STATUSES = {"pinned", "unpinned", "local_build"}
SCAFFOLD_PLACEHOLDER_MARKER = "TODO"
IDENTITY_REQUIRED_METADATA = {
    "owner",
    "purpose",
    "scope_boundary",
    "rotation_or_expiry",
    "credential_storage",
}


def require_str_int_mapping(value: Any, path: str) -> dict[str, int]:
    value = require_mapping(value, path)
    result: dict[str, int] = {}
    for key, item in value.items():
        key = require_identifier(key, f"{path} key '{key}'")
        result[key] = require_int(item, f"{path}.{key}", 1)
    return result


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


def require_int_or_template(value: Any, path: str, minimum: int | None = None) -> int | str:
    if isinstance(value, str):
        value = require_str(value, path)
        if value.startswith("{{") and value.endswith("}}"):
            return value
        raise ValueError(f"{path} must be an integer or a Jinja template expression")
    return require_int(value, path, minimum)


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


def validate_placeholder_free(value: Any, path: str) -> None:
    if isinstance(value, str):
        if SCAFFOLD_PLACEHOLDER_MARKER in value:
            raise ValueError(
                f"{path} contains scaffold placeholder marker '{SCAFFOLD_PLACEHOLDER_MARKER}'"
            )
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            validate_placeholder_free(item, f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            validate_placeholder_free(item, f"{path}.{key}")


def validate_no_scaffold_placeholders() -> None:
    structured_paths = {
        HEALTH_PROBE_CATALOG_PATH: load_json(HEALTH_PROBE_CATALOG_PATH),
        CERTIFICATE_CATALOG_PATH: load_json(CERTIFICATE_CATALOG_PATH),
        SECRET_CATALOG_PATH: load_json(SECRET_CATALOG_PATH),
        TOKEN_POLICY_PATH: load_yaml(TOKEN_POLICY_PATH),
        TOKEN_INVENTORY_PATH: load_yaml(TOKEN_INVENTORY_PATH),
        IMAGE_CATALOG_PATH: load_json(IMAGE_CATALOG_PATH),
        repo_path("config", "service-capability-catalog.json"): load_json(
            repo_path("config", "service-capability-catalog.json")
        ),
        repo_path("config", "api-gateway-catalog.json"): load_json(
            repo_path("config", "api-gateway-catalog.json")
        ),
        repo_path("config", "subdomain-catalog.json"): load_json(
            repo_path("config", "subdomain-catalog.json")
        ),
        repo_path("config", "controller-local-secrets.json"): load_json(
            repo_path("config", "controller-local-secrets.json")
        ),
        repo_path("config", "api-gateway-catalog.json"): load_json(
            repo_path("config", "api-gateway-catalog.json")
        ),
        repo_path("config", "dependency-graph.json"): load_json(
            repo_path("config", "dependency-graph.json")
        ),
        repo_path("config", "slo-catalog.json"): load_json(repo_path("config", "slo-catalog.json")),
        repo_path("config", "data-catalog.json"): load_json(repo_path("config", "data-catalog.json")),
        repo_path("config", "service-completeness.json"): load_json(
            repo_path("config", "service-completeness.json")
        ),
        HOST_VARS_PATH: load_yaml(HOST_VARS_PATH),
    }
    for path, payload in structured_paths.items():
        validate_placeholder_free(payload, str(path))


def validate_no_tracked_env_files() -> None:
    completed = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "ls-files", "*.env"],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "git ls-files failed")
    tracked = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    if tracked:
        raise ValueError(f"tracked .env files are not allowed: {', '.join(tracked)}")


def guest_plan_key(role: str) -> str:
    return f"{role.replace('-', '_')}_vm"


def validate_proxmox_guest(guest: Any, path: str) -> tuple[int, str, str, str]:
    guest = require_mapping(guest, path)
    vmid = require_int(guest.get("vmid"), f"{path}.vmid", 1)
    name = require_hostname(guest.get("name"), f"{path}.name")
    require_identifier(guest.get("role"), f"{path}.role")
    template_key = require_identifier(guest.get("template_key"), f"{path}.template_key")
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

    return vmid, name, ipv4, template_key


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
                if "root_proxy_path" in edge:
                    root_proxy_path = require_str(
                        edge.get("root_proxy_path"),
                        f"lv3_service_topology.{service_id}.edge.root_proxy_path",
                    )
                    if not root_proxy_path.startswith("/"):
                        raise ValueError(
                            f"lv3_service_topology.{service_id}.edge.root_proxy_path must start with '/'"
                        )

    return service_name, public_hostname


def validate_public_ingress_forwards(value: Any, path: str, allowed_ports: list[int]) -> None:
    forwards = require_list(value, path)
    seen_ports: set[int] = set()
    for index, forward in enumerate(forwards):
        forward = require_mapping(forward, f"{path}[{index}]")
        listen_port = require_int(forward.get("listen_port"), f"{path}[{index}].listen_port", 1)
        require_ipv4(forward.get("target_host"), f"{path}[{index}].target_host")
        require_int(forward.get("target_port"), f"{path}[{index}].target_port", 1)
        if listen_port in seen_ports:
            raise ValueError(f"{path}[{index}].listen_port duplicates an earlier public ingress forward")
        if listen_port not in allowed_ports:
            raise ValueError(f"{path}[{index}].listen_port must be declared in proxmox_public_ingress_tcp_ports")
        seen_ports.add(listen_port)
    if set(allowed_ports) != seen_ports:
        raise ValueError(f"{path} must define exactly one forward for each public ingress port")


def validate_extra_dns_records(value: Any, path: str) -> None:
    records = require_list(value, path)
    for index, record in enumerate(records):
        record = require_mapping(record, f"{path}[{index}]")
        require_str(record.get("name"), f"{path}[{index}].name")
        require_enum(record.get("type"), f"{path}[{index}].type", EXTRA_DNS_RECORD_TYPES)
        require_str(record.get("value"), f"{path}[{index}].value")
        require_int(record.get("ttl"), f"{path}[{index}].ttl", 1)


def validate_network_policy(value: Any, path: str, guest_names: set[str]) -> None:
    policy = require_mapping(value, path)
    guest_management_sources = require_string_list(
        policy.get("guest_management_sources"),
        f"{path}.guest_management_sources",
    )
    if not guest_management_sources:
        raise ValueError(f"{path}.guest_management_sources must not be empty")
    for index, source in enumerate(guest_management_sources):
        require_network(source, f"{path}.guest_management_sources[{index}]")

    require_network(policy.get("host_source"), f"{path}.host_source")

    guest_policies = require_mapping(policy.get("guests"), f"{path}.guests")
    if set(guest_policies.keys()) != guest_names:
        raise ValueError(f"{path}.guests must define exactly one policy entry for each managed guest")

    allowed_source_tokens = {"management", "host", "public", "all_guests"}
    for guest_name in sorted(guest_names):
        guest_policy = require_mapping(guest_policies.get(guest_name), f"{path}.guests.{guest_name}")
        allowed_inbound = require_list(guest_policy.get("allowed_inbound"), f"{path}.guests.{guest_name}.allowed_inbound")
        if not allowed_inbound:
            raise ValueError(f"{path}.guests.{guest_name}.allowed_inbound must not be empty")
        for index, rule in enumerate(allowed_inbound):
            rule = require_mapping(rule, f"{path}.guests.{guest_name}.allowed_inbound[{index}]")
            source = require_str(rule.get("source"), f"{path}.guests.{guest_name}.allowed_inbound[{index}].source")
            require_enum(
                rule.get("protocol"),
                f"{path}.guests.{guest_name}.allowed_inbound[{index}].protocol",
                NETWORK_POLICY_PROTOCOLS,
            )
            ports = rule.get("ports", [])
            if rule.get("protocol") != "vrrp":
                ports = require_int_list(
                    ports,
                    f"{path}.guests.{guest_name}.allowed_inbound[{index}].ports",
                )
                if not ports:
                    raise ValueError(f"{path}.guests.{guest_name}.allowed_inbound[{index}].ports must not be empty")
            else:
                if "ports" in rule and require_list(
                    ports,
                    f"{path}.guests.{guest_name}.allowed_inbound[{index}].ports",
                ):
                    raise ValueError(
                        f"{path}.guests.{guest_name}.allowed_inbound[{index}].ports must be omitted for VRRP rules"
                    )
            require_str(
                rule.get("description"),
                f"{path}.guests.{guest_name}.allowed_inbound[{index}].description",
            )
            if source in allowed_source_tokens or source in guest_names:
                continue
            require_network(source, f"{path}.guests.{guest_name}.allowed_inbound[{index}].source")


def validate_host_vars() -> dict[str, Any]:
    host_vars = require_mapping(load_yaml(HOST_VARS_PATH), str(HOST_VARS_PATH))
    global_vars = require_mapping(load_yaml(GLOBAL_VARS_PATH), str(GLOBAL_VARS_PATH))
    host_id = require_identifier(HOST_VARS_PATH.stem, "host_vars host id")
    require_ipv4(host_vars.get("management_ipv4"), "host_vars.management_ipv4")
    require_ipv4(host_vars.get("management_tailscale_ipv4"), "host_vars.management_tailscale_ipv4")
    public_ingress_ports = require_int_list(
        host_vars.get("proxmox_public_ingress_tcp_ports"),
        "host_vars.proxmox_public_ingress_tcp_ports",
    )
    if "proxmox_public_ingress_tcp_forwards" in host_vars:
        validate_public_ingress_forwards(
            host_vars.get("proxmox_public_ingress_tcp_forwards"),
            "host_vars.proxmox_public_ingress_tcp_forwards",
            public_ingress_ports,
        )

    proxmox_vm_templates = require_mapping(global_vars.get("proxmox_vm_templates"), "inventory/group_vars/all.yml.proxmox_vm_templates")
    template_vmids: set[int] = set()
    template_names: set[str] = set()
    for template_key, template in proxmox_vm_templates.items():
        template_key = require_identifier(template_key, f"inventory/group_vars/all.yml.proxmox_vm_templates key '{template_key}'")
        template = require_mapping(template, f"inventory/group_vars/all.yml.proxmox_vm_templates.{template_key}")
        template_vmid = require_int(template.get("vmid"), f"inventory/group_vars/all.yml.proxmox_vm_templates.{template_key}.vmid", 1)
        template_name = require_hostname(template.get("name"), f"inventory/group_vars/all.yml.proxmox_vm_templates.{template_key}.name")
        source_template = template.get("source_template")
        if source_template is not None:
            require_str(source_template, f"inventory/group_vars/all.yml.proxmox_vm_templates.{template_key}.source_template")
        if template_vmid in template_vmids:
            raise ValueError(f"duplicate proxmox template vmid: {template_vmid}")
        if template_name in template_names:
            raise ValueError(f"duplicate proxmox template name: {template_name}")
        template_vmids.add(template_vmid)
        template_names.add(template_name)

    proxmox_guests = require_list(host_vars.get("proxmox_guests"), "host_vars.proxmox_guests")
    guest_vmids: set[int] = set()
    guest_names: set[str] = set()
    guest_ips: set[str] = set()
    guest_plan_keys: set[str] = set()
    guest_vmids_by_key: dict[str, int] = {}
    guest_ips_by_key: dict[str, str] = {}
    backup_guest_key: str | None = None
    for index, guest in enumerate(proxmox_guests):
        vmid, name, ipv4, template_key = validate_proxmox_guest(guest, f"host_vars.proxmox_guests[{index}]")
        role = guest_plan_key(require_identifier(guest.get("role"), f"host_vars.proxmox_guests[{index}].role"))
        if template_key not in proxmox_vm_templates:
            raise ValueError(
                f"host_vars.proxmox_guests[{index}].template_key must reference inventory/group_vars/all.yml.proxmox_vm_templates"
            )
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
        require_int_or_template(
            proxy.get("listen_port"), f"host_vars.proxmox_tailscale_tcp_proxies[{index}].listen_port", 1
        )
        require_ipv4(proxy.get("upstream_host"), f"host_vars.proxmox_tailscale_tcp_proxies[{index}].upstream_host")
        require_int_or_template(
            proxy.get("upstream_port"), f"host_vars.proxmox_tailscale_tcp_proxies[{index}].upstream_port", 1
        )

    if "mail_platform_dns_records" in host_vars:
        validate_extra_dns_records(host_vars.get("mail_platform_dns_records"), "host_vars.mail_platform_dns_records")

    platform_port_assignments = require_str_int_mapping(
        host_vars.get("platform_port_assignments"), "host_vars.platform_port_assignments"
    )
    missing_port_keys = sorted(set(PORT_KEYS) - set(platform_port_assignments.keys()))
    if missing_port_keys:
        raise ValueError(
            "host_vars.platform_port_assignments is missing required keys: "
            + ", ".join(missing_port_keys)
        )
    validate_network_policy(host_vars.get("network_policy"), "host_vars.network_policy", guest_names)

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
        "host_vars": host_vars,
        "guest_names": guest_names,
        "guest_plan_keys": guest_plan_keys,
        "guest_vmids_by_key": guest_vmids_by_key,
        "guest_ips_by_key": guest_ips_by_key,
        "proxmox_vm_templates": proxmox_vm_templates,
        "platform_port_assignments": platform_port_assignments,
        "topology": {
            service_id: {
                "service_name": service["service_name"],
                "owning_vm": service["owning_vm"],
            }
            for service_id, service in topology.items()
        },
    }


def validate_vm_template_manifest(template_catalog: dict[str, Any]) -> None:
    manifest = require_mapping(load_json(VM_TEMPLATE_MANIFEST_PATH), str(VM_TEMPLATE_MANIFEST_PATH))
    templates = require_mapping(manifest.get("templates"), "config/vm-template-manifest.json.templates")
    if set(templates.keys()) != set(template_catalog.keys()):
        raise ValueError("config/vm-template-manifest.json.templates must match host_vars.proxmox_vm_templates")

    for template_key, template in template_catalog.items():
        template = require_mapping(template, f"inventory/group_vars/all.yml.proxmox_vm_templates.{template_key}")
        manifest_entry = require_mapping(templates.get(template_key), f"config/vm-template-manifest.json.templates.{template_key}")
        manifest_vmid = require_int(manifest_entry.get("vmid"), f"config/vm-template-manifest.json.templates.{template_key}.vmid", 1)
        inventory_vmid = require_int(template.get("vmid"), f"inventory/group_vars/all.yml.proxmox_vm_templates.{template_key}.vmid", 1)
        if manifest_vmid != inventory_vmid:
            raise ValueError(f"config/vm-template-manifest.json.templates.{template_key}.vmid must match inventory template vmid")

        manifest_name = require_hostname(
            manifest_entry.get("name"),
            f"config/vm-template-manifest.json.templates.{template_key}.name",
        )
        inventory_name = require_hostname(template.get("name"), f"inventory/group_vars/all.yml.proxmox_vm_templates.{template_key}.name")
        if manifest_name != inventory_name:
            raise ValueError(f"config/vm-template-manifest.json.templates.{template_key}.name must match inventory template name")

        source_template = manifest_entry.get("source_template")
        if source_template is not None:
            require_str(source_template, f"config/vm-template-manifest.json.templates.{template_key}.source_template")

        build_date = manifest_entry.get("build_date")
        if build_date is not None:
            dt.datetime.fromisoformat(
                require_str(build_date, f"config/vm-template-manifest.json.templates.{template_key}.build_date").replace("Z", "+00:00")
            )

        version = manifest_entry.get("version")
        if version is not None:
            require_semver(version, f"config/vm-template-manifest.json.templates.{template_key}.version")

        digest = manifest_entry.get("digest")
        if digest is not None:
            require_str(digest, f"config/vm-template-manifest.json.templates.{template_key}.digest")

        packer_commit = manifest_entry.get("packer_commit")
        if packer_commit is not None:
            require_str(packer_commit, f"config/vm-template-manifest.json.templates.{template_key}.packer_commit")


def validate_platform_vars() -> None:
    platform_vars = require_mapping(load_yaml(PLATFORM_VARS_PATH), str(PLATFORM_VARS_PATH))
    expected_platform_vars = build_platform_vars()
    if platform_vars != expected_platform_vars:
        raise ValueError(
            "inventory/group_vars/platform.yml must match scripts/generate_platform_vars.py output"
        )


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


def validate_probe_definition(probe: Any, path: str) -> None:
    probe = require_mapping(probe, path)
    kind = require_enum(probe.get("kind"), f"{path}.kind", PROBE_KINDS)
    require_str(probe.get("description"), f"{path}.description")
    require_int(probe.get("timeout_seconds"), f"{path}.timeout_seconds", 1)
    require_int(probe.get("retries"), f"{path}.retries", 1)
    require_int(probe.get("delay_seconds"), f"{path}.delay_seconds", 0)

    if "headers" in probe:
        headers = require_mapping(probe.get("headers"), f"{path}.headers")
        for key, value in headers.items():
            require_str(key, f"{path}.headers key")
            require_str(value, f"{path}.headers.{key}")

    if "validate_tls" in probe:
        require_bool(probe.get("validate_tls"), f"{path}.validate_tls")

    if kind == "http":
        url = require_str(probe.get("url"), f"{path}.url")
        if not (url.startswith("http://") or url.startswith("https://")):
            raise ValueError(f"{path}.url must start with http:// or https://")
        method = require_str(probe.get("method"), f"{path}.method").upper()
        if method not in HTTP_METHODS:
            raise ValueError(f"{path}.method must be one of {sorted(HTTP_METHODS)}")
        expected_status = require_int_list(probe.get("expected_status"), f"{path}.expected_status", 100)
        for index, status in enumerate(expected_status):
            if status > 599:
                raise ValueError(f"{path}.expected_status[{index}] must be <= 599")

    if kind == "tcp":
        require_str(probe.get("host"), f"{path}.host")
        require_int(probe.get("port"), f"{path}.port", 1)

    if kind == "command":
        argv = require_string_list(probe.get("argv"), f"{path}.argv")
        if not argv:
            raise ValueError(f"{path}.argv must not be empty")
        if "success_rc" in probe:
            require_int(probe.get("success_rc"), f"{path}.success_rc", 0)

    if kind == "systemd":
        require_str(probe.get("unit"), f"{path}.unit")
        require_str(probe.get("expected_state"), f"{path}.expected_state")


def validate_health_probe_catalog(host_vars_context: dict[str, Any]) -> None:
    catalog = require_mapping(
        json.loads(HEALTH_PROBE_CATALOG_PATH.read_text()),
        str(HEALTH_PROBE_CATALOG_PATH),
    )
    require_semver(catalog.get("schema_version"), "config/health-probe-catalog.json.schema_version")
    services = require_mapping(catalog.get("services"), "config/health-probe-catalog.json.services")
    topology = host_vars_context["topology"]
    certificate_catalog = require_mapping(load_json(CERTIFICATE_CATALOG_PATH), str(CERTIFICATE_CATALOG_PATH))
    certificate_entries = require_list(certificate_catalog.get("certificates"), "config/certificate-catalog.json.certificates")
    certificate_service_map = {
        require_identifier(entry.get("id"), f"config/certificate-catalog.json.certificates[{index}].id"): require_identifier(
            entry.get("service_id"),
            f"config/certificate-catalog.json.certificates[{index}].service_id",
        )
        for index, entry in enumerate(certificate_entries)
    }

    if set(services.keys()) != set(topology.keys()):
        raise ValueError(
            "config/health-probe-catalog.json.services must define exactly the canonical lv3_service_topology services"
        )

    expected_monitors: dict[str, dict[str, Any]] = {}
    for service_id, topology_entry in topology.items():
        service_path = f"config/health-probe-catalog.json.services.{service_id}"
        service = require_mapping(services.get(service_id), service_path)
        if require_str(service.get("service_name"), f"{service_path}.service_name") != topology_entry["service_name"]:
            raise ValueError(f"{service_path}.service_name must match inventory/host_vars/proxmox_florin.yml")
        if require_str(service.get("owning_vm"), f"{service_path}.owning_vm") != topology_entry["owning_vm"]:
            raise ValueError(f"{service_path}.owning_vm must match inventory/host_vars/proxmox_florin.yml")

        role = service.get("role")
        verify_file = service.get("verify_file")
        if role is None:
            if verify_file is not None:
                raise ValueError(f"{service_path}.verify_file must be null when {service_path}.role is null")
        else:
            require_str(role, f"{service_path}.role")
            verify_file = require_str(verify_file, f"{service_path}.verify_file")
            if not (REPO_ROOT / verify_file).is_file():
                raise ValueError(f"{service_path}.verify_file does not exist: {verify_file}")

        validate_probe_definition(service.get("liveness"), f"{service_path}.liveness")
        validate_probe_definition(service.get("readiness"), f"{service_path}.readiness")
        if "tls_certificate_ids" in service:
            certificate_ids = require_string_list(service.get("tls_certificate_ids"), f"{service_path}.tls_certificate_ids")
            for index, certificate_id in enumerate(certificate_ids):
                if certificate_id not in certificate_service_map:
                    raise ValueError(
                        f"{service_path}.tls_certificate_ids[{index}] references unknown certificate '{certificate_id}'"
                    )
                if certificate_service_map[certificate_id] != service_id:
                    raise ValueError(
                        f"{service_path}.tls_certificate_ids[{index}] must reference a certificate owned by service '{service_id}'"
                    )

        uptime_kuma = require_mapping(service.get("uptime_kuma"), f"{service_path}.uptime_kuma")
        enabled = require_bool(uptime_kuma.get("enabled"), f"{service_path}.uptime_kuma.enabled")
        if enabled:
            monitor = require_mapping(uptime_kuma.get("monitor"), f"{service_path}.uptime_kuma.monitor")
            name = validate_monitor(monitor, f"{service_path}.uptime_kuma.monitor")
            if name in expected_monitors:
                raise ValueError(f"duplicate Uptime Kuma monitor contract in health probe catalog: {name}")
            expected_monitors[name] = monitor
        elif "reason" in uptime_kuma:
            require_str(uptime_kuma.get("reason"), f"{service_path}.uptime_kuma.reason")

    actual_monitors = require_list(
        json.loads(UPTIME_MONITORS_PATH.read_text()),
        str(UPTIME_MONITORS_PATH),
    )
    actual_monitors_by_name: dict[str, dict[str, Any]] = {}
    for index, monitor in enumerate(actual_monitors):
        name = validate_monitor(monitor, f"config/uptime-kuma/monitors.json[{index}]")
        if name in actual_monitors_by_name:
            raise ValueError(f"duplicate monitor name in config/uptime-kuma/monitors.json: {name}")
        actual_monitors_by_name[name] = monitor

    if set(actual_monitors_by_name.keys()) != set(expected_monitors.keys()):
        raise ValueError(
            "config/uptime-kuma/monitors.json must match the enabled uptime_kuma monitors in config/health-probe-catalog.json"
        )

    for name, expected_monitor in expected_monitors.items():
        if actual_monitors_by_name[name] != expected_monitor:
            raise ValueError(
                f"config/uptime-kuma/monitors.json monitor '{name}' does not match the health probe catalog contract"
            )


def validate_certificate_catalog(host_vars_context: dict[str, Any]) -> None:
    catalog = require_mapping(load_json(CERTIFICATE_CATALOG_PATH), str(CERTIFICATE_CATALOG_PATH))
    require_semver(catalog.get("schema_version"), "config/certificate-catalog.json.schema_version")
    require_str(catalog.get("$schema"), "config/certificate-catalog.json.$schema")
    certificates = require_list(catalog.get("certificates"), "config/certificate-catalog.json.certificates")
    if not certificates:
        raise ValueError("config/certificate-catalog.json.certificates must not be empty")

    topology = host_vars_context["topology"]
    certificate_ids: set[str] = set()
    for index, item in enumerate(certificates):
        path = f"config/certificate-catalog.json.certificates[{index}]"
        item = require_mapping(item, path)
        certificate_id = require_identifier(item.get("id"), f"{path}.id")
        if certificate_id in certificate_ids:
            raise ValueError(f"duplicate certificate id: {certificate_id}")
        certificate_ids.add(certificate_id)

        service_id = require_identifier(item.get("service_id"), f"{path}.service_id")
        if service_id not in topology:
            raise ValueError(f"{path}.service_id references unknown platform service '{service_id}'")

        require_enum(item.get("status"), f"{path}.status", {"active", "planned"})
        require_str(item.get("summary"), f"{path}.summary")
        require_enum(item.get("expected_issuer"), f"{path}.expected_issuer", {"any", "letsencrypt", "self-signed", "step-ca"})

        endpoint = require_mapping(item.get("endpoint"), f"{path}.endpoint")
        require_str(endpoint.get("host"), f"{path}.endpoint.host")
        require_int(endpoint.get("port"), f"{path}.endpoint.port", 1)
        require_str(endpoint.get("server_name"), f"{path}.endpoint.server_name")

        policy = require_mapping(item.get("policy"), f"{path}.policy")
        warn_days = require_int(policy.get("warn_days"), f"{path}.policy.warn_days", 1)
        critical_days = require_int(policy.get("critical_days"), f"{path}.policy.critical_days", 1)
        if warn_days <= critical_days:
            raise ValueError(f"{path}.policy.warn_days must be greater than {path}.policy.critical_days")

        renewal = require_mapping(item.get("renewal"), f"{path}.renewal")
        require_str(renewal.get("agent"), f"{path}.renewal.agent")
        managed_by_repo = require_bool(renewal.get("managed_by_repo"), f"{path}.renewal.managed_by_repo")
        if managed_by_repo:
            require_str(renewal.get("host"), f"{path}.renewal.host")
            require_str(renewal.get("unit_name"), f"{path}.renewal.unit_name")
            require_str(renewal.get("on_calendar"), f"{path}.renewal.on_calendar")
            require_int(renewal.get("randomized_delay_seconds"), f"{path}.renewal.randomized_delay_seconds", 0)
            material = require_mapping(item.get("material"), f"{path}.material")
            require_str(material.get("certificate_file"), f"{path}.material.certificate_file")
            require_str(material.get("key_file"), f"{path}.material.key_file")
            require_str(material.get("root_file"), f"{path}.material.root_file")
            require_str(material.get("subject"), f"{path}.material.subject")
            require_string_list(material.get("sans"), f"{path}.material.sans")
            require_str(material.get("ca_url"), f"{path}.material.ca_url")
            require_str(material.get("provisioner"), f"{path}.material.provisioner")
            require_str(material.get("password_file"), f"{path}.material.password_file")
            require_str(material.get("not_after"), f"{path}.material.not_after")


def validate_secret_catalog(secret_manifest: dict[str, Any]) -> None:
    catalog = require_mapping(load_json(SECRET_CATALOG_PATH), str(SECRET_CATALOG_PATH))
    require_semver(catalog.get("schema_version"), "config/secret-catalog.json.schema_version")
    secrets = require_list(catalog.get("secrets"), "config/secret-catalog.json.secrets")
    if not secrets:
        raise ValueError("config/secret-catalog.json.secrets must not be empty")
    secret_ids: set[str] = set()
    manifest_secrets = secret_manifest["secrets"]
    for index, secret in enumerate(secrets):
        path = f"config/secret-catalog.json.secrets[{index}]"
        secret = require_mapping(secret, path)
        secret_id = require_identifier(secret.get("id"), f"{path}.id")
        if secret_id in secret_ids:
            raise ValueError(f"duplicate secret-catalog id: {secret_id}")
        secret_ids.add(secret_id)
        require_identifier(secret.get("owner_service"), f"{path}.owner_service")
        require_str(secret.get("storage_contract"), f"{path}.storage_contract")
        storage_ref = require_identifier(secret.get("storage_ref"), f"{path}.storage_ref")
        if storage_ref not in manifest_secrets:
            raise ValueError(f"{path}.storage_ref references unknown controller-local secret '{storage_ref}'")
        require_int(secret.get("rotation_period_days"), f"{path}.rotation_period_days", 1)
        require_int(secret.get("warning_window_days"), f"{path}.warning_window_days", 0)
        require_date(secret.get("last_rotated_at"), f"{path}.last_rotated_at")
        require_str(secret.get("rotation_mode"), f"{path}.rotation_mode")

    if "rotation_contracts" not in catalog:
        return

    rotation_metadata = require_mapping(
        catalog.get("rotation_metadata"),
        "config/secret-catalog.json.rotation_metadata",
    )
    require_str(
        rotation_metadata.get("state_source"),
        "config/secret-catalog.json.rotation_metadata.state_source",
    )
    require_str(
        rotation_metadata.get("value_field"),
        "config/secret-catalog.json.rotation_metadata.value_field",
    )
    require_str(
        rotation_metadata.get("last_rotated_metadata_key"),
        "config/secret-catalog.json.rotation_metadata.last_rotated_metadata_key",
    )
    require_str(
        rotation_metadata.get("rotated_by_metadata_key"),
        "config/secret-catalog.json.rotation_metadata.rotated_by_metadata_key",
    )
    require_str(
        rotation_metadata.get("default_event_subject"),
        "config/secret-catalog.json.rotation_metadata.default_event_subject",
    )
    require_str(
        rotation_metadata.get("default_glitchtip_component"),
        "config/secret-catalog.json.rotation_metadata.default_glitchtip_component",
    )

    rotation_contracts = require_mapping(
        catalog.get("rotation_contracts"),
        "config/secret-catalog.json.rotation_contracts",
    )
    allowed_secret_types = {
        "admin_password",
        "admin_token",
        "api_key",
        "database_password",
        "mailbox_password",
        "metrics_password",
    }
    allowed_risk_levels = {"low", "high"}
    allowed_approval_modes = {"auto", "approval_required"}
    allowed_generators = {"base64_24", "hex_32"}
    allowed_apply_targets = {
        "mail_platform_profile_field",
        "mail_platform_runtime_field",
        "windmill_database",
        "windmill_superadmin",
    }

    for secret_id, secret in rotation_contracts.items():
        path = f"config/secret-catalog.json.rotation_contracts.{secret_id}"
        require_identifier(secret_id, path)
        if secret_id not in secret_ids:
            raise ValueError(f"{path} must also exist in config/secret-catalog.json.secrets")

        secret = require_mapping(secret, path)
        require_str(secret.get("owner"), f"{path}.owner")
        require_identifier(secret.get("service"), f"{path}.service")
        require_enum(secret.get("secret_type"), f"{path}.secret_type", allowed_secret_types)
        risk_level = require_enum(secret.get("risk_level"), f"{path}.risk_level", allowed_risk_levels)
        approval_mode = require_enum(
            secret.get("approval_mode"),
            f"{path}.approval_mode",
            allowed_approval_modes,
        )
        if risk_level == "high" and approval_mode != "approval_required":
            raise ValueError(f"{path}.approval_mode must be approval_required for high-risk secrets")

        require_identifier(secret.get("command_contract"), f"{path}.command_contract")
        rotation_period_days = require_int(secret.get("rotation_period_days"), f"{path}.rotation_period_days", 1)
        warning_window_days = require_int(secret.get("warning_window_days"), f"{path}.warning_window_days", 0)
        if warning_window_days >= rotation_period_days:
            raise ValueError(f"{path}.warning_window_days must be smaller than rotation_period_days")

        last_rotated = secret.get("last_rotated")
        if last_rotated is not None:
            require_str(last_rotated, f"{path}.last_rotated")

        seed_secret_id = require_identifier(
            secret.get("seed_controller_secret_id"),
            f"{path}.seed_controller_secret_id",
        )
        if seed_secret_id not in manifest_secrets:
            raise ValueError(
                f"{path}.seed_controller_secret_id references unknown controller-local secret '{seed_secret_id}'"
            )

        require_enum(secret.get("value_generator"), f"{path}.value_generator", allowed_generators)
        require_str(secret.get("openbao_path"), f"{path}.openbao_path")
        require_str(secret.get("openbao_field"), f"{path}.openbao_field")
        apply_target = require_enum(secret.get("apply_target"), f"{path}.apply_target", allowed_apply_targets)

        apply_field = secret.get("apply_field")
        if apply_target in {"mail_platform_profile_field", "mail_platform_runtime_field"}:
            require_identifier(apply_field, f"{path}.apply_field")
        elif apply_field is not None:
            require_identifier(apply_field, f"{path}.apply_field")

        profile_id = secret.get("profile_id")
        if apply_target == "mail_platform_profile_field":
            require_identifier(profile_id, f"{path}.profile_id")
        elif profile_id is not None:
            require_identifier(profile_id, f"{path}.profile_id")

        compatibility_mirror = secret.get("compatibility_mirror")
        if compatibility_mirror is not None:
            compatibility_mirror = require_mapping(compatibility_mirror, f"{path}.compatibility_mirror")
            require_str(
                compatibility_mirror.get("openbao_path"),
                f"{path}.compatibility_mirror.openbao_path",
            )
            require_identifier(
                compatibility_mirror.get("field"),
                f"{path}.compatibility_mirror.field",
            )

        require_str(secret.get("event_subject"), f"{path}.event_subject")
        require_str(secret.get("glitchtip_component"), f"{path}.glitchtip_component")


def validate_token_policy() -> set[str]:
    payload = require_mapping(load_yaml(TOKEN_POLICY_PATH), str(TOKEN_POLICY_PATH))
    require_semver(payload.get("schema_version"), "config/token-policy.yaml.schema_version")
    classes = require_list(payload.get("token_classes"), "config/token-policy.yaml.token_classes")
    if not classes:
        raise ValueError("config/token-policy.yaml.token_classes must not be empty")

    class_names: set[str] = set()
    for index, item in enumerate(classes):
        path = f"config/token-policy.yaml.token_classes[{index}]"
        item = require_mapping(item, path)
        class_name = require_identifier(item.get("class"), f"{path}.class")
        if class_name in class_names:
            raise ValueError(f"duplicate token policy class: {class_name}")
        class_names.add(class_name)
        max_ttl_days = require_int(item.get("max_ttl_days"), f"{path}.max_ttl_days", 1)
        warning_window_days = require_int(item.get("warning_window_days"), f"{path}.warning_window_days", 0)
        require_int(item.get("enforcement_grace_days"), f"{path}.enforcement_grace_days", 0)
        if warning_window_days > max_ttl_days:
            raise ValueError(f"{path}.warning_window_days must not exceed max_ttl_days")
        require_str(item.get("rotation_trigger"), f"{path}.rotation_trigger")
        require_str(item.get("storage"), f"{path}.storage")
        require_identifier(item.get("revocation_workflow"), f"{path}.revocation_workflow")
        require_str(item.get("on_exposure"), f"{path}.on_exposure")
    return class_names


def validate_token_inventory(token_classes: set[str], workflow_catalog: dict[str, Any]) -> None:
    payload = require_mapping(load_yaml(TOKEN_INVENTORY_PATH), str(TOKEN_INVENTORY_PATH))
    require_semver(payload.get("schema_version"), "config/token-inventory.yaml.schema_version")
    tokens = require_list(payload.get("tokens"), "config/token-inventory.yaml.tokens")
    if not tokens:
        raise ValueError("config/token-inventory.yaml.tokens must not be empty")
    workflows = require_mapping(workflow_catalog.get("workflows"), "config/workflow-catalog.json.workflows")
    token_ids: set[str] = set()
    for index, token in enumerate(tokens):
        path = f"config/token-inventory.yaml.tokens[{index}]"
        token = require_mapping(token, path)
        token_id = require_identifier(token.get("id"), f"{path}.id")
        if token_id in token_ids:
            raise ValueError(f"duplicate token inventory id: {token_id}")
        token_ids.add(token_id)
        token_class = require_identifier(token.get("token_class"), f"{path}.token_class")
        if token_class not in token_classes:
            raise ValueError(f"{path}.token_class references unknown policy class '{token_class}'")
        require_identifier(token.get("owner_service"), f"{path}.owner_service")
        require_str(token.get("subject"), f"{path}.subject")
        require_str(token.get("issued_at"), f"{path}.issued_at")
        expires_at = token.get("expires_at")
        if expires_at is not None:
            require_str(expires_at, f"{path}.expires_at")
        require_str(token.get("storage_ref"), f"{path}.storage_ref")
        permissions = token.get("permissions", [])
        if permissions:
            require_string_list(permissions, f"{path}.permissions")
        workflow_refs = require_mapping(token.get("workflows", {}), f"{path}.workflows")
        for workflow_name, workflow_id in workflow_refs.items():
            require_identifier(workflow_name, f"{path}.workflows key '{workflow_name}'")
            workflow_id = require_identifier(workflow_id, f"{path}.workflows.{workflow_name}")
            if workflow_id not in workflows:
                raise ValueError(f"{path}.workflows.{workflow_name} references unknown workflow '{workflow_id}'")
        hooks = require_mapping(token.get("hooks", {}), f"{path}.hooks")
        for hook_name, hook in hooks.items():
            hook_path = f"{path}.hooks.{hook_name}"
            require_identifier(hook_name, f"{path}.hooks key '{hook_name}'")
            hook = require_mapping(hook, hook_path)
            require_enum(hook.get("kind"), f"{hook_path}.kind", {"command"})
            command = require_list(hook.get("command"), f"{hook_path}.command")
            if not command:
                raise ValueError(f"{hook_path}.command must not be empty")
            for command_index, part in enumerate(command):
                require_str(part, f"{hook_path}.command[{command_index}]")
            env = require_mapping(hook.get("env", {}), f"{hook_path}.env")
            for env_key, env_value in env.items():
                require_str(env_key, f"{hook_path}.env key '{env_key}'")
                require_str(env_value, f"{hook_path}.env.{env_key}")


def validate_circuit_policies() -> None:
    policies = load_circuit_policies(CIRCUIT_POLICIES_PATH)
    if not policies:
        raise ValueError("config/circuit-policies.yaml must define at least one circuit")
    for name, policy in policies.items():
        require_identifier(name, f"config/circuit-policies.yaml {name}.name")
        require_str(policy.service, f"config/circuit-policies.yaml {name}.service")
        require_int(policy.failure_threshold, f"config/circuit-policies.yaml {name}.failure_threshold", 1)
        require_int(policy.recovery_window_s, f"config/circuit-policies.yaml {name}.recovery_window_s", 1)
        require_int(policy.success_threshold, f"config/circuit-policies.yaml {name}.success_threshold", 1)
        if policy.timeout_s is not None and float(policy.timeout_s) <= 0:
            raise ValueError(f"config/circuit-policies.yaml {name}.timeout_s must be > 0 when set")


def validate_legacy_image_catalog(host_vars_context: dict[str, Any]) -> None:
    catalog = require_mapping(load_json(IMAGE_CATALOG_PATH), str(IMAGE_CATALOG_PATH))
    require_semver(catalog.get("schema_version"), "config/image-catalog.json.schema_version")
    images = require_list(catalog.get("images"), "config/image-catalog.json.images")
    if not images:
        raise ValueError("config/image-catalog.json.images must not be empty")
    image_ids: set[str] = set()
    allowed_targets = host_vars_context["guest_names"]
    for index, image in enumerate(images):
        path = f"config/image-catalog.json.images[{index}]"
        image = require_mapping(image, path)
        image_id = require_identifier(image.get("id"), f"{path}.id")
        if image_id in image_ids:
            raise ValueError(f"duplicate image-catalog id: {image_id}")
        image_ids.add(image_id)
        require_identifier(image.get("service_id"), f"{path}.service_id")
        runtime_host = require_identifier(image.get("runtime_host"), f"{path}.runtime_host")
        if runtime_host not in allowed_targets:
            raise ValueError(f"{path}.runtime_host must reference a managed guest")
        require_str(image.get("container_name"), f"{path}.container_name")
        require_str(image.get("image_reference"), f"{path}.image_reference")
        require_enum(image.get("source_kind"), f"{path}.source_kind", IMAGE_SOURCE_KINDS)
        pin_status = require_enum(image.get("pin_status"), f"{path}.pin_status", IMAGE_PIN_STATUSES)
        pinned_digest = image.get("pinned_digest")
        if pin_status == "pinned":
            if pinned_digest is None:
                raise ValueError(f"{path}.pinned_digest must be set when pin_status is pinned")
            require_str(pinned_digest, f"{path}.pinned_digest")
        elif pinned_digest is not None:
            require_str(pinned_digest, f"{path}.pinned_digest")
        pinned_at = image.get("pinned_at")
        if pinned_at is not None:
            require_date(pinned_at, f"{path}.pinned_at")
        require_int(image.get("freshness_window_days"), f"{path}.freshness_window_days", 1)


def validate_platform_finding_schema() -> None:
    schema = require_mapping(load_json(PLATFORM_FINDING_SCHEMA_PATH), str(PLATFORM_FINDING_SCHEMA_PATH))
    require_str(schema.get("$schema"), "docs/schema/platform-finding.json.$schema")
    require_str(schema.get("$id"), "docs/schema/platform-finding.json.$id")
    if schema.get("type") != "object":
        raise ValueError("docs/schema/platform-finding.json.type must be object")
    required_fields = set(require_string_list(schema.get("required"), "docs/schema/platform-finding.json.required"))
    expected_fields = {"check", "severity", "summary", "details", "ts", "run_id"}
    if required_fields != expected_fields:
        raise ValueError("docs/schema/platform-finding.json.required must match the ADR 0071 finding contract")
    severity_enum = set(
        require_string_list(
            schema["properties"]["severity"].get("enum", []),
            "docs/schema/platform-finding.json.properties.severity.enum",
        )
    )
    if severity_enum != {"ok", "warning", "critical", "suppressed"}:
        raise ValueError("docs/schema/platform-finding.json severity enum must include suppressed maintenance findings")


def validate_maintenance_window_schema() -> None:
    schema = require_mapping(load_json(MAINTENANCE_WINDOW_SCHEMA_PATH), str(MAINTENANCE_WINDOW_SCHEMA_PATH))
    require_str(schema.get("$schema"), "docs/schema/maintenance-window.json.$schema")
    require_str(schema.get("$id"), "docs/schema/maintenance-window.json.$id")
    if schema.get("type") != "object":
        raise ValueError("docs/schema/maintenance-window.json.type must be object")
    required_fields = set(
        require_string_list(schema.get("required"), "docs/schema/maintenance-window.json.required")
    )
    expected_fields = {
        "window_id",
        "service_id",
        "reason",
        "opened_by",
        "opened_at",
        "expected_duration_minutes",
        "auto_close_at",
    }
    if required_fields != expected_fields:
        raise ValueError("docs/schema/maintenance-window.json.required must match the ADR 0080 contract")


def validate_capacity_model() -> None:
    load_capacity_model(CAPACITY_MODEL_PATH)
    violations = validate_ephemeral_vmid_ranges()
    if violations:
        raise ValueError("; ".join(violations))


def validate_capacity_model_schema() -> None:
    schema = require_mapping(load_json(CAPACITY_MODEL_SCHEMA_PATH), str(CAPACITY_MODEL_SCHEMA_PATH))
    require_str(schema.get("$schema"), "docs/schema/capacity-model.schema.json.$schema")
    require_str(schema.get("$id"), "docs/schema/capacity-model.schema.json.$id")
    require_str(schema.get("title"), "docs/schema/capacity-model.schema.json.title")
    properties = require_mapping(
        schema.get("properties"),
        "docs/schema/capacity-model.schema.json.properties",
    )
    for field in ("$schema", "schema_version", "host", "guests", "reservations"):
        if field not in properties:
            raise ValueError(f"docs/schema/capacity-model.schema.json.properties must include '{field}'")


def validate_error_registry() -> None:
    payload = require_mapping(load_yaml(ERROR_REGISTRY_PATH), str(ERROR_REGISTRY_PATH))
    require_semver(payload.get("schema_version"), "config/error-codes.yaml.schema_version")
    registry = ErrorRegistry.load(ERROR_REGISTRY_PATH)
    openapi_fragment = registry.openapi_fragment()
    if not openapi_fragment:
        raise ValueError("config/error-codes.yaml must define at least one error code")
    for code, definition in openapi_fragment.items():
        http_status = definition["http_status"]
        if http_status < 100 or http_status > 599:
            raise ValueError(f"config/error-codes.yaml.error_codes.{code}.http_status must be between 100 and 599")
        require_str(definition["severity"], f"config/error-codes.yaml.error_codes.{code}.severity")
        require_str(definition["category"], f"config/error-codes.yaml.error_codes.{code}.category")
        require_enum(
            definition["retry_advice"],
            f"config/error-codes.yaml.error_codes.{code}.retry_advice",
            {"none", "immediate", "backoff", "manual"},
        )


def validate_version_semantics() -> None:
    payload = load_json(VERSION_SEMANTICS_PATH)
    require_semver(payload.get("schema_version"), "config/version-semantics.json.schema_version")

    repository_versioning = require_mapping(
        payload.get("repository_versioning"), "config/version-semantics.json.repository_versioning"
    )
    for level in ("major", "minor", "patch"):
        level_payload = require_mapping(
            repository_versioning.get(level),
            f"config/version-semantics.json.repository_versioning.{level}",
        )
        require_str(
            level_payload.get("meaning"),
            f"config/version-semantics.json.repository_versioning.{level}.meaning",
        )
        require_string_list(
            level_payload.get("triggers"),
            f"config/version-semantics.json.repository_versioning.{level}.triggers",
        )

    criteria = require_list(
        payload.get("breaking_change_criteria"),
        "config/version-semantics.json.breaking_change_criteria",
    )
    for index, criterion in enumerate(criteria):
        criterion = require_mapping(criterion, f"config/version-semantics.json.breaking_change_criteria[{index}]")
        require_identifier(
            criterion.get("id"),
            f"config/version-semantics.json.breaking_change_criteria[{index}].id",
        )
        require_str(
            criterion.get("surface"),
            f"config/version-semantics.json.breaking_change_criteria[{index}].surface",
        )
        require_str(
            criterion.get("description"),
            f"config/version-semantics.json.breaking_change_criteria[{index}].description",
        )

    release_artifacts = require_mapping(
        payload.get("release_artifacts"), "config/version-semantics.json.release_artifacts"
    )
    for field in (
        "working_section",
        "version_file",
        "changelog_path",
        "root_release_notes",
        "release_notes_dir",
        "release_notes_index",
        "upgrade_guides_dir",
        "git_tag_prefix",
    ):
        require_str(release_artifacts.get(field), f"config/version-semantics.json.release_artifacts.{field}")

    release_gates = require_mapping(payload.get("release_gates"), "config/version-semantics.json.release_gates")
    require_string_list(
        release_gates.get("blocking_workstream_statuses"),
        "config/version-semantics.json.release_gates.blocking_workstream_statuses",
    )

    upgrade_policy = require_mapping(payload.get("upgrade_policy"), "config/version-semantics.json.upgrade_policy")
    require_bool(
        upgrade_policy.get("minor_version_skip_supported"),
        "config/version-semantics.json.upgrade_policy.minor_version_skip_supported",
    )
    require_bool(
        upgrade_policy.get("major_version_skip_supported"),
        "config/version-semantics.json.upgrade_policy.major_version_skip_supported",
    )
    rules = require_list(upgrade_policy.get("rules"), "config/version-semantics.json.upgrade_policy.rules")
    for index, rule in enumerate(rules):
        rule = require_mapping(rule, f"config/version-semantics.json.upgrade_policy.rules[{index}]")
        require_str(rule.get("source"), f"config/version-semantics.json.upgrade_policy.rules[{index}].source")
        require_str(rule.get("target"), f"config/version-semantics.json.upgrade_policy.rules[{index}].target")
        require_bool(
            rule.get("operator_action_required"),
            f"config/version-semantics.json.upgrade_policy.rules[{index}].operator_action_required",
        )
        require_str(rule.get("notes"), f"config/version-semantics.json.upgrade_policy.rules[{index}].notes")

    readiness_targets = require_mapping(
        payload.get("readiness_targets"), "config/version-semantics.json.readiness_targets"
    )
    readiness = require_mapping(
        readiness_targets.get("1.0.0"),
        "config/version-semantics.json.readiness_targets.1.0.0",
    )
    adr_window = require_mapping(
        readiness.get("adr_window"),
        "config/version-semantics.json.readiness_targets.1.0.0.adr_window",
    )
    require_int(adr_window.get("start"), "config/version-semantics.json.readiness_targets.1.0.0.adr_window.start", 1)
    require_int(adr_window.get("end"), "config/version-semantics.json.readiness_targets.1.0.0.adr_window.end", 1)
    require_string_list(
        adr_window.get("required_statuses"),
        "config/version-semantics.json.readiness_targets.1.0.0.adr_window.required_statuses",
    )
    require_string_list(
        adr_window.get("required_implementation_statuses"),
        "config/version-semantics.json.readiness_targets.1.0.0.adr_window.required_implementation_statuses",
    )

    services = require_list(
        readiness.get("required_services"),
        "config/version-semantics.json.readiness_targets.1.0.0.required_services",
    )
    for index, service in enumerate(services):
        service = require_mapping(service, f"config/version-semantics.json.readiness_targets.1.0.0.required_services[{index}]")
        require_str(
            service.get("id"),
            f"config/version-semantics.json.readiness_targets.1.0.0.required_services[{index}].id",
        )
        require_str(
            service.get("label"),
            f"config/version-semantics.json.readiness_targets.1.0.0.required_services[{index}].label",
        )
        require_str(
            service.get("url"),
            f"config/version-semantics.json.readiness_targets.1.0.0.required_services[{index}].url",
        )

    slos = require_list(readiness.get("required_slos"), "config/version-semantics.json.readiness_targets.1.0.0.required_slos")
    for index, slo in enumerate(slos):
        slo = require_mapping(slo, f"config/version-semantics.json.readiness_targets.1.0.0.required_slos[{index}]")
        require_identifier(
            slo.get("service_id"),
            f"config/version-semantics.json.readiness_targets.1.0.0.required_slos[{index}].service_id",
        )
        minimum = slo.get("minimum_error_budget_remaining_percent")
        if not isinstance(minimum, (int, float)):
            raise ValueError(
                f"config/version-semantics.json.readiness_targets.1.0.0.required_slos[{index}].minimum_error_budget_remaining_percent must be numeric"
            )

    require_str(
        readiness.get("slo_report_path"),
        "config/version-semantics.json.readiness_targets.1.0.0.slo_report_path",
    )
    restore = require_mapping(
        readiness.get("restore_verification"),
        "config/version-semantics.json.readiness_targets.1.0.0.restore_verification",
    )
    require_str(
        restore.get("receipt_dir"),
        "config/version-semantics.json.readiness_targets.1.0.0.restore_verification.receipt_dir",
    )
    require_int(
        restore.get("required_consecutive_passes"),
        "config/version-semantics.json.readiness_targets.1.0.0.restore_verification.required_consecutive_passes",
        1,
    )
    dr_review = require_mapping(
        readiness.get("dr_table_top_review"),
        "config/version-semantics.json.readiness_targets.1.0.0.dr_table_top_review",
    )
    require_str(
        dr_review.get("receipt_dir"),
        "config/version-semantics.json.readiness_targets.1.0.0.dr_table_top_review.receipt_dir",
    )


def validate_workstreams_release_policy() -> None:
    registry = load_yaml(WORKSTREAMS_PATH)
    release_policy = require_mapping(registry.get("release_policy"), "workstreams.yaml.release_policy")
    breaking_change_path = require_str(
        release_policy.get("breaking_change_criteria"),
        "workstreams.yaml.release_policy.breaking_change_criteria",
    )
    if not breaking_change_path.endswith("/config/version-semantics.json"):
        raise ValueError("workstreams.yaml.release_policy.breaking_change_criteria must point to config/version-semantics.json")


def validate_workstream_canonical_truth_metadata() -> None:
    registry = load_yaml(WORKSTREAMS_PATH)
    workstreams = require_list(registry.get("workstreams"), "workstreams.yaml.workstreams")
    allowed_release_bumps = {"patch", "minor", "major"}
    semver_pattern = re.compile(r"^\d+\.\d+\.\d+$")

    for index, workstream in enumerate(workstreams):
        workstream_path = f"workstreams.yaml.workstreams[{index}]"
        workstream = require_mapping(workstream, workstream_path)
        canonical_truth = workstream.get("canonical_truth")
        if canonical_truth is None:
            continue
        canonical_truth = require_mapping(canonical_truth, f"{workstream_path}.canonical_truth")

        changelog_entry = canonical_truth.get("changelog_entry")
        if changelog_entry is not None:
            require_str(changelog_entry, f"{workstream_path}.canonical_truth.changelog_entry")

        release_bump = canonical_truth.get("release_bump")
        if release_bump is not None:
            release_bump = require_str(release_bump, f"{workstream_path}.canonical_truth.release_bump")
            if release_bump not in allowed_release_bumps:
                raise ValueError(
                    f"{workstream_path}.canonical_truth.release_bump must be one of {sorted(allowed_release_bumps)}"
                )

        included_in_repo_version = canonical_truth.get("included_in_repo_version")
        if included_in_repo_version is not None:
            included_in_repo_version = require_str(
                included_in_repo_version,
                f"{workstream_path}.canonical_truth.included_in_repo_version",
            )
            if not semver_pattern.fullmatch(included_in_repo_version):
                raise ValueError(
                    f"{workstream_path}.canonical_truth.included_in_repo_version must use semantic version format"
                )

        latest_receipts = require_mapping(
            canonical_truth.get("latest_receipts", {}),
            f"{workstream_path}.canonical_truth.latest_receipts",
        )
        for capability, receipt_id in latest_receipts.items():
            require_str(capability, f"{workstream_path}.canonical_truth.latest_receipts.key")
            require_str(
                receipt_id,
                f"{workstream_path}.canonical_truth.latest_receipts[{capability}]",
            )


def validate_merge_eligible_files_contract() -> None:
    validate_merge_eligible_catalog(MERGE_ELIGIBLE_FILES_PATH)


def validate_triage_rule_contracts() -> None:
    import incident_triage

    rules = incident_triage.load_triage_rules(TRIAGE_RULES_PATH)
    allowlist = incident_triage.load_auto_check_allowlist(TRIAGE_AUTO_CHECK_ALLOWLIST_PATH)
    if not allowlist:
        raise ValueError("config/triage-auto-check-allowlist.yaml must not be empty")
    for index, rule in enumerate(rules["rules"]):
        if not rule["auto_check"]:
            continue
        check_types = [
            check["type"]
            for check in rule["discriminating_checks"]
            if isinstance(check, dict) and isinstance(check.get("type"), str)
        ]
        if not check_types:
            raise ValueError(f"config/triage-rules.yaml.rules[{index}] auto_check rule must define at least one check type")
        if check_types[0] not in allowlist:
            raise ValueError(
                f"config/triage-rules.yaml.rules[{index}] first auto_check type '{check_types[0]}' must be allowlisted"
            )


def validate_changelog_redaction_contract() -> None:
    validate_redaction_policy(load_redaction_policy(CHANGELOG_REDACTION_PATH), path=CHANGELOG_REDACTION_PATH)

def validate_agent_policies(workflow_catalog: dict[str, Any]) -> None:
    payload = load_yaml(AGENT_POLICIES_PATH)
    if not isinstance(payload, list) or not payload:
        raise ValueError(f"{AGENT_POLICIES_PATH} must define a non-empty list")
    workflows = workflow_catalog.get("workflows")
    if not isinstance(workflows, dict):
        raise ValueError("workflow catalog must define a workflows object before agent policies are validated")
    allowed_surfaces = {
        "health_probes",
        "ledger",
        "loki_logs",
        "maintenance_windows",
        "netbox",
        "opentofu_state",
        "search",
        "world_state",
    }
    seen_ids: set[str] = set()
    for index, item in enumerate(payload):
        path = f"{AGENT_POLICIES_PATH}[{index}]"
        entry = require_mapping(item, path)
        agent_id = require_str(entry.get("agent_id"), f"{path}.agent_id")
        if agent_id in seen_ids:
            raise ValueError(f"{path}.agent_id duplicates '{agent_id}'")
        seen_ids.add(agent_id)
        require_str(entry.get("description"), f"{path}.description")
        identity_class = require_enum(entry.get("identity_class"), f"{path}.identity_class", AGENT_POLICY_IDENTITY_CLASSES)
        trust_tier = require_enum(entry.get("trust_tier"), f"{path}.trust_tier", TRUST_TIERS)
        read_surfaces = require_string_list(entry.get("read_surfaces"), f"{path}.read_surfaces")
        unknown_surfaces = sorted(set(read_surfaces) - allowed_surfaces)
        if unknown_surfaces:
            raise ValueError(f"{path}.read_surfaces references unknown surfaces: {', '.join(unknown_surfaces)}")

        autonomous_actions = require_mapping(entry.get("autonomous_actions"), f"{path}.autonomous_actions")
        require_enum(
            autonomous_actions.get("max_risk_class"),
            f"{path}.autonomous_actions.max_risk_class",
            {"LOW", "MEDIUM", "HIGH", "CRITICAL"},
        )
        allowed_tags = require_string_list(
            autonomous_actions.get("allowed_workflow_tags"),
            f"{path}.autonomous_actions.allowed_workflow_tags",
        )
        for tag_index, tag in enumerate(allowed_tags):
            require_identifier(tag, f"{path}.autonomous_actions.allowed_workflow_tags[{tag_index}]")
        disallowed_workflow_ids = require_string_list(
            autonomous_actions.get("disallowed_workflow_ids"),
            f"{path}.autonomous_actions.disallowed_workflow_ids",
        )
        for workflow_id in disallowed_workflow_ids:
            if workflow_id not in workflows:
                raise ValueError(f"{path}.autonomous_actions.disallowed_workflow_ids references unknown workflow '{workflow_id}'")
        require_int(
            autonomous_actions.get("max_daily_autonomous_executions"),
            f"{path}.autonomous_actions.max_daily_autonomous_executions",
            0,
        )

        escalation = require_mapping(entry.get("escalation"), f"{path}.escalation")
        require_enum(escalation.get("on_risk_above"), f"{path}.escalation.on_risk_above", {"LOW", "MEDIUM", "HIGH", "CRITICAL"})
        require_str(escalation.get("escalation_target"), f"{path}.escalation.escalation_target")
        require_str(escalation.get("escalation_event"), f"{path}.escalation.escalation_event")

        if identity_class == "service-agent" and trust_tier == "T4":
            raise ValueError(f"{path}.trust_tier T4 is reserved for operator-agent identities")


def validate_identity_taxonomy(
    desired_state: dict[str, Any],
    observed_state: dict[str, Any],
) -> None:
    identity_taxonomy = require_mapping(
        desired_state.get("identity_taxonomy"), "versions/stack.yaml.desired_state.identity_taxonomy"
    )
    classes = require_mapping(
        identity_taxonomy.get("classes"), "versions/stack.yaml.desired_state.identity_taxonomy.classes"
    )
    if set(classes.keys()) != IDENTITY_CLASSES:
        raise ValueError(
            "versions/stack.yaml.desired_state.identity_taxonomy.classes must define exactly the four identity classes"
        )
    for class_name in sorted(IDENTITY_CLASSES):
        class_def = require_mapping(
            classes.get(class_name),
            f"versions/stack.yaml.desired_state.identity_taxonomy.classes.{class_name}",
        )
        require_str(
            class_def.get("description"),
            f"versions/stack.yaml.desired_state.identity_taxonomy.classes.{class_name}.description",
        )
        require_str(
            class_def.get("interactive_use"),
            f"versions/stack.yaml.desired_state.identity_taxonomy.classes.{class_name}.interactive_use",
        )
        require_str(
            class_def.get("automation_use"),
            f"versions/stack.yaml.desired_state.identity_taxonomy.classes.{class_name}.automation_use",
        )

    required_metadata = set(
        require_string_list(
            identity_taxonomy.get("required_metadata"),
            "versions/stack.yaml.desired_state.identity_taxonomy.required_metadata",
        )
    )
    if required_metadata != IDENTITY_REQUIRED_METADATA:
        raise ValueError(
            "versions/stack.yaml.desired_state.identity_taxonomy.required_metadata must match the ADR 0046 contract"
        )

    managed_identities = require_list(
        identity_taxonomy.get("managed_identities"),
        "versions/stack.yaml.desired_state.identity_taxonomy.managed_identities",
    )
    if not managed_identities:
        raise ValueError(
            "versions/stack.yaml.desired_state.identity_taxonomy.managed_identities must not be empty"
        )

    identity_ids: set[str] = set()
    principals: set[str] = set()
    classes_in_use: set[str] = set()
    shared_credential_material: set[str] = set()
    principal_classes: dict[str, str] = {}
    for index, identity in enumerate(managed_identities):
        path = f"versions/stack.yaml.desired_state.identity_taxonomy.managed_identities[{index}]"
        identity = require_mapping(identity, path)
        identity_id = require_identifier(identity.get("id"), f"{path}.id")
        identity_class = require_enum(identity.get("class"), f"{path}.class", IDENTITY_CLASSES)
        principal = require_str(identity.get("principal"), f"{path}.principal")
        require_str(identity.get("owner"), f"{path}.owner")
        require_str(identity.get("purpose"), f"{path}.purpose")
        require_str(identity.get("scope_boundary"), f"{path}.scope_boundary")
        require_str(identity.get("rotation_or_expiry"), f"{path}.rotation_or_expiry")
        require_str(identity.get("credential_storage"), f"{path}.credential_storage")
        require_bool(identity.get("shared_credential_material"), f"{path}.shared_credential_material")
        surfaces = require_string_list(identity.get("surfaces"), f"{path}.surfaces")
        if not surfaces:
            raise ValueError(f"{path}.surfaces must not be empty")
        if identity_id in identity_ids:
            raise ValueError(f"duplicate identity id in versions/stack.yaml: {identity_id}")
        if principal in principals:
            raise ValueError(f"duplicate identity principal in versions/stack.yaml: {principal}")
        identity_ids.add(identity_id)
        principals.add(principal)
        classes_in_use.add(identity_class)
        principal_classes[principal] = identity_class
        if identity["shared_credential_material"]:
            shared_credential_material.add(identity_id)

    if classes_in_use != IDENTITY_CLASSES:
        raise ValueError(
            "versions/stack.yaml.desired_state.identity_taxonomy.managed_identities must exercise all four identity classes"
        )

    if principal_classes.get("ops") != "human_operator":
        raise ValueError("identity principal 'ops' must be classified as a human_operator")
    if principal_classes.get("ops@pam") != "human_operator":
        raise ValueError("identity principal 'ops@pam' must be classified as a human_operator")
    if principal_classes.get("lv3-automation@pve") != "agent":
        raise ValueError("identity principal 'lv3-automation@pve' must be classified as an agent")
    if principal_classes.get("server@lv3.org") != "service":
        raise ValueError("identity principal 'server@lv3.org' must be classified as a service")
    if principal_classes.get("root") != "break_glass":
        raise ValueError("identity principal 'root' must be classified as break_glass")

    observed_identity_taxonomy = require_mapping(
        observed_state.get("identity_taxonomy"), "versions/stack.yaml.observed_state.identity_taxonomy"
    )
    require_date(
        observed_identity_taxonomy.get("reviewed_at"),
        "versions/stack.yaml.observed_state.identity_taxonomy.reviewed_at",
    )
    require_bool(
        observed_identity_taxonomy.get("all_identities_documented"),
        "versions/stack.yaml.observed_state.identity_taxonomy.all_identities_documented",
    )
    observed_classes = set(
        require_string_list(
            observed_identity_taxonomy.get("classes_in_use"),
            "versions/stack.yaml.observed_state.identity_taxonomy.classes_in_use",
        )
    )
    if observed_classes != classes_in_use:
        raise ValueError(
            "versions/stack.yaml.observed_state.identity_taxonomy.classes_in_use must match the desired managed identity classes"
        )

    reviewed_principals = set(
        require_string_list(
            observed_identity_taxonomy.get("reviewed_principals"),
            "versions/stack.yaml.observed_state.identity_taxonomy.reviewed_principals",
        )
    )
    if reviewed_principals != principals:
        raise ValueError(
            "versions/stack.yaml.observed_state.identity_taxonomy.reviewed_principals must match the desired identity principals"
        )

    reviewed_shared_credential_material = set(
        require_string_list(
            observed_identity_taxonomy.get("shared_credential_material"),
            "versions/stack.yaml.observed_state.identity_taxonomy.shared_credential_material",
        )
    )
    if reviewed_shared_credential_material != shared_credential_material:
        raise ValueError(
            "versions/stack.yaml.observed_state.identity_taxonomy.shared_credential_material must match the identities that share credential material"
        )

    automation_access = require_mapping(
        desired_state.get("automation_access"), "versions/stack.yaml.desired_state.automation_access"
    )
    if automation_access.get("proxmox_api_user") not in principals:
        raise ValueError(
            "versions/stack.yaml.desired_state.automation_access.proxmox_api_user must be declared in the identity taxonomy"
        )

    security = require_mapping(desired_state.get("security"), "versions/stack.yaml.desired_state.security")
    if security.get("proxmox_tfa_user") not in principals:
        raise ValueError(
            "versions/stack.yaml.desired_state.security.proxmox_tfa_user must be declared in the identity taxonomy"
        )

    mail = require_mapping(desired_state.get("mail"), "versions/stack.yaml.desired_state.mail")
    if mail.get("mailbox_address") not in principals:
        raise ValueError(
            "versions/stack.yaml.desired_state.mail.mailbox_address must be declared in the identity taxonomy"
        )

    proxmox_state = require_mapping(observed_state.get("proxmox"), "versions/stack.yaml.observed_state.proxmox")
    if proxmox_state.get("automation_api_user") not in principals:
        raise ValueError(
            "versions/stack.yaml.observed_state.proxmox.automation_api_user must be declared in the identity taxonomy"
        )

    mail_state = require_mapping(observed_state.get("mail"), "versions/stack.yaml.observed_state.mail")
    if mail_state.get("mailbox_address") not in principals:
        raise ValueError(
            "versions/stack.yaml.observed_state.mail.mailbox_address must be declared in the identity taxonomy"
        )


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
    validate_identity_taxonomy(desired_state, observed_state)

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


def validate_slo_catalog_assets() -> None:
    catalog = load_slo_catalog(SLO_CATALOG_PATH)
    for path in (
        SLO_CATALOG_PATH,
        PROMETHEUS_RULES_PATH,
        PROMETHEUS_ALERTS_PATH,
        PROMETHEUS_TARGETS_PATH,
        GRAFANA_DASHBOARD_PATH,
    ):
        if not path.exists():
            raise ValueError(f"missing SLO artifact: {path}")
    if not slo_outputs_match(catalog):
        raise ValueError("generated SLO artifacts are out of date")


def validate_repository_data_models() -> int:
    load_dependency_graph(validate_schema=True)
    secret_manifest = load_secret_manifest()
    validate_secret_manifest(secret_manifest)
    workflow_catalog = load_workflow_catalog()
    validate_workflow_catalog(workflow_catalog, secret_manifest)
    validate_agent_policies(workflow_catalog)
    command_catalog = load_command_catalog()
    validate_command_catalog(command_catalog, workflow_catalog, secret_manifest)
    validate_container_image_catalog(load_image_catalog())
    validate_error_registry()
    api_gateway_catalog, _ = load_api_gateway_catalog()
    validate_api_gateway_catalog(api_gateway_catalog)
    lane_catalog, _ = load_lane_catalog()
    load_execution_lane_catalog(repo_root=REPO_ROOT)
    api_publication_catalog, _, _ = load_api_publication_catalog()
    validate_api_publication_catalog(api_publication_catalog, lane_catalog)
    load_service_completeness_context()
    validate_mutation_audit_schema(load_mutation_audit_schema())
    validate_receipts()
    validate_promotion_receipts()
    validate_uptime_monitors()
    host_vars_context = validate_host_vars()
    validate_certificate_catalog(host_vars_context)
    validate_health_probe_catalog(host_vars_context)
    validate_data_catalog(load_data_catalog())
    validate_slo_catalog_assets()
    validate_secret_catalog(secret_manifest)
    token_classes = validate_token_policy()
    validate_token_inventory(token_classes, workflow_catalog)
    validate_circuit_policies()
    validate_version_semantics()
    validate_merge_eligible_files_contract()
    validate_workstreams_release_policy()
    validate_workstream_canonical_truth_metadata()
    validate_triage_rule_contracts()
    validate_changelog_redaction_contract()
    validate_platform_finding_schema()
    validate_maintenance_window_schema()
    validate_capacity_model_schema()
    validate_capacity_model()
    load_public_surface_scan_policy()
    validate_vm_template_manifest(host_vars_context["proxmox_vm_templates"])
    validate_operator_roster(load_yaml(ROSTER_PATH))
    validate_versions_stack(host_vars_context)
    validate_platform_vars()
    validate_no_tracked_env_files()
    validate_no_scaffold_placeholders()
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
    except (OSError, json.JSONDecodeError, ValueError, RuntimeError) as exc:
        return emit_cli_error("Repository data model", exc)


if __name__ == "__main__":
    sys.exit(main())
