#!/usr/bin/env python3

from __future__ import annotations

import argparse
import base64
import copy
import datetime as dt
import hashlib
import json
import os
import re
import secrets
import string
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from controller_automation_toolkit import emit_cli_error, load_json, load_yaml, repo_path
from mutation_audit import build_event, emit_event


ROSTER_PATH = repo_path("config", "operators.yaml")
ROSTER_SCHEMA_PATH = repo_path("config", "schemas", "operators.schema.json")
POLICY_DIR = repo_path("config", "openbao", "policies")
STATE_DIR = repo_path(".local", "state", "operator-access")
KEYCLOAK_BOOTSTRAP_PASSWORD_PATH = repo_path(".local", "keycloak", "bootstrap-admin-password.txt")
OPENBAO_INIT_PATH = repo_path(".local", "openbao", "init.json")
TAILSCALE_API_KEY_PATH = repo_path(".local", "tailscale", "api-key.txt")
SERVICE_CATALOG_PATH = repo_path("config", "service-capability-catalog.json")

KEYCLOAK_REALM = "lv3"
KEYCLOAK_BOOTSTRAP_ADMIN = "lv3-bootstrap-admin"
ROLE_NAMES = {"admin", "operator", "viewer"}
STATUS_NAMES = {"active", "inactive"}
ISO8601_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
OPERATOR_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*$")
KEYCLOAK_USERNAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
SSH_PUBKEY_PREFIXES = {"ssh-ed25519", "ssh-rsa", "ecdsa-sha2-nistp256", "ecdsa-sha2-nistp384", "ecdsa-sha2-nistp521"}


@dataclass(frozen=True)
class RoleDefinition:
    keycloak_roles: tuple[str, ...]
    keycloak_groups: tuple[str, ...]
    openbao_policies: tuple[str, ...]
    tailscale_tags: tuple[str, ...]
    ssh_enabled: bool


ROLE_DEFINITIONS: dict[str, RoleDefinition] = {
    "admin": RoleDefinition(
        keycloak_roles=("platform-admin",),
        keycloak_groups=("lv3-platform-admins", "grafana-admins"),
        openbao_policies=("platform-admin",),
        tailscale_tags=("tag:platform-operator",),
        ssh_enabled=True,
    ),
    "operator": RoleDefinition(
        keycloak_roles=("platform-operator",),
        keycloak_groups=("lv3-platform-operators", "grafana-viewers"),
        openbao_policies=("platform-operator",),
        tailscale_tags=("tag:platform-operator",),
        ssh_enabled=True,
    ),
    "viewer": RoleDefinition(
        keycloak_roles=("platform-read",),
        keycloak_groups=("lv3-platform-viewers", "grafana-viewers"),
        openbao_policies=("platform-read",),
        tailscale_tags=("tag:platform-operator",),
        ssh_enabled=False,
    ),
}

OPENBAO_POLICY_GROUPS = {
    "platform-admin": "platform-admin.hcl",
    "platform-operator": "platform-operator.hcl",
    "platform-read": "platform-read.hcl",
}


class OperatorManagerError(RuntimeError):
    pass


class OperatorBackend(Protocol):
    def ensure_prerequisites(self) -> dict[str, Any]:
        ...

    def onboard_operator(self, operator: dict[str, Any], bootstrap_password: str) -> dict[str, Any]:
        ...

    def offboard_operator(self, operator: dict[str, Any], reason: str | None) -> dict[str, Any]:
        ...

    def recover_totp(self, operator: dict[str, Any]) -> dict[str, Any]:
        ...

    def reset_password(self, operator: dict[str, Any], password: str, *, temporary: bool) -> dict[str, Any]:
        ...

    def inventory_operator(self, operator: dict[str, Any], state: dict[str, Any], offline: bool) -> dict[str, Any]:
        ...

    def quarterly_review(self, review: dict[str, Any]) -> dict[str, Any]:
        ...


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def get_yaml_module():
    try:
        import yaml
    except ModuleNotFoundError as exc:  # pragma: no cover - runtime dependency guard
        raise OperatorManagerError(
            "Missing dependency: PyYAML. Run via 'uvx --from pyyaml python ...' or 'uv run --with pyyaml ...'."
        ) from exc
    return yaml


def slugify(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return normalized or "operator"


def default_username(name: str, email: str) -> str:
    local = email.split("@", 1)[0].strip().lower()
    if KEYCLOAK_USERNAME_PATTERN.match(local):
        return local
    return slugify(name)


def normalize_ssh_public_key(value: str) -> str:
    candidate = value.strip()
    if candidate.startswith("@"):
        candidate = Path(candidate[1:]).read_text(encoding="utf-8").strip()
    if not candidate:
        raise OperatorManagerError("SSH public key content is required.")
    parts = candidate.split()
    if len(parts) < 2 or parts[0] not in SSH_PUBKEY_PREFIXES:
        raise OperatorManagerError("SSH public key must use the standard OpenSSH public key format.")
    return candidate


def ssh_public_key_fingerprint(public_key: str) -> str:
    parts = public_key.strip().split()
    try:
        decoded = base64.b64decode(parts[1].encode("utf-8"))
    except Exception as exc:  # pragma: no cover - guarded by normalize_ssh_public_key
        raise OperatorManagerError("SSH public key payload is not valid base64.") from exc
    digest = hashlib.sha256(decoded).digest()
    return "SHA256:" + base64.b64encode(digest).decode("ascii").rstrip("=")


def load_service_catalog() -> dict[str, dict[str, Any]]:
    payload = load_json(SERVICE_CATALOG_PATH)
    services = payload.get("services")
    if not isinstance(services, list):
        raise OperatorManagerError("config/service-capability-catalog.json must define a services list")
    return {service["id"]: service for service in services if isinstance(service, dict) and "id" in service}


def service_url(service_id: str, *, prefer_public: bool = False) -> str:
    env_name = f"LV3_{service_id.upper().replace('-', '_')}_URL"
    override = os.environ.get(env_name, "").strip()
    if override:
        return override.rstrip("/")
    service = load_service_catalog().get(service_id)
    if service is None:
        raise OperatorManagerError(f"Service catalog entry '{service_id}' is missing.")
    fields = ("public_url", "internal_url") if prefer_public else ("internal_url", "public_url")
    for field in fields:
        value = service.get(field)
        if isinstance(value, str) and value.strip():
            return value.rstrip("/")
    raise OperatorManagerError(f"Service '{service_id}' does not define a usable URL.")


def load_text_if_exists(path: Path) -> str | None:
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8").strip()


def load_tailscale_api_key() -> str | None:
    for env_name in ("TAILSCALE_API_KEY", "LV3_TAILSCALE_API_KEY"):
        value = os.environ.get(env_name, "").strip()
        if value:
            return value
    return load_text_if_exists(TAILSCALE_API_KEY_PATH)


def load_tailscale_tailnet() -> str | None:
    for env_name in ("TAILSCALE_TAILNET", "LV3_TAILSCALE_TAILNET"):
        value = os.environ.get(env_name, "").strip()
        if value:
            return value
    return None


def load_mattermost_webhook() -> str | None:
    for env_name in ("LV3_MATTERMOST_WEBHOOK", "MATTERMOST_WEBHOOK_URL"):
        value = os.environ.get(env_name, "").strip()
        if value:
            return value
    return None


def load_keycloak_bootstrap_password() -> str | None:
    value = os.environ.get("KEYCLOAK_BOOTSTRAP_PASSWORD", "").strip()
    if value:
        return value
    return load_text_if_exists(KEYCLOAK_BOOTSTRAP_PASSWORD_PATH)


def load_openbao_init_payload() -> dict[str, Any]:
    value = os.environ.get("OPENBAO_INIT_JSON", "").strip()
    if value:
        try:
            payload = json.loads(value)
        except json.JSONDecodeError as exc:
            raise OperatorManagerError("OPENBAO_INIT_JSON must contain valid JSON.") from exc
        if not isinstance(payload, dict):
            raise OperatorManagerError("OPENBAO_INIT_JSON must decode to an object.")
        return payload
    return load_json(OPENBAO_INIT_PATH)


def load_openbao_root_token() -> str:
    payload = load_openbao_init_payload()
    root_token = payload.get("root_token")
    if not isinstance(root_token, str) or not root_token.strip():
        raise OperatorManagerError("OpenBao init payload does not contain a root_token")
    return root_token


def generate_bootstrap_password() -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(24))


