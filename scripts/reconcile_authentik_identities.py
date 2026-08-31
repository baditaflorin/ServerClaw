#!/usr/bin/env python3
"""Reconcile Authentik groups and initial human identities without exposing secrets.

The manifest contains no passwords.  A password is read from the shared
ignored ``.local`` overlay only while creating a new internal user, which lets
an operator subsequently change their password without a later converge
silently overwriting it.
"""

from __future__ import annotations

import argparse
import json
import stat
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Protocol

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

from platform.repo import local_overlay_root, validate_repo_relative_path
from validation_toolkit import (
    require_bool,
    require_enum,
    require_identifier,
    require_list,
    require_mapping,
    require_str,
    require_unique_string_list,
    resolve_jinja2_vars,
)


DEFAULT_MANIFEST = REPO_ROOT / "config" / "authentik" / "identities.yaml"
GROUPS_PATH = "/api/v3/core/groups/"
USERS_PATH = "/api/v3/core/users/"
MANAGED_GROUP_FIELDS = ("name", "attributes")
MANAGED_USER_FIELDS = ("name", "email", "groups", "is_active", "type", "attributes")
USER_PROVISIONING_MODES = {"create_if_missing", "existing_only"}
USER_TYPES = {"internal", "service_account"}


class ReconcileError(RuntimeError):
    """Raised when safe identity reconciliation cannot continue."""


class AuthentikAPI(Protocol):
    def list_all(self, path: str) -> list[dict[str, Any]]: ...

    def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]: ...

    def patch(self, path: str, payload: dict[str, Any]) -> dict[str, Any]: ...


