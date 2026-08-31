from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "reconcile_authentik_identities.py"
SPEC = importlib.util.spec_from_file_location("reconcile_authentik_identities", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class FakeAPI:
    def __init__(self, *, groups: list[dict[str, Any]], users: list[dict[str, Any]]) -> None:
        self.groups = groups
        self.users = users
        self.posts: list[tuple[str, dict[str, Any]]] = []
        self.patches: list[tuple[str, dict[str, Any]]] = []

    def list_all(self, path: str) -> list[dict[str, Any]]:
        return {MODULE.GROUPS_PATH: self.groups, MODULE.USERS_PATH: self.users}[path]

    def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.posts.append((path, dict(payload)))
        if path == MODULE.GROUPS_PATH:
            return {**payload, "pk": f"group-{len(self.groups) + 1}"}
        if path == MODULE.USERS_PATH:
            return {**payload, "pk": len(self.users) + 100}
        if path.endswith("/set_password/"):
            return {}
        raise AssertionError(path)

    def patch(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.patches.append((path, dict(payload)))
        if path.startswith(MODULE.GROUPS_PATH):
            group = next(item for item in self.groups if path == f"{MODULE.GROUPS_PATH}{item['pk']}/")
            group.update(payload)
            return dict(group)
        user = next(item for item in self.users if path == f"{MODULE.USERS_PATH}{item['pk']}/")
        user.update(payload)
        return dict(user)


def manifest() -> dict[str, Any]:
    return {
        "version": 1,
        "groups": [
            {"id": "platform-admins", "name": "example-platform-admins", "attributes": {"scope": "admin"}},
        ],
        "users": [
            {
                "id": "operator",
                "username": "operator",
                "name": "Platform Operator",
                "email": "operator@example.com",
                "password_file": "authentik/operator-password.txt",
                "groups": ["authentik Admins", "example-platform-admins"],
                "is_active": True,
            }
        ],
    }


def validated_manifest(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": payload["version"],
        "groups": [MODULE._validate_group(item, index) for index, item in enumerate(payload["groups"])],
        "users": [MODULE._validate_user(item, index) for index, item in enumerate(payload["users"])],
    }


def test_manifest_resolves_generic_operator_identity() -> None:
    loaded = MODULE.load_manifest(
        REPO_ROOT / "config" / "authentik" / "identities.yaml",
        variables={
            "platform_domain": "example.net",
            "platform_config_prefix": "example",
            "authentik_bootstrap_admin_username": "akadmin",
            "platform_operator_name": "Platform Operator",
            "platform_operator_email": "operator@example.net",
        },
    )
    assert loaded["groups"][0]["name"] == "example-platform-admins"
    assert loaded["users"][0]["username"] == "akadmin"
    assert loaded["users"][0]["provisioning"] == "existing_only"


def test_create_sets_initial_password_once_then_is_idempotent(tmp_path: Path) -> None:
    password = tmp_path / "authentik" / "operator-password.txt"
    password.parent.mkdir()
    password.write_text("initial-password\n", encoding="utf-8")
    api = FakeAPI(groups=[{"pk": "built-in-admins", "name": "authentik Admins", "attributes": {}}], users=[])

    first = MODULE.reconcile_manifest(validated_manifest(manifest()), api, apply=True, local_secret_root=tmp_path)

    assert first["changed"] is True
    assert any(path.endswith("/set_password/") for path, _ in api.posts)
    assert "initial-password" not in json.dumps(first)
    user_post = next(payload for path, payload in api.posts if path == MODULE.USERS_PATH)
    assert user_post["groups"] == ["built-in-admins", "group-2"]

    password.unlink()
    api.posts.clear()
    second = MODULE.reconcile_manifest(validated_manifest(manifest()), api, apply=True, local_secret_root=tmp_path)

    assert second["changed"] is False
    assert api.posts == []
    assert api.patches == []


def test_missing_builtin_group_fails_before_creating_user(tmp_path: Path) -> None:
    password = tmp_path / "authentik" / "operator-password.txt"
    password.parent.mkdir()
    password.write_text("initial-password\n", encoding="utf-8")
    api = FakeAPI(groups=[], users=[])

    with pytest.raises(MODULE.ReconcileError, match="missing Authentik group"):
        MODULE.reconcile_manifest(validated_manifest(manifest()), api, apply=True, local_secret_root=tmp_path)

    assert api.posts == []


def test_password_paths_cannot_escape_shared_local_root() -> None:
    payload = manifest()
    payload["users"][0]["password_file"] = "../outside.txt"
    with pytest.raises(ValueError):
        MODULE._validate_user(payload["users"][0], 0)


def test_existing_service_account_only_reconciles_declared_groups(tmp_path: Path) -> None:
    payload = {
        "version": 1,
        "groups": [
            {"id": "operator", "name": "platform-operator", "attributes": {}},
            {"id": "read", "name": "platform-read", "attributes": {}},
        ],
        "users": [
            {
                "id": "agent-hub-client-credentials",
                "username": "ak-agent-hub-client_credentials",
                "provisioning": "existing_only",
                "managed_fields": ["groups"],
                "groups": ["platform-operator", "platform-read"],
            }
        ],
    }
    api = FakeAPI(
        groups=[
            {"pk": "operator", "name": "platform-operator", "attributes": {}},
            {"pk": "read", "name": "platform-read", "attributes": {}},
        ],
        users=[
            {
                "pk": 900,
                "username": "ak-agent-hub-client_credentials",
                "groups": [],
                "name": "agent-hub service account",
                "email": "",
                "is_active": True,
                "type": "service_account",
                "attributes": {},
            }
        ],
    )

    result = MODULE.reconcile_manifest(validated_manifest(payload), api, apply=True, local_secret_root=tmp_path)

    assert result["changed"] is True
    assert all(path != MODULE.USERS_PATH for path, _ in api.posts)
    assert api.patches == [(f"{MODULE.USERS_PATH}900/", {"groups": ["operator", "read"]})]


def test_group_order_canonicalization_is_idempotent(tmp_path: Path) -> None:
    payload = {
        "version": 1,
        "groups": [
            {"id": "operator", "name": "platform-operator", "attributes": {}},
            {"id": "read", "name": "platform-read", "attributes": {}},
        ],
        "users": [
            {
                "id": "agent",
                "username": "agent",
                "provisioning": "existing_only",
                "managed_fields": ["groups"],
                "groups": ["platform-operator", "platform-read"],
            }
        ],
    }
    api = FakeAPI(
        groups=[
            {"pk": "operator", "name": "platform-operator", "attributes": {}},
            {"pk": "read", "name": "platform-read", "attributes": {}},
        ],
        users=[
            {
                "pk": 901,
                "username": "agent",
                "groups": ["read", "operator"],
                "name": "agent",
                "email": "",
                "is_active": True,
                "type": "service_account",
                "attributes": {},
            }
        ],
    )

    result = MODULE.reconcile_manifest(validated_manifest(payload), api, apply=False, local_secret_root=tmp_path)

    assert result["changed"] is False
    assert api.patches == []


def test_existing_service_account_must_exist_before_any_identity_mutation(tmp_path: Path) -> None:
    payload = {
        "version": 1,
        "groups": [{"id": "operator", "name": "platform-operator", "attributes": {}}],
        "users": [
            {
                "id": "agent-hub-client-credentials",
                "username": "ak-agent-hub-client_credentials",
                "provisioning": "existing_only",
                "managed_fields": ["groups"],
                "groups": ["platform-operator"],
            }
        ],
    }
    api = FakeAPI(groups=[], users=[])

    with pytest.raises(MODULE.ReconcileError, match="is required before identity reconciliation"):
        MODULE.reconcile_manifest(validated_manifest(payload), api, apply=True, local_secret_root=tmp_path)

    assert api.posts == []
