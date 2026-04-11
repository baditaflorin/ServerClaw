#!/usr/bin/env python3
"""Provision and manage ephemeral Proxmox VM fixtures."""

from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import getpass
import ipaddress
import json
import math
import os
import re
import shlex
import shutil
import socket
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from urllib.parse import urlparse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import vmid_allocator
from mutation_audit import build_event, emit_event_best_effort
import seed_data_snapshots


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DEFINITIONS_DIR = REPO_ROOT / "tests" / "fixtures"
FIXTURE_RECEIPTS_DIR = REPO_ROOT / "receipts" / "fixtures"
FIXTURE_LOCAL_ROOT = REPO_ROOT / ".local" / "fixtures"
FIXTURE_REAPER_RUNS_DIR = FIXTURE_LOCAL_ROOT / "reaper-runs"
FIXTURE_RUNTIME_DIR = FIXTURE_LOCAL_ROOT / "runtime"
FIXTURE_ARCHIVE_DIR = FIXTURE_LOCAL_ROOT / "archive"
FIXTURE_LOCKS_DIR = FIXTURE_LOCAL_ROOT / "locks"
CONTROLLER_SECRETS_PATH = REPO_ROOT / "config" / "controller-local-secrets.json"
TEMPLATE_MANIFEST_PATH = REPO_ROOT / "config" / "vm-template-manifest.json"
GROUP_VARS_PATH = REPO_ROOT / "inventory" / "group_vars" / "all.yml"
HOST_VARS_PATH = REPO_ROOT / "inventory" / "host_vars" / "proxmox_florin.yml"
PROXMOX_ENV_KEYS = ("TF_VAR_proxmox_endpoint", "TF_VAR_proxmox_api_token")
TOFU_IMAGE = os.environ.get("TOFU_IMAGE", "registry.localhost/check-runner/infra:2026.03.23")
TOFU_PLATFORM = os.environ.get("TOFU_PLATFORM", "linux/amd64")
TOFU_DOCKER_NETWORK = os.environ.get("TOFU_DOCKER_NETWORK", "host")
CAPACITY_MODEL_PATH = REPO_ROOT / "config" / "capacity-model.json"
EPHEMERAL_POOL_CATALOG_PATH = REPO_ROOT / "config" / "ephemeral-capacity-pools.json"
DEFAULT_FIXTURE_PROFILE = "ops-base"
DEFAULT_EPHEMERAL_POLICY = "adr-development"
DEFAULT_UNTAGGED_GRACE_MINUTES = 60
EPHEMERAL_VMID_RANGE = (910, 979)
DEFAULT_WARM_OWNER = "pool-manager"
DEFAULT_WARM_PURPOSE = "pool-warm"
DEFAULT_LEASE_PURPOSE = "fixture"
LEASE_PURPOSES = {"fixture", "preview", "recovery-drill", "load-test"}
LEASE_PURPOSE_TO_PLACEMENT_CLASS = {
    "fixture": "fixture",
    "preview": "preview",
    "recovery-drill": "recovery",
    "load-test": "fixture",
}
EPHEMERAL_POLICY_LIMITS_MINUTES = {
    "restore-verification": 120,
    "integration-test": 60,
    "adr-development": 480,
    "extended-fixture": 1440,
}
EPHEMERAL_TAG_PREFIX = "ephemeral-"
EPHEMERAL_OWNER_PREFIX = "ephemeral-owner-"
EPHEMERAL_PURPOSE_PREFIX = "ephemeral-purpose-"
EPHEMERAL_EXPIRES_PREFIX = "ephemeral-expires-"
EPHEMERAL_POLICY_PREFIX = "ephemeral-policy-"
EPHEMERAL_POOL_PREFIX = "ephemeral-pool-"
EPHEMERAL_POOL_STATE_PREFIX = "ephemeral-pool-state-"
EPHEMERAL_LEASE_PURPOSE_PREFIX = "ephemeral-lease-purpose-"
PROXMOX_RESOURCE_TYPE = "qemu"


@dataclass
class CommandResult:
    argv: list[str]
    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class EphemeralTagMetadata:
    owner: str
    purpose: str
    expires_epoch: int
    policy: str


@dataclass(frozen=True)
class EphemeralPoolDefaults:
    max_local_active_leases: int
    protected_capacity_class: str
    spillover_domain: str
    warm_lifetime_minutes: int


@dataclass(frozen=True)
class EphemeralPoolConfig:
    pool_id: str
    fixture_id: str
    warm_count: int
    refill_target: int
    max_concurrent_leases: int
    allowed_lease_purposes: tuple[str, ...]
    allowed_placement_classes: tuple[str, ...]
    ip_addresses: tuple[str, ...]
    placement_domain: str
    spillover_domain: str
    protected_capacity_class: str
    warm_lifetime_minutes: int
    notes: str | None = None


class SpilloverRequiredError(RuntimeError):
    """Raised when local ephemeral capacity is exhausted and spillover is required."""

    def __init__(self, *, pool_id: str, spillover_domain: str, reason: str) -> None:
        super().__init__(f"Local pool '{pool_id}' is exhausted; spill over to '{spillover_domain}' ({reason})")
        self.pool_id = pool_id
        self.spillover_domain = spillover_domain
        self.reason = reason


def current_owner() -> str:
    return os.environ.get("LV3_EPHEMERAL_OWNER", "").strip() or getpass.getuser()


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def isoformat(value: dt.datetime) -> str:
    return value.astimezone(dt.UTC).isoformat().replace("+00:00", "Z")