def require_string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise OperatorManagerError(f"{path} must be a non-empty string.")
    return value


def require_string_list(value: Any, path: str) -> list[str]:
    if not isinstance(value, list):
        raise OperatorManagerError(f"{path} must be a list.")
    result: list[str] = []
    for index, item in enumerate(value):
        result.append(require_string(item, f"{path}[{index}]"))
    return result


def require_mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise OperatorManagerError(f"{path} must be a mapping.")
    return value


def validate_timestamp(value: str, path: str) -> str:
    require_string(value, path)
    if not ISO8601_PATTERN.match(value):
        raise OperatorManagerError(f"{path} must use an ISO-8601 UTC timestamp ending in Z.")
    return value


def ensure_schema_constant(value: Any, expected: str, path: str) -> None:
    actual = require_string(value, path)
    if actual != expected:
        raise OperatorManagerError(f"{path} must be '{expected}'.")


def normalize_operator_record(raw: Any, *, index: int) -> dict[str, Any]:
    path = f"config/operators.yaml.operators[{index}]"
    operator = require_mapping(raw, path)
    operator_id = require_string(operator.get("id"), f"{path}.id")
    if not OPERATOR_ID_PATTERN.match(operator_id):
        raise OperatorManagerError(f"{path}.id must use lowercase letters, numbers, and hyphens.")
    role = require_string(operator.get("role"), f"{path}.role")
    if role not in ROLE_NAMES:
        raise OperatorManagerError(f"{path}.role must be one of {sorted(ROLE_NAMES)}.")
    role_definition = ROLE_DEFINITIONS[role]
    status = require_string(operator.get("status"), f"{path}.status")
    if status not in STATUS_NAMES:
        raise OperatorManagerError(f"{path}.status must be one of {sorted(STATUS_NAMES)}.")

    keycloak = require_mapping(operator.get("keycloak"), f"{path}.keycloak")
    username = require_string(keycloak.get("username"), f"{path}.keycloak.username")
    if not KEYCLOAK_USERNAME_PATTERN.match(username):
        raise OperatorManagerError(f"{path}.keycloak.username must use lowercase Keycloak identifier format.")
    keycloak_roles = require_string_list(keycloak.get("realm_roles"), f"{path}.keycloak.realm_roles")
    keycloak_groups = require_string_list(keycloak.get("groups"), f"{path}.keycloak.groups")
    enabled = keycloak.get("enabled")
    if not isinstance(enabled, bool):
        raise OperatorManagerError(f"{path}.keycloak.enabled must be boolean.")

    ssh = require_mapping(operator.get("ssh"), f"{path}.ssh")
    ssh_principal = require_string(ssh.get("principal"), f"{path}.ssh.principal")
    certificate_ttl_hours = ssh.get("certificate_ttl_hours")
    if isinstance(certificate_ttl_hours, bool) or not isinstance(certificate_ttl_hours, int) or certificate_ttl_hours < 1:
        raise OperatorManagerError(f"{path}.ssh.certificate_ttl_hours must be an integer >= 1.")
    public_keys_raw = ssh.get("public_keys")
    if not isinstance(public_keys_raw, list):
        raise OperatorManagerError(f"{path}.ssh.public_keys must be a list.")
    public_keys: list[dict[str, str]] = []
    for key_index, public_key_raw in enumerate(public_keys_raw):
        key_path = f"{path}.ssh.public_keys[{key_index}]"
        public_key_payload = require_mapping(public_key_raw, key_path)
        public_key = normalize_ssh_public_key(require_string(public_key_payload.get("public_key"), f"{key_path}.public_key"))
        fingerprint = require_string(public_key_payload.get("fingerprint"), f"{key_path}.fingerprint")
        if fingerprint != ssh_public_key_fingerprint(public_key):
            raise OperatorManagerError(f"{key_path}.fingerprint does not match the declared public key.")
        public_keys.append(
            {
                "name": require_string(public_key_payload.get("name"), f"{key_path}.name"),
                "public_key": public_key,
                "fingerprint": fingerprint,
            }
        )
    if role_definition.ssh_enabled and not public_keys:
        raise OperatorManagerError(f"{path}.ssh.public_keys must be a non-empty list for role '{role}'.")
    if not role_definition.ssh_enabled and public_keys:
        raise OperatorManagerError(f"{path}.ssh.public_keys must be empty for role '{role}' because SSH is disabled.")

    openbao = require_mapping(operator.get("openbao"), f"{path}.openbao")
    openbao_entity_name = require_string(openbao.get("entity_name"), f"{path}.openbao.entity_name")
    openbao_policies = require_string_list(openbao.get("policies"), f"{path}.openbao.policies")

    tailscale = require_mapping(operator.get("tailscale"), f"{path}.tailscale")
    tailscale_login_email = require_string(tailscale.get("login_email"), f"{path}.tailscale.login_email")
    tailscale_tags = require_string_list(tailscale.get("tags"), f"{path}.tailscale.tags")

    audit = require_mapping(operator.get("audit"), f"{path}.audit")
    normalized_audit = {
        "onboarded_at": validate_timestamp(require_string(audit.get("onboarded_at"), f"{path}.audit.onboarded_at"), f"{path}.audit.onboarded_at"),
        "onboarded_by": require_string(audit.get("onboarded_by"), f"{path}.audit.onboarded_by"),
    }
    for field in ("offboarded_at", "offboarded_by", "last_reviewed_at", "last_reviewed_by", "last_seen_at"):
        value = audit.get(field)
        if value is None:
            continue
        if field.endswith("_at"):
            normalized_audit[field] = validate_timestamp(require_string(value, f"{path}.audit.{field}"), f"{path}.audit.{field}")
        else:
            normalized_audit[field] = require_string(value, f"{path}.audit.{field}")

    normalized = {
        "id": operator_id,
        "name": require_string(operator.get("name"), f"{path}.name"),
        "email": require_string(operator.get("email"), f"{path}.email"),
        "role": role,
        "status": status,
        "keycloak": {
            "username": username,
            "realm_roles": keycloak_roles,
            "groups": keycloak_groups,
            "enabled": enabled,
        },
        "ssh": {
            "principal": ssh_principal,
            "certificate_ttl_hours": certificate_ttl_hours,
            "public_keys": public_keys,
        },
        "openbao": {
            "entity_name": openbao_entity_name,
            "policies": openbao_policies,
        },
        "tailscale": {
            "login_email": tailscale_login_email,
            "tags": tailscale_tags,
        },
        "audit": normalized_audit,
    }
    notes = operator.get("notes")
    if notes is not None:
        normalized["notes"] = require_string(notes, f"{path}.notes")
    for optional_field in ("device_name", "device_id"):
        value = tailscale.get(optional_field)
        if value is not None:
            normalized["tailscale"][optional_field] = require_string(value, f"{path}.tailscale.{optional_field}")
    return normalized


def validate_operator_roster(payload: Any) -> dict[str, Any]:
    roster = require_mapping(payload, "config/operators.yaml")
    ensure_schema_constant(roster.get("$schema"), "config/schemas/operators.schema.json", "config/operators.yaml.$schema")
    ensure_schema_constant(roster.get("schema_version"), "1.0.0", "config/operators.yaml.schema_version")
    operators_raw = roster.get("operators")
    if not isinstance(operators_raw, list):
        raise OperatorManagerError("config/operators.yaml.operators must be a list.")
    normalized_operators = [normalize_operator_record(item, index=index) for index, item in enumerate(operators_raw)]
    seen_ids: set[str] = set()
    seen_emails: set[str] = set()
    seen_usernames: set[str] = set()
    for operator in normalized_operators:
        if operator["id"] in seen_ids:
            raise OperatorManagerError(f"Duplicate operator id '{operator['id']}' in config/operators.yaml.")
        if operator["email"] in seen_emails:
            raise OperatorManagerError(f"Duplicate operator email '{operator['email']}' in config/operators.yaml.")
        if operator["keycloak"]["username"] in seen_usernames:
            raise OperatorManagerError(
                f"Duplicate Keycloak username '{operator['keycloak']['username']}' in config/operators.yaml."
            )
        seen_ids.add(operator["id"])
        seen_emails.add(operator["email"])
        seen_usernames.add(operator["keycloak"]["username"])
    return {
        "$schema": "config/schemas/operators.schema.json",
        "schema_version": "1.0.0",
        "operators": normalized_operators,
    }