class HTTPAuthentikAPI:
    """Minimal Authentik API client whose failures never echo response bodies."""

    def __init__(self, base_url: str, token: str, *, timeout: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.token}",
            "User-Agent": "serverclaw-authentik-identity-reconciler/1",
        }
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(f"{self.base_url}{path}", data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = response.read()
                return {} if not body else require_mapping(json.loads(body), f"{method} {path} response")
        except urllib.error.HTTPError as exc:
            exc.read()
            raise ReconcileError(f"Authentik {method} {path} returned HTTP {exc.code}") from None
        except urllib.error.URLError as exc:
            raise ReconcileError(f"Authentik {method} {path} failed: {exc.reason}") from None

    def list_all(self, path: str) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        page = 1
        while True:
            query = urllib.parse.urlencode({"page": page, "page_size": 100})
            payload = self._request("GET", f"{path}?{query}")
            page_results = require_list(payload.get("results"), f"GET {path}.results")
            results.extend(
                require_mapping(item, f"GET {path}.results[{index}]") for index, item in enumerate(page_results)
            )
            pagination = require_mapping(payload.get("pagination"), f"GET {path}.pagination")
            next_page = pagination.get("next")
            if not next_page:
                return results
            if isinstance(next_page, bool) or not isinstance(next_page, int) or next_page <= page:
                raise ReconcileError(f"Authentik pagination for {path} returned an invalid next page")
            page = next_page

    def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", path, payload)

    def patch(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("PATCH", path, payload)


def _relative_secret_path(value: Any, path: str) -> str:
    normalized = validate_repo_relative_path(require_str(value, path), label=path)
    if normalized.startswith(".local/"):
        raise ValueError(f"{path} must be relative to the shared .local root")
    return normalized


def _attributes(value: Any, path: str) -> dict[str, Any]:
    attributes = require_mapping(value if value is not None else {}, path)
    try:
        json.dumps(attributes)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{path} must be JSON serializable") from exc
    return attributes


def _validate_group(raw: Any, index: int) -> dict[str, Any]:
    path = f"groups[{index}]"
    group = require_mapping(raw, path)
    return {
        "id": require_identifier(group.get("id"), f"{path}.id"),
        "name": require_str(group.get("name"), f"{path}.name"),
        "attributes": _attributes(group.get("attributes", {}), f"{path}.attributes"),
    }


def _validate_user(raw: Any, index: int) -> dict[str, Any]:
    path = f"users[{index}]"
    user = require_mapping(raw, path)
    provisioning = require_enum(
        user.get("provisioning", "create_if_missing"),
        f"{path}.provisioning",
        USER_PROVISIONING_MODES,
    )
    managed_fields = require_unique_string_list(
        user.get("managed_fields", list(MANAGED_USER_FIELDS)),
        f"{path}.managed_fields",
        min_length=1,
    )
    unknown_managed_fields = sorted(set(managed_fields) - set(MANAGED_USER_FIELDS))
    if unknown_managed_fields:
        raise ValueError(f"{path}.managed_fields contains unsupported fields: {', '.join(unknown_managed_fields)}")
    if provisioning == "create_if_missing" and set(managed_fields) != set(MANAGED_USER_FIELDS):
        raise ValueError(
            f"{path}.managed_fields must include every managed user field when provisioning=create_if_missing"
        )

    def optional_string(field: str) -> str | None:
        return require_str(user.get(field), f"{path}.{field}") if field in managed_fields else None

    name = optional_string("name")
    email = optional_string("email")
    if email is not None and "@" not in email:
        raise ValueError(f"{path}.email must be an email address")
    user_type = (
        require_enum(user.get("type", "internal"), f"{path}.type", USER_TYPES) if "type" in managed_fields else None
    )
    password_file: str | None = None
    if provisioning == "create_if_missing":
        password_file = _relative_secret_path(user.get("password_file"), f"{path}.password_file")
    elif user.get("password_file") is not None:
        password_file = _relative_secret_path(user.get("password_file"), f"{path}.password_file")
    return {
        "id": require_identifier(user.get("id"), f"{path}.id"),
        "username": require_str(user.get("username"), f"{path}.username"),
        "name": name,
        "email": email,
        "password_file": password_file,
        "groups": require_unique_string_list(user.get("groups", []), f"{path}.groups"),
        "is_active": require_bool(user.get("is_active", True), f"{path}.is_active")
        if "is_active" in managed_fields
        else None,
        "type": user_type,
        "attributes": _attributes(user.get("attributes", {}), f"{path}.attributes"),
        "managed_fields": managed_fields,
        "provisioning": provisioning,
    }


def load_manifest(path: Path, *, variables: dict[str, str] | None = None) -> dict[str, Any]:
    rendered_variables = dict(variables or {})
    platform_domain = rendered_variables.get("platform_domain")
    if platform_domain and not rendered_variables.get("platform_config_prefix"):
        rendered_variables["platform_config_prefix"] = platform_domain.split(".", 1)[0]
    rendered = resolve_jinja2_vars(path.read_text(encoding="utf-8"), rendered_variables)
    payload = require_mapping(yaml.safe_load(rendered), str(path))
    if payload.get("version") != 1:
        raise ValueError(f"{path}.version must be 1")
    groups = [_validate_group(item, index) for index, item in enumerate(require_list(payload.get("groups"), "groups"))]
    users = [_validate_user(item, index) for index, item in enumerate(require_list(payload.get("users"), "users"))]
    for label, values in (
        ("group id", [group["id"] for group in groups]),
        ("group name", [group["name"] for group in groups]),
        ("user id", [user["id"] for user in users]),
        ("username", [user["username"] for user in users]),
    ):
        duplicates = sorted({value for value in values if values.count(value) > 1})
        if duplicates:
            raise ValueError(f"manifest must use unique {label} values: {', '.join(duplicates)}")
    return {"version": 1, "groups": groups, "users": users}


def _find_unique(items: list[dict[str, Any]], field: str, value: Any, label: str) -> dict[str, Any] | None:
    matches = [item for item in items if item.get(field) == value]
    if len(matches) > 1:
        raise ReconcileError(f"Multiple Authentik {label} objects match {field}={value!r}")
    return matches[0] if matches else None


def _safe_secret_path(local_secret_root: Path, relative_path: str) -> Path:
    root = local_secret_root.resolve()
    destination = (root / relative_path).resolve()
    if destination != root and root not in destination.parents:
        raise ReconcileError("Identity password path escapes the shared .local root")
    return destination


def _read_initial_password(path: Path) -> str:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        raise ReconcileError(f"Initial identity password file {path} is missing") from None
    if not stat.S_ISREG(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
        raise ReconcileError(f"Initial identity password file {path} must be a regular file")
    password = path.read_text(encoding="utf-8").strip()
    if not password:
        raise ReconcileError(f"Initial identity password file {path} is empty")
    return password


def _changed_fields(current: dict[str, Any], desired: dict[str, Any], fields: tuple[str, ...]) -> list[str]:
    def values_equal(field: str) -> bool:
        current_value = current.get(field)
        desired_value = desired.get(field)
        # Authentik may canonicalize group membership ordering when it returns
        # a user.  Membership is set-like, so a harmless order change must not
        # cause every converge to patch the account again.
        if field == "groups":
            return sorted(current_value or []) == sorted(desired_value or [])
        return current_value == desired_value

    return [field for field in fields if not values_equal(field)]


def _change(identity_id: str, object_type: str, action: str, pk: Any, fields: list[str]) -> dict[str, Any]:
    return {
        "identity": identity_id,
        "object": object_type,
        "action": action,
        "pk": pk,
        "fields": sorted(fields),
    }


def reconcile_manifest(
    manifest: dict[str, Any],
    api: AuthentikAPI,
    *,
    apply: bool,
    local_secret_root: Path,
) -> dict[str, Any]:
    groups = api.list_all(GROUPS_PATH)
    users = api.list_all(USERS_PATH)
    changes: list[dict[str, Any]] = []
    group_plans: list[dict[str, Any]] = []

    for group_config in manifest["groups"]:
        group = _find_unique(groups, "name", group_config["name"], "group")
        desired = {"name": group_config["name"], "attributes": group_config["attributes"]}
        action = "create" if group is None else "unchanged"
        fields = list(MANAGED_GROUP_FIELDS) if group is None else _changed_fields(group, desired, MANAGED_GROUP_FIELDS)
        if fields and group is not None:
            action = "update"
        if action != "unchanged":
            changes.append(_change(group_config["id"], "group", action, group.get("pk") if group else None, fields))
        group_plans.append(
            {"config": group_config, "group": group, "desired": desired, "action": action, "fields": fields}
        )

    # Prove every referenced group either already exists or is declared in the
    # same manifest before creating anything.  A typo in a built-in group name
    # must not leave half of an identity bootstrap applied.
    available_group_names = {str(group.get("name")) for group in groups}
    available_group_names.update(plan["config"]["name"] for plan in group_plans)
    for user_config in manifest["users"]:
        unresolved = sorted(set(user_config["groups"]) - available_group_names)
        if unresolved:
            raise ReconcileError(
                f"User {user_config['id']!r} references missing Authentik group(s): {', '.join(unresolved)}"
            )
        if (
            user_config["provisioning"] == "existing_only"
            and _find_unique(users, "username", user_config["username"], "user") is None
        ):
            raise ReconcileError(
                f"Existing Authentik user {user_config['username']!r} is required before identity reconciliation"
            )

    if apply:
        for plan in group_plans:
            group = plan["group"]
            if plan["action"] == "create":
                group = api.post(GROUPS_PATH, plan["desired"])
                groups.append(group)
            elif plan["action"] == "update":
                group = api.patch(
                    f"{GROUPS_PATH}{group['pk']}/",
                    {field: plan["desired"][field] for field in plan["fields"]},
                )
            plan["group"] = group

    group_by_name = {str(group.get("name")): group for group in groups if group.get("pk") is not None}
    if not apply:
        # A dry run must be able to describe the complete first bootstrap even
        # though its managed groups do not have server-assigned PKs yet.
        for plan in group_plans:
            if plan["group"] is None:
                group_by_name[plan["config"]["name"]] = {"pk": f"planned:{plan['config']['id']}"}
    user_plans: list[dict[str, Any]] = []
    for user_config in manifest["users"]:
        unresolved = sorted(set(user_config["groups"]) - set(group_by_name))
        if unresolved:
            raise ReconcileError(
                f"User {user_config['id']!r} references missing Authentik group(s): {', '.join(unresolved)}"
            )
        group_pks = [group_by_name[name]["pk"] for name in user_config["groups"]]
        user = _find_unique(users, "username", user_config["username"], "user")
        attributes = dict(user.get("attributes") or {}) if user else {}
        attributes.update(user_config.get("attributes", {}))
        desired_values = {
            "name": user_config["name"],
            "email": user_config["email"],
            "groups": group_pks,
            "is_active": user_config["is_active"],
            "type": user_config["type"],
            "attributes": attributes,
        }
        desired = {field: desired_values[field] for field in user_config["managed_fields"]}
        if user is None and user_config["provisioning"] == "existing_only":
            raise ReconcileError(
                f"Existing Authentik user {user_config['username']!r} is required before identity reconciliation"
            )
        action = "create" if user is None else "unchanged"
        fields = (
            list(user_config["managed_fields"])
            if user is None
            else _changed_fields(user, desired, tuple(user_config["managed_fields"]))
        )
        if fields and user is not None:
            action = "update"
        password_path = (
            _safe_secret_path(local_secret_root, user_config["password_file"])
            if user_config["password_file"] is not None
            else None
        )
        if action == "create":
            # Validate every needed password before the first identity mutation.
            if password_path is None:
                raise ReconcileError(f"New Authentik user {user_config['id']!r} has no initial password file")
            _read_initial_password(password_path)
            changes.append(_change(user_config["id"], "user", "create", None, fields + ["initial_password"]))
        elif action != "unchanged":
            changes.append(_change(user_config["id"], "user", action, user.get("pk"), fields))
        user_plans.append(
            {
                "config": user_config,
                "user": user,
                "desired": desired,
                "action": action,
                "fields": fields,
                "password_path": password_path,
            }
        )

    reconciled_groups: list[dict[str, Any]] = []
    for plan in group_plans:
        group = plan["group"]
        reconciled_groups.append(
            {"group": plan["config"]["id"], "pk": group.get("pk") if group else None, "action": plan["action"]}
        )

    reconciled_users: list[dict[str, Any]] = []
    if apply:
        for plan in user_plans:
            user = plan["user"]
            if plan["action"] == "create":
                user = api.post(
                    USERS_PATH,
                    {"username": plan["config"]["username"], **plan["desired"]},
                )
                user_pk = user.get("pk")
                if user_pk is None:
                    raise ReconcileError(f"Created Authentik user {plan['config']['id']!r} has no primary key")
                password_path = plan["password_path"]
                if password_path is None:
                    raise ReconcileError(f"New Authentik user {plan['config']['id']!r} has no initial password file")
                api.post(f"{USERS_PATH}{user_pk}/set_password/", {"password": _read_initial_password(password_path)})
                users.append(user)
            elif plan["action"] == "update":
                user = api.patch(
                    f"{USERS_PATH}{user['pk']}/",
                    {field: plan["desired"][field] for field in plan["fields"]},
                )
            reconciled_users.append(
                {"user": plan["config"]["id"], "pk": user.get("pk") if user else None, "action": plan["action"]}
            )
    else:
        reconciled_users = [
            {
                "user": plan["config"]["id"],
                "pk": plan["user"].get("pk") if plan["user"] else None,
                "action": plan["action"],
            }
            for plan in user_plans
        ]

    return {
        "status": "ok",
        "mode": "apply" if apply else "check",
        "changed": bool(changes),
        "change_count": len(changes),
        "changes": changes,
        "groups": reconciled_groups,
        "users": reconciled_users,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--token-file", type=Path, required=True)
    parser.add_argument("--platform-domain", required=True)
    parser.add_argument("--platform-config-prefix")
    parser.add_argument("--authentik-bootstrap-admin-username", required=True)
    parser.add_argument("--platform-operator-name", required=True)
    parser.add_argument("--platform-operator-email", required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--apply", action="store_true")
    parser.add_argument("--expect-no-change", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.expect_no_change and args.apply:
        raise ReconcileError("--expect-no-change cannot be combined with --apply")
    token = args.token_file.read_text(encoding="utf-8").strip()
    if not token:
        raise ReconcileError(f"Authentik token file {args.token_file} is empty")
    manifest = load_manifest(
        args.manifest,
        variables={
            "platform_domain": args.platform_domain,
            "platform_config_prefix": args.platform_config_prefix or args.platform_domain.split(".", 1)[0],
            "authentik_bootstrap_admin_username": args.authentik_bootstrap_admin_username,
            "platform_operator_name": args.platform_operator_name,
            "platform_operator_email": args.platform_operator_email,
        },
    )
    result = reconcile_manifest(
        manifest,
        HTTPAuthentikAPI(args.base_url, token),
        apply=args.apply,
        local_secret_root=local_overlay_root(REPO_ROOT),
    )
    print(json.dumps(result, sort_keys=True))
    return 2 if args.expect_no_change and result["changed"] else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, ReconcileError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