def parse_timestamp(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def compact_timestamp(value: dt.datetime) -> str:
    return value.astimezone(dt.UTC).strftime("%Y%m%dT%H%M%SZ")


def sanitize_tag_component(value: str) -> str:
    candidate = re.sub(r"[^a-z0-9-]+", "-", value.lower()).strip("-")
    if not candidate:
        raise ValueError("Ephemeral owner and purpose must contain at least one alphanumeric character")
    return candidate


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_capacity_model() -> dict[str, Any]:
    payload = load_json(CAPACITY_MODEL_PATH)
    if not isinstance(payload, dict):
        raise ValueError(f"Capacity model must be a mapping: {CAPACITY_MODEL_PATH}")
    return payload


def load_ephemeral_pool() -> dict[str, Any]:
    payload = load_capacity_model()
    legacy_pool = payload.get("ephemeral_pool")
    if isinstance(legacy_pool, dict):
        vmid_range = legacy_pool.get("vmid_range")
        if (
            isinstance(vmid_range, list)
            and len(vmid_range) == 2
            and all(isinstance(value, int) for value in vmid_range)
        ):
            normalized_vmid_range = [int(value) for value in vmid_range]
        else:
            raise ValueError(f"{CAPACITY_MODEL_PATH} ephemeral_pool.vmid_range must be a two-item integer list")
        return {
            "vmid_range": normalized_vmid_range,
            "max_concurrent_vms": int(legacy_pool["max_concurrent_vms"]),
            "reserved_ram_gb": int(legacy_pool["reserved_ram_gb"]),
            "reserved_vcpu": int(legacy_pool["reserved_vcpu"]),
            "reserved_disk_gb": int(legacy_pool["reserved_disk_gb"]),
            "capacity_class": str(legacy_pool.get("capacity_class", "preview_burst")),
            "notes": str(legacy_pool.get("notes", "")),
        }

    reservations = payload.get("reservations")
    if not isinstance(reservations, list):
        raise ValueError(f"{CAPACITY_MODEL_PATH} must define reservations for the preview_burst pool")

    pool = next(
        (
            reservation
            for reservation in reservations
            if isinstance(reservation, dict) and reservation.get("kind") == "ephemeral_pool"
        ),
        None,
    )
    if not isinstance(pool, dict):
        raise ValueError(f"{CAPACITY_MODEL_PATH} must define one reservation with kind=ephemeral_pool")

    vmid_range = pool.get("vmid_range")
    reserved = pool.get("reserved")
    if not isinstance(vmid_range, dict) or not isinstance(reserved, dict):
        raise ValueError(
            f"{CAPACITY_MODEL_PATH} reservations.ephemeral_pool must define vmid_range and reserved mappings"
        )

    return {
        "vmid_range": [int(vmid_range["start"]), int(vmid_range["end"])],
        "max_concurrent_vms": int(pool["max_concurrent_vms"]),
        "reserved_ram_gb": int(reserved["ram_gb"]),
        "reserved_vcpu": int(reserved["vcpu"]),
        "reserved_disk_gb": int(reserved["disk_gb"]),
        "capacity_class": pool.get("capacity_class", "preview_burst"),
        "notes": pool.get("notes", ""),
    }


def load_ephemeral_pool_catalog() -> tuple[EphemeralPoolDefaults, dict[str, EphemeralPoolConfig]]:
    payload = load_json(EPHEMERAL_POOL_CATALOG_PATH)
    if not isinstance(payload, dict):
        raise ValueError(f"Ephemeral pool catalog must be a mapping: {EPHEMERAL_POOL_CATALOG_PATH}")
    defaults_payload = payload.get("defaults")
    if not isinstance(defaults_payload, dict):
        raise ValueError(f"{EPHEMERAL_POOL_CATALOG_PATH} must define defaults")
    defaults = EphemeralPoolDefaults(
        max_local_active_leases=int(defaults_payload.get("max_local_active_leases", 1)),
        protected_capacity_class=str(defaults_payload.get("protected_capacity_class", "ephemeral-burst-local")),
        spillover_domain=str(defaults_payload.get("spillover_domain", "auxiliary-cloud")),
        warm_lifetime_minutes=int(defaults_payload.get("warm_lifetime_minutes", 1440)),
    )
    pools_payload = payload.get("pools")
    if not isinstance(pools_payload, list):
        raise ValueError(f"{EPHEMERAL_POOL_CATALOG_PATH} must define a pools list")
    pools: dict[str, EphemeralPoolConfig] = {}
    fixture_ids: set[str] = set()
    for index, item in enumerate(pools_payload):
        if not isinstance(item, dict):
            raise ValueError(f"{EPHEMERAL_POOL_CATALOG_PATH} pools[{index}] must be a mapping")
        pool_id = str(item.get("id", "")).strip()
        fixture_id = str(item.get("fixture_id", "")).strip()
        if not pool_id or not fixture_id:
            raise ValueError(f"{EPHEMERAL_POOL_CATALOG_PATH} pools[{index}] must define id and fixture_id")
        if pool_id in pools:
            raise ValueError(f"Duplicate ephemeral pool id '{pool_id}'")
        if fixture_id in fixture_ids:
            raise ValueError(f"Duplicate ephemeral pool fixture_id '{fixture_id}'")
        allowed_lease_purposes = tuple(str(value) for value in item.get("allowed_lease_purposes", []))
        if not allowed_lease_purposes:
            raise ValueError(f"{EPHEMERAL_POOL_CATALOG_PATH} pools[{index}] must define allowed_lease_purposes")
        for purpose in allowed_lease_purposes:
            if purpose not in LEASE_PURPOSES:
                raise ValueError(f"Unsupported lease purpose '{purpose}' in pool '{pool_id}'")
        allowed_placement_classes = tuple(str(value) for value in item.get("allowed_placement_classes", []))
        if not allowed_placement_classes:
            raise ValueError(f"{EPHEMERAL_POOL_CATALOG_PATH} pools[{index}] must define allowed_placement_classes")
        ip_addresses = tuple(str(value) for value in item.get("ip_addresses", []))
        if not ip_addresses:
            raise ValueError(f"{EPHEMERAL_POOL_CATALOG_PATH} pools[{index}] must define ip_addresses")
        warm_count = int(item.get("warm_count", 0))
        refill_target = int(item.get("refill_target", warm_count))
        max_concurrent_leases = int(item.get("max_concurrent_leases", len(ip_addresses)))
        minimum_addresses = max(warm_count, refill_target, max_concurrent_leases + refill_target)
        if len(ip_addresses) < minimum_addresses:
            raise ValueError(
                f"Pool '{pool_id}' needs at least {minimum_addresses} ip_addresses for its warm and lease targets"
            )
        pools[pool_id] = EphemeralPoolConfig(
            pool_id=pool_id,
            fixture_id=fixture_id,
            warm_count=warm_count,
            refill_target=refill_target,
            max_concurrent_leases=max_concurrent_leases,
            allowed_lease_purposes=allowed_lease_purposes,
            allowed_placement_classes=allowed_placement_classes,
            ip_addresses=ip_addresses,
            placement_domain=str(item.get("placement_domain", "proxmox-local")),
            spillover_domain=str(item.get("spillover_domain", defaults.spillover_domain)),
            protected_capacity_class=str(item.get("protected_capacity_class", defaults.protected_capacity_class)),
            warm_lifetime_minutes=int(item.get("warm_lifetime_minutes", defaults.warm_lifetime_minutes)),
            notes=str(item.get("notes", "")).strip() or None,
        )
        fixture_ids.add(fixture_id)
    return defaults, pools


def load_fixture_definition(path: Path) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        try:
            import yaml
        except ModuleNotFoundError as exc:  # pragma: no cover - runtime guard
            raise RuntimeError("PyYAML is required for non-JSON fixture definitions.") from exc
        payload = yaml.safe_load(raw)
    if not isinstance(payload, dict):
        raise ValueError(f"Fixture definition must be a mapping: {path}")
    return payload


def resolve_fixture_path(fixture_name: str) -> Path:
    candidates = [
        FIXTURE_DEFINITIONS_DIR / f"{fixture_name}.yml",
        FIXTURE_DEFINITIONS_DIR / f"{fixture_name}-fixture.yml",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"Unknown fixture '{fixture_name}'")


def yaml_scalar(path: Path, key: str, default: str) -> str:
    pattern = re.compile(rf"^{re.escape(key)}:\s*(.+?)\s*$", flags=re.MULTILINE)
    match = pattern.search(path.read_text(encoding="utf-8"))
    if not match:
        return default
    return match.group(1).strip().strip("\"'")


def controller_secret_path(secret_id: str) -> Path:
    payload = load_json(CONTROLLER_SECRETS_PATH)
    return Path(payload["secrets"][secret_id]["path"])


def default_fixture_context() -> dict[str, str]:
    proxmox_node_name = yaml_scalar(
        HOST_VARS_PATH,
        "proxmox_node_name",
        yaml_scalar(HOST_VARS_PATH, "host_public_hostname", "proxmox_florin"),
    )
    jump_host = yaml_scalar(
        HOST_VARS_PATH,
        "management_tailscale_ipv4",
        yaml_scalar(HOST_VARS_PATH, "management_ipv4", "65.108.75.123"),
    )
    return {
        "node_name": proxmox_node_name,
        "template_node_name": proxmox_node_name,
        "datastore_id": yaml_scalar(GROUP_VARS_PATH, "proxmox_storage_id", "local"),
        "cloud_init_datastore_id": yaml_scalar(GROUP_VARS_PATH, "proxmox_snippets_storage_id", "local"),
        "ci_user": yaml_scalar(GROUP_VARS_PATH, "proxmox_guest_ci_user", "ops"),
        "nameserver": yaml_scalar(GROUP_VARS_PATH, "proxmox_guest_nameserver", "1.1.1.1"),
        "search_domain": yaml_scalar(GROUP_VARS_PATH, "proxmox_guest_searchdomain", "localhost"),
        "jump_user": yaml_scalar(GROUP_VARS_PATH, "proxmox_host_admin_user", "ops"),
        "jump_host": os.environ.get("LV3_PROXMOX_HOST_ADDR", "").strip() or jump_host,
    }


def bootstrap_private_key() -> Path:
    return controller_secret_path("bootstrap_ssh_private_key")


def bootstrap_public_key() -> str:
    private_key = bootstrap_private_key()
    public_key = Path(f"{private_key}.pub")
    if public_key.exists():
        return public_key.read_text(encoding="utf-8").strip()
    if private_key.exists():
        result = run_command(["ssh-keygen", "-y", "-f", str(private_key)])
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    raise FileNotFoundError(f"Missing public bootstrap key: {public_key}")


def proxmox_api_credentials() -> tuple[str, str]:
    endpoint = os.environ.get(PROXMOX_ENV_KEYS[0], "").strip()
    api_token = os.environ.get(PROXMOX_ENV_KEYS[1], "").strip()
    if endpoint and api_token:
        return endpoint, api_token
    return vmid_allocator.read_api_credentials()


def insecure_proxmox_ssl_context(endpoint: str) -> ssl.SSLContext | None:
    hostname = urllib.parse.urlparse(endpoint).hostname
    if not hostname:
        return None
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return None
    if address.is_loopback or not address.is_global:
        return ssl._create_unverified_context()
    return None


def template_vmid(template_name: str) -> int:
    manifest = load_json(TEMPLATE_MANIFEST_PATH)
    templates = manifest.get("templates", {})
    template = templates.get(template_name)
    if not isinstance(template, dict):
        raise KeyError(f"Unknown template '{template_name}' in {TEMPLATE_MANIFEST_PATH}")
    return int(template["vmid"])


def resolve_template_vmid(template_name: str, cluster_resources: list[dict[str, Any]]) -> int:
    manifest = load_json(TEMPLATE_MANIFEST_PATH)
    templates = manifest.get("templates", {})
    current_name = template_name
    available_vmids = {
        int(item["vmid"])
        for item in cluster_resources
        if str(item.get("vmid", "")).isdigit() and int(item.get("template", 0) or 0) == 1
    }
    visited: set[str] = set()
    while current_name and current_name not in visited:
        visited.add(current_name)
        template = templates.get(current_name)
        if not isinstance(template, dict):
            break
        vmid = int(template["vmid"])
        if vmid in available_vmids:
            return vmid
        source_template = str(template.get("source_template", "")).strip()
        if not source_template:
            break
        current_name = source_template
    return template_vmid(template_name)


def parse_ip_cidr(value: str) -> tuple[str, int]:
    ip_text, separator, cidr_text = value.partition("/")
    if separator != "/" or not cidr_text.isdigit():
        raise ValueError(f"Expected ip/cidr, got '{value}'")
    return ip_text, int(cidr_text)


def split_tag_text(value: str | list[str] | None) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if not value:
        return []
    return [item.strip() for item in re.split(r"[;,]", value) if item.strip()]


def build_ephemeral_tag_metadata(
    *,
    owner: str,
    purpose: str,
    expires_epoch: int,
    policy: str,
) -> EphemeralTagMetadata:
    normalized_policy = sanitize_tag_component(policy)
    if normalized_policy not in EPHEMERAL_POLICY_LIMITS_MINUTES:
        raise ValueError(f"Unknown ephemeral policy '{policy}'")
    return EphemeralTagMetadata(
        owner=sanitize_tag_component(owner),
        purpose=sanitize_tag_component(purpose),
        expires_epoch=expires_epoch,
        policy=normalized_policy,
    )


def build_ephemeral_tags(metadata: EphemeralTagMetadata) -> list[str]:
    composite = f"{EPHEMERAL_TAG_PREFIX}{metadata.owner}-{metadata.purpose}-{metadata.expires_epoch}"
    return [
        composite,
        EPHEMERAL_OWNER_PREFIX + metadata.owner,
        EPHEMERAL_PURPOSE_PREFIX + metadata.purpose,
        EPHEMERAL_EXPIRES_PREFIX + str(metadata.expires_epoch),
        EPHEMERAL_POLICY_PREFIX + metadata.policy,
        "ephemeral",
    ]


def parse_ephemeral_tags(tags: str | list[str] | None) -> EphemeralTagMetadata | None:
    parsed_tags = split_tag_text(tags)
    owner = ""
    purpose = ""
    expires_epoch: int | None = None
    policy = DEFAULT_EPHEMERAL_POLICY
    for tag in parsed_tags:
        if tag.startswith(EPHEMERAL_OWNER_PREFIX):
            owner = tag.removeprefix(EPHEMERAL_OWNER_PREFIX)
        elif tag.startswith(EPHEMERAL_PURPOSE_PREFIX):
            purpose = tag.removeprefix(EPHEMERAL_PURPOSE_PREFIX)
        elif tag.startswith(EPHEMERAL_EXPIRES_PREFIX):
            value = tag.removeprefix(EPHEMERAL_EXPIRES_PREFIX)
            if value.isdigit():
                expires_epoch = int(value)
        elif tag.startswith(EPHEMERAL_POLICY_PREFIX):
            policy = tag.removeprefix(EPHEMERAL_POLICY_PREFIX)
    if owner and purpose and expires_epoch is not None:
        return build_ephemeral_tag_metadata(
            owner=owner,
            purpose=purpose,
            expires_epoch=expires_epoch,
            policy=policy or DEFAULT_EPHEMERAL_POLICY,
        )

    for tag in parsed_tags:
        if not tag.startswith(EPHEMERAL_TAG_PREFIX):
            continue
        match = re.match(r"^ephemeral-(?P<owner>[a-z0-9-]+)-(?P<purpose>[a-z0-9-]+)-(?P<expires>\d+)$", tag)
        if not match:
            continue
        return build_ephemeral_tag_metadata(
            owner=match.group("owner"),
            purpose=match.group("purpose"),
            expires_epoch=int(match.group("expires")),
            policy=policy or DEFAULT_EPHEMERAL_POLICY,
        )
    return None


def receipt_pool_tags(receipt: dict[str, Any]) -> list[str]:
    tags: list[str] = []
    pool_id = str(receipt.get("pool_id") or "").strip()
    pool_state = str(receipt.get("pool_state") or "").strip()
    lease_purpose = str(receipt.get("lease_purpose") or "").strip()
    if pool_id:
        tags.append(EPHEMERAL_POOL_PREFIX + sanitize_tag_component(pool_id))
    if pool_state:
        tags.append(EPHEMERAL_POOL_STATE_PREFIX + sanitize_tag_component(pool_state))
    if lease_purpose:
        tags.append(EPHEMERAL_LEASE_PURPOSE_PREFIX + sanitize_tag_component(lease_purpose))
    return tags


def refresh_receipt_tags(receipt: dict[str, Any]) -> None:
    metadata = build_ephemeral_tag_metadata(
        owner=str(receipt.get("owner") or current_owner()),
        purpose=str(receipt.get("purpose") or "fixture"),
        expires_epoch=int(receipt.get("expires_epoch") or expiry_for_receipt(receipt).timestamp()),
        policy=str(receipt.get("policy") or DEFAULT_EPHEMERAL_POLICY),
    )
    receipt["owner"] = metadata.owner
    receipt["purpose"] = metadata.purpose
    receipt["policy"] = metadata.policy
    receipt["expires_epoch"] = metadata.expires_epoch
    receipt["ephemeral_tags"] = list(dict.fromkeys([*build_ephemeral_tags(metadata), *receipt_pool_tags(receipt)]))


def mac_from_vmid(vmid: int) -> str:
    octets = [0xBC, 0x24, 0x11, (vmid >> 16) & 0xFF, (vmid >> 8) & 0xFF, vmid & 0xFF]
    return ":".join(f"{octet:02X}" for octet in octets)


def receipt_path(receipt_id: str) -> Path:
    return FIXTURE_RECEIPTS_DIR / f"{receipt_id}.json"


def list_receipt_paths() -> list[Path]:
    if not FIXTURE_RECEIPTS_DIR.exists():
        return []
    return sorted(path for path in FIXTURE_RECEIPTS_DIR.glob("*.json") if not path.name.startswith("reaper-run-"))


def load_receipt(path: Path) -> dict[str, Any]:
    payload = load_json(path)
    if not isinstance(payload, dict):
        raise ValueError(f"Invalid receipt payload: {path}")
    payload.setdefault("receipt_path", str(path))
    return payload


def managed_receipts(
    fixture_name: str | None = None,
    *,
    statuses: set[str] | None = None,
) -> list[dict[str, Any]]:
    receipts = []
    for path in list_receipt_paths():
        payload = load_receipt(path)
        if statuses is not None and payload.get("status") not in statuses:
            continue
        if fixture_name and payload.get("fixture_id") != fixture_name:
            continue
        receipts.append(payload)
    return sorted(receipts, key=lambda item: item["created_at"])


def active_receipts(fixture_name: str | None = None) -> list[dict[str, Any]]:
    return managed_receipts(fixture_name, statuses={"provisioning", "active"})


def nonfinal_receipts(fixture_name: str | None = None) -> list[dict[str, Any]]:
    return managed_receipts(fixture_name, statuses={"provisioning", "active", "prewarming", "prewarmed"})


def prewarmed_receipts(pool_id: str | None = None) -> list[dict[str, Any]]:
    receipts = managed_receipts(statuses={"prewarming", "prewarmed"})
    if pool_id:
        receipts = [receipt for receipt in receipts if receipt.get("pool_id") == pool_id]
    return receipts


def format_duration(delta: dt.timedelta) -> str:
    seconds = int(delta.total_seconds())
    sign = "-" if seconds < 0 else ""
    seconds = abs(seconds)
    hours, remainder = divmod(seconds, 3600)
    minutes, _ = divmod(remainder, 60)
    if hours:
        return f"{sign}{hours}h{minutes:02d}m"
    return f"{sign}{minutes}m"


def placement_class_for_lease_purpose(lease_purpose: str) -> str:
    if lease_purpose not in LEASE_PURPOSE_TO_PLACEMENT_CLASS:
        raise ValueError(f"Unsupported lease purpose '{lease_purpose}'")
    return LEASE_PURPOSE_TO_PLACEMENT_CLASS[lease_purpose]


def pool_for_fixture(fixture_id: str) -> tuple[EphemeralPoolDefaults, EphemeralPoolConfig | None]:
    defaults, pools = load_ephemeral_pool_catalog()
    for pool in pools.values():
        if pool.fixture_id == fixture_id:
            return defaults, pool
    return defaults, None


def select_pool_ip_address(pool: EphemeralPoolConfig, *, exclude_receipt_id: str | None = None) -> str:
    used_addresses = {
        str(receipt.get("definition", {}).get("network", {}).get("ip_cidr", "")).strip()
        for receipt in nonfinal_receipts()
        if receipt.get("receipt_id") != exclude_receipt_id
    }
    for candidate in pool.ip_addresses:
        if candidate not in used_addresses:
            return candidate
    raise SpilloverRequiredError(
        pool_id=pool.pool_id,
        spillover_domain=pool.spillover_domain,
        reason="no free local pool addresses remain",
    )


def apply_pool_member_definition(
    definition: dict[str, Any], pool: EphemeralPoolConfig, *, ip_cidr: str
) -> dict[str, Any]:
    updated = json.loads(json.dumps(definition))
    updated.setdefault("network", {})
    updated["network"]["ip_cidr"] = ip_cidr
    return updated


def active_local_leases() -> list[dict[str, Any]]:
    return active_receipts()


def active_pool_leases(pool_id: str) -> list[dict[str, Any]]:
    return [receipt for receipt in active_local_leases() if receipt.get("pool_id") == pool_id]


def pool_refill_target(pool: EphemeralPoolConfig) -> int:
    return max(pool.warm_count, pool.refill_target)


def available_prewarmed_receipt(pool_id: str) -> dict[str, Any] | None:
    candidates = [receipt for receipt in prewarmed_receipts(pool_id) if receipt.get("status") == "prewarmed"]
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: item["created_at"])[0]


