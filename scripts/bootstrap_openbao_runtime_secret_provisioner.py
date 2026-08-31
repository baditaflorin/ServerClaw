#!/usr/bin/env python3
"""Bootstrap the narrow OpenBao runtime-secret provisioner without runtime changes.

This bounded recovery tool exists for the one-time transition away from broad
initialization credentials. It authenticates with the named ``breakglass``
userpass identity, derives every runtime-service contract from the canonical
service registry, and reconciles only the policies and AppRoles required by
those contracts. It never reads initialization, unseal, root-token, or
controller-AppRole artifacts and never starts, stops, or reconfigures OpenBao.

Secret material is accepted only through files, is never included in output or
exceptions, and is persisted with atomic root-only controller-local writes.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import hmac
import ipaddress
import json
import os
import re
import shlex
import socket
import ssl
import stat
import subprocess  # nosec B404
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final, Protocol

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

existing_platform = sys.modules.get("platform")
if existing_platform is not None and not hasattr(existing_platform, "__path__"):
    del sys.modules["platform"]

import yaml

from platform.repo import local_overlay_root


SERVICE_REGISTRY_PATH: Final[Path] = REPO_ROOT / "inventory/group_vars/all/platform_services.yml"
OPENBAO_DEFAULTS_PATH: Final[Path] = (
    REPO_ROOT / "collections/ansible_collections/lv3/platform/roles/openbao_runtime/defaults/main.yml"
)
PLATFORM_VARS_PATH: Final[Path] = REPO_ROOT / "inventory/group_vars/platform.yml"
HOST_NATIVE_CONTRACTS_PATH: Final[Path] = REPO_ROOT / "config/openbao-host-native-service-contracts.yml"

WORKFLOW_ID: Final[str] = "bootstrap-openbao-runtime-secret-provisioner"
PROVISIONER_ROLE_NAME: Final[str] = "runtime-secret-provisioner"
ARTIFACT_FILENAME: Final[str] = "runtime-secret-provisioner-approle.json"
RECEIPT_FILENAME: Final[str] = "runtime-secret-provisioner-bootstrap-receipt.json"
SAFE_NAME_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
SAFE_PREFIX_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[a-z0-9][a-z0-9-]*$")
SAFE_SSH_HOST_ALIAS_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
HCL_PATH_PATTERN: Final[re.Pattern[str]] = re.compile(r'^path\s+"([^"]+)"\s+\{$')
MAX_SECRET_FILE_BYTES: Final[int] = 4096
MAX_ARTIFACT_BYTES: Final[int] = 64 * 1024
SSH_BINARY: Final[str] = "/usr/bin/ssh"
SSH_USER: Final[str] = "ops"
SSH_TUNNEL_START_TIMEOUT_SECONDS: Final[float] = 15.0
SSH_TUNNEL_STOP_TIMEOUT_SECONDS: Final[float] = 3.0


class AnsibleDefaultsSafeLoader(yaml.SafeLoader):
    """Safely read the small Ansible tag subset used by role defaults.

    ``!unsafe`` tells Ansible to retain literal template markers.  It does not
    carry executable semantics, so treating its scalar value as ordinary text
    lets this controller-side validator consume the canonical defaults without
    broadening PyYAML's safe-loader surface.
    """


def _construct_ansible_unsafe(loader: yaml.SafeLoader, node: yaml.ScalarNode) -> str:
    return loader.construct_scalar(node)


AnsibleDefaultsSafeLoader.add_constructor("!unsafe", _construct_ansible_unsafe)


class BootstrapError(RuntimeError):
    """A deliberately sanitized, operator-safe bootstrap failure."""


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Reject redirects so authenticated requests cannot change origin."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        return None


class OpenBaoAPI(Protocol):
    """Minimal API surface used by the bootstrap and its deterministic fakes."""

    def request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        token: str | None = None,
        expected_statuses: set[int] | None = None,
    ) -> tuple[int, dict[str, Any]]: ...


class HTTPOpenBaoAPI:
    """Small OpenBao JSON client whose failures never expose response bodies."""

    def __init__(self, base_url: str, *, timeout: float = 30.0, ssl_context: ssl.SSLContext | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        handlers: list[urllib.request.BaseHandler] = [NoRedirectHandler()]
        if ssl_context is not None:
            handlers.insert(0, urllib.request.HTTPSHandler(context=ssl_context))
        self.opener = urllib.request.build_opener(*handlers)

    def request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        token: str | None = None,
        expected_statuses: set[int] | None = None,
    ) -> tuple[int, dict[str, Any]]:
        expected = expected_statuses or {200}
        body = None if payload is None else json.dumps(payload, separators=(",", ":")).encode("utf-8")
        headers = {
            "Accept": "application/json",
            "User-Agent": "serverclaw-openbao-runtime-secret-bootstrap/1",
        }
        if body is not None:
            headers["Content-Type"] = "application/json"
        if token is not None:
            headers["X-Vault-Token"] = token
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=body,
            headers=headers,
            method=method,
        )
        try:
            # The constructor receives a validated HTTP(S)-origin-only URL and
            # the opener rejects every redirect before credentials can move.
            with self.opener.open(  # nosec B310
                request,
                timeout=self.timeout,
            ) as response:
                status_code = response.status
                response_body = response.read()
        except urllib.error.HTTPError as exc:
            status_code = exc.code
            response_body = exc.read()
        except (urllib.error.URLError, TimeoutError, OSError):
            raise BootstrapError(f"OpenBao {method} {path} could not be reached") from None

        if status_code not in expected:
            raise BootstrapError(f"OpenBao {method} {path} returned HTTP {status_code}")
        if not response_body:
            return status_code, {}
        try:
            parsed = json.loads(response_body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise BootstrapError(f"OpenBao {method} {path} returned invalid JSON") from None
        if not isinstance(parsed, dict):
            raise BootstrapError(f"OpenBao {method} {path} returned an invalid response shape")
        return status_code, parsed


@dataclass(frozen=True)
class ServiceContract:
    registry_key: str
    secret_namespace: str
    secret_path: str
    policy_name: str
    approle_name: str

    @property
    def kv_capability_path(self) -> str:
        return f"kv/data/{self.secret_path}"

    @property
    def role_path(self) -> str:
        return f"auth/approle/role/{self.approle_name}"

    @property
    def role_id_path(self) -> str:
        return f"{self.role_path}/role-id"

    @property
    def secret_id_path(self) -> str:
        return f"{self.role_path}/secret-id"


@dataclass(frozen=True)
class DesiredRole:
    name: str
    policy_name: str
    bind_secret_id: bool = True
    token_ttl_seconds: int = 900
    token_max_ttl_seconds: int = 3600
    token_explicit_max_ttl_seconds: int = 0
    token_period_seconds: int = 0
    token_num_uses: int = 0
    token_type: str = "default"
    token_no_default_policy: bool = False
    token_bound_cidrs: tuple[str, ...] = ()
    secret_id_ttl_seconds: int = 0
    secret_id_num_uses: int = 0
    secret_id_bound_cidrs: tuple[str, ...] = ()
    local_secret_ids: bool = False

    @property
    def api_payload(self) -> dict[str, Any]:
        # OpenBao accepts local_secret_ids only while creating a role and
        # rejects the field on every update, even when the requested value is
        # false. All roles in this bounded plan require the safe default
        # (false), so omit the creation-only field and verify the retained
        # value through _role_matches instead.
        return {
            "token_policies": self.policy_name,
            "bind_secret_id": self.bind_secret_id,
            "token_ttl": f"{self.token_ttl_seconds}s",
            "token_max_ttl": f"{self.token_max_ttl_seconds}s",
            "token_explicit_max_ttl": f"{self.token_explicit_max_ttl_seconds}s",
            "token_period": f"{self.token_period_seconds}s",
            "token_num_uses": self.token_num_uses,
            "token_type": self.token_type,
            "token_no_default_policy": self.token_no_default_policy,
            "token_bound_cidrs": list(self.token_bound_cidrs),
            "secret_id_ttl": f"{self.secret_id_ttl_seconds}s",
            "secret_id_num_uses": self.secret_id_num_uses,
            "secret_id_bound_cidrs": list(self.secret_id_bound_cidrs),
        }


@dataclass(frozen=True)
class SSHTunnelConfiguration:
    jump_host: str
    jump_port: int
    target_guest: str
    target_host: str
    remote_port: int


@dataclass(frozen=True)
class BootstrapConfiguration:
    platform_domain: str
    config_prefix: str
    api_url: str
    ssh_tunnel: SSHTunnelConfiguration
    contracts: tuple[ServiceContract, ...]
    policies: dict[str, str]
    roles: dict[str, DesiredRole]
    provisioner_policy_name: str
    protected_approle_names: tuple[str, ...]


@dataclass(frozen=True)
class FileSnapshot:
    exists: bool
    device: int | None = None
    inode: int | None = None
    size: int | None = None
    mtime_ns: int | None = None
    digest: str | None = None


@dataclass(frozen=True)
class ArtifactInspection:
    snapshot: FileSnapshot
    payload: dict[str, str] | None
    state: str


@dataclass(frozen=True)
class VerificationSummary:
    login_verified: bool
    policy_set_verified: bool
    allow_path_count: int
    deny_path_count: int


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise BootstrapError(f"{label} must be a mapping")
    return value


def _string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BootstrapError(f"{label} must be a non-empty string")
    return value.strip()


def _safe_name(value: Any, label: str) -> str:
    name = _string(value, label)
    if not SAFE_NAME_PATTERN.fullmatch(name):
        raise BootstrapError(f"{label} has an unsafe identifier")
    return name


def _ssh_host_alias(value: str | None, label: str) -> str | None:
    if value is None or not value.strip():
        return None
    alias = value.strip()
    if not SAFE_SSH_HOST_ALIAS_PATTERN.fullmatch(alias):
        raise BootstrapError(f"{label} has an unsafe SSH host alias")
    return alias


def _load_yaml_mapping(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = yaml.load(path.read_text(encoding="utf-8"), Loader=AnsibleDefaultsSafeLoader)
    except FileNotFoundError:
        raise BootstrapError(f"{label} is missing") from None
    except (OSError, UnicodeError, yaml.YAMLError):
        raise BootstrapError(f"{label} could not be read safely") from None
    return _mapping(payload, label)


def _ipv4(value: Any, label: str) -> str:
    raw = _string(value, label)
    try:
        address = ipaddress.IPv4Address(raw)
    except ipaddress.AddressValueError:
        raise BootstrapError(f"{label} must be a valid IPv4 address") from None
    if address.is_unspecified or address.is_multicast:
        raise BootstrapError(f"{label} must be a usable unicast IPv4 address")
    return str(address)


def _validate_identity(identity_file: Path) -> tuple[str, str, str]:
    identity = _load_yaml_mapping(identity_file, "the explicit identity selector")
    domain = _string(identity.get("platform_domain"), "platform_domain").lower()
    if domain == "example.com" or "." not in domain or "{{" in domain:
        raise BootstrapError("the explicit identity selector must name a concrete deployment domain")
    # ADR 0438 makes platform_identity.config_prefix authoritative. The
    # Ansible filter derives it from the first domain label; the legacy
    # platform_config_prefix scalar can be stale and must not fork policy names.
    prefix = domain.split(".", 1)[0]
    if not SAFE_PREFIX_PATTERN.fullmatch(prefix):
        raise BootstrapError("platform_config_prefix has an unsafe identifier")
    management_tailscale_ipv4 = _ipv4(
        identity.get("management_tailscale_ipv4"),
        "management_tailscale_ipv4",
    )
    return domain, prefix, management_tailscale_ipv4


def _validate_api_url(value: Any) -> str:
    api_url = _string(value, "openbao_controller_url").rstrip("/")
    parsed = urllib.parse.urlsplit(api_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise BootstrapError("openbao_controller_url must be an HTTP(S) origin")
    if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
        raise BootstrapError("openbao_controller_url must not contain credentials, query data, or a path")
    if parsed.scheme == "http" and parsed.hostname not in {"127.0.0.1", "::1", "localhost"}:
        raise BootstrapError("plaintext OpenBao access is permitted only through a loopback endpoint")
    return api_url


def _proxmox_jump_port_from_environment() -> int:
    """Return the explicit management SSH port used by the guest jump path.

    The same ``LV3_PROXMOX_HOST_PORT`` override drives Ansible's managed
    ``proxmox_host_jump`` transport.  Keeping this bounded bootstrap on that
    source prevents a break-glass-port migration from silently making the
    controller-local OpenBao tunnel fall back to port 22.
    """

    raw_port = os.environ.get("LV3_PROXMOX_HOST_PORT", "").strip()
    if not raw_port:
        return 22
    try:
        port = int(raw_port)
    except ValueError:
        raise BootstrapError("LV3_PROXMOX_HOST_PORT must be a valid TCP port") from None
    if not 1 <= port <= 65535:
        raise BootstrapError("LV3_PROXMOX_HOST_PORT must be a valid TCP port")
    return port


def _guest_addresses(payload: dict[str, Any], *, label: str) -> dict[str, str]:
    raw_guests = payload.get("proxmox_guests")
    if not isinstance(raw_guests, list) or not raw_guests:
        raise BootstrapError(f"{label}.proxmox_guests must be a non-empty list")
    addresses: dict[str, str] = {}
    for index, raw_guest in enumerate(raw_guests):
        guest = _mapping(raw_guest, f"{label}.proxmox_guests[{index}]")
        name = _safe_name(guest.get("name"), f"{label}.proxmox_guests[{index}].name")
        address = _ipv4(guest.get("ipv4"), f"{label}.proxmox_guests[{index}].ipv4")
        if name in addresses:
            raise BootstrapError(f"{label}.proxmox_guests contains a duplicate guest")
        addresses[name] = address
    return addresses


def _tracked_guest_addresses(platform_vars: dict[str, Any]) -> dict[str, str]:
    catalog = _mapping(platform_vars.get("platform_guest_catalog"), "platform_guest_catalog")
    by_name = _mapping(catalog.get("by_name"), "platform_guest_catalog.by_name")
    addresses = {
        _safe_name(name, "tracked guest name"): _ipv4(
            _mapping(guest, f"platform_guest_catalog.by_name.{name}").get("ipv4"),
            f"platform_guest_catalog.by_name.{name}.ipv4",
        )
        for name, guest in by_name.items()
    }
    if not addresses:
        raise BootstrapError("platform_guest_catalog.by_name must not be empty")
    return addresses


def _validate_topology_binding(
    topology_file: Path,
    *,
    registry: dict[str, Any],
    platform_vars: dict[str, Any],
    generation: dict[str, Any],
    management_tailscale_ipv4: str,
) -> tuple[str, str, str, int]:
    selected_topology = _load_yaml_mapping(topology_file, "the explicit topology selector")
    source_label = _string(generation.get("host_vars_source"), "platform_generation.host_vars_source")
    source_path = Path(source_label)
    if not source_path.is_absolute():
        source_path = REPO_ROOT / source_path
    try:
        selected_path = topology_file.resolve(strict=True)
        generated_source_path = source_path.resolve(strict=True)
    except OSError:
        raise BootstrapError("the selected or generated topology source cannot be resolved") from None
    if selected_path != generated_source_path:
        raise BootstrapError("the generated platform variables do not match the explicit topology selector")

    selected_guests = _guest_addresses(selected_topology, label="selected topology")
    tracked_guests = _tracked_guest_addresses(platform_vars)
    if selected_guests != tracked_guests:
        raise BootstrapError("the selected topology guest map does not match the generated platform variables")

    tracked_host = _mapping(platform_vars.get("platform_host"), "platform_host")
    tracked_network = _mapping(tracked_host.get("network"), "platform_host.network")
    if selected_topology.get("proxmox_internal_ipv4") != tracked_network.get("internal_ipv4"):
        raise BootstrapError("the selected topology internal network does not match the generated platform variables")

    service_registry = _mapping(registry.get("platform_service_registry"), "platform_service_registry")
    openbao_registry = _mapping(service_registry.get("openbao"), "platform_service_registry.openbao")
    expected_owner = _safe_name(openbao_registry.get("host_group"), "platform_service_registry.openbao.host_group")
    selected_services = _mapping(
        selected_topology.get("platform_service_topology"), "selected platform_service_topology"
    )
    tracked_services = _mapping(platform_vars.get("platform_service_topology"), "platform_service_topology")
    selected_openbao = _mapping(selected_services.get("openbao"), "selected platform_service_topology.openbao")
    tracked_openbao = _mapping(tracked_services.get("openbao"), "platform_service_topology.openbao")
    if selected_openbao.get("owning_vm") != expected_owner or tracked_openbao.get("owning_vm") != expected_owner:
        raise BootstrapError("the selected or generated OpenBao owner does not match the service registry")
    if tracked_openbao.get("private_ip") != selected_guests.get(expected_owner):
        raise BootstrapError("the generated OpenBao private IP does not match the selected topology")

    # ``.local/identity.yml`` deliberately overlays the deployment's
    # management address at generation time.  The committed topology can be a
    # portable baseline (and therefore retain a placeholder or an older
    # address), so bind the controller endpoint to the explicit identity
    # selector rather than that lower-precedence source file.
    controller_ip = _ipv4(management_tailscale_ipv4, "selected management_tailscale_ipv4")
    port_assignments = _mapping(selected_topology.get("platform_port_assignments"), "platform_port_assignments")
    controller_port = port_assignments.get("openbao_proxy_port")
    if isinstance(controller_port, bool) or not isinstance(controller_port, int) or not 1 <= controller_port <= 65535:
        raise BootstrapError("platform_port_assignments.openbao_proxy_port must be a valid TCP port")
    automation_port = port_assignments.get("openbao_http_port")
    if isinstance(automation_port, bool) or not isinstance(automation_port, int) or not 1 <= automation_port <= 65535:
        raise BootstrapError("platform_port_assignments.openbao_http_port must be a valid TCP port")
    tracked_ports = _mapping(platform_vars.get("platform_port_assignments"), "platform_port_assignments")
    if tracked_ports.get("openbao_proxy_port") != controller_port:
        raise BootstrapError("the generated OpenBao proxy port does not match the selected topology")
    if tracked_ports.get("openbao_http_port") != automation_port:
        raise BootstrapError("the generated OpenBao automation port does not match the selected topology")
    tracked_management = _mapping(
        _mapping(platform_vars.get("platform_host"), "platform_host").get("management"), "platform_host.management"
    )
    if _ipv4(tracked_management.get("tailscale_ipv4"), "platform_host.management.tailscale_ipv4") != controller_ip:
        raise BootstrapError("the generated management address does not match the explicit identity selector")
    expected_api_url = _validate_api_url(f"https://{controller_ip}:{controller_port}")
    generated_api_url = _validate_api_url(platform_vars.get("openbao_controller_url"))
    if generated_api_url != expected_api_url:
        raise BootstrapError("the generated OpenBao controller URL does not match the selected topology")
    target_host = selected_guests[expected_owner]
    return generated_api_url, expected_owner, target_host, automation_port


def _secret_path(value: Any, label: str) -> str:
    raw_path = _string(value, label)
    segments = raw_path.split("/")
    if len(segments) != 3 or segments[0] != "services":
        raise BootstrapError(f"{label} must be an exact services/<namespace>/<payload> KV path")
    return "/".join(_safe_name(segment, f"{label} segment") for segment in segments)


def _derive_host_native_contracts(
    path: Path,
    *,
    config_prefix: str,
    protected_approle_names: set[str],
) -> list[ServiceContract]:
    catalog = _load_yaml_mapping(path, "the host-native OpenBao contract catalog")
    raw_contracts = catalog.get("openbao_host_native_service_contracts")
    if not isinstance(raw_contracts, list) or not raw_contracts:
        raise BootstrapError("the host-native OpenBao contract catalog must contain a non-empty contract list")

    contracts: list[ServiceContract] = []
    for index, raw_contract in enumerate(raw_contracts):
        contract = _mapping(raw_contract, f"host-native OpenBao contract {index}")
        registry_key = _safe_name(contract.get("id"), f"host-native OpenBao contract {index}.id")
        secret_path = _secret_path(
            contract.get("secret_path"), f"host-native OpenBao contract {registry_key}.secret_path"
        )
        policy_suffix = _safe_name(
            contract.get("policy_suffix"), f"host-native OpenBao contract {registry_key}.policy_suffix"
        )
        approle_name = _safe_name(
            contract.get("approle_name"), f"host-native OpenBao contract {registry_key}.approle_name"
        )
        if approle_name in protected_approle_names:
            raise BootstrapError("a host-native OpenBao contract collides with a protected AppRole")
        contracts.append(
            ServiceContract(
                registry_key=registry_key,
                secret_namespace=secret_path.split("/")[1],
                secret_path=secret_path,
                policy_name=f"{config_prefix}-{policy_suffix}",
                approle_name=approle_name,
            )
        )
    return contracts


def _derive_contracts(
    registry: dict[str, Any],
    *,
    config_prefix: str,
    namespace_overrides: dict[str, Any],
    protected_approle_names: set[str],
    host_native_contracts_path: Path,
) -> tuple[ServiceContract, ...]:
    service_registry = _mapping(registry.get("platform_service_registry"), "platform_service_registry")
    normalized_overrides: dict[str, str] = {}
    for raw_key, raw_value in namespace_overrides.items():
        key = _safe_name(raw_key, "OpenBao namespace override key")
        value = _safe_name(raw_value, f"OpenBao namespace override for {key}")
        if key not in service_registry:
            raise BootstrapError("an OpenBao namespace override refers to an unknown service")
        normalized_overrides[key] = value

    contracts: list[ServiceContract] = []
    for registry_key in sorted(service_registry):
        key = _safe_name(registry_key, "service registry key")
        service = _mapping(service_registry[registry_key], f"platform_service_registry.{key}")
        service_type = service.get("service_type")
        needs_openbao = service.get("needs_openbao", True)
        if not isinstance(needs_openbao, bool):
            raise BootstrapError(f"platform_service_registry.{key}.needs_openbao must be a boolean")
        if service_type != "docker_compose" or not needs_openbao:
            continue
        namespace = normalized_overrides.get(key, key)
        approle_name = f"{namespace}-runtime"
        if approle_name in protected_approle_names:
            raise BootstrapError("a runtime-service contract collides with a protected OpenBao AppRole")
        contracts.append(
            ServiceContract(
                registry_key=key,
                secret_namespace=namespace,
                secret_path=f"services/{namespace}/runtime-env",
                policy_name=f"{config_prefix}-service-{namespace}-runtime",
                approle_name=approle_name,
            )
        )

    contracts.extend(
        _derive_host_native_contracts(
            host_native_contracts_path,
            config_prefix=config_prefix,
            protected_approle_names=protected_approle_names,
        )
    )

    if not contracts:
        raise BootstrapError("the OpenBao contract catalog contains no managed services")
    for attribute in ("secret_namespace", "secret_path", "policy_name", "approle_name"):
        values = [getattr(contract, attribute) for contract in contracts]
        if len(values) != len(set(values)):
            raise BootstrapError(f"runtime-service contracts contain duplicate {attribute} values")
    return tuple(contracts)


def _service_policy(contract: ServiceContract) -> str:
    return (
        f"# managed-by: script={WORKFLOW_ID} adr=0491\n"
        f"# Generated service policy for {contract.registry_key}.\n"
        f'path "{contract.kv_capability_path}" {{\n'
        '  capabilities = ["read"]\n'
        "}\n"
    )


def _provisioner_policy(contracts: tuple[ServiceContract, ...]) -> str:
    lines = [
        f"# managed-by: script={WORKFLOW_ID} adr=0491",
        "# Generated from registered Compose and host-native OpenBao contracts.",
        "# This identity can write exact runtime payloads and mint credentials only",
        "# for pre-created registered service AppRoles.",
    ]
    for contract in contracts:
        lines.extend(
            [
                f'path "{contract.kv_capability_path}" {{',
                '  capabilities = ["create", "read", "update"]',
                "}",
                "",
                f'path "{contract.role_id_path}" {{',
                '  capabilities = ["read"]',
                "}",
                "",
                f'path "{contract.secret_id_path}" {{',
                '  capabilities = ["create", "update"]',
                "}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def _validate_exact_policy_paths(policies: dict[str, str]) -> None:
    for policy_name, rules in policies.items():
        found_path = False
        for raw_line in rules.splitlines():
            line = raw_line.strip()
            match = HCL_PATH_PATTERN.fullmatch(line)
            if not match:
                continue
            found_path = True
            path = match.group(1)
            if "*" in path or "+" in path or "{{" in path or "}}" in path:
                raise BootstrapError(f"generated OpenBao policy {policy_name} contains a non-exact path")
        if not found_path:
            raise BootstrapError(f"generated OpenBao policy {policy_name} contains no paths")


def load_configuration(
    identity_file: Path,
    topology_file: Path,
    *,
    registry_path: Path = SERVICE_REGISTRY_PATH,
    defaults_path: Path = OPENBAO_DEFAULTS_PATH,
    platform_vars_path: Path = PLATFORM_VARS_PATH,
    host_native_contracts_path: Path = HOST_NATIVE_CONTRACTS_PATH,
) -> BootstrapConfiguration:
    """Load and fail-closed validate every non-secret input before API access."""

    domain, config_prefix, management_tailscale_ipv4 = _validate_identity(identity_file)
    registry = _load_yaml_mapping(registry_path, "the canonical service registry")
    defaults = _load_yaml_mapping(defaults_path, "the OpenBao role defaults")
    platform_vars = _load_yaml_mapping(platform_vars_path, "the generated platform variables")
    generation = _mapping(platform_vars.get("platform_generation"), "platform_generation")
    generated_identity = _mapping(generation.get("identity_overlay"), "platform_generation.identity_overlay")
    if generated_identity.get("platform_domain") != domain:
        raise BootstrapError("the generated platform variables do not match the explicit identity selector")
    generated_prefix = _string(
        generated_identity.get("platform_domain"), "platform_generation.identity_overlay.platform_domain"
    ).split(".", 1)[0]
    if generated_prefix != config_prefix:
        raise BootstrapError("the generated platform identity prefix does not match the explicit selector")
    generated_management_tailscale_ipv4 = _ipv4(
        generated_identity.get("management_tailscale_ipv4"),
        "platform_generation.identity_overlay.management_tailscale_ipv4",
    )
    if generated_management_tailscale_ipv4 != management_tailscale_ipv4:
        raise BootstrapError("the generated management address does not match the explicit identity selector")
    api_url, target_guest, target_host, automation_port = _validate_topology_binding(
        topology_file,
        registry=registry,
        platform_vars=platform_vars,
        generation=generation,
        management_tailscale_ipv4=management_tailscale_ipv4,
    )

    provisioner_role_name = _safe_name(
        defaults.get("openbao_runtime_secret_provisioner_approle_name"),
        "openbao_runtime_secret_provisioner_approle_name",
    )
    if provisioner_role_name != PROVISIONER_ROLE_NAME:
        raise BootstrapError("the canonical runtime-secret provisioner AppRole name has changed")
    protected_raw = defaults.get("openbao_runtime_secret_protected_approle_names")
    if not isinstance(protected_raw, list) or not protected_raw:
        raise BootstrapError("openbao_runtime_secret_protected_approle_names must be a non-empty list")
    protected = {_safe_name(item, "protected OpenBao AppRole name") for item in protected_raw}
    if {"controller-automation", PROVISIONER_ROLE_NAME} - protected:
        raise BootstrapError("the canonical protected AppRole set is incomplete")
    overrides = _mapping(
        defaults.get("openbao_runtime_secret_namespace_overrides", {}),
        "openbao_runtime_secret_namespace_overrides",
    )
    contracts = _derive_contracts(
        registry,
        config_prefix=config_prefix,
        namespace_overrides=overrides,
        protected_approle_names=protected,
        host_native_contracts_path=host_native_contracts_path,
    )
    provisioner_policy_name = f"{config_prefix}-agent-runtime-secret-provisioner"
    policies = {contract.policy_name: _service_policy(contract) for contract in contracts}
    policies[provisioner_policy_name] = _provisioner_policy(contracts)
    roles = {contract.approle_name: DesiredRole(contract.approle_name, contract.policy_name) for contract in contracts}
    roles[PROVISIONER_ROLE_NAME] = DesiredRole(PROVISIONER_ROLE_NAME, provisioner_policy_name)
    _validate_exact_policy_paths(policies)

    return BootstrapConfiguration(
        platform_domain=domain,
        config_prefix=config_prefix,
        api_url=api_url,
        ssh_tunnel=SSHTunnelConfiguration(
            jump_host=management_tailscale_ipv4,
            jump_port=_proxmox_jump_port_from_environment(),
            target_guest=target_guest,
            target_host=target_host,
            remote_port=automation_port,
        ),
        contracts=contracts,
        policies=policies,
        roles=roles,
        provisioner_policy_name=provisioner_policy_name,
        protected_approle_names=tuple(sorted(protected)),
    )


def _normalize_policy(rules: str) -> str:
    """Compare policy semantics while ignoring non-authoritative comments."""

    normalized: list[str] = []
    for raw_line in rules.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        normalized.append(re.sub(r"\s+", " ", line))
    return "\n".join(normalized)


def _duration_seconds(value: Any, label: str) -> int:
    if isinstance(value, bool):
        raise BootstrapError(f"{label} has an invalid duration")
    if isinstance(value, int) and value >= 0:
        return value
    if not isinstance(value, str):
        raise BootstrapError(f"{label} has an invalid duration")
    duration = value.strip().lower()
    match = re.fullmatch(r"(\d+)(s|m|h)?", duration)
    if not match:
        raise BootstrapError(f"{label} has an invalid duration")
    multiplier = {None: 1, "s": 1, "m": 60, "h": 3600}[match.group(2)]
    return int(match.group(1)) * multiplier


def _normalized_policy_names(value: Any, label: str) -> tuple[str, ...]:
    if isinstance(value, str):
        raw_names = [part.strip() for part in value.split(",") if part.strip()]
    elif isinstance(value, list):
        raw_names = [_string(part, label) for part in value]
    else:
        raise BootstrapError(f"{label} has an invalid policy list")
    return tuple(sorted(set(raw_names)))


def _normalized_string_list(value: Any, label: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise BootstrapError(f"{label} has an invalid string list")
    return tuple(sorted({item.strip() for item in value if item.strip()}))


def _role_matches(current: dict[str, Any], desired: DesiredRole) -> bool:
    data = _mapping(current.get("data"), f"OpenBao AppRole {desired.name} response data")
    try:
        return (
            _normalized_policy_names(data.get("token_policies", []), "token_policies") == (desired.policy_name,)
            and data.get("bind_secret_id") is desired.bind_secret_id
            and _duration_seconds(data.get("token_ttl", -1), "token_ttl") == desired.token_ttl_seconds
            and _duration_seconds(data.get("token_max_ttl", -1), "token_max_ttl") == desired.token_max_ttl_seconds
            and _duration_seconds(data.get("token_explicit_max_ttl", -1), "token_explicit_max_ttl")
            == desired.token_explicit_max_ttl_seconds
            and _duration_seconds(data.get("token_period", -1), "token_period") == desired.token_period_seconds
            and data.get("token_num_uses") == desired.token_num_uses
            and data.get("token_type") == desired.token_type
            and data.get("token_no_default_policy") is desired.token_no_default_policy
            and _normalized_string_list(data.get("token_bound_cidrs", []), "token_bound_cidrs")
            == desired.token_bound_cidrs
            and _duration_seconds(data.get("secret_id_ttl", -1), "secret_id_ttl") == desired.secret_id_ttl_seconds
            and data.get("secret_id_num_uses") == desired.secret_id_num_uses
            and _normalized_string_list(data.get("secret_id_bound_cidrs", []), "secret_id_bound_cidrs")
            == desired.secret_id_bound_cidrs
            and data.get("local_secret_ids", False) is desired.local_secret_ids
        )
    except BootstrapError:
        return False


def _health_and_seal_preflight(api: OpenBaoAPI) -> dict[str, Any]:
    health_status, _ = api.request(
        "GET",
        "/v1/sys/health",
        expected_statuses={200, 429, 472, 473, 501, 503},
    )
    _, seal = api.request("GET", "/v1/sys/seal-status", expected_statuses={200})
    if health_status not in {200, 429, 472, 473}:
        raise BootstrapError("OpenBao is sealed, uninitialized, or unavailable")
    if seal.get("initialized") is not True or seal.get("sealed") is not False:
        raise BootstrapError("OpenBao is sealed or uninitialized; this workflow will not alter runtime state")
    return {"health_status": health_status, "initialized": True, "sealed": False}


def _login_breakglass(api: OpenBaoAPI, password: str, expected_policy: str) -> str:
    status_code, response = api.request(
        "POST",
        "/v1/auth/userpass/login/breakglass",
        payload={"password": password},
        expected_statuses={200, 400, 403},
    )
    if status_code != 200:
        raise BootstrapError("OpenBao break-glass userpass authentication failed")
    auth = response.get("auth")
    if not isinstance(auth, dict):
        raise BootstrapError("OpenBao break-glass authentication returned an invalid response")
    token = auth.get("client_token")
    policies = auth.get("policies")
    if not isinstance(token, str) or not token:
        raise BootstrapError("OpenBao break-glass authentication returned no client token")
    if not isinstance(policies, list) or not all(isinstance(item, str) for item in policies):
        raise BootstrapError("OpenBao break-glass authentication returned an invalid policy set")
    policy_set = set(policies)
    if expected_policy not in policy_set or "root" in policy_set or policy_set - {"default", expected_policy}:
        raise BootstrapError("OpenBao break-glass authentication returned an unexpected policy set")
    return token


def _capabilities(api: OpenBaoAPI, token: str, paths: list[str]) -> dict[str, list[str]]:
    _, response = api.request(
        "POST",
        "/v1/sys/capabilities-self",
        payload={"paths": paths},
        token=token,
        expected_statuses={200},
    )
    data = response.get("data")
    if not isinstance(data, dict):
        raise BootstrapError("OpenBao capabilities response has an invalid shape")
    normalized: dict[str, list[str]] = {}
    for path in paths:
        value = data.get(path)
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise BootstrapError("OpenBao capabilities response omitted a requested path")
        normalized[path] = sorted(set(value))
    return normalized


def _management_capability_requirements(configuration: BootstrapConfiguration) -> dict[str, set[str]]:
    requirements: dict[str, set[str]] = {}
    for policy_name in configuration.policies:
        requirements[f"sys/policies/acl/{policy_name}"] = {"create", "read", "update"}
    for role_name in configuration.roles:
        base = f"auth/approle/role/{role_name}"
        requirements[base] = {"create", "read", "update"}
    provisioner_base = f"auth/approle/role/{PROVISIONER_ROLE_NAME}"
    requirements[f"{provisioner_base}/role-id"] = {"read"}
    requirements[f"{provisioner_base}/secret-id"] = {"create", "update"}
    requirements[f"{provisioner_base}/secret-id-accessor/destroy"] = {"update"}
    return requirements


def _preflight_management_capabilities(
    api: OpenBaoAPI,
    token: str,
    configuration: BootstrapConfiguration,
) -> None:
    requirements = _management_capability_requirements(configuration)
    effective = _capabilities(api, token, list(requirements))
    for path, required in requirements.items():
        if not required.issubset(effective[path]):
            raise BootstrapError("the break-glass token lacks a required bounded management capability")


def _inspect_remote_state(
    api: OpenBaoAPI,
    token: str,
    configuration: BootstrapConfiguration,
) -> tuple[list[str], list[str]]:
    policy_drift: list[str] = []
    role_drift: list[str] = []
    for policy_name, desired_rules in configuration.policies.items():
        status_code, current = api.request(
            "GET",
            f"/v1/sys/policies/acl/{policy_name}",
            token=token,
            expected_statuses={200, 404},
        )
        if status_code == 404:
            policy_drift.append(policy_name)
            continue
        data = _mapping(current.get("data"), f"OpenBao policy {policy_name} response data")
        current_rules = data.get("rules", data.get("policy"))
        if not isinstance(current_rules, str) or _normalize_policy(current_rules) != _normalize_policy(desired_rules):
            policy_drift.append(policy_name)

    for role_name, desired_role in configuration.roles.items():
        status_code, current = api.request(
            "GET",
            f"/v1/auth/approle/role/{role_name}",
            token=token,
            expected_statuses={200, 404},
        )
        if status_code == 404 or not _role_matches(current, desired_role):
            role_drift.append(role_name)
    return policy_drift, role_drift


def _apply_remote_plan(
    api: OpenBaoAPI,
    token: str,
    configuration: BootstrapConfiguration,
    policy_drift: list[str],
    role_drift: list[str],
) -> None:
    # Policies are established before identities can receive them. Service
    # identities are reconciled before the provisioner identity itself.
    ordered_policies = [name for name in policy_drift if name != configuration.provisioner_policy_name]
    if configuration.provisioner_policy_name in policy_drift:
        ordered_policies.append(configuration.provisioner_policy_name)
    for policy_name in ordered_policies:
        api.request(
            "PUT",
            f"/v1/sys/policies/acl/{policy_name}",
            payload={"policy": configuration.policies[policy_name]},
            token=token,
            expected_statuses={204},
        )

    ordered_roles = [name for name in role_drift if name != PROVISIONER_ROLE_NAME]
    if PROVISIONER_ROLE_NAME in role_drift:
        ordered_roles.append(PROVISIONER_ROLE_NAME)
    for role_name in ordered_roles:
        api.request(
            "POST",
            f"/v1/auth/approle/role/{role_name}",
            payload=configuration.roles[role_name].api_payload,
            token=token,
            expected_statuses={204},
        )


def _read_file_snapshot(path: Path) -> tuple[FileSnapshot, bytes | None]:
    try:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
    except FileNotFoundError:
        return FileSnapshot(False), None
    except OSError:
        raise BootstrapError(f"sensitive local file {path.name} could not be opened safely") from None
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise BootstrapError(f"sensitive local file {path.name} must be a regular file")
        if metadata.st_uid != os.getuid():
            raise BootstrapError(f"sensitive local file {path.name} must be owned by the current operator")
        if stat.S_IMODE(metadata.st_mode) != 0o600:
            raise BootstrapError(f"sensitive local file {path.name} must have mode 0600")
        if metadata.st_size > MAX_ARTIFACT_BYTES:
            raise BootstrapError(f"sensitive local file {path.name} is unexpectedly large")
        chunks: list[bytes] = []
        remaining = MAX_ARTIFACT_BYTES + 1
        while remaining > 0:
            chunk = os.read(descriptor, min(remaining, 8192))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        content = b"".join(chunks)
        if len(content) > MAX_ARTIFACT_BYTES:
            raise BootstrapError(f"sensitive local file {path.name} is unexpectedly large")
        after = os.fstat(descriptor)
        if (metadata.st_ino, metadata.st_dev, metadata.st_size, metadata.st_mtime_ns) != (
            after.st_ino,
            after.st_dev,
            after.st_size,
            after.st_mtime_ns,
        ):
            raise BootstrapError(f"sensitive local file {path.name} changed while it was being read")
        snapshot = FileSnapshot(
            True,
            device=after.st_dev,
            inode=after.st_ino,
            size=after.st_size,
            mtime_ns=after.st_mtime_ns,
            digest=hashlib.sha256(content).hexdigest(),
        )
        return snapshot, content
    finally:
        os.close(descriptor)


def _snapshot_matches(left: FileSnapshot, right: FileSnapshot) -> bool:
    if left.exists != right.exists:
        return False
    if not left.exists:
        return True
    return (
        left.device == right.device
        and left.inode == right.inode
        and left.size == right.size
        and left.mtime_ns == right.mtime_ns
        and isinstance(left.digest, str)
        and isinstance(right.digest, str)
        and hmac.compare_digest(left.digest, right.digest)
    )


def _inspect_artifact(path: Path) -> ArtifactInspection:
    snapshot, content = _read_file_snapshot(path)
    if not snapshot.exists or content is None:
        return ArtifactInspection(snapshot, None, "missing")
    try:
        raw = json.loads(content)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return ArtifactInspection(snapshot, None, "stale")
    if not isinstance(raw, dict):
        return ArtifactInspection(snapshot, None, "stale")
    role_name = raw.get("role_name")
    auth_path = raw.get("auth_path", "approle")
    if role_name not in {None, PROVISIONER_ROLE_NAME} or auth_path != "approle":
        raise BootstrapError("the provisioner artifact belongs to a different identity and will not be overwritten")
    required = ("role_id", "secret_id")
    if any(
        not isinstance(raw.get(key), str) or not raw[key] or len(raw[key]) > MAX_SECRET_FILE_BYTES for key in required
    ):
        return ArtifactInspection(snapshot, None, "stale")
    payload = {
        "role_name": PROVISIONER_ROLE_NAME,
        "auth_path": "approle",
        "role_id": raw["role_id"],
        "secret_id": raw["secret_id"],
    }
    accessor = raw.get("secret_id_accessor")
    generated_at = raw.get("generated_at")
    if isinstance(accessor, str) and accessor:
        payload["secret_id_accessor"] = accessor
    if isinstance(generated_at, str) and generated_at:
        payload["generated_at"] = generated_at
    return ArtifactInspection(snapshot, payload, "candidate")


def _ensure_secure_directory(path: Path, *, create: bool) -> None:
    try:
        if create:
            path.mkdir(parents=True, mode=0o700, exist_ok=True)
        metadata = path.lstat()
    except FileNotFoundError:
        raise BootstrapError("the controller-local OpenBao output directory is missing") from None
    except OSError:
        raise BootstrapError("the controller-local OpenBao output directory could not be prepared") from None
    if not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
        raise BootstrapError("the controller-local OpenBao output path must be a real directory")
    if metadata.st_uid != os.getuid():
        raise BootstrapError("the controller-local OpenBao output directory must be operator-owned")
    if stat.S_IMODE(metadata.st_mode) & 0o022:
        raise BootstrapError("the controller-local OpenBao output directory must not be group/world writable")


def _atomic_sensitive_write(
    path: Path,
    content: bytes,
    *,
    expected_snapshot: FileSnapshot,
    before_replace: Callable[[], None] | None = None,
) -> None:
    """Write a sensitive file atomically without clobbering a raced artifact."""

    current, _ = _read_file_snapshot(path)
    if not _snapshot_matches(expected_snapshot, current):
        raise BootstrapError(f"sensitive local file {path.name} changed concurrently; refusing to overwrite it")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        if before_replace is not None:
            before_replace()
        latest, _ = _read_file_snapshot(path)
        if not _snapshot_matches(expected_snapshot, latest):
            raise BootstrapError(f"sensitive local file {path.name} changed concurrently; refusing to overwrite it")
        if expected_snapshot.exists:
            os.replace(temporary_path, path)
        else:
            try:
                os.link(temporary_path, path)
            except FileExistsError:
                raise BootstrapError(
                    f"sensitive local file {path.name} appeared concurrently; refusing to overwrite it"
                ) from None
            temporary_path.unlink()
        path.chmod(0o600)
        directory_descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    finally:
        try:
            os.close(descriptor)
        except OSError:
            pass
        temporary_path.unlink(missing_ok=True)


def _atomic_receipt_write(path: Path, payload: dict[str, Any], *, expected_snapshot: FileSnapshot) -> None:
    content = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    _atomic_sensitive_write(path, content, expected_snapshot=expected_snapshot)


def _invalidate_success_receipt(path: Path, *, expected_snapshot: FileSnapshot) -> Path | None:
    """Move prior success evidence aside before any remote mutation begins."""

    latest, _ = _read_file_snapshot(path)
    if not _snapshot_matches(expected_snapshot, latest):
        raise BootstrapError("the bootstrap receipt changed concurrently; refusing to mutate OpenBao")
    if not expected_snapshot.exists:
        return None
    descriptor, backup_name = tempfile.mkstemp(prefix=f".{path.name}.superseded-", dir=path.parent)
    os.close(descriptor)
    backup_path = Path(backup_name)
    backup_path.unlink()
    try:
        os.replace(path, backup_path)
        directory_descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except OSError:
        backup_path.unlink(missing_ok=True)
        raise BootstrapError("the prior bootstrap receipt could not be invalidated safely") from None
    return backup_path


def _read_breakglass_password(path: Path) -> str:
    snapshot, content = _read_file_snapshot(path)
    if not snapshot.exists or content is None:
        raise BootstrapError("the break-glass password file is missing")
    if not content or len(content) > MAX_SECRET_FILE_BYTES:
        raise BootstrapError("the break-glass password file has an invalid size")
    try:
        password = content.decode("utf-8").rstrip("\r\n")
    except UnicodeDecodeError:
        raise BootstrapError("the break-glass password file is not valid text") from None
    if not password or "\n" in password or "\r" in password or "\x00" in password:
        raise BootstrapError("the break-glass password file must contain exactly one non-empty line")
    return password


def _validate_controller_paths(output_root: Path, breakglass_password_file: Path) -> tuple[Path, Path]:
    """Bind sensitive inputs and outputs to the shared controller-local root."""

    canonical_output_root = Path(os.path.abspath(local_overlay_root(REPO_ROOT) / "openbao"))
    selected_output_root = Path(os.path.abspath(output_root.expanduser()))
    if selected_output_root != canonical_output_root:
        raise BootstrapError("--output-root must select the shared controller-local OpenBao directory")
    canonical_password_file = canonical_output_root / "breakglass-password.txt"
    selected_password_file = Path(os.path.abspath(breakglass_password_file.expanduser()))
    if selected_password_file != canonical_password_file:
        raise BootstrapError("--breakglass-password-file must select the governed controller-local password file")
    return selected_output_root, selected_password_file


def _validate_ssh_private_key(path: Path) -> Path:
    """Accept only a real, operator-owned mode-0600 SSH private-key file."""

    selected = Path(os.path.abspath(path.expanduser()))
    try:
        descriptor = os.open(selected, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError:
        raise BootstrapError("the SSH private key must be a regular operator-owned mode-0600 file") from None
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid():
            raise BootstrapError("the SSH private key must be a regular operator-owned mode-0600 file")
        if stat.S_IMODE(metadata.st_mode) != 0o600:
            raise BootstrapError("the SSH private key must be a regular operator-owned mode-0600 file")
        if not 0 < metadata.st_size <= MAX_ARTIFACT_BYTES:
            raise BootstrapError("the SSH private key must be a non-empty regular operator-owned mode-0600 file")
    finally:
        os.close(descriptor)
    return selected


def _reserve_loopback_port() -> int:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(("127.0.0.1", 0))
            return int(listener.getsockname()[1])
    except OSError:
        raise BootstrapError("a loopback port for the OpenBao SSH tunnel could not be reserved") from None


def _build_ssh_tunnel_command(
    configuration: BootstrapConfiguration,
    ssh_private_key_file: Path,
    *,
    local_port: int,
    ssh_jump_alias: str | None = None,
) -> list[str]:
    if not 1 <= local_port <= 65535:
        raise BootstrapError("the OpenBao SSH tunnel local port is invalid")
    jump_host = _ipv4(configuration.ssh_tunnel.jump_host, "OpenBao SSH jump host")
    jump_port = configuration.ssh_tunnel.jump_port
    target_host = _ipv4(configuration.ssh_tunnel.target_host, "OpenBao SSH target host")
    if isinstance(jump_port, bool) or not isinstance(jump_port, int) or not 1 <= jump_port <= 65535:
        raise BootstrapError("the OpenBao SSH tunnel jump port is invalid")
    remote_port = configuration.ssh_tunnel.remote_port
    if isinstance(remote_port, bool) or not isinstance(remote_port, int) or not 1 <= remote_port <= 65535:
        raise BootstrapError("the OpenBao SSH tunnel remote port is invalid")
    key_path = str(ssh_private_key_file)
    selected_jump_alias = _ssh_host_alias(ssh_jump_alias, "the OpenBao SSH jump alias")
    if selected_jump_alias is not None:
        # A local SSH alias is the only safe way to select a managed route
        # whose Proxmox hop has a distinct management key.  The alias is
        # constrained to a host-token, and OpenSSH resolves its identity and
        # host-key policy; the outer connection still uses the explicit guest
        # bootstrap key and selector-derived target.
        proxy_command = shlex.join(
            [
                SSH_BINARY,
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=10",
                "-o",
                "LogLevel=ERROR",
                "-o",
                "StrictHostKeyChecking=yes",
                "-W",
                "[%h]:%p",
                selected_jump_alias,
            ]
        )
    else:
        proxy_command = shlex.join(
            [
                SSH_BINARY,
                "-i",
                key_path,
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=10",
                "-o",
                "IdentitiesOnly=yes",
                "-o",
                "LogLevel=ERROR",
                "-o",
                "StrictHostKeyChecking=yes",
                "-p",
                str(jump_port),
                "-W",
                "%h:%p",
                f"{SSH_USER}@{jump_host}",
            ]
        )
    return [
        SSH_BINARY,
        "-i",
        key_path,
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=10",
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "LogLevel=ERROR",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        f"ProxyCommand={proxy_command}",
        "-o",
        "ExitOnForwardFailure=yes",
        "-T",
        "-N",
        "-L",
        f"127.0.0.1:{local_port}:127.0.0.1:{remote_port}",
        f"{SSH_USER}@{target_host}",
    ]


def _wait_for_ssh_tunnel(process: subprocess.Popen[bytes], local_port: int) -> None:
    deadline = time.monotonic() + SSH_TUNNEL_START_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise BootstrapError("the OpenBao SSH tunnel could not be established")
        try:
            with socket.create_connection(("127.0.0.1", local_port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.1)
    raise BootstrapError("the OpenBao SSH tunnel did not become ready in time")


def _stop_ssh_tunnel(process: subprocess.Popen[bytes]) -> None:
    try:
        if process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=SSH_TUNNEL_STOP_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=SSH_TUNNEL_STOP_TIMEOUT_SECONDS)
    except (OSError, subprocess.SubprocessError):
        # Cleanup is best-effort and must not hide the bounded bootstrap result.
        return


@contextmanager
def _open_ssh_tunnel(
    configuration: BootstrapConfiguration,
    ssh_private_key_file: Path,
    *,
    ssh_jump_alias: str | None = None,
) -> Iterator[str]:
    key_file = _validate_ssh_private_key(ssh_private_key_file)
    local_port = _reserve_loopback_port()
    command = _build_ssh_tunnel_command(
        configuration,
        key_file,
        local_port=local_port,
        ssh_jump_alias=ssh_jump_alias,
    )
    try:
        # The binary is fixed and every host/port argv value is selector-validated; shell is never used.
        process = subprocess.Popen(  # nosec B603
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        raise BootstrapError("the OpenBao SSH tunnel process could not be started") from None
    try:
        _wait_for_ssh_tunnel(process, local_port)
        yield _validate_api_url(f"http://127.0.0.1:{local_port}")
    finally:
        _stop_ssh_tunnel(process)


def _artifact_login(api: OpenBaoAPI, artifact: dict[str, str]) -> tuple[str, list[str]]:
    status_code, response = api.request(
        "POST",
        "/v1/auth/approle/login",
        payload={"role_id": artifact["role_id"], "secret_id": artifact["secret_id"]},
        expected_statuses={200, 400, 403},
    )
    if status_code != 200:
        raise BootstrapError("the runtime-secret provisioner credential is stale")
    auth = response.get("auth")
    if not isinstance(auth, dict):
        raise BootstrapError("the runtime-secret provisioner login response is invalid")
    token = auth.get("client_token")
    policies = auth.get("policies")
    if not isinstance(token, str) or not token or not isinstance(policies, list):
        raise BootstrapError("the runtime-secret provisioner login response is invalid")
    if not all(isinstance(policy, str) for policy in policies):
        raise BootstrapError("the runtime-secret provisioner policy response is invalid")
    return token, policies


def _provisioner_capability_expectations(
    configuration: BootstrapConfiguration,
) -> tuple[dict[str, list[str]], list[str]]:
    allowed: dict[str, list[str]] = {}
    denied: set[str] = {
        "sys/policies/acl",
        "auth/approle/role",
        f"sys/policies/acl/{configuration.provisioner_policy_name}",
    }
    for contract in configuration.contracts:
        allowed[contract.kv_capability_path] = ["create", "read", "update"]
        allowed[contract.role_id_path] = ["read"]
        allowed[contract.secret_id_path] = ["create", "update"]
        denied.update(
            {
                contract.role_path,
                f"sys/policies/acl/{contract.policy_name}",
                f"kv/data/services/{contract.secret_namespace}/__contract_probe__",
                f"{contract.kv_capability_path}/__contract_probe__",
            }
        )
    for role_name in configuration.protected_approle_names:
        base = f"auth/approle/role/{role_name}"
        denied.update(
            {
                base,
                f"{base}/role-id",
                f"{base}/secret-id",
                f"{base}/secret-id-accessor/destroy",
            }
        )
    overlap = set(allowed) & denied
    if overlap:
        raise BootstrapError("the provisioner allow and deny capability plans overlap")
    return allowed, sorted(denied)


def _verify_provisioner(
    api: OpenBaoAPI,
    artifact: dict[str, str],
    configuration: BootstrapConfiguration,
) -> VerificationSummary:
    token, policies = _artifact_login(api, artifact)
    policy_set = set(policies)
    if (
        configuration.provisioner_policy_name not in policy_set
        or "root" in policy_set
        or policy_set - {"default", configuration.provisioner_policy_name}
    ):
        raise BootstrapError("the runtime-secret provisioner received an unsafe policy set")
    allowed, denied = _provisioner_capability_expectations(configuration)
    effective = _capabilities(api, token, [*allowed, *denied])
    for path, expected in allowed.items():
        if effective[path] != sorted(expected):
            raise BootstrapError("the runtime-secret provisioner has an incorrect exact-path allow capability")
    for path in denied:
        if effective[path] != ["deny"]:
            raise BootstrapError("the runtime-secret provisioner has access outside its bounded contract")
    return VerificationSummary(True, True, len(allowed), len(denied))


def _mint_provisioner_artifact(
    api: OpenBaoAPI,
    admin_token: str,
) -> dict[str, str]:
    base = f"/v1/auth/approle/role/{PROVISIONER_ROLE_NAME}"
    _, role_response = api.request("GET", f"{base}/role-id", token=admin_token, expected_statuses={200})
    role_data = role_response.get("data")
    if not isinstance(role_data, dict) or not isinstance(role_data.get("role_id"), str) or not role_data["role_id"]:
        raise BootstrapError("OpenBao did not return a provisioner role ID")
    _, secret_response = api.request(
        "POST",
        f"{base}/secret-id",
        payload={},
        token=admin_token,
        expected_statuses={200},
    )
    secret_data = secret_response.get("data")
    if not isinstance(secret_data, dict):
        raise BootstrapError("OpenBao did not return a provisioner secret ID")
    secret_id = secret_data.get("secret_id")
    accessor = secret_data.get("secret_id_accessor")
    if not isinstance(secret_id, str) or not secret_id or not isinstance(accessor, str) or not accessor:
        raise BootstrapError("OpenBao did not return a complete provisioner credential")
    return {
        "role_name": PROVISIONER_ROLE_NAME,
        "auth_path": "approle",
        "role_id": role_data["role_id"],
        "secret_id": secret_id,
        "secret_id_accessor": accessor,
        "generated_at": datetime.now(UTC).isoformat(),
    }


def _revoke_provisioner_secret_id_accessor(
    api: OpenBaoAPI,
    admin_token: str,
    accessor: str,
) -> None:
    if not accessor:
        raise BootstrapError("the minted provisioner credential has no revocation accessor")
    api.request(
        "POST",
        f"/v1/auth/approle/role/{PROVISIONER_ROLE_NAME}/secret-id-accessor/destroy",
        payload={"secret_id_accessor": accessor},
        token=admin_token,
        expected_statuses={204},
    )


def _configuration_hashes(configuration: BootstrapConfiguration) -> tuple[str, str]:
    contract_payload = [
        {
            "approle_name": contract.approle_name,
            "policy_name": contract.policy_name,
            "registry_key": contract.registry_key,
            "secret_namespace": contract.secret_namespace,
            "secret_path": contract.secret_path,
        }
        for contract in configuration.contracts
    ]
    contract_bytes = json.dumps(contract_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    normalized_policies = {name: _normalize_policy(rules) for name, rules in sorted(configuration.policies.items())}
    policy_bytes = json.dumps(normalized_policies, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(contract_bytes).hexdigest(), hashlib.sha256(policy_bytes).hexdigest()


def _receipt_payload(
    configuration: BootstrapConfiguration,
    health: dict[str, Any],
    verification: VerificationSummary,
    *,
    artifact_action: str,
    remote_changed: bool,
) -> dict[str, Any]:
    contract_hash, policy_hash = _configuration_hashes(configuration)
    return {
        "schema_version": 1,
        "workflow": WORKFLOW_ID,
        "verified_at": datetime.now(UTC).isoformat(),
        "identity": {
            "platform_domain": configuration.platform_domain,
            "config_prefix": configuration.config_prefix,
        },
        "openbao": {
            "endpoint": configuration.api_url,
            "access_mode": "ssh_loopback_forward",
            "target_guest": configuration.ssh_tunnel.target_guest,
            "jump_port": configuration.ssh_tunnel.jump_port,
            "automation_listener_port": configuration.ssh_tunnel.remote_port,
            "health_status": health["health_status"],
            "initialized": health["initialized"],
            "sealed": health["sealed"],
        },
        "contracts": {
            "count": len(configuration.contracts),
            "sha256": contract_hash,
        },
        "desired_state": {
            "policy_count": len(configuration.policies),
            "approle_count": len(configuration.roles),
            "policy_bundle_sha256": policy_hash,
            "remote_changed": remote_changed,
        },
        "provisioner": {
            "role_name": PROVISIONER_ROLE_NAME,
            "policy_name": configuration.provisioner_policy_name,
            "artifact_filename": ARTIFACT_FILENAME,
            "artifact_action": artifact_action,
            "login_verified": verification.login_verified,
            "policy_set_verified": verification.policy_set_verified,
            "allow_capabilities_verified": True,
            "deny_capabilities_verified": True,
            "allow_path_count": verification.allow_path_count,
            "deny_path_count": verification.deny_path_count,
        },
    }


def _verify_candidate_if_possible(
    api: OpenBaoAPI,
    artifact: ArtifactInspection,
    configuration: BootstrapConfiguration,
) -> tuple[bool, VerificationSummary | None]:
    if artifact.payload is None:
        return False, None
    try:
        return True, _verify_provisioner(api, artifact.payload, configuration)
    except BootstrapError:
        return False, None


def reconcile(
    api: OpenBaoAPI,
    configuration: BootstrapConfiguration,
    *,
    breakglass_password: str,
    output_root: Path,
    apply: bool,
) -> dict[str, Any]:
    """Check or apply the bounded bootstrap, returning only non-secret facts."""

    _ensure_secure_directory(output_root, create=apply)
    artifact_path = output_root / ARTIFACT_FILENAME
    receipt_path = output_root / RECEIPT_FILENAME
    try:
        lock_descriptor = os.open(
            output_root,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
    except OSError:
        raise BootstrapError("the controller-local OpenBao output directory could not be locked safely") from None
    try:
        lock_metadata = os.fstat(lock_descriptor)
        if not stat.S_ISDIR(lock_metadata.st_mode) or lock_metadata.st_uid != os.getuid():
            raise BootstrapError("the controller-local OpenBao output directory must remain operator-owned")
        fcntl.flock(lock_descriptor, fcntl.LOCK_EX)
        artifact = _inspect_artifact(artifact_path)
        receipt_snapshot = _read_file_snapshot(receipt_path)[0] if apply else FileSnapshot(False)
        health = _health_and_seal_preflight(api)
        admin_token = _login_breakglass(
            api,
            breakglass_password,
            f"{configuration.config_prefix}-breakglass",
        )
        _preflight_management_capabilities(api, admin_token, configuration)
        policy_drift, role_drift = _inspect_remote_state(api, admin_token, configuration)
        credential_valid, verification = _verify_candidate_if_possible(api, artifact, configuration)

        if not apply:
            converged = not policy_drift and not role_drift and credential_valid
            return {
                "status": "ok" if converged else "drift",
                "mode": "check",
                "changed": False,
                "converged": converged,
                "contract_count": len(configuration.contracts),
                "policy_drift_count": len(policy_drift),
                "approle_drift_count": len(role_drift),
                "artifact_state": "valid"
                if credential_valid
                else ("missing" if artifact.state == "missing" else "stale"),
                "verification": {
                    "login": bool(verification and verification.login_verified),
                    "allow_path_count": 0 if verification is None else verification.allow_path_count,
                    "deny_path_count": 0 if verification is None else verification.deny_path_count,
                },
                "receipt_emitted": False,
            }

        remote_changed = bool(policy_drift or role_drift)
        if remote_changed or not credential_valid:
            _invalidate_success_receipt(receipt_path, expected_snapshot=receipt_snapshot)
            receipt_snapshot = FileSnapshot(False)
        _apply_remote_plan(api, admin_token, configuration, policy_drift, role_drift)
        remaining_policy_drift, remaining_role_drift = _inspect_remote_state(api, admin_token, configuration)
        if remaining_policy_drift or remaining_role_drift:
            raise BootstrapError("OpenBao did not retain the complete bounded policy/AppRole plan")

        credential_valid, verification = _verify_candidate_if_possible(api, artifact, configuration)
        artifact_action = "preserved"
        minted_accessor: str | None = None
        try:
            if credential_valid:
                latest, _ = _read_file_snapshot(artifact_path)
                if not _snapshot_matches(artifact.snapshot, latest):
                    raise BootstrapError("the provisioner artifact changed concurrently during verification")
                effective_artifact = artifact.payload
            else:
                effective_artifact = _mint_provisioner_artifact(api, admin_token)
                minted_accessor = effective_artifact["secret_id_accessor"]
                verification = _verify_provisioner(api, effective_artifact, configuration)
                encoded = (json.dumps(effective_artifact, indent=2, sort_keys=True) + "\n").encode("utf-8")
                _atomic_sensitive_write(artifact_path, encoded, expected_snapshot=artifact.snapshot)
                artifact_action = "created" if artifact.state == "missing" else "refreshed"
                persisted = _inspect_artifact(artifact_path)
                if persisted.payload is None:
                    raise BootstrapError("the provisioner artifact failed secure read-back validation")
                verification = _verify_provisioner(api, persisted.payload, configuration)

            if effective_artifact is None or verification is None:
                raise BootstrapError("the runtime-secret provisioner could not be verified")
            receipt = _receipt_payload(
                configuration,
                health,
                verification,
                artifact_action=artifact_action,
                remote_changed=remote_changed,
            )
            _atomic_receipt_write(receipt_path, receipt, expected_snapshot=receipt_snapshot)
        except BaseException:
            if minted_accessor is not None:
                try:
                    _revoke_provisioner_secret_id_accessor(api, admin_token, minted_accessor)
                except BootstrapError:
                    raise BootstrapError(
                        "bootstrap failed after credential minting and automatic revocation also failed"
                    ) from None
            raise
        return {
            "status": "ok",
            "mode": "apply",
            "changed": remote_changed or artifact_action != "preserved",
            "converged": True,
            "contract_count": len(configuration.contracts),
            "policy_changes": len(policy_drift),
            "approle_changes": len(role_drift),
            "artifact_action": artifact_action,
            "verification": {
                "login": True,
                "allow_path_count": verification.allow_path_count,
                "deny_path_count": verification.deny_path_count,
            },
            "receipt_emitted": True,
            "receipt_filename": RECEIPT_FILENAME,
        }
    finally:
        try:
            fcntl.flock(lock_descriptor, fcntl.LOCK_UN)
        finally:
            os.close(lock_descriptor)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Reconcile the bounded OpenBao runtime-secret provisioner without altering OpenBao runtime state.",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--check", action="store_true", help="Report drift without changing policies, AppRoles, or files."
    )
    mode.add_argument(
        "--apply", action="store_true", help="Apply the exact bounded policy/AppRole plan and emit evidence."
    )
    parser.add_argument(
        "--identity-file",
        type=Path,
        required=True,
        help="Explicit concrete deployment identity selector.",
    )
    parser.add_argument(
        "--topology-file",
        type=Path,
        required=True,
        help="Explicit deployment topology selector already represented by generated platform variables.",
    )
    parser.add_argument(
        "--breakglass-password-file",
        type=Path,
        required=True,
        help="Mode-0600 file containing the break-glass userpass password; the password itself is never accepted on argv.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        required=True,
        help="Controller-local OpenBao directory for the provisioner artifact and non-secret receipt.",
    )
    parser.add_argument(
        "--ssh-private-key-file",
        type=Path,
        required=True,
        help="Mode-0600 private key used for the selector-derived ops SSH jump to the OpenBao automation listener.",
    )
    parser.add_argument(
        "--ssh-jump-alias",
        default=os.environ.get("LV3_OPENBAO_SSH_JUMP_ALIAS", "") or None,
        help=(
            "Optional local OpenSSH host alias for the management hop. Use this when the "
            "Proxmox host requires a distinct management key; the alias is never treated as a shell command."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        configuration = load_configuration(
            args.identity_file.expanduser().resolve(),
            args.topology_file.expanduser().resolve(),
        )
        output_root, password_file = _validate_controller_paths(args.output_root, args.breakglass_password_file)
        with _open_ssh_tunnel(
            configuration,
            args.ssh_private_key_file,
            ssh_jump_alias=_ssh_host_alias(args.ssh_jump_alias, "--ssh-jump-alias"),
        ) as tunnel_url:
            password = _read_breakglass_password(password_file)
            api = HTTPOpenBaoAPI(tunnel_url)
            result = reconcile(
                api,
                configuration,
                breakglass_password=password,
                output_root=output_root,
                apply=args.apply,
            )
    except BootstrapError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # pragma: no cover - last-resort secret-safe boundary
        print(f"ERROR: bootstrap failed unexpectedly ({type(exc).__name__})", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("converged") else 1


if __name__ == "__main__":
    raise SystemExit(main())