def load_operator_roster(path: Path = ROSTER_PATH) -> dict[str, Any]:
    return validate_operator_roster(load_yaml(path))


def dump_operator_roster(payload: dict[str, Any], path: Path = ROSTER_PATH) -> None:
    yaml = get_yaml_module()
    normalized = validate_operator_roster(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(normalized, sort_keys=False), encoding="utf-8")


def role_payload(role: str) -> dict[str, Any]:
    definition = ROLE_DEFINITIONS[role]
    return {
        "keycloak": {
            "realm_roles": list(definition.keycloak_roles),
            "groups": list(definition.keycloak_groups),
            "enabled": True,
        },
        "ssh": {
            "certificate_ttl_hours": 24,
        },
        "openbao": {
            "policies": list(definition.openbao_policies),
        },
        "tailscale": {
            "tags": list(definition.tailscale_tags),
        },
    }


def create_operator_record(
    *,
    name: str,
    email: str,
    role: str,
    ssh_public_key: str,
    operator_id: str | None,
    keycloak_username: str | None,
    ssh_key_name: str,
    tailscale_login_email: str | None,
    tailscale_device_name: str | None,
    onboarded_by: str,
) -> dict[str, Any]:
    if role not in ROLE_NAMES:
        raise OperatorManagerError(f"role must be one of {sorted(ROLE_NAMES)}.")
    role_definition = ROLE_DEFINITIONS[role]
    derived_id = operator_id or slugify(name)
    if not OPERATOR_ID_PATTERN.match(derived_id):
        raise OperatorManagerError("operator id must use lowercase letters, numbers, and hyphens.")
    username = keycloak_username or default_username(name, email)
    if not KEYCLOAK_USERNAME_PATTERN.match(username):
        raise OperatorManagerError("keycloak username must use lowercase letters, numbers, dots, underscores, or hyphens.")
    derived = role_payload(role)
    public_keys: list[dict[str, str]] = []
    if role_definition.ssh_enabled:
        if not ssh_public_key.strip():
            raise OperatorManagerError(f"role '{role}' requires an SSH public key.")
        public_key = normalize_ssh_public_key(ssh_public_key)
        public_keys.append(
            {
                "name": ssh_key_name,
                "public_key": public_key,
                "fingerprint": ssh_public_key_fingerprint(public_key),
            }
        )
    record = {
        "id": derived_id,
        "name": name.strip(),
        "email": email.strip().lower(),
        "role": role,
        "status": "active",
        "keycloak": {
            "username": username,
            "realm_roles": derived["keycloak"]["realm_roles"],
            "groups": derived["keycloak"]["groups"],
            "enabled": True,
        },
        "ssh": {
            "principal": username,
            "certificate_ttl_hours": derived["ssh"]["certificate_ttl_hours"],
            "public_keys": public_keys,
        },
        "openbao": {
            "entity_name": username,
            "policies": derived["openbao"]["policies"],
        },
        "tailscale": {
            "login_email": (tailscale_login_email or email).strip().lower(),
            "tags": derived["tailscale"]["tags"],
        },
        "audit": {
            "onboarded_at": utc_now(),
            "onboarded_by": onboarded_by,
        },
    }
    if tailscale_device_name:
        record["tailscale"]["device_name"] = tailscale_device_name.strip()
    return validate_operator_roster({"$schema": "config/schemas/operators.schema.json", "schema_version": "1.0.0", "operators": [record]})["operators"][0]