def expiry_for_receipt(receipt: dict[str, Any]) -> dt.datetime:
    expires_at = receipt.get("expires_at")
    if isinstance(expires_at, str) and expires_at:
        return parse_timestamp(expires_at)
    created_at = parse_timestamp(receipt["created_at"])
    minutes = int(receipt.get("lifetime_minutes", 0)) + int(receipt.get("extend_minutes", 0))
    return created_at + dt.timedelta(minutes=minutes)


def tofu_module_source_path() -> str:
    if shutil.which("tofu"):
        return str(REPO_ROOT / "tofu" / "modules" / "proxmox-fixture")
    return "./modules/proxmox-fixture"


def build_runtime_main(receipt: dict[str, Any]) -> str:
    definition = receipt["definition"]
    fixture_context = receipt["context"]
    network_ip, network_cidr = parse_ip_cidr(definition["network"]["ip_cidr"])
    tags = list(
        dict.fromkeys(
            [
                *definition.get("tags", []),
                *receipt.get("ephemeral_tags", []),
                receipt["receipt_id"],
            ]
        )
    )
    module_path = tofu_module_source_path()
    assignments = {
        "name": f"{definition['fixture_id']}-{receipt['vm_id']}",
        "description": f"ephemeral fixture {definition['fixture_id']}",
        "node_name": fixture_context["node_name"],
        "vm_id": receipt["vm_id"],
        "template_node_name": fixture_context["template_node_name"],
        "template_vmid": int(definition.get("template_vmid") or template_vmid(definition["template"])),
        "datastore_id": fixture_context["datastore_id"],
        "cloud_init_datastore_id": fixture_context["cloud_init_datastore_id"],
        "cores": definition["resources"]["cores"],
        "memory_mb": definition["resources"]["memory_mb"],
        "disk_gb": definition["resources"]["disk_gb"],
        "bridge": definition["network"]["bridge"],
        "mac_address": receipt["mac_address"],
        "ip_address": network_ip,
        "ip_cidr": network_cidr,
        "gateway": definition["network"]["gateway"],
        "nameserver": definition.get("nameserver", fixture_context["nameserver"]),
        "search_domain": definition.get("search_domain", fixture_context["search_domain"]),
        "tags": tags,
        "ci_user": definition.get("ssh_user", fixture_context["ci_user"]),
        "ssh_authorized_keys": [bootstrap_public_key()],
        "agent_enabled": False,
        "agent_timeout": "10s",
        "network_firewall": False,
        "protection": False,
    }
    lines = [
        "terraform {",
        '  required_version = ">= 1.10.0"',
        "  required_providers {",
        "    proxmox = {",
        '      source  = "bpg/proxmox"',
        '      version = "= 0.99.0"',
        "    }",
        "  }",
        "}",
        "",
        'variable "proxmox_endpoint" {',
        "  type      = string",
        "  sensitive = true",
        "}",
        "",
        'variable "proxmox_api_token" {',
        "  type      = string",
        "  sensitive = true",
        "}",
        "",
        'provider "proxmox" {',
        "  endpoint  = var.proxmox_endpoint",
        "  api_token = var.proxmox_api_token",
        "  insecure  = true",
        "}",
        "",
        'module "fixture" {',
        f"  source = {json.dumps(str(module_path))}",
    ]
    for key, value in assignments.items():
        lines.append(f"  {key} = {json.dumps(value)}")
    lines.extend(
        [
            "}",
            "",
            'output "vm_id" {',
            "  value = module.fixture.vm_id",
            "}",
            "",
            'output "ip_address" {',
            f'  value = "{network_ip}"',
            "}",
        ]
    )
    return "\n".join(lines) + "\n"


def ensure_runtime_files(receipt: dict[str, Any]) -> Path:
    runtime_dir = REPO_ROOT / receipt["runtime_dir"]
    runtime_dir.mkdir(parents=True, exist_ok=True)
    if not shutil.which("tofu"):
        shutil.copytree(REPO_ROOT / "tofu" / "modules", runtime_dir / "modules", dirs_exist_ok=True)
    (runtime_dir / "main.tf").write_text(build_runtime_main(receipt), encoding="utf-8")
    return runtime_dir