def upsert_operator_in_roster(roster: dict[str, Any], record: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    updated = copy.deepcopy(roster)
    operators = updated["operators"]
    for index, existing in enumerate(operators):
        if existing["id"] == record["id"]:
            operators[index] = record
            return validate_operator_roster(updated), False
    operators.append(record)
    operators.sort(key=lambda item: item["id"])
    return validate_operator_roster(updated), True


def mark_operator_inactive(roster: dict[str, Any], operator_id: str, offboarded_by: str) -> tuple[dict[str, Any], dict[str, Any]]:
    updated = copy.deepcopy(roster)
    for operator in updated["operators"]:
        if operator["id"] != operator_id:
            continue
        operator["status"] = "inactive"
        operator["keycloak"]["enabled"] = False
        operator["audit"]["offboarded_at"] = utc_now()
        operator["audit"]["offboarded_by"] = offboarded_by
        return validate_operator_roster(updated), operator
    raise OperatorManagerError(f"Operator '{operator_id}' was not found in {ROSTER_PATH}.")


def find_operator(roster: dict[str, Any], operator_id: str) -> dict[str, Any]:
    for operator in roster["operators"]:
        if operator["id"] == operator_id:
            return copy.deepcopy(operator)
    raise OperatorManagerError(f"Operator '{operator_id}' was not found in {ROSTER_PATH}.")


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_state(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def operator_state_path(operator_id: str, state_dir: Path = STATE_DIR) -> Path:
    return state_dir / f"{operator_id}.json"


def policy_documents() -> dict[str, str]:
    payload: dict[str, str] = {}
    for policy_name, filename in OPENBAO_POLICY_GROUPS.items():
        path = POLICY_DIR / filename
        payload[policy_name] = path.read_text(encoding="utf-8")
    return payload


def json_request(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    body: dict[str, Any] | list[Any] | str | None = None,
    form: dict[str, str] | None = None,
    expected_status: tuple[int, ...] = (200,),
) -> Any:
    request_headers = dict(headers or {})
    data: bytes | None = None
    if body is not None and form is not None:
        raise OperatorManagerError("json_request cannot encode JSON and form payloads at the same time.")
    if body is not None:
        if isinstance(body, str):
            data = body.encode("utf-8")
        else:
            data = json.dumps(body).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json")
    elif form is not None:
        data = urllib.parse.urlencode(form).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/x-www-form-urlencoded")

    request = urllib.request.Request(url, data=data, method=method, headers=request_headers)
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            content = response.read().decode("utf-8")
            if response.status not in expected_status:
                raise OperatorManagerError(f"{method} {url} returned unexpected HTTP {response.status}.")
            if not content.strip():
                return {}
            if "application/json" in response.headers.get("Content-Type", ""):
                return json.loads(content)
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                return {"raw": content}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise OperatorManagerError(f"{method} {url} failed with HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise OperatorManagerError(f"{method} {url} failed: {exc}") from exc


class LiveBackend:
    def __init__(self, *, actor_class: str, actor_id: str):
        self.actor_class = actor_class
        self.actor_id = actor_id
        self._keycloak_token: str | None = None
        self._keycloak_user_cache: dict[str, dict[str, Any]] = {}
        self._openbao_root_token: str | None = None

    def ensure_prerequisites(self) -> dict[str, Any]:
        details = {
            "keycloak_url": service_url("keycloak", prefer_public=True),
            "openbao_url": service_url("openbao"),
            "tailscale_tailnet": load_tailscale_tailnet() or "",
            "mattermost_webhook_configured": bool(load_mattermost_webhook()),
        }
        missing: list[str] = []
        if not load_keycloak_bootstrap_password():
            missing.append("KEYCLOAK_BOOTSTRAP_PASSWORD or " + str(KEYCLOAK_BOOTSTRAP_PASSWORD_PATH))
        try:
            load_openbao_init_payload()
        except (OperatorManagerError, FileNotFoundError):
            missing.append("OPENBAO_INIT_JSON or " + str(OPENBAO_INIT_PATH))
        if missing:
            raise OperatorManagerError("Missing required local artifacts: " + ", ".join(missing))
        return details

    def _keycloak_admin_token(self) -> str:
        if self._keycloak_token is not None:
            return self._keycloak_token
        password = load_keycloak_bootstrap_password()
        if not password:
            raise OperatorManagerError(
                "Keycloak bootstrap admin password is missing from KEYCLOAK_BOOTSTRAP_PASSWORD and "
                f"{KEYCLOAK_BOOTSTRAP_PASSWORD_PATH}"
            )
        payload = json_request(
            f"{service_url('keycloak', prefer_public=True)}/realms/master/protocol/openid-connect/token",
            method="POST",
            form={
                "grant_type": "password",
                "client_id": "admin-cli",
                "username": KEYCLOAK_BOOTSTRAP_ADMIN,
                "password": password,
            },
        )
        access_token = payload.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise OperatorManagerError("Keycloak did not return an access_token for the bootstrap admin.")
        self._keycloak_token = access_token
        return access_token

    def _keycloak_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._keycloak_admin_token()}"}

    def _keycloak_role(self, role_name: str) -> dict[str, Any]:
        base = f"{service_url('keycloak', prefer_public=True)}/admin/realms/{KEYCLOAK_REALM}/roles/{urllib.parse.quote(role_name, safe='')}"
        try:
            return json_request(base, headers=self._keycloak_headers(), expected_status=(200,))
        except OperatorManagerError:
            json_request(
                f"{service_url('keycloak', prefer_public=True)}/admin/realms/{KEYCLOAK_REALM}/roles",
                method="POST",
                headers=self._keycloak_headers(),
                body={"name": role_name, "description": f"Repo-managed ADR 0108 operator role {role_name}."},
                expected_status=(201, 204),
            )
            return json_request(base, headers=self._keycloak_headers(), expected_status=(200,))

    def _keycloak_group(self, group_name: str) -> dict[str, Any]:
        search_url = (
            f"{service_url('keycloak', prefer_public=True)}/admin/realms/{KEYCLOAK_REALM}/groups"
            f"?search={urllib.parse.quote(group_name, safe='')}"
        )
        groups = json_request(search_url, headers=self._keycloak_headers(), expected_status=(200,))
        if isinstance(groups, list):
            for group in groups:
                if isinstance(group, dict) and group.get("name") == group_name:
                    return group
        json_request(
            f"{service_url('keycloak', prefer_public=True)}/admin/realms/{KEYCLOAK_REALM}/groups",
            method="POST",
            headers=self._keycloak_headers(),
            body={"name": group_name},
            expected_status=(201, 204),
        )
        groups = json_request(search_url, headers=self._keycloak_headers(), expected_status=(200,))
        if isinstance(groups, list):
            for group in groups:
                if isinstance(group, dict) and group.get("name") == group_name:
                    return group
        raise OperatorManagerError(f"Keycloak group '{group_name}' could not be created or found.")

    def _keycloak_user(self, username: str) -> dict[str, Any] | None:
        if username in self._keycloak_user_cache:
            return self._keycloak_user_cache[username]
        url = (
            f"{service_url('keycloak', prefer_public=True)}/admin/realms/{KEYCLOAK_REALM}/users"
            f"?username={urllib.parse.quote(username, safe='')}&exact=true"
        )
        users = json_request(url, headers=self._keycloak_headers(), expected_status=(200,))
        if isinstance(users, list) and users:
            for user in users:
                if isinstance(user, dict) and user.get("username") == username:
                    self._keycloak_user_cache[username] = user
                    return user
        return None

    def _keycloak_user_id(self, username: str) -> str:
        user = self._keycloak_user(username)
        if user is None:
            raise OperatorManagerError(f"Keycloak user '{username}' was not found.")
        user_id = user.get("id")
        if not isinstance(user_id, str) or not user_id:
            raise OperatorManagerError(f"Keycloak user '{username}' does not expose an id.")
        return user_id

    def _keycloak_user_details(self, username: str) -> dict[str, Any]:
        user_id = self._keycloak_user_id(username)
        details = json_request(
            f"{service_url('keycloak', prefer_public=True)}/admin/realms/{KEYCLOAK_REALM}/users/{user_id}",
            headers=self._keycloak_headers(),
            expected_status=(200,),
        )
        if not isinstance(details, dict):
            raise OperatorManagerError(f"Keycloak user '{username}' did not return a valid detail payload.")
        return details

    def _keycloak_user_credentials(self, username: str) -> list[dict[str, Any]]:
        user_id = self._keycloak_user_id(username)
        payload = json_request(
            f"{service_url('keycloak', prefer_public=True)}/admin/realms/{KEYCLOAK_REALM}/users/{user_id}/credentials",
            headers=self._keycloak_headers(),
            expected_status=(200,),
        )
        if not isinstance(payload, list):
            raise OperatorManagerError(f"Keycloak credentials for '{username}' did not return a list.")
        return [entry for entry in payload if isinstance(entry, dict)]

    def _openbao_headers(self) -> dict[str, str]:
        if self._openbao_root_token is None:
            self._openbao_root_token = load_openbao_root_token()
        return {"X-Vault-Token": self._openbao_root_token}

    def _emit_audit(self, action: str, target: str) -> dict[str, Any]:
        event = build_event(
            actor_class=self.actor_class,
            actor_id=self.actor_id,
            surface=os.environ.get("LV3_OPERATOR_MANAGER_SURFACE", "manual"),
            action=action,
            target=target,
            outcome="success",
        )
        return emit_event(event)

    def _ensure_openbao_policies(self) -> dict[str, Any]:
        results: dict[str, Any] = {}
        for policy_name, document in policy_documents().items():
            json_request(
                f"{service_url('openbao')}/v1/sys/policies/acl/{urllib.parse.quote(policy_name, safe='')}",
                method="PUT",
                headers=self._openbao_headers(),
                body={"policy": document},
                expected_status=(200, 204),
            )
            results[policy_name] = "upserted"
        return results

    def ensure_prerequisites_payload(self) -> dict[str, Any]:
        policy_results = self._ensure_openbao_policies()
        role_results = {}
        group_results = {}
        for definition in ROLE_DEFINITIONS.values():
            for role_name in definition.keycloak_roles:
                role_results[role_name] = self._keycloak_role(role_name).get("name", role_name)
            for group_name in definition.keycloak_groups:
                group_results[group_name] = self._keycloak_group(group_name).get("name", group_name)
        return {"keycloak_roles": role_results, "keycloak_groups": group_results, "openbao_policies": policy_results}

    def ensure_prerequisites(self) -> dict[str, Any]:
        details = self.ensure_prerequisites_payload()
        details.update(
            {
                "keycloak_url": service_url("keycloak", prefer_public=True),
                "openbao_url": service_url("openbao"),
                "tailscale_tailnet": load_tailscale_tailnet() or "",
                "mattermost_webhook_configured": bool(load_mattermost_webhook()),
            }
        )
        return details

    def _ensure_keycloak_user(self, operator: dict[str, Any], bootstrap_password: str) -> dict[str, Any]:
        username = operator["keycloak"]["username"]
        role_def = ROLE_DEFINITIONS[operator["role"]]
        existing = self._keycloak_user(username)
        payload = {
            "username": username,
            "firstName": operator["name"].split(" ", 1)[0],
            "lastName": operator["name"].split(" ", 1)[1] if " " in operator["name"] else operator["name"],
            "email": operator["email"],
            "enabled": operator["status"] == "active",
            "emailVerified": True,
            "requiredActions": ["UPDATE_PASSWORD", "CONFIGURE_TOTP"],
            "credentials": [
                {
                    "type": "password",
                    "value": bootstrap_password,
                    "temporary": True,
                }
            ],
            "groups": list(role_def.keycloak_groups),
        }
        if existing is None:
            json_request(
                f"{service_url('keycloak', prefer_public=True)}/admin/realms/{KEYCLOAK_REALM}/users",
                method="POST",
                headers=self._keycloak_headers(),
                body=payload,
                expected_status=(201, 204),
            )
        else:
            json_request(
                f"{service_url('keycloak', prefer_public=True)}/admin/realms/{KEYCLOAK_REALM}/users/{self._keycloak_user_id(username)}",
                method="PUT",
                headers=self._keycloak_headers(),
                body=payload,
                expected_status=(204,),
            )

        self._keycloak_user_cache.pop(username, None)
        user_id = self._keycloak_user_id(username)
        role_representations = [self._keycloak_role(role_name) for role_name in role_def.keycloak_roles]
        json_request(
            f"{service_url('keycloak', prefer_public=True)}/admin/realms/{KEYCLOAK_REALM}/users/{user_id}/role-mappings/realm",
            method="POST",
            headers=self._keycloak_headers(),
            body=role_representations,
            expected_status=(204,),
        )
        return {"user_id": user_id, "username": username, "realm_roles": list(role_def.keycloak_roles)}

    def _disable_keycloak_user(self, username: str) -> dict[str, Any]:
        user = self._keycloak_user(username)
        if user is None:
            return {"status": "missing", "username": username}
        updated = dict(user)
        updated["enabled"] = False
        json_request(
            f"{service_url('keycloak', prefer_public=True)}/admin/realms/{KEYCLOAK_REALM}/users/{self._keycloak_user_id(username)}",
            method="PUT",
            headers=self._keycloak_headers(),
            body=updated,
            expected_status=(204,),
        )
        return {"status": "disabled", "username": username, "user_id": self._keycloak_user_id(username)}

    def _ensure_openbao_entity(self, operator: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "policies": operator["openbao"]["policies"],
            "metadata": {
                "email": operator["email"],
                "role": operator["role"],
                "status": operator["status"],
                "operator_id": operator["id"],
            },
            "disabled": operator["status"] != "active",
        }
        json_request(
            f"{service_url('openbao')}/v1/identity/entity/name/{urllib.parse.quote(operator['openbao']['entity_name'], safe='')}",
            method="POST",
            headers=self._openbao_headers(),
            body=payload,
            expected_status=(200, 204),
        )
        current = json_request(
            f"{service_url('openbao')}/v1/identity/entity/name/{urllib.parse.quote(operator['openbao']['entity_name'], safe='')}",
            headers=self._openbao_headers(),
            expected_status=(200,),
        )
        entity = current.get("data", {}) if isinstance(current, dict) else {}
        return {
            "entity_name": operator["openbao"]["entity_name"],
            "entity_id": entity.get("id", ""),
            "policies": operator["openbao"]["policies"],
            "disabled": payload["disabled"],
        }

    def _register_step_ca_principal(self, operator: dict[str, Any]) -> dict[str, Any]:
        if not ROLE_DEFINITIONS[operator["role"]].ssh_enabled:
            return {
                "status": "skipped",
                "reason": f"role '{operator['role']}' does not receive SSH access",
                "principal": operator["ssh"]["principal"],
            }
        command_template = os.environ.get("LV3_STEP_CA_SSH_REGISTER_COMMAND", "").strip()
        if not command_template:
            return {
                "status": "skipped",
                "reason": "LV3_STEP_CA_SSH_REGISTER_COMMAND is not configured",
                "principal": operator["ssh"]["principal"],
            }
        public_key = operator["ssh"]["public_keys"][0]["public_key"]
        temp_key = STATE_DIR / f"{operator['id']}.pub"
        temp_key.parent.mkdir(parents=True, exist_ok=True)
        temp_key.write_text(public_key + "\n", encoding="utf-8")
        try:
            command = command_template.format(principal=operator["ssh"]["principal"], public_key_path=str(temp_key))
            result = subprocess.run(command, shell=True, text=True, capture_output=True, check=False)
        finally:
            temp_key.unlink(missing_ok=True)
        return {
            "status": "ok" if result.returncode == 0 else "error",
            "principal": operator["ssh"]["principal"],
            "command": command,
            "returncode": result.returncode,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
        }

    def _revoke_step_ca_principal(self, operator: dict[str, Any]) -> dict[str, Any]:
        if not ROLE_DEFINITIONS[operator["role"]].ssh_enabled:
            return {
                "status": "skipped",
                "reason": f"role '{operator['role']}' does not receive SSH access",
                "principal": operator["ssh"]["principal"],
            }
        command_template = os.environ.get("LV3_STEP_CA_SSH_REVOKE_COMMAND", "").strip()
        if not command_template:
            return {
                "status": "skipped",
                "reason": "LV3_STEP_CA_SSH_REVOKE_COMMAND is not configured",
                "principal": operator["ssh"]["principal"],
            }
        command = command_template.format(principal=operator["ssh"]["principal"])
        result = subprocess.run(command, shell=True, text=True, capture_output=True, check=False)
        return {
            "status": "ok" if result.returncode == 0 else "error",
            "principal": operator["ssh"]["principal"],
            "command": command,
            "returncode": result.returncode,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
        }

    def _tailscale_headers(self) -> dict[str, str]:
        api_key = load_tailscale_api_key()
        if not api_key:
            raise OperatorManagerError("Tailscale API key is not configured. Set TAILSCALE_API_KEY or create .local/tailscale/api-key.txt.")
        return {"Authorization": f"Bearer {api_key}"}

    def _tailscale_invite(self, operator: dict[str, Any]) -> dict[str, Any]:
        tailnet = load_tailscale_tailnet()
        endpoint = os.environ.get("LV3_TAILSCALE_INVITE_ENDPOINT", "").strip()
        if not tailnet or not endpoint:
            return {
                "status": "skipped",
                "reason": "TAILSCALE_TAILNET or LV3_TAILSCALE_INVITE_ENDPOINT is not configured",
                "login_email": operator["tailscale"]["login_email"],
            }
        payload = {
            "email": operator["tailscale"]["login_email"],
            "tags": operator["tailscale"]["tags"],
        }
        invite = json_request(
            endpoint.format(tailnet=tailnet),
            method="POST",
            headers=self._tailscale_headers(),
            body=payload,
            expected_status=(200, 201, 202),
        )
        return {
            "status": "ok",
            "login_email": operator["tailscale"]["login_email"],
            "invite": invite,
        }

    def _tailscale_devices(self) -> list[dict[str, Any]]:
        tailnet = load_tailscale_tailnet()
        if not tailnet:
            raise OperatorManagerError("TAILSCALE_TAILNET is not configured.")
        response = json_request(
            f"https://api.tailscale.com/api/v2/tailnet/{urllib.parse.quote(tailnet, safe='')}/devices",
            headers=self._tailscale_headers(),
            expected_status=(200,),
        )
        devices = response.get("devices", response if isinstance(response, list) else [])
        if not isinstance(devices, list):
            raise OperatorManagerError("Tailscale devices response did not contain a list.")
        return [device for device in devices if isinstance(device, dict)]

    def _tailscale_remove(self, operator: dict[str, Any]) -> dict[str, Any]:
        if not load_tailscale_api_key() or not load_tailscale_tailnet():
            return {
                "status": "skipped",
                "reason": "TAILSCALE_API_KEY or TAILSCALE_TAILNET is not configured",
                "login_email": operator["tailscale"]["login_email"],
            }
        devices = self._tailscale_devices()
        device_name = operator["tailscale"].get("device_name")
        device_id = operator["tailscale"].get("device_id")
        login_email = operator["tailscale"]["login_email"]
        matches = [
            device
            for device in devices
            if (device_id and device.get("id") == device_id)
            or (device_name and device.get("hostname") == device_name)
            or device.get("user") == login_email
        ]
        deleted_ids: list[str] = []
        for device in matches:
            candidate_id = device.get("id")
            if not isinstance(candidate_id, str) or not candidate_id:
                continue
            json_request(
                f"https://api.tailscale.com/api/v2/device/{urllib.parse.quote(candidate_id, safe='')}",
                method="DELETE",
                headers=self._tailscale_headers(),
                expected_status=(200, 202, 204),
            )
            deleted_ids.append(candidate_id)
        return {"status": "ok", "deleted_device_ids": deleted_ids}

    def _mattermost_post(self, text: str) -> dict[str, Any]:
        webhook = load_mattermost_webhook()
        if not webhook:
            return {"status": "skipped", "reason": "LV3_MATTERMOST_WEBHOOK is not configured"}
        json_request(webhook, method="POST", body={"text": text}, expected_status=(200,))
        return {"status": "ok"}

    def onboard_operator(self, operator: dict[str, Any], bootstrap_password: str) -> dict[str, Any]:
        prereq = self.ensure_prerequisites_payload()
        keycloak = self._ensure_keycloak_user(operator, bootstrap_password)
        openbao = self._ensure_openbao_entity(operator)
        step_ca = self._register_step_ca_principal(operator)
        tailscale = self._tailscale_invite(operator)
        mattermost = self._mattermost_post(
            "\n".join(
                [
                    f"Operator onboarded: {operator['name']} ({operator['role']})",
                    f"Keycloak user: `{operator['keycloak']['username']}`",
                    f"Tailscale login: `{operator['tailscale']['login_email']}`",
                ]
            )
        )
        audit = self._emit_audit("operator.onboarded", operator["id"])
        return {
            "bootstrap_password": bootstrap_password,
            "prerequisites": prereq,
            "keycloak": keycloak,
            "openbao": openbao,
            "step_ca": step_ca,
            "tailscale": tailscale,
            "mattermost": mattermost,
            "audit": audit,
        }

    def offboard_operator(self, operator: dict[str, Any], reason: str | None) -> dict[str, Any]:
        prereq = self.ensure_prerequisites_payload()
        keycloak = self._disable_keycloak_user(operator["keycloak"]["username"])
        openbao = self._ensure_openbao_entity(operator)
        step_ca = self._revoke_step_ca_principal(operator)
        tailscale = self._tailscale_remove(operator)
        message = f"Operator offboarded: {operator['name']}"
        if reason:
            message += f" ({reason})"
        mattermost = self._mattermost_post(message)
        audit = self._emit_audit("operator.offboarded", operator["id"])
        return {
            "prerequisites": prereq,
            "keycloak": keycloak,
            "openbao": openbao,
            "step_ca": step_ca,
            "tailscale": tailscale,
            "mattermost": mattermost,
            "audit": audit,
        }

    def recover_totp(self, operator: dict[str, Any]) -> dict[str, Any]:
        username = operator["keycloak"]["username"]
        user_id = self._keycloak_user_id(username)
        details = self._keycloak_user_details(username)
        removed_credentials: list[dict[str, str]] = []
        for credential in self._keycloak_user_credentials(username):
            if credential.get("type") != "otp":
                continue
            credential_id = credential.get("id")
            if not isinstance(credential_id, str) or not credential_id:
                continue
            json_request(
                f"{service_url('keycloak', prefer_public=True)}/admin/realms/{KEYCLOAK_REALM}/users/{user_id}/credentials/{credential_id}",
                method="DELETE",
                headers=self._keycloak_headers(),
                expected_status=(200, 204),
            )
            removed_credentials.append(
                {
                    "id": credential_id,
                    "userLabel": str(credential.get("userLabel") or ""),
                }
            )

        required_actions = details.get("requiredActions")
        if not isinstance(required_actions, list):
            required_actions = []
        normalized_required_actions = [str(action) for action in required_actions if str(action).strip()]
        if "CONFIGURE_TOTP" not in normalized_required_actions:
            normalized_required_actions.append("CONFIGURE_TOTP")
        details["requiredActions"] = normalized_required_actions
        json_request(
            f"{service_url('keycloak', prefer_public=True)}/admin/realms/{KEYCLOAK_REALM}/users/{user_id}",
            method="PUT",
            headers=self._keycloak_headers(),
            body=details,
            expected_status=(204,),
        )
        json_request(
            f"{service_url('keycloak', prefer_public=True)}/admin/realms/{KEYCLOAK_REALM}/attack-detection/brute-force/users/{user_id}",
            method="DELETE",
            headers=self._keycloak_headers(),
            expected_status=(200, 204),
        )
        self._keycloak_user_cache.pop(username, None)
        audit = self._emit_audit("operator.totp_recovered", operator["id"])
        return {
            "keycloak": {
                "status": "totp-reset",
                "username": username,
                "user_id": user_id,
                "removed_otp_credentials": removed_credentials,
                "required_actions": normalized_required_actions,
                "failure_counters_cleared": True,
            },
            "audit": audit,
        }

    def reset_password(self, operator: dict[str, Any], password: str, *, temporary: bool) -> dict[str, Any]:
        if not password.strip():
            raise OperatorManagerError("Password reset requires a non-empty password.")
        username = operator["keycloak"]["username"]
        user_id = self._keycloak_user_id(username)
        details = self._keycloak_user_details(username)
        json_request(
            f"{service_url('keycloak', prefer_public=True)}/admin/realms/{KEYCLOAK_REALM}/users/{user_id}/reset-password",
            method="PUT",
            headers=self._keycloak_headers(),
            body={"type": "password", "temporary": temporary, "value": password},
            expected_status=(204,),
        )
        required_actions = details.get("requiredActions")
        if not isinstance(required_actions, list):
            required_actions = []
        normalized_required_actions = [str(action) for action in required_actions if str(action).strip()]
        if temporary and "UPDATE_PASSWORD" not in normalized_required_actions:
            normalized_required_actions.append("UPDATE_PASSWORD")
        details["requiredActions"] = normalized_required_actions
        json_request(
            f"{service_url('keycloak', prefer_public=True)}/admin/realms/{KEYCLOAK_REALM}/users/{user_id}",
            method="PUT",
            headers=self._keycloak_headers(),
            body=details,
            expected_status=(204,),
        )
        json_request(
            f"{service_url('keycloak', prefer_public=True)}/admin/realms/{KEYCLOAK_REALM}/attack-detection/brute-force/users/{user_id}",
            method="DELETE",
            headers=self._keycloak_headers(),
            expected_status=(200, 204),
        )
        self._keycloak_user_cache.pop(username, None)
        audit = self._emit_audit("operator.password_recovered", operator["id"])
        return {
            "keycloak": {
                "status": "password-reset",
                "username": username,
                "user_id": user_id,
                "temporary": temporary,
                "required_actions": normalized_required_actions,
                "failure_counters_cleared": True,
            },
            "audit": audit,
        }

    def inventory_operator(self, operator: dict[str, Any], state: dict[str, Any], offline: bool) -> dict[str, Any]:
        ssh_enabled = ROLE_DEFINITIONS[operator["role"]].ssh_enabled
        summary = {
            "operator": operator,
            "keycloak": {"status": "offline" if offline else "unknown"},
            "openbao": {"status": "offline" if offline else "unknown"},
            "step_ca": (
                {"status": "disabled", "reason": f"role '{operator['role']}' does not receive SSH access"}
                if not ssh_enabled
                else state.get("step_ca", {"status": "offline" if offline else "unknown"})
            ),
            "tailscale": {"status": "offline" if offline else "unknown"},
            "audit": state.get("audit", {}),
        }
        if offline:
            return summary

        user = self._keycloak_user(operator["keycloak"]["username"])
        if user is None:
            summary["keycloak"] = {"status": "missing", "username": operator["keycloak"]["username"]}
        else:
            summary["keycloak"] = {
                "status": "active" if user.get("enabled") else "disabled",
                "username": operator["keycloak"]["username"],
                "email": user.get("email", operator["email"]),
            }

        entity = json_request(
            f"{service_url('openbao')}/v1/identity/entity/name/{urllib.parse.quote(operator['openbao']['entity_name'], safe='')}",
            headers=self._openbao_headers(),
            expected_status=(200,),
        )
        entity_data = entity.get("data", {}) if isinstance(entity, dict) else {}
        summary["openbao"] = {
            "status": "disabled" if entity_data.get("disabled") else "active",
            "entity_name": operator["openbao"]["entity_name"],
            "entity_id": entity_data.get("id", ""),
            "policies": entity_data.get("policies", operator["openbao"]["policies"]),
        }

        try:
            devices = self._tailscale_devices()
        except OperatorManagerError as exc:
            summary["tailscale"] = {"status": "unavailable", "reason": str(exc)}
        else:
            matches = [
                device
                for device in devices
                if device.get("id") == operator["tailscale"].get("device_id")
                or device.get("hostname") == operator["tailscale"].get("device_name")
                or device.get("user") == operator["tailscale"]["login_email"]
            ]
            if matches:
                summary["tailscale"] = {
                    "status": "connected",
                    "devices": [
                        {
                            "id": match.get("id", ""),
                            "hostname": match.get("hostname", ""),
                            "last_seen": match.get("lastSeen", ""),
                            "addresses": match.get("addresses", []),
                        }
                        for match in matches
                    ],
                }
            else:
                summary["tailscale"] = {
                    "status": "absent",
                    "login_email": operator["tailscale"]["login_email"],
                }
        return summary

    def quarterly_review(self, review: dict[str, Any]) -> dict[str, Any]:
        markdown_lines = [
            f"Quarterly access review ({review['generated_at']})",
            "",
            "Active operators:",
        ]
        for entry in review["operators"]:
            suffix = " FLAGGED" if entry["flagged"] else ""
            markdown_lines.append(
                f"- {entry['id']} ({entry['role']}) last seen {entry['last_seen']}{suffix}"
            )
        mattermost = self._mattermost_post("\n".join(markdown_lines))
        return {"mattermost": mattermost}


class NoopBackend:
    def __init__(self, *, actor_class: str, actor_id: str):
        self.actor_class = actor_class
        self.actor_id = actor_id

    def ensure_prerequisites(self) -> dict[str, Any]:
        return {"status": "skipped", "backend": "noop"}

    def onboard_operator(self, operator: dict[str, Any], bootstrap_password: str) -> dict[str, Any]:
        return {
            "status": "dry-run",
            "operator_id": operator["id"],
            "bootstrap_password": bootstrap_password,
        }

    def offboard_operator(self, operator: dict[str, Any], reason: str | None) -> dict[str, Any]:
        return {
            "status": "dry-run",
            "operator_id": operator["id"],
            "reason": reason or "",
        }

    def recover_totp(self, operator: dict[str, Any]) -> dict[str, Any]:
        return {
            "keycloak": {
                "status": "dry-run",
                "username": operator["keycloak"]["username"],
                "required_actions": ["CONFIGURE_TOTP"],
                "failure_counters_cleared": True,
            }
        }

    def reset_password(self, operator: dict[str, Any], password: str, *, temporary: bool) -> dict[str, Any]:
        return {
            "keycloak": {
                "status": "dry-run",
                "username": operator["keycloak"]["username"],
                "temporary": temporary,
                "required_actions": ["UPDATE_PASSWORD"] if temporary else [],
                "failure_counters_cleared": True,
            }
        }

    def inventory_operator(self, operator: dict[str, Any], state: dict[str, Any], offline: bool) -> dict[str, Any]:
        return {
            "operator": operator,
            "keycloak": {"status": "dry-run"},
            "openbao": {"status": "dry-run"},
            "step_ca": (
                {"status": "disabled", "reason": f"role '{operator['role']}' does not receive SSH access"}
                if not ROLE_DEFINITIONS[operator["role"]].ssh_enabled
                else state.get("step_ca", {"status": "unknown"})
            ),
            "tailscale": {"status": "dry-run"},
            "audit": state.get("audit", {}),
        }

    def quarterly_review(self, review: dict[str, Any]) -> dict[str, Any]:
        return {"status": "dry-run", "flagged_count": review["flagged_count"]}


def select_backend(*, dry_run: bool, actor_class: str, actor_id: str) -> OperatorBackend:
    if dry_run:
        return NoopBackend(actor_class=actor_class, actor_id=actor_id)
    return LiveBackend(actor_class=actor_class, actor_id=actor_id)


def persist_state(operator_id: str, operation: str, result: dict[str, Any], *, state_dir: Path = STATE_DIR) -> Path:
    path = operator_state_path(operator_id, state_dir)
    current = load_state(path)
    current.update(
        {
            "operator_id": operator_id,
            "last_operation": operation,
            "updated_at": utc_now(),
        }
    )
    for key in ("keycloak", "openbao", "step_ca", "tailscale", "mattermost", "audit"):
        if key in result:
            current[key] = result[key]
    if "bootstrap_password" in result:
        current["bootstrap_password_issued_at"] = utc_now()
    write_state(path, current)
    return path


def onboard(
    *,
    roster_path: Path,
    state_dir: Path,
    name: str,
    email: str,
    role: str,
    ssh_key: str,
    actor_id: str,
    actor_class: str,
    operator_id: str | None,
    keycloak_username: str | None,
    ssh_key_name: str,
    tailscale_login_email: str | None,
    tailscale_device_name: str | None,
    bootstrap_password: str | None,
    dry_run: bool,
) -> dict[str, Any]:
    roster = load_operator_roster(roster_path)
    record = create_operator_record(
        name=name,
        email=email,
        role=role,
        ssh_public_key=ssh_key,
        operator_id=operator_id,
        keycloak_username=keycloak_username,
        ssh_key_name=ssh_key_name,
        tailscale_login_email=tailscale_login_email,
        tailscale_device_name=tailscale_device_name,
        onboarded_by=actor_id,
    )
    updated_roster, created = upsert_operator_in_roster(roster, record)
    if not dry_run:
        dump_operator_roster(updated_roster, roster_path)
    backend = select_backend(dry_run=dry_run, actor_class=actor_class, actor_id=actor_id)
    result = backend.onboard_operator(record, bootstrap_password or generate_bootstrap_password())
    state_path = operator_state_path(record["id"], state_dir)
    if not dry_run:
        state_path = persist_state(record["id"], "onboard", result, state_dir=state_dir)
    return {
        "status": "dry-run" if dry_run else "ok",
        "created": created,
        "operator": record,
        "roster_path": str(roster_path),
        "state_path": str(state_path),
        "result": result,
    }


def offboard(
    *,
    roster_path: Path,
    state_dir: Path,
    operator_id: str,
    actor_id: str,
    actor_class: str,
    reason: str | None,
    dry_run: bool,
) -> dict[str, Any]:
    roster = load_operator_roster(roster_path)
    updated_roster, updated_operator = mark_operator_inactive(roster, operator_id, actor_id)
    if not dry_run:
        dump_operator_roster(updated_roster, roster_path)
    backend = select_backend(dry_run=dry_run, actor_class=actor_class, actor_id=actor_id)
    result = backend.offboard_operator(updated_operator, reason)
    state_path = operator_state_path(operator_id, state_dir)
    if not dry_run:
        state_path = persist_state(operator_id, "offboard", result, state_dir=state_dir)
    return {
        "status": "dry-run" if dry_run else "ok",
        "operator": updated_operator,
        "roster_path": str(roster_path),
        "state_path": str(state_path),
        "result": result,
    }


def recover_totp(
    *,
    roster_path: Path,
    state_dir: Path,
    operator_id: str,
    actor_id: str,
    actor_class: str,
    dry_run: bool,
) -> dict[str, Any]:
    roster = load_operator_roster(roster_path)
    operator = find_operator(roster, operator_id)
    backend = select_backend(dry_run=dry_run, actor_class=actor_class, actor_id=actor_id)
    result = backend.recover_totp(operator)
    state_path = operator_state_path(operator_id, state_dir)
    if not dry_run:
        state_path = persist_state(operator_id, "recover-totp", result, state_dir=state_dir)
    return {
        "status": "dry-run" if dry_run else "ok",
        "operator": operator,
        "state_path": str(state_path),
        "result": result,
    }


def reset_password(
    *,
    roster_path: Path,
    state_dir: Path,
    operator_id: str,
    actor_id: str,
    actor_class: str,
    password: str,
    temporary: bool,
    dry_run: bool,
) -> dict[str, Any]:
    roster = load_operator_roster(roster_path)
    operator = find_operator(roster, operator_id)
    backend = select_backend(dry_run=dry_run, actor_class=actor_class, actor_id=actor_id)
    result = backend.reset_password(operator, password, temporary=temporary)
    state_path = operator_state_path(operator_id, state_dir)
    if not dry_run:
        state_path = persist_state(operator_id, "reset-password", result, state_dir=state_dir)
    return {
        "status": "dry-run" if dry_run else "ok",
        "operator": operator,
        "state_path": str(state_path),
        "result": result,
    }


def sync(
    *,
    roster_path: Path,
    state_dir: Path,
    actor_id: str,
    actor_class: str,
    operator_id: str | None,
    dry_run: bool,
) -> dict[str, Any]:
    roster = load_operator_roster(roster_path)
    backend = select_backend(dry_run=dry_run, actor_class=actor_class, actor_id=actor_id)
    prereq = backend.ensure_prerequisites()
    applied: list[dict[str, Any]] = []
    operators = roster["operators"]
    if operator_id:
        operators = [find_operator(roster, operator_id)]
    for operator in operators:
        if operator["status"] == "active":
            result = backend.onboard_operator(operator, generate_bootstrap_password())
            operation = "sync-onboard"
        else:
            result = backend.offboard_operator(operator, None)
            operation = "sync-offboard"
        state_path = operator_state_path(operator["id"], state_dir)
        if not dry_run:
            state_path = persist_state(operator["id"], operation, result, state_dir=state_dir)
        applied.append({"operator_id": operator["id"], "state_path": str(state_path), "result": result})
    return {
        "status": "dry-run" if dry_run else "ok",
        "prerequisites": prereq,
        "operators": applied,
    }


def inventory(
    *,
    roster_path: Path,
    state_dir: Path,
    operator_id: str,
    actor_id: str,
    actor_class: str,
    dry_run: bool,
    offline: bool,
) -> dict[str, Any]:
    roster = load_operator_roster(roster_path)
    operator = find_operator(roster, operator_id)
    backend = select_backend(dry_run=dry_run, actor_class=actor_class, actor_id=actor_id)
    state = load_state(operator_state_path(operator_id, state_dir))
    return backend.inventory_operator(operator, state, offline)


def quarterly_review(
    *,
    roster_path: Path,
    actor_id: str,
    actor_class: str,
    dry_run: bool,
    warning_days: int,
    inactive_days: int,
) -> dict[str, Any]:
    roster = load_operator_roster(roster_path)
    now = dt.datetime.now(dt.timezone.utc)
    review_entries: list[dict[str, Any]] = []
    flagged_count = 0
    for operator in roster["operators"]:
        if operator["status"] != "active":
            continue
        last_seen = operator["audit"].get("last_seen_at")
        last_seen_label = "never"
        age_days: int | None = None
        if last_seen:
            observed = dt.datetime.fromisoformat(last_seen.replace("Z", "+00:00"))
            age_days = (now - observed).days
            last_seen_label = f"{age_days} day(s) ago"
        flagged = age_days is None or age_days >= warning_days
        if flagged:
            flagged_count += 1
        review_entries.append(
            {
                "id": operator["id"],
                "role": operator["role"],
                "last_seen": last_seen_label,
                "inactive_days": age_days,
                "flagged": flagged,
                "stale": age_days is not None and age_days >= inactive_days,
            }
        )
    review = {
        "generated_at": utc_now(),
        "warning_days": warning_days,
        "inactive_days": inactive_days,
        "flagged_count": flagged_count,
        "operators": review_entries,
    }
    backend = select_backend(dry_run=dry_run, actor_class=actor_class, actor_id=actor_id)
    review["delivery"] = backend.quarterly_review(review)
    return review


def render_inventory_text(payload: dict[str, Any]) -> str:
    operator = payload["operator"]
    lines = [
        f"Access inventory for: {operator['id']}",
        f"  Name: {operator['name']}",
        f"  Email: {operator['email']}",
        f"  Keycloak: {payload['keycloak'].get('status', 'unknown')}, username={operator['keycloak']['username']}",
        (
            f"  step-ca SSH: disabled for role {operator['role']}"
            if not ROLE_DEFINITIONS[operator["role"]].ssh_enabled
            else f"  step-ca SSH: principal={operator['ssh']['principal']}, ttl={operator['ssh']['certificate_ttl_hours']}h"
        ),
        f"  OpenBao: {payload['openbao'].get('status', 'unknown')}, entity={operator['openbao']['entity_name']}",
        f"  Tailscale: {payload['tailscale'].get('status', 'unknown')}, login={operator['tailscale']['login_email']}",
    ]
    last_seen = operator["audit"].get("last_seen_at")
    if last_seen:
        lines.append(f"  Last seen: {last_seen}")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage the repo-authoritative LV3 human operator roster.")
    parser.add_argument("--roster-path", default=str(ROSTER_PATH))
    parser.add_argument("--state-dir", default=str(STATE_DIR))
    parser.add_argument("--actor-id", default=os.environ.get("USER", "unknown"))
    parser.add_argument("--actor-class", default=os.environ.get("LV3_OPERATOR_ACTOR_CLASS", "operator"))
    parser.add_argument("--emit-json", action="store_true")

    subparsers = parser.add_subparsers(dest="command", required=True)

    onboard_parser = subparsers.add_parser("onboard", help="Create or update one active operator.")
    onboard_parser.add_argument("--id")
    onboard_parser.add_argument("--name", required=True)
    onboard_parser.add_argument("--email", required=True)
    onboard_parser.add_argument("--role", required=True, choices=sorted(ROLE_NAMES))
    onboard_parser.add_argument("--ssh-key", default="")
    onboard_parser.add_argument("--ssh-key-name", default="primary")
    onboard_parser.add_argument("--keycloak-username")
    onboard_parser.add_argument("--tailscale-login-email")
    onboard_parser.add_argument("--tailscale-device-name")
    onboard_parser.add_argument("--bootstrap-password")
    onboard_parser.add_argument("--dry-run", action="store_true")

    offboard_parser = subparsers.add_parser("offboard", help="Disable one operator everywhere and mark them inactive in the roster.")
    offboard_parser.add_argument("--id", required=True)
    offboard_parser.add_argument("--reason")
    offboard_parser.add_argument("--dry-run", action="store_true")

    recover_totp_parser = subparsers.add_parser(
        "recover-totp",
        help="Reset one operator's Keycloak TOTP enrollment and require fresh setup on next login.",
    )
    recover_totp_parser.add_argument("--id", required=True)
    recover_totp_parser.add_argument("--dry-run", action="store_true")

    reset_password_parser = subparsers.add_parser(
        "reset-password",
        help="Set one operator's Keycloak password and optionally require rotation on next login.",
    )
    reset_password_parser.add_argument("--id", required=True)
    reset_password_parser.add_argument("--password", required=True)
    reset_password_parser.add_argument("--temporary", action="store_true")
    reset_password_parser.add_argument("--dry-run", action="store_true")

    inventory_parser = subparsers.add_parser("inventory", help="Show the access inventory for one operator.")
    inventory_parser.add_argument("--id", required=True)
    inventory_parser.add_argument("--offline", action="store_true")
    inventory_parser.add_argument("--dry-run", action="store_true")
    inventory_parser.add_argument("--format", choices=["text", "json"], default="text")

    sync_parser = subparsers.add_parser("sync", help="Apply the roster to external systems.")
    sync_parser.add_argument("--id")
    sync_parser.add_argument("--dry-run", action="store_true")

    review_parser = subparsers.add_parser("quarterly-review", help="Build and optionally publish the quarterly access review.")
    review_parser.add_argument("--warning-days", type=int, default=45)
    review_parser.add_argument("--inactive-days", type=int, default=60)
    review_parser.add_argument("--dry-run", action="store_true")

    validate_parser = subparsers.add_parser("validate", help="Validate config/operators.yaml and exit.")
    validate_parser.add_argument("--dry-run", action="store_true")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    roster_path = Path(args.roster_path)
    state_dir = Path(args.state_dir)
    try:
        if args.command == "onboard":
            payload = onboard(
                roster_path=roster_path,
                state_dir=state_dir,
                name=args.name,
                email=args.email,
                role=args.role,
                ssh_key=args.ssh_key,
                actor_id=args.actor_id,
                actor_class=args.actor_class,
                operator_id=args.id,
                keycloak_username=args.keycloak_username,
                ssh_key_name=args.ssh_key_name,
                tailscale_login_email=args.tailscale_login_email,
                tailscale_device_name=args.tailscale_device_name,
                bootstrap_password=args.bootstrap_password,
                dry_run=args.dry_run,
            )
        elif args.command == "offboard":
            payload = offboard(
                roster_path=roster_path,
                state_dir=state_dir,
                operator_id=args.id,
                actor_id=args.actor_id,
                actor_class=args.actor_class,
                reason=args.reason,
                dry_run=args.dry_run,
            )
        elif args.command == "recover-totp":
            payload = recover_totp(
                roster_path=roster_path,
                state_dir=state_dir,
                operator_id=args.id,
                actor_id=args.actor_id,
                actor_class=args.actor_class,
                dry_run=args.dry_run,
            )
        elif args.command == "reset-password":
            payload = reset_password(
                roster_path=roster_path,
                state_dir=state_dir,
                operator_id=args.id,
                actor_id=args.actor_id,
                actor_class=args.actor_class,
                password=args.password,
                temporary=args.temporary,
                dry_run=args.dry_run,
            )
        elif args.command == "inventory":
            payload = inventory(
                roster_path=roster_path,
                state_dir=state_dir,
                operator_id=args.id,
                actor_id=args.actor_id,
                actor_class=args.actor_class,
                dry_run=args.dry_run,
                offline=args.offline,
            )
            if args.format == "text" and not args.emit_json:
                print(render_inventory_text(payload))
                return 0
        elif args.command == "sync":
            payload = sync(
                roster_path=roster_path,
                state_dir=state_dir,
                actor_id=args.actor_id,
                actor_class=args.actor_class,
                operator_id=args.id,
                dry_run=args.dry_run,
            )
        elif args.command == "quarterly-review":
            payload = quarterly_review(
                roster_path=roster_path,
                actor_id=args.actor_id,
                actor_class=args.actor_class,
                dry_run=args.dry_run,
                warning_days=args.warning_days,
                inactive_days=args.inactive_days,
            )
        else:
            payload = load_operator_roster(roster_path)

        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    except (OSError, ValueError, json.JSONDecodeError, OperatorManagerError) as exc:
        return emit_cli_error("Operator manager", exc)


if __name__ == "__main__":
    sys.exit(main())