def run_command(argv: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None) -> CommandResult:
    completed = subprocess.run(
        argv,
        cwd=str(cwd) if cwd else None,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    return CommandResult(
        argv=argv,
        returncode=completed.returncode,
        stdout=completed.stdout.strip(),
        stderr=completed.stderr.strip(),
    )


def ensure_command(result: CommandResult, action: str) -> None:
    if result.returncode == 0:
        return
    message = result.stderr or result.stdout or f"{action} failed"
    raise RuntimeError(f"{action}: {message}")


def ensure_ephemeral_lifetime_minutes(
    *,
    lifetime_hours: float | None,
    definition: dict[str, Any],
    policy: str,
    extend: bool,
) -> int:
    if policy not in EPHEMERAL_POLICY_LIMITS_MINUTES:
        raise ValueError(f"Unsupported ephemeral policy '{policy}'")
    if policy == "extended-fixture" and not extend:
        raise ValueError("Extended ephemeral fixtures require the explicit --extend flag")
    minutes = (
        int(round(lifetime_hours * 60)) if lifetime_hours is not None else int(definition.get("lifetime_minutes", 60))
    )
    if minutes <= 0:
        raise ValueError("Ephemeral fixture lifetime must be positive")
    maximum = EPHEMERAL_POLICY_LIMITS_MINUTES[policy]
    if minutes > maximum:
        raise ValueError(f"Ephemeral policy '{policy}' may not exceed {maximum // 60} hours")
    hard_limit = EPHEMERAL_POLICY_LIMITS_MINUTES["extended-fixture"]
    if minutes > hard_limit:
        raise ValueError(f"Ephemeral fixtures may not exceed {hard_limit // 60} hours")
    return minutes


def proxmox_api_request(
    endpoint: str,
    api_token: str,
    path: str,
    *,
    method: str = "GET",
    params: dict[str, Any] | None = None,
) -> Any:
    url = endpoint.rstrip("/") + path
    headers = {"Authorization": f"PVEAPIToken={api_token}"}
    data = None
    parsed = urlparse(endpoint)
    context = None
    try:
        ipaddress.ip_address(parsed.hostname or "")
        context = ssl._create_unverified_context()
    except ValueError:
        context = None
    if method in {"POST", "PUT"} and params:
        data = urllib.parse.urlencode(params).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    elif method == "DELETE" and params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    if context is None:
        context = insecure_proxmox_ssl_context(endpoint)
    if context is None and vmid_allocator.proxmox_api_insecure(endpoint):
        context = ssl._create_unverified_context()
    with urllib.request.urlopen(request, timeout=10, context=context) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload.get("data")


def fetch_cluster_resources(endpoint: str, api_token: str) -> list[dict[str, Any]]:
    payload = proxmox_api_request(endpoint, api_token, "/cluster/resources?type=vm")
    if not isinstance(payload, list):
        raise ValueError("Proxmox cluster resources response must be a list")
    return [item for item in payload if isinstance(item, dict)]


def is_ephemeral_vmid(vmid: int) -> bool:
    start, end = EPHEMERAL_VMID_RANGE
    return start <= vmid <= end


def filter_ephemeral_cluster_vms(resources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    filtered = []
    for item in resources:
        vmid = item.get("vmid")
        if isinstance(vmid, str) and vmid.isdigit():
            vmid = int(vmid)
        if not isinstance(vmid, int) or not is_ephemeral_vmid(vmid):
            continue
        if item.get("type", PROXMOX_RESOURCE_TYPE) != PROXMOX_RESOURCE_TYPE:
            continue
        filtered.append(item)
    return sorted(filtered, key=lambda item: int(item["vmid"]))


def find_receipt_by_vmid(vmid: int) -> dict[str, Any] | None:
    for receipt in nonfinal_receipts():
        if int(receipt.get("vm_id", -1)) == vmid:
            return receipt
    return None


def bytes_to_gb(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0
    if value <= 0:
        return 0
    return math.ceil(float(value) / (1024**3))


def emit_ephemeral_event(action: str, target: str, *, actor_id: str, evidence_ref: str = "") -> None:
    emit_event_best_effort(
        build_event(
            actor_class="automation",
            actor_id=actor_id,
            surface="manual",
            action=action,
            target=target,
            outcome="success",
            evidence_ref=evidence_ref,
        ),
        context=action,
        stderr=sys.stderr,
    )


def ensure_ephemeral_pool_capacity(definition: dict[str, Any], cluster_resources: list[dict[str, Any]]) -> None:
    pool = load_ephemeral_pool()
    if pool.get("capacity_class") not in {None, "preview_burst"}:
        raise ValueError("ephemeral_pool must map to the preview_burst capacity class")
    pool_range = tuple(int(value) for value in pool.get("vmid_range", EPHEMERAL_VMID_RANGE))
    if tuple(int(value) for value in definition["vmid_range"]) != pool_range:
        return

    active = filter_ephemeral_cluster_vms(cluster_resources)
    active_leases = [
        resource
        for resource in active
        if (receipt := find_receipt_by_vmid(int(resource["vmid"]))) is None
        or receipt.get("status") not in {"prewarming", "prewarmed"}
    ]
    if len(active_leases) >= int(pool["max_concurrent_vms"]):
        raise RuntimeError("preview_burst capacity exhausted: max_concurrent_vms reached")

    proposed = definition.get("resources")
    if not isinstance(proposed, dict):
        raise ValueError("fixture definition resources must be a mapping")
    proposed_ram_gb = math.ceil(int(proposed["memory_mb"]) / 1024)
    proposed_vcpu = int(proposed["cores"])
    proposed_disk_gb = int(proposed["disk_gb"])

    used_ram_gb = 0
    used_vcpu = 0
    used_disk_gb = 0
    for item in active:
        receipt = find_receipt_by_vmid(int(item["vmid"]))
        if receipt is None or receipt.get("status") not in {"prewarming", "prewarmed"}:
            used_ram_gb += bytes_to_gb(item.get("maxmem"))
            used_vcpu += int(item.get("cpus", 0) or 0)
        used_disk_gb += bytes_to_gb(item.get("maxdisk"))

    if used_ram_gb + proposed_ram_gb > int(pool["reserved_ram_gb"]):
        raise RuntimeError("preview_burst capacity exhausted: reserved RAM budget exceeded")
    if used_vcpu + proposed_vcpu > int(pool["reserved_vcpu"]):
        raise RuntimeError("preview_burst capacity exhausted: reserved vCPU budget exceeded")
    if used_disk_gb + proposed_disk_gb > int(pool["reserved_disk_gb"]):
        raise RuntimeError("preview_burst capacity exhausted: reserved disk budget exceeded")


def tofu_command(runtime_dir: Path, *args: str, env: dict[str, str] | None = None) -> list[str]:
    if shutil.which("tofu"):
        return ["tofu", *args]
    if not shutil.which("docker"):
        raise RuntimeError("Missing both 'tofu' and 'docker' required for fixture provisioning")
    command = [
        "docker",
        "run",
        "--rm",
        "--platform",
        TOFU_PLATFORM,
        "-e",
        "TF_VAR_proxmox_endpoint",
        "-e",
        "TF_VAR_proxmox_api_token",
        "-v",
        f"{REPO_ROOT}:/workspace",
        "-v",
        f"{REPO_ROOT}:{REPO_ROOT}",
        "-v",
        f"{runtime_dir}:/runtime",
        "-w",
        "/runtime",
    ]
    effective_env = env or os.environ
    for key in PROXMOX_ENV_KEYS:
        value = effective_env.get(key, "").strip()
        if value:
            command.extend(["-e", f"{key}={value}"])
    if TOFU_DOCKER_NETWORK:
        command.extend(["--network", TOFU_DOCKER_NETWORK])
    command.extend([TOFU_IMAGE, "tofu", *args])
    return command


def tofu_endpoint(endpoint: str) -> str:
    if shutil.which("tofu"):
        return endpoint
    parsed = urllib.parse.urlsplit(endpoint)
    if parsed.hostname not in {"127.0.0.1", "localhost"}:
        return endpoint
    port = f":{parsed.port}" if parsed.port else ""
    rewritten = parsed._replace(netloc=f"host.docker.internal{port}")
    return urllib.parse.urlunsplit(rewritten)


def proxmox_host_ssh_argv(receipt: dict[str, Any], remote_command: str, *, timeout_seconds: int = 60) -> list[str]:
    key_path = bootstrap_private_key()
    jump_user = receipt["context"]["jump_user"]
    jump_host = receipt["context"]["jump_host"]
    return [
        "ssh",
        "-i",
        str(key_path),
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "BatchMode=yes",
        "-o",
        f"ConnectTimeout={timeout_seconds}",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        "UserKnownHostsFile=/dev/null",
        f"{jump_user}@{jump_host}",
        remote_command,
    ]


def run_proxmox_host_command(receipt: dict[str, Any], script: str, *, timeout_seconds: int = 300) -> None:
    result = run_command(proxmox_host_ssh_argv(receipt, script, timeout_seconds=timeout_seconds))
    ensure_command(result, "proxmox host command")


def apply_fixture(runtime_dir: Path, endpoint: str, api_token: str, *, receipt: dict[str, Any] | None = None) -> None:
    if receipt is None:
        raise ValueError("apply_fixture requires the fixture receipt")

    definition = receipt["definition"]
    context = receipt["context"]
    resources = definition["resources"]
    network = definition["network"]
    name = f"{definition['fixture_id']}-{receipt['vm_id']}"
    tags = ";".join(str(tag) for tag in receipt["ephemeral_tags"] + definition.get("tags", []) + [name])
    description = f"ephemeral fixture {definition['fixture_id']}"
    net0 = f"virtio={receipt['mac_address']},bridge={network['bridge']},firewall=0"
    ipconfig0 = f"ip={network['ip_cidr']},gw={network['gateway']}"
    ssh_key = bootstrap_public_key()
    template_id = template_vmid(definition["template"])
    ci_user = definition.get("ssh_user", context["ci_user"])

    script = "\n".join(
        [
            "set -euo pipefail",
            f"tmpfile=$(mktemp /tmp/lv3-fixture-{receipt['vm_id']}-keys.XXXXXX)",
            'cleanup() { rm -f "$tmpfile"; }',
            "trap cleanup EXIT",
            "cat >\"$tmpfile\" <<'EOF'",
            ssh_key,
            "EOF",
            (
                "sudo qm clone "
                f"{template_id} {receipt['vm_id']} "
                f"--name {shlex.quote(name)} "
                "--full 1 "
                f"--target {shlex.quote(context['node_name'])} "
                f"--storage {shlex.quote(context['datastore_id'])}"
            ),
            (
                "sudo qm set "
                f"{receipt['vm_id']} "
                f"--description {shlex.quote(description)} "
                f"--cores {int(resources['cores'])} "
                f"--memory {int(resources['memory_mb'])} "
                "--scsihw virtio-scsi-single "
                "--onboot 1 "
                "--agent enabled=0 "
                f"--nameserver {shlex.quote(context['nameserver'])} "
                f"--searchdomain {shlex.quote(context['search_domain'])} "
                f"--ciuser {shlex.quote(ci_user)} "
                f"--ipconfig0 {shlex.quote(ipconfig0)} "
                f"--net0 {shlex.quote(net0)} "
                f"--tags {shlex.quote(tags)} "
                '--sshkeys "$tmpfile"'
            ),
            f"sudo qm resize {receipt['vm_id']} scsi0 {int(resources['disk_gb'])}G",
            f"sudo qm cloudinit update {receipt['vm_id']}",
            f"sudo qm start {receipt['vm_id']}",
        ]
    )
    run_proxmox_host_command(receipt, script, timeout_seconds=300)


def destroy_fixture(runtime_dir: Path, endpoint: str, api_token: str, *, receipt: dict[str, Any] | None = None) -> None:
    if receipt is None:
        raise ValueError("destroy_fixture requires the fixture receipt")
    script = "\n".join(
        [
            "set -euo pipefail",
            f"sudo qm stop {receipt['vm_id']} >/dev/null 2>&1 || true",
            f"sudo qm destroy {receipt['vm_id']} --destroy-unreferenced-disks 1 --purge 1 || true",
        ]
    )
    run_proxmox_host_command(receipt, script, timeout_seconds=300)


def ssh_base_argv(receipt: dict[str, Any], *, timeout_seconds: int = 5) -> list[str]:
    key_path = bootstrap_private_key()
    jump_user = receipt["context"]["jump_user"]
    jump_host = receipt["context"]["jump_host"]
    ssh_user = receipt["definition"].get("ssh_user", receipt["context"]["ci_user"])
    proxy = (
        f"ssh -i {key_path} -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=5 {jump_user}@{jump_host} -W %h:%p"
    )
    return [
        "ssh",
        "-i",
        str(key_path),
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "BatchMode=yes",
        "-o",
        f"ConnectTimeout={timeout_seconds}",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        "UserKnownHostsFile=/dev/null",
        "-o",
        f"ProxyCommand={proxy}",
        f"{ssh_user}@{receipt['ip_address']}",
    ]


def ssh_argv(receipt: dict[str, Any], remote_command: str, *, timeout_seconds: int = 5) -> list[str]:
    return [*ssh_base_argv(receipt, timeout_seconds=timeout_seconds), remote_command]


def wait_for_ssh(receipt: dict[str, Any], timeout_seconds: int = 300) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        result = run_command(ssh_argv(receipt, "true"))
        if result.returncode == 0:
            return
        time.sleep(5)
    raise RuntimeError(f"SSH did not become ready for fixture {receipt['receipt_id']}")


def wait_for_cloud_init(receipt: dict[str, Any], timeout_seconds: int = 120) -> None:
    deadline = time.monotonic() + timeout_seconds
    lock_check = "sudo fuser /var/lib/apt/lists/lock /var/lib/dpkg/lock-frontend >/dev/null 2>&1"
    while time.monotonic() < deadline:
        status = run_command(ssh_argv(receipt, "cloud-init status || true", timeout_seconds=10))
        locks = run_command(ssh_argv(receipt, lock_check, timeout_seconds=10))
        if locks.returncode != 0:
            return
        if "status: done" in status.stdout:
            return
        time.sleep(5)

    # Ephemeral previews hand package management to Ansible after boot. If cloud-init's
    # first-boot apt update is still holding the lock past the grace window, terminate it
    # so the governed converge step can continue.
    run_command(
        ssh_argv(
            receipt,
            "sudo pkill -TERM apt-get >/dev/null 2>&1 || true; sudo pkill -TERM apt >/dev/null 2>&1 || true",
            timeout_seconds=10,
        )
    )
    unlock_deadline = time.monotonic() + 30
    while time.monotonic() < unlock_deadline:
        locks = run_command(ssh_argv(receipt, lock_check, timeout_seconds=10))
        if locks.returncode != 0:
            return
        time.sleep(2)
    raise RuntimeError("cloud-init left apt locked after the preview grace window")


def prepare_guest_for_converge(receipt: dict[str, Any]) -> None:
    script = "\n".join(
        [
            "set -euo pipefail",
            "sudo install -d -m 0755 /etc/apt/apt.conf.d",
            "printf 'Acquire::ForceIPv4 \"true\";\\n' | sudo tee /etc/apt/apt.conf.d/99-lv3-force-ipv4 >/dev/null",
        ]
    )
    ensure_command(run_command(ssh_argv(receipt, script, timeout_seconds=10)), "prepare guest for converge")


def ansible_inventory(receipt: dict[str, Any]) -> dict[str, Any]:
    key_path = bootstrap_private_key()
    jump_user = receipt["context"]["jump_user"]
    jump_host = receipt["context"]["jump_host"]
    proxy = f'-o IdentitiesOnly=yes -o ProxyCommand="ssh -i {key_path} -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=5 {jump_user}@{jump_host} -W %h:%p"'
    ssh_user = receipt["definition"].get("ssh_user", receipt["context"]["ci_user"])
    return {
        "all": {
            "hosts": {
                "fixture": {
                    "ansible_host": receipt["ip_address"],
                    "ansible_user": ssh_user,
                    "ansible_become": True,
                    "ansible_python_interpreter": "/usr/bin/python3",
                    "ansible_ssh_private_key_file": str(key_path),
                    "ansible_ssh_common_args": proxy,
                }
            }
        }
    }


def converge_roles(receipt: dict[str, Any], *, skip_roles: bool = False) -> None:
    roles = receipt["definition"].get("roles_under_test", [])
    if skip_roles or not roles:
        return
    runtime_dir = REPO_ROOT / receipt["runtime_dir"]
    inventory_path = runtime_dir / "inventory.json"
    playbook_path = runtime_dir / "converge.json"
    write_json(inventory_path, ansible_inventory(receipt))
    play_vars = receipt["definition"].get("ansible_vars", {})
    playbook = [
        {
            "name": "Converge ephemeral fixture roles",
            "hosts": "fixture",
            "gather_facts": True,
            "become": True,
            "vars_files": [str(GROUP_VARS_PATH), str(HOST_VARS_PATH)],
            "vars": play_vars,
            "roles": roles,
        }
    ]
    write_json(playbook_path, playbook)
    ensure_command(
        run_command(["ansible-playbook", "-i", str(inventory_path), str(playbook_path)], cwd=REPO_ROOT),
        "ansible-playbook converge",
    )


def verify_http(url: str, expected_status: int, timeout_seconds: int) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": "fixture-manager/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            observed = response.status
    except urllib.error.URLError as exc:
        return {"ok": False, "kind": "http", "target": url, "error": str(exc)}
    return {
        "ok": observed == expected_status,
        "kind": "http",
        "target": url,
        "status": observed,
        "expected_status": expected_status,
    }


def verify_tcp(host: str, port: int, timeout_seconds: int) -> dict[str, Any]:
    try:
        with socket.create_connection((host, port), timeout=timeout_seconds):
            return {"ok": True, "kind": "tcp", "target": f"{host}:{port}"}
    except OSError as exc:
        return {"ok": False, "kind": "tcp", "target": f"{host}:{port}", "error": str(exc)}


def verify_command(receipt: dict[str, Any], command: str, timeout_seconds: int) -> dict[str, Any]:
    result = run_command(ssh_argv(receipt, command, timeout_seconds=timeout_seconds))
    return {
        "ok": result.returncode == 0,
        "kind": "command",
        "target": command,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def verify_fixture(receipt: dict[str, Any], definition: dict[str, Any]) -> dict[str, Any]:
    checks = []
    for item in definition.get("verify", []):
        timeout_seconds = int(item.get("timeout_seconds", 30))
        if "url" in item:
            checks.append(verify_http(item["url"], int(item.get("expected_status", 200)), timeout_seconds))
            continue
        if "port" in item:
            checks.append(verify_tcp(receipt["ip_address"], int(item["port"]), timeout_seconds))
            continue
        if "command" in item:
            checks.append(verify_command(receipt, item["command"], timeout_seconds))
            continue
        checks.append(
            {
                "ok": False,
                "kind": "unknown",
                "target": json.dumps(item, sort_keys=True),
                "error": "Unsupported verify block",
            }
        )
    return {"ok": all(check["ok"] for check in checks), "checks": checks}


def stage_seed_snapshot(
    receipt: dict[str, Any],
    *,
    seed_class: str | None = None,
    snapshot_id: str | None = None,
) -> dict[str, Any] | None:
    selected_seed_class = seed_class or receipt.get("seed_class")
    if not selected_seed_class:
        return None
    stage_root = seed_data_snapshots.guest_stage_root()
    remote_dir = f"{stage_root.rstrip('/')}/{receipt['receipt_id']}"
    staged = seed_data_snapshots.stage_snapshot_to_remote_dir(
        selected_seed_class,
        ssh_base_argv(receipt),
        remote_dir=remote_dir,
        snapshot_name=snapshot_id or receipt.get("seed_snapshot_id"),
    )
    receipt["seed_class"] = staged["seed_class"]
    receipt["seed_snapshot_id"] = staged["snapshot_id"]
    receipt["seed_snapshot_remote_dir"] = staged["remote_dir"]
    return staged


def capture_ssh_fingerprint(receipt: dict[str, Any]) -> str:
    if not shutil.which("ssh-keyscan") or not shutil.which("ssh-keygen"):
        return ""
    keyscan = run_command(["ssh-keyscan", "-T", "5", receipt["ip_address"]])
    if keyscan.returncode != 0 or not keyscan.stdout:
        return ""
    keygen = subprocess.run(
        ["ssh-keygen", "-lf", "-"],
        input=keyscan.stdout,
        text=True,
        capture_output=True,
        check=False,
    )
    if keygen.returncode != 0:
        return ""
    return keygen.stdout.strip()


def allocator_lock() -> Any:
    FIXTURE_LOCKS_DIR.mkdir(parents=True, exist_ok=True)
    handle = (FIXTURE_LOCKS_DIR / "vmid.lock").open("w", encoding="utf-8")
    fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
    return handle


def reserved_vmids() -> set[int]:
    return {int(receipt["vm_id"]) for receipt in nonfinal_receipts()}


def build_receipt(
    definition: dict[str, Any],
    fixture_path: Path,
    vm_id: int,
    now: dt.datetime,
    *,
    owner: str,
    purpose: str,
    policy: str,
    lifetime_minutes: int,
    seed_class: str | None = None,
    seed_snapshot_id: str | None = None,
    lease_purpose: str = DEFAULT_LEASE_PURPOSE,
    pool: EphemeralPoolConfig | None = None,
    status: str = "provisioning",
    pool_state: str | None = None,
    allocation_mode: str = "cold-start",
) -> dict[str, Any]:
    network_ip, _network_cidr = parse_ip_cidr(definition["network"]["ip_cidr"])
    receipt_id = f"{definition['fixture_id']}-{compact_timestamp(now)}"
    context = default_fixture_context()
    runtime_dir = FIXTURE_RUNTIME_DIR / receipt_id
    expires_at = now + dt.timedelta(minutes=lifetime_minutes)
    metadata = build_ephemeral_tag_metadata(
        owner=owner,
        purpose=purpose,
        expires_epoch=int(expires_at.timestamp()),
        policy=policy,
    )
    placement_class = placement_class_for_lease_purpose(lease_purpose)
    receipt = {
        "receipt_id": receipt_id,
        "fixture_id": definition["fixture_id"],
        "status": status,
        "created_at": isoformat(now),
        "updated_at": isoformat(now),
        "lifetime_minutes": lifetime_minutes,
        "extend_minutes": int(definition.get("extend_minutes", 0)),
        "owner": metadata.owner,
        "purpose": metadata.purpose,
        "lease_purpose": lease_purpose,
        "policy": metadata.policy,
        "expires_epoch": metadata.expires_epoch,
        "expires_at": isoformat(expires_at),
        "definition_path": str(fixture_path.relative_to(REPO_ROOT)),
        "runtime_dir": str(runtime_dir.relative_to(REPO_ROOT)),
        "vm_id": vm_id,
        "ip_address": network_ip,
        "mac_address": definition.get("mac_address", mac_from_vmid(vm_id)),
        "capacity_class": pool.protected_capacity_class if pool is not None else "ephemeral-pool",
        "placement_class": placement_class,
        "allocation_domain": pool.placement_domain if pool is not None else "proxmox-local",
        "spillover_domain": pool.spillover_domain if pool is not None else "auxiliary-cloud",
        "allocation_mode": allocation_mode,
        "pool_id": pool.pool_id if pool is not None else None,
        "pool_state": pool_state,
        "definition": definition,
        "context": context,
        "seed_class": seed_class or definition.get("default_seed_class"),
        "seed_snapshot_id": seed_snapshot_id,
    }
    refresh_receipt_tags(receipt)
    return receipt


def save_receipt(receipt: dict[str, Any]) -> Path:
    receipt["expires_at"] = isoformat(dt.datetime.fromtimestamp(int(receipt["expires_epoch"]), tz=dt.UTC))
    refresh_receipt_tags(receipt)
    receipt["updated_at"] = isoformat(utc_now())
    path = receipt_path(receipt["receipt_id"])
    write_json(path, receipt)
    return path


def archive_receipt(receipt: dict[str, Any]) -> None:
    archive_path = FIXTURE_ARCHIVE_DIR / f"{receipt['receipt_id']}.json"
    write_json(archive_path, receipt)


def release_receipt(receipt: dict[str, Any]) -> None:
    path = receipt_path(receipt["receipt_id"])
    if path.exists():
        path.unlink()


def cold_provision_receipt(
    receipt: dict[str, Any],
    *,
    endpoint: str,
    api_token: str,
    skip_roles: bool,
    skip_verify: bool,
) -> dict[str, Any]:
    runtime_dir = ensure_runtime_files(receipt)
    try:
        apply_fixture(runtime_dir, endpoint, api_token, receipt=receipt)
        wait_for_ssh(receipt)
        wait_for_cloud_init(receipt)
        prepare_guest_for_converge(receipt)
        converge_roles(receipt, skip_roles=skip_roles)
        stage_seed_snapshot(receipt)
        verification = {"ok": True, "checks": []} if skip_verify else verify_fixture(receipt, receipt["definition"])
        if not verification["ok"]:
            raise RuntimeError(f"Fixture verification failed for {receipt['receipt_id']}")
        receipt["verification"] = verification
        receipt["ssh_fingerprint"] = capture_ssh_fingerprint(receipt)
        return receipt
    except Exception:
        try:
            destroy_fixture(runtime_dir, endpoint, api_token, receipt=receipt)
        except Exception:
            pass
        receipt["status"] = "failed"
        archive_receipt(receipt)
        release_receipt(receipt)
        raise


def mark_receipt_active(
    receipt: dict[str, Any],
    *,
    owner: str,
    purpose: str,
    lease_purpose: str,
    lifetime_minutes: int,
    allocation_mode: str,
    pool_state: str | None = None,
) -> dict[str, Any]:
    now = utc_now()
    expires_at = now + dt.timedelta(minutes=lifetime_minutes)
    receipt["status"] = "active"
    receipt["owner"] = owner
    receipt["purpose"] = purpose
    receipt["lease_purpose"] = lease_purpose
    receipt["lifetime_minutes"] = lifetime_minutes
    receipt["allocation_mode"] = allocation_mode
    receipt["pool_state"] = pool_state
    receipt["capacity_class"] = str(receipt.get("capacity_class") or "ephemeral-pool")
    receipt["placement_class"] = placement_class_for_lease_purpose(lease_purpose)
    receipt["expires_epoch"] = int(expires_at.timestamp())
    receipt["expires_at"] = isoformat(expires_at)
    refresh_receipt_tags(receipt)
    return receipt


def mark_receipt_prewarmed(
    receipt: dict[str, Any],
    *,
    pool: EphemeralPoolConfig,
) -> dict[str, Any]:
    now = utc_now()
    expires_at = now + dt.timedelta(minutes=pool.warm_lifetime_minutes)
    receipt["status"] = "prewarmed"
    receipt["owner"] = DEFAULT_WARM_OWNER
    receipt["purpose"] = f"{DEFAULT_WARM_PURPOSE}-{pool.pool_id}"
    receipt["lease_purpose"] = DEFAULT_LEASE_PURPOSE
    receipt["lifetime_minutes"] = pool.warm_lifetime_minutes
    receipt["allocation_mode"] = "prewarmed"
    receipt["pool_state"] = "prewarmed"
    receipt["expires_epoch"] = int(expires_at.timestamp())
    receipt["expires_at"] = isoformat(expires_at)
    refresh_receipt_tags(receipt)
    return receipt


def provision_prewarmed_fixture(
    fixture_name: str,
    *,
    fixture_path: Path,
    definition: dict[str, Any],
    pool: EphemeralPoolConfig,
    endpoint: str,
    api_token: str,
) -> dict[str, Any]:
    lock_handle = allocator_lock()
    try:
        cluster_resources = fetch_cluster_resources(endpoint, api_token)
        ensure_ephemeral_pool_capacity(definition, cluster_resources)
        used_vmids = vmid_allocator.parse_cluster_vmids({"data": cluster_resources}) | reserved_vmids()
        start, end = tuple(int(value) for value in definition["vmid_range"])
        vm_id = vmid_allocator.allocate_free_vmid(used_vmids, start, end)
        receipt = build_receipt(
            definition,
            fixture_path,
            vm_id,
            utc_now(),
            owner=DEFAULT_WARM_OWNER,
            purpose=f"{DEFAULT_WARM_PURPOSE}-{pool.pool_id}",
            policy="extended-fixture",
            lifetime_minutes=pool.warm_lifetime_minutes,
            lease_purpose=DEFAULT_LEASE_PURPOSE,
            pool=pool,
            status="prewarming",
            pool_state="prewarming",
            allocation_mode="prewarm",
        )
        receipt["definition"]["template_vmid"] = resolve_template_vmid(str(definition["template"]), cluster_resources)
        save_receipt(receipt)
    finally:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
        lock_handle.close()

    receipt = cold_provision_receipt(
        receipt, endpoint=endpoint, api_token=api_token, skip_roles=False, skip_verify=False
    )
    resource = cluster_resource_by_vmid(fetch_cluster_resources(endpoint, api_token), int(receipt["vm_id"]))
    if resource is None:
        raise RuntimeError(f"Unable to locate freshly provisioned warm fixture {receipt['vm_id']}")
    stop_cluster_vm(endpoint, api_token, resource)
    mark_receipt_prewarmed(receipt, pool=pool)
    sync_receipt_tags(endpoint, api_token, receipt)
    save_receipt(receipt)
    emit_ephemeral_event(
        "ephemeral.prewarm",
        f"vmid:{receipt['vm_id']}",
        actor_id=DEFAULT_WARM_OWNER,
        evidence_ref=str(receipt_path(receipt["receipt_id"]).relative_to(REPO_ROOT)),
    )
    return receipt


def lease_prewarmed_fixture(
    receipt: dict[str, Any],
    *,
    owner: str,
    purpose: str,
    lease_purpose: str,
    lifetime_minutes: int,
    endpoint: str,
    api_token: str,
    skip_verify: bool,
    seed_class: str | None = None,
    seed_snapshot_id: str | None = None,
) -> dict[str, Any]:
    resources = filter_ephemeral_cluster_vms(fetch_cluster_resources(endpoint, api_token))
    resource = cluster_resource_by_vmid(resources, int(receipt["vm_id"]))
    if resource is None:
        raise RuntimeError(f"Warm fixture vmid {receipt['vm_id']} no longer exists on the cluster")
    start_cluster_vm(endpoint, api_token, resource)
    wait_for_ssh(receipt)
    stage_seed_snapshot(receipt, seed_class=seed_class, snapshot_id=seed_snapshot_id)
    verification = receipt.get("verification", {"ok": False, "checks": []})
    if not skip_verify:
        verification = verify_fixture(receipt, receipt["definition"])
        if not verification["ok"]:
            raise RuntimeError(f"Warm fixture verification failed for {receipt['receipt_id']}")
    receipt["verification"] = verification
    receipt["ssh_fingerprint"] = capture_ssh_fingerprint(receipt)
    mark_receipt_active(
        receipt,
        owner=owner,
        purpose=purpose,
        lease_purpose=lease_purpose,
        lifetime_minutes=lifetime_minutes,
        allocation_mode="warm-handoff",
        pool_state="leased",
    )
    sync_receipt_tags(endpoint, api_token, receipt)
    save_receipt(receipt)
    emit_ephemeral_event(
        "ephemeral.lease",
        f"vmid:{receipt['vm_id']}",
        actor_id=receipt["owner"],
        evidence_ref=str(receipt_path(receipt["receipt_id"]).relative_to(REPO_ROOT)),
    )
    return receipt


def ensure_local_lease_capacity(
    *,
    defaults: EphemeralPoolDefaults,
    pool: EphemeralPoolConfig | None,
    lease_purpose: str,
) -> None:
    active_leases = active_local_leases()
    if len(active_leases) >= defaults.max_local_active_leases:
        target_pool = pool.pool_id if pool is not None else "default"
        raise SpilloverRequiredError(
            pool_id=target_pool,
            spillover_domain=pool.spillover_domain if pool is not None else defaults.spillover_domain,
            reason="global local lease ceiling reached",
        )
    if pool is not None and len(active_pool_leases(pool.pool_id)) >= pool.max_concurrent_leases:
        raise SpilloverRequiredError(
            pool_id=pool.pool_id,
            spillover_domain=pool.spillover_domain,
            reason=f"pool lease ceiling reached for purpose '{lease_purpose}'",
        )


def fixture_up(
    fixture_name: str | None = None,
    *,
    purpose: str | None = None,
    owner: str | None = None,
    lifetime_hours: float | None = None,
    policy: str = DEFAULT_EPHEMERAL_POLICY,
    extend: bool = False,
    lease_purpose: str = DEFAULT_LEASE_PURPOSE,
    skip_roles: bool = False,
    skip_verify: bool = False,
    seed_class: str | None = None,
    seed_snapshot_id: str | None = None,
) -> dict[str, Any]:
    fixture_name = fixture_name or DEFAULT_FIXTURE_PROFILE
    fixture_path = resolve_fixture_path(fixture_name)
    definition = load_fixture_definition(fixture_path)
    lifetime_minutes = ensure_ephemeral_lifetime_minutes(
        lifetime_hours=lifetime_hours,
        definition=definition,
        policy=policy,
        extend=extend,
    )
    if lease_purpose not in LEASE_PURPOSES:
        raise ValueError(f"Unsupported lease purpose '{lease_purpose}'")
    resolved_owner = owner or current_owner()
    resolved_purpose = purpose or f"{fixture_name}-{lease_purpose}"
    defaults, pool = pool_for_fixture(definition["fixture_id"])
    placement_class = placement_class_for_lease_purpose(lease_purpose)
    if pool is not None and placement_class not in pool.allowed_placement_classes:
        raise ValueError(f"Pool '{pool.pool_id}' does not allow placement class '{placement_class}'")
    if pool is not None and lease_purpose not in pool.allowed_lease_purposes:
        raise ValueError(f"Pool '{pool.pool_id}' does not allow lease purpose '{lease_purpose}'")

    endpoint, api_token = proxmox_api_credentials()
    ensure_local_lease_capacity(defaults=defaults, pool=pool, lease_purpose=lease_purpose)

    if pool is not None:
        warm_receipt = available_prewarmed_receipt(pool.pool_id)
        if warm_receipt is not None:
            return lease_prewarmed_fixture(
                warm_receipt,
                owner=resolved_owner,
                purpose=resolved_purpose,
                lease_purpose=lease_purpose,
                lifetime_minutes=lifetime_minutes,
                endpoint=endpoint,
                api_token=api_token,
                skip_verify=skip_verify,
                seed_class=seed_class,
                seed_snapshot_id=seed_snapshot_id,
            )
        definition = apply_pool_member_definition(
            definition,
            pool,
            ip_cidr=select_pool_ip_address(pool),
        )

    start, end = tuple(int(value) for value in definition["vmid_range"])
    lock_handle = allocator_lock()
    try:
        cluster_resources = fetch_cluster_resources(endpoint, api_token)
        ensure_ephemeral_pool_capacity(definition, cluster_resources)
        used_vmids = vmid_allocator.parse_cluster_vmids({"data": cluster_resources}) | reserved_vmids()
        vm_id = vmid_allocator.allocate_free_vmid(used_vmids, start, end)
        receipt = build_receipt(
            definition,
            fixture_path,
            vm_id,
            utc_now(),
            owner=resolved_owner,
            purpose=resolved_purpose,
            policy=policy,
            lifetime_minutes=lifetime_minutes,
            seed_class=seed_class,
            seed_snapshot_id=seed_snapshot_id,
            lease_purpose=lease_purpose,
            pool=pool,
            status="provisioning",
            pool_state="leased" if pool is not None else None,
            allocation_mode="cold-start",
        )
        receipt["definition"]["template_vmid"] = resolve_template_vmid(str(definition["template"]), cluster_resources)
        save_receipt(receipt)
    finally:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
        lock_handle.close()

    receipt = cold_provision_receipt(
        receipt, endpoint=endpoint, api_token=api_token, skip_roles=skip_roles, skip_verify=skip_verify
    )
    mark_receipt_active(
        receipt,
        owner=resolved_owner,
        purpose=resolved_purpose,
        lease_purpose=lease_purpose,
        lifetime_minutes=lifetime_minutes,
        allocation_mode="cold-start",
        pool_state="leased" if pool is not None else None,
    )
    save_receipt(receipt)
    emit_ephemeral_event(
        "ephemeral.create",
        f"vmid:{receipt['vm_id']}",
        actor_id=receipt["owner"],
        evidence_ref=str(receipt_path(receipt["receipt_id"]).relative_to(REPO_ROOT)),
    )
    return receipt


def stop_cluster_vm(endpoint: str, api_token: str, resource: dict[str, Any]) -> None:
    if str(resource.get("status", "")).lower() == "stopped":
        return
    proxmox_api_request(
        endpoint,
        api_token,
        f"/nodes/{resource['node']}/qemu/{int(resource['vmid'])}/status/stop",
        method="POST",
    )


def start_cluster_vm(endpoint: str, api_token: str, resource: dict[str, Any]) -> None:
    if str(resource.get("status", "")).lower() == "running":
        return
    proxmox_api_request(
        endpoint,
        api_token,
        f"/nodes/{resource['node']}/qemu/{int(resource['vmid'])}/status/start",
        method="POST",
    )


def destroy_cluster_vm(endpoint: str, api_token: str, resource: dict[str, Any]) -> None:
    stop_cluster_vm(endpoint, api_token, resource)
    proxmox_api_request(
        endpoint,
        api_token,
        f"/nodes/{resource['node']}/qemu/{int(resource['vmid'])}",
        method="DELETE",
        params={"purge": 1, "destroy-unreferenced-disks": 1},
    )


def apply_cluster_vm_tags(
    endpoint: str,
    api_token: str,
    resource: dict[str, Any],
    tags: list[str],
) -> None:
    proxmox_api_request(
        endpoint,
        api_token,
        f"/nodes/{resource['node']}/qemu/{int(resource['vmid'])}/config",
        method="PUT",
        params={"tags": ";".join(tags)},
    )


def cluster_resource_by_vmid(resources: list[dict[str, Any]], vmid: int) -> dict[str, Any] | None:
    for resource in resources:
        if int(resource.get("vmid", -1)) == vmid:
            return resource
    return None


def sync_receipt_tags(endpoint: str, api_token: str, receipt: dict[str, Any]) -> None:
    resources = filter_ephemeral_cluster_vms(fetch_cluster_resources(endpoint, api_token))
    resource = cluster_resource_by_vmid(resources, int(receipt["vm_id"]))
    if resource is None:
        raise RuntimeError(f"Unable to find cluster resource for vmid {receipt['vm_id']}")
    apply_cluster_vm_tags(endpoint, api_token, resource, list(receipt.get("ephemeral_tags", [])))


def fixture_down(
    fixture_name: str | None = None,
    *,
    receipt_id: str | None = None,
    vmid: int | None = None,
) -> dict[str, Any]:
    if not fixture_name and not receipt_id and vmid is None:
        raise ValueError("fixture_down requires a fixture name, receipt_id, or vmid")
    receipts = nonfinal_receipts(fixture_name) if fixture_name else nonfinal_receipts()
    if receipt_id:
        receipts = [receipt for receipt in receipts if receipt["receipt_id"] == receipt_id]
    if vmid is not None:
        receipts = [receipt for receipt in receipts if int(receipt["vm_id"]) == vmid]
    endpoint, api_token = proxmox_api_credentials()
    destroyed = []
    for receipt in receipts:
        runtime_dir = REPO_ROOT / receipt["runtime_dir"]
        destroy_fixture(runtime_dir, endpoint, api_token, receipt=receipt)
        receipt["status"] = "destroyed"
        receipt["destroyed_at"] = isoformat(utc_now())
        archive_receipt(receipt)
        release_receipt(receipt)
        if runtime_dir.exists():
            shutil.rmtree(runtime_dir)
        destroyed.append({"receipt_id": receipt["receipt_id"], "vm_id": receipt["vm_id"]})
        emit_ephemeral_event(
            "ephemeral.destroy",
            f"vmid:{receipt['vm_id']}",
            actor_id=str(receipt.get("owner") or current_owner()),
            evidence_ref=str((FIXTURE_ARCHIVE_DIR / f"{receipt['receipt_id']}.json").relative_to(REPO_ROOT)),
        )

    if destroyed or vmid is None:
        return {"fixture_id": fixture_name, "destroyed": destroyed}

    for resource in filter_ephemeral_cluster_vms(fetch_cluster_resources(endpoint, api_token)):
        if int(resource["vmid"]) != vmid:
            continue
        destroy_cluster_vm(endpoint, api_token, resource)
        emit_ephemeral_event("ephemeral.destroy", f"vmid:{vmid}", actor_id=current_owner())
        return {"fixture_id": fixture_name, "destroyed": [{"receipt_id": None, "vm_id": vmid}]}
    return {"fixture_id": fixture_name, "destroyed": []}


def build_cluster_fixture_row(
    resource: dict[str, Any], receipt: dict[str, Any] | None, *, refresh_health: bool
) -> dict[str, Any]:
    metadata = parse_ephemeral_tags(resource.get("tags"))
    if metadata is None and receipt is not None:
        metadata = build_ephemeral_tag_metadata(
            owner=str(receipt.get("owner") or current_owner()),
            purpose=str(receipt.get("purpose") or receipt.get("fixture_id") or "fixture"),
            expires_epoch=int(receipt.get("expires_epoch") or expiry_for_receipt(receipt).timestamp()),
            policy=str(receipt.get("policy") or DEFAULT_EPHEMERAL_POLICY),
        )
    if metadata is not None:
        expires_at = dt.datetime.fromtimestamp(metadata.expires_epoch, tz=dt.UTC)
        owner = metadata.owner
        purpose = metadata.purpose
    else:
        expires_at = utc_now() + dt.timedelta(minutes=DEFAULT_UNTAGGED_GRACE_MINUTES)
        owner = "manual"
        purpose = "untagged"

    health = {"ok": True}
    if receipt is not None:
        health = receipt.get("verification", {"ok": False})
        if refresh_health and receipt.get("status") not in {"prewarming", "prewarmed"}:
            health = verify_fixture(receipt, receipt["definition"])

    age = "n/a"
    if receipt is not None:
        age = format_duration(utc_now() - parse_timestamp(receipt["created_at"]))
    elif isinstance(resource.get("uptime"), (int, float)):
        age = format_duration(dt.timedelta(seconds=int(resource["uptime"])))

    ip_address = receipt["ip_address"] if receipt is not None else str(resource.get("ip", "n/a"))
    return {
        "fixture_id": receipt["fixture_id"] if receipt is not None else "manual",
        "receipt_id": receipt["receipt_id"] if receipt is not None else None,
        "vm_id": int(resource["vmid"]),
        "ip_address": ip_address,
        "age": age,
        "remaining": format_duration(expires_at - utc_now()),
        "health": "ok" if health.get("ok") else "failed" if receipt is not None else "unknown",
        "status": receipt["status"] if receipt is not None else str(resource.get("status", "unknown")),
        "owner": owner,
        "purpose": purpose,
        "lease_purpose": str(receipt.get("lease_purpose") or DEFAULT_LEASE_PURPOSE)
        if receipt is not None
        else DEFAULT_LEASE_PURPOSE,
        "pool_id": str(receipt.get("pool_id") or "") if receipt is not None else "",
        "pool_state": str(receipt.get("pool_state") or "") if receipt is not None else "",
        "policy": metadata.policy if metadata is not None else "grace",
        "tags": split_tag_text(resource.get("tags")),
    }


def fixture_list(*, refresh_health: bool = True) -> list[dict[str, Any]]:
    endpoint, api_token = proxmox_api_credentials()
    rows = []
    try:
        cluster_resources = filter_ephemeral_cluster_vms(fetch_cluster_resources(endpoint, api_token))
    except Exception:
        cluster_resources = []
    if not cluster_resources:
        for receipt in active_receipts():
            remaining = expiry_for_receipt(receipt) - utc_now()
            health = receipt.get("verification", {"ok": False})
            if refresh_health and receipt.get("status") not in {"prewarming", "prewarmed"}:
                health = verify_fixture(receipt, receipt["definition"])
            rows.append(
                {
                    "fixture_id": receipt["fixture_id"],
                    "receipt_id": receipt["receipt_id"],
                    "vm_id": receipt["vm_id"],
                    "ip_address": receipt["ip_address"],
                    "age": format_duration(utc_now() - parse_timestamp(receipt["created_at"])),
                    "remaining": format_duration(remaining),
                    "health": "ok" if health.get("ok") else "failed",
                    "status": receipt["status"],
                    "owner": str(receipt.get("owner") or current_owner()),
                    "purpose": str(receipt.get("purpose") or receipt["fixture_id"]),
                    "lease_purpose": str(receipt.get("lease_purpose") or DEFAULT_LEASE_PURPOSE),
                    "pool_id": str(receipt.get("pool_id") or ""),
                    "pool_state": str(receipt.get("pool_state") or ""),
                    "policy": str(receipt.get("policy") or DEFAULT_EPHEMERAL_POLICY),
                    "tags": list(receipt.get("ephemeral_tags", [])),
                }
            )
        return rows

    for resource in cluster_resources:
        rows.append(
            build_cluster_fixture_row(
                resource, find_receipt_by_vmid(int(resource["vmid"])), refresh_health=refresh_health
            )
        )
    return rows


def reap_expired() -> dict[str, Any]:
    endpoint, api_token = proxmox_api_credentials()
    resources = filter_ephemeral_cluster_vms(fetch_cluster_resources(endpoint, api_token))
    expired_vmids: list[int] = []
    skipped_vmids: list[int] = []
    warned_vmids: list[int] = []
    retagged_vmids: list[int] = []
    now = utc_now()
    for resource in resources:
        vmid = int(resource["vmid"])
        receipt = find_receipt_by_vmid(vmid)
        metadata = parse_ephemeral_tags(resource.get("tags"))
        if metadata is None:
            warning_metadata = build_ephemeral_tag_metadata(
                owner="manual",
                purpose="untagged",
                expires_epoch=int((now + dt.timedelta(minutes=DEFAULT_UNTAGGED_GRACE_MINUTES)).timestamp()),
                policy="extended-fixture",
            )
            tags = list(dict.fromkeys([*split_tag_text(resource.get("tags")), *build_ephemeral_tags(warning_metadata)]))
            apply_cluster_vm_tags(endpoint, api_token, resource, tags)
            warned_vmids.append(vmid)
            retagged_vmids.append(vmid)
            continue

        if dt.datetime.fromtimestamp(metadata.expires_epoch, tz=dt.UTC) > now:
            skipped_vmids.append(vmid)
            continue

        expired_vmids.append(vmid)
        if receipt is not None:
            fixture_down(receipt_id=receipt["receipt_id"])
        else:
            destroy_cluster_vm(endpoint, api_token, resource)
            emit_ephemeral_event("ephemeral.reap", f"vmid:{vmid}", actor_id="ephemeral-vm-reaper")

    summary = {
        "run_at": isoformat(now),
        "expired_vmids": expired_vmids,
        "skipped_vmids": skipped_vmids,
        "warned_vmids": warned_vmids,
        "retagged_vmids": retagged_vmids,
    }
    write_json(FIXTURE_REAPER_RUNS_DIR / f"reaper-run-{compact_timestamp(utc_now())}.json", summary)
    return summary


def pool_status() -> list[dict[str, Any]]:
    defaults, pools = load_ephemeral_pool_catalog()
    rows = []
    for pool in pools.values():
        warm_receipts = [
            receipt for receipt in prewarmed_receipts(pool.pool_id) if receipt.get("status") == "prewarmed"
        ]
        leased_receipts = active_pool_leases(pool.pool_id)
        rows.append(
            {
                "pool_id": pool.pool_id,
                "fixture_id": pool.fixture_id,
                "warm_count": len(warm_receipts),
                "warm_target": pool_refill_target(pool),
                "active_leases": len(leased_receipts),
                "max_concurrent_leases": pool.max_concurrent_leases,
                "max_local_active_leases": defaults.max_local_active_leases,
                "placement_domain": pool.placement_domain,
                "spillover_domain": pool.spillover_domain,
                "protected_capacity_class": pool.protected_capacity_class,
                "available_addresses": len(pool.ip_addresses)
                - len([receipt for receipt in nonfinal_receipts() if receipt.get("pool_id") == pool.pool_id]),
                "status": "ready" if len(warm_receipts) >= pool_refill_target(pool) else "needs-refill",
            }
        )
    return rows


def reconcile_pools(pool_id: str | None = None) -> dict[str, Any]:
    defaults, pools = load_ephemeral_pool_catalog()
    selected = [pool for pool in pools.values() if pool_id in {None, pool.pool_id}]
    if pool_id is not None and not selected:
        raise ValueError(f"Unknown pool '{pool_id}'")
    endpoint, api_token = proxmox_api_credentials()
    created: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    spillovers: list[dict[str, Any]] = []
    for pool in selected:
        warm_receipts = [
            receipt for receipt in prewarmed_receipts(pool.pool_id) if receipt.get("status") == "prewarmed"
        ]
        deficit = max(pool_refill_target(pool) - len(warm_receipts), 0)
        if deficit <= 0:
            skipped.append({"pool_id": pool.pool_id, "reason": "warm target already satisfied"})
            continue
        for _ in range(deficit):
            try:
                if len(active_local_leases()) >= defaults.max_local_active_leases and warm_receipts:
                    skipped.append(
                        {"pool_id": pool.pool_id, "reason": "global local lease ceiling already fully committed"}
                    )
                    break
                definition = load_fixture_definition(resolve_fixture_path(pool.fixture_id))
                definition = apply_pool_member_definition(
                    definition,
                    pool,
                    ip_cidr=select_pool_ip_address(pool),
                )
                receipt = provision_prewarmed_fixture(
                    pool.fixture_id,
                    fixture_path=resolve_fixture_path(pool.fixture_id),
                    definition=definition,
                    pool=pool,
                    endpoint=endpoint,
                    api_token=api_token,
                )
                created.append(
                    {
                        "pool_id": pool.pool_id,
                        "receipt_id": receipt["receipt_id"],
                        "vm_id": receipt["vm_id"],
                        "ip_address": receipt["ip_address"],
                    }
                )
                warm_receipts.append(receipt)
            except SpilloverRequiredError as exc:
                spillovers.append(
                    {
                        "pool_id": pool.pool_id,
                        "spillover_domain": exc.spillover_domain,
                        "reason": exc.reason,
                    }
                )
                break
    return {
        "run_at": isoformat(utc_now()),
        "created": created,
        "skipped": skipped,
        "spillovers": spillovers,
        "status": pool_status(),
    }


def render_fixture_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "No active fixtures"
    headers = ("FIXTURE", "VMID", "OWNER", "PURPOSE", "STATE", "IP", "REMAINING", "HEALTH")
    widths = {
        "FIXTURE": max(len("FIXTURE"), *(len(row["fixture_id"]) for row in rows)),
        "VMID": max(len("VMID"), *(len(str(row["vm_id"])) for row in rows)),
        "OWNER": max(len("OWNER"), *(len(row["owner"]) for row in rows)),
        "PURPOSE": max(len("PURPOSE"), *(len(row["purpose"]) for row in rows)),
        "STATE": max(len("STATE"), *(len(row["status"]) for row in rows)),
        "IP": max(len("IP"), *(len(row["ip_address"]) for row in rows)),
        "REMAINING": max(len("REMAINING"), *(len(row["remaining"]) for row in rows)),
        "HEALTH": max(len("HEALTH"), *(len(row["health"]) for row in rows)),
    }
    lines = [
        " ".join(
            [
                headers[0].ljust(widths["FIXTURE"]),
                headers[1].ljust(widths["VMID"]),
                headers[2].ljust(widths["OWNER"]),
                headers[3].ljust(widths["PURPOSE"]),
                headers[4].ljust(widths["STATE"]),
                headers[5].ljust(widths["IP"]),
                headers[6].ljust(widths["REMAINING"]),
                headers[7].ljust(widths["HEALTH"]),
            ]
        )
    ]
    for row in rows:
        lines.append(
            " ".join(
                [
                    row["fixture_id"].ljust(widths["FIXTURE"]),
                    str(row["vm_id"]).ljust(widths["VMID"]),
                    row["owner"].ljust(widths["OWNER"]),
                    row["purpose"].ljust(widths["PURPOSE"]),
                    row["status"].ljust(widths["STATE"]),
                    row["ip_address"].ljust(widths["IP"]),
                    row["remaining"].ljust(widths["REMAINING"]),
                    row["health"].ljust(widths["HEALTH"]),
                ]
            )
        )
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="action", required=True)

    create = subparsers.add_parser("create", aliases=["up"])
    create.add_argument("fixture_name", nargs="?", default=DEFAULT_FIXTURE_PROFILE)
    create.add_argument("--purpose")
    create.add_argument("--owner")
    create.add_argument("--lifetime-hours", type=float)
    create.add_argument("--lease-purpose", default=DEFAULT_LEASE_PURPOSE, choices=sorted(LEASE_PURPOSES))
    create.add_argument(
        "--policy",
        default=DEFAULT_EPHEMERAL_POLICY,
        choices=sorted(EPHEMERAL_POLICY_LIMITS_MINUTES),
    )
    create.add_argument("--extend", action="store_true")
    create.add_argument("--json", action="store_true")
    create.add_argument("--skip-role-converge", action="store_true")
    create.add_argument("--skip-verify", action="store_true")
    create.add_argument("--seed-class", choices=seed_data_snapshots.seed_classes())
    create.add_argument("--seed-snapshot-id")

    destroy = subparsers.add_parser("destroy", aliases=["down"])
    destroy.add_argument("fixture_name", nargs="?")
    destroy.add_argument("--receipt-id")
    destroy.add_argument("--vmid", type=int)
    destroy.add_argument("--json", action="store_true")

    fixture_list_parser = subparsers.add_parser("list")
    fixture_list_parser.add_argument("--json", action="store_true")
    fixture_list_parser.add_argument("--no-refresh-health", action="store_true")

    pool_status_parser = subparsers.add_parser("pool-status")
    pool_status_parser.add_argument("--json", action="store_true")

    reconcile = subparsers.add_parser("reconcile-pools")
    reconcile.add_argument("--pool")
    reconcile.add_argument("--json", action="store_true")

    reap = subparsers.add_parser("reap-expired")
    reap.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    FIXTURE_RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)
    FIXTURE_LOCAL_ROOT.mkdir(parents=True, exist_ok=True)
    FIXTURE_REAPER_RUNS_DIR.mkdir(parents=True, exist_ok=True)
    try:
        if args.action in {"create", "up"}:
            payload = fixture_up(
                args.fixture_name,
                purpose=args.purpose,
                owner=args.owner,
                lifetime_hours=args.lifetime_hours,
                policy=args.policy,
                extend=args.extend,
                lease_purpose=args.lease_purpose,
                skip_roles=args.skip_role_converge,
                skip_verify=args.skip_verify,
                seed_class=args.seed_class,
                seed_snapshot_id=args.seed_snapshot_id,
            )
            if args.json:
                print(json.dumps(payload, indent=2, sort_keys=True))
            else:
                print(f"Fixture {payload['fixture_id']} ready: vmid={payload['vm_id']} ip={payload['ip_address']}")
            return 0
        if args.action in {"destroy", "down"}:
            payload = fixture_down(args.fixture_name, receipt_id=args.receipt_id, vmid=args.vmid)
            if args.json:
                print(json.dumps(payload, indent=2, sort_keys=True))
            else:
                print(f"Destroyed {len(payload['destroyed'])} fixture(s)")
            return 0
        if args.action == "list":
            rows = fixture_list(refresh_health=not args.no_refresh_health)
            if args.json:
                print(json.dumps(rows, indent=2, sort_keys=True))
            else:
                print(render_fixture_table(rows))
            return 0
        if args.action == "pool-status":
            rows = pool_status()
            print(
                json.dumps(rows, indent=2, sort_keys=True) if args.json else json.dumps(rows, indent=2, sort_keys=True)
            )
            return 0
        if args.action == "reconcile-pools":
            payload = reconcile_pools(args.pool)
            print(
                json.dumps(payload, indent=2, sort_keys=True)
                if args.json
                else json.dumps(payload, indent=2, sort_keys=True)
            )
            return 0
        if args.action == "reap-expired":
            payload = reap_expired()
            if args.json:
                print(json.dumps(payload, indent=2, sort_keys=True))
            else:
                print(f"Expired fixtures destroyed: {len(payload['expired_vmids'])}")
            return 0
    except Exception as exc:
        print(f"fixture-manager error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
