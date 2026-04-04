from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import operator_manager  # noqa: E402
import provision_operator  # noqa: E402


def test_discover_local_root_prefers_shared_repo_root_for_worktrees(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    worktree_root = repo_root / ".worktrees" / "ws-0317"
    (repo_root / ".local").mkdir(parents=True)
    worktree_root.mkdir(parents=True)

    assert provision_operator.discover_local_root(worktree_root, repo_root) == repo_root / ".local"


def test_discover_local_root_ignores_worktree_shadow_local_dir(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    worktree_root = repo_root / ".worktrees" / "ws-0318"
    (repo_root / ".local").mkdir(parents=True)
    (worktree_root / ".local" / "keycloak").mkdir(parents=True)

    assert provision_operator.discover_local_root(worktree_root, repo_root) == repo_root / ".local"


def test_repo_path_routes_dot_local_to_shared_checkout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    worktree_root = repo_root / ".worktrees" / "ws-0317"
    shared_local = repo_root / ".local"
    worktree_root.mkdir(parents=True)
    shared_local.mkdir(parents=True)

    monkeypatch.setattr(provision_operator, "REPO_ROOT", worktree_root)
    monkeypatch.setattr(provision_operator, "COMMON_REPO_ROOT", repo_root)
    monkeypatch.setattr(provision_operator, "LOCAL_ROOT", shared_local)

    assert provision_operator.repo_path(".local", "keycloak", "bootstrap-admin-password.txt") == (
        shared_local / "keycloak" / "bootstrap-admin-password.txt"
    )
    assert provision_operator.repo_path("config", "operators.yaml") == worktree_root / "config" / "operators.yaml"


def test_role_definitions_align_with_operator_manager() -> None:
    for role_name, expected in operator_manager.ROLE_DEFINITIONS.items():
        observed = provision_operator.ROLE_DEFINITIONS[role_name]
        assert tuple(observed["realm_roles"]) == expected.keycloak_roles
        assert tuple(observed["groups"]) == expected.keycloak_groups
        assert tuple(observed["openbao_policies"]) == expected.openbao_policies


def test_configured_url_prefers_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LV3_KEYCLOAK_URL", "http://127.0.0.1:18080/")
    assert provision_operator.configured_url("LV3_KEYCLOAK_URL", provision_operator.DEFAULT_KEYCLOAK_URL) == (
        "http://127.0.0.1:18080"
    )


def test_configured_url_falls_back_to_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LV3_HEADSCALE_URL", raising=False)
    assert (
        provision_operator.configured_url("LV3_HEADSCALE_URL", provision_operator.DEFAULT_HEADSCALE_URL)
        == provision_operator.DEFAULT_HEADSCALE_URL
    )


def test_read_keycloak_bootstrap_password_prefers_env_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    bootstrap_file = tmp_path / "bootstrap-admin-password.txt"
    bootstrap_file.write_text("stale-file-password\n", encoding="utf-8")

    monkeypatch.setattr(provision_operator, "BOOTSTRAP_PASS_FILE", bootstrap_file)
    monkeypatch.setenv("LV3_KEYCLOAK_BOOTSTRAP_PASSWORD", "live-runtime-password")

    assert provision_operator.read_keycloak_bootstrap_password() == "live-runtime-password"


def test_read_platform_smtp_password_prefers_env_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    smtp_file = tmp_path / "platform-transactional-mailbox-password.txt"
    smtp_file.write_text("stale-file-password\n", encoding="utf-8")

    monkeypatch.setattr(provision_operator, "SMTP_PASS_FILE", smtp_file)
    monkeypatch.setenv("LV3_PLATFORM_SMTP_PASSWORD", "live-runtime-password")

    assert provision_operator.read_platform_smtp_password() == "live-runtime-password"


def test_provision_skip_email_verifies_existing_assignments(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    local_root = tmp_path / ".local"
    password_dir = local_root / "keycloak"
    bootstrap_file = password_dir / "bootstrap-admin-password.txt"
    password_dir.mkdir(parents=True)
    bootstrap_file.write_text("Bootstrap123\n", encoding="utf-8")

    monkeypatch.setattr(provision_operator, "BOOTSTRAP_PASS_FILE", bootstrap_file)
    monkeypatch.setattr(provision_operator, "PASSWORD_DIR", password_dir)
    monkeypatch.setattr(
        provision_operator,
        "SMTP_PASS_FILE",
        tmp_path / ".local" / "mail-platform" / "profiles" / "platform-transactional-mailbox-password.txt",
    )
    monkeypatch.setattr(
        provision_operator,
        "SSH_KEY_FILE",
        tmp_path / ".local" / "ssh" / "bootstrap.id_ed25519",
    )

    monkeypatch.setattr(provision_operator, "get_token", lambda _password: "token")

    created_user = {"id": None}
    assigned_roles: list[str] = []
    assigned_groups: list[str] = []
    group_id_map = {"lv3-platform-viewers": "g-1", "grafana-viewers": "g-2"}

    def fake_kc(method: str, path: str, token: str, body=None):  # noqa: ANN001
        assert token == "token"
        if method == "GET" and path == "/users?username=viewer.example&exact=true":
            if created_user["id"] is None:
                return 200, []
            return 200, [{"id": created_user["id"]}]
        if method == "POST" and path == "/users":
            created_user["id"] = "user-123"
            return 201, None
        if method == "GET" and path == "/roles/platform-read":
            return 200, {"id": "role-123", "name": "platform-read"}
        if method == "POST" and path == "/users/user-123/role-mappings/realm":
            assigned_roles.extend(item["name"] for item in body)
            return 204, None
        if method == "GET" and path == "/groups?max=200":
            return 200, [{"name": name, "id": group_id} for name, group_id in group_id_map.items()]
        if method == "PUT" and path.startswith("/users/user-123/groups/"):
            group_id = path.rsplit("/", 1)[-1]
            for group_name, known_group_id in group_id_map.items():
                if group_id == known_group_id:
                    assigned_groups.append(group_name)
                    break
            return 204, None
        if method == "GET" and path == "/users/user-123/role-mappings/realm":
            return 200, [{"name": role_name} for role_name in assigned_roles]
        if method == "GET" and path == "/users/user-123/groups":
            return 200, [{"name": group_name} for group_name in assigned_groups]
        raise AssertionError(f"unexpected Keycloak call: {method} {path}")

    monkeypatch.setattr(provision_operator, "kc", fake_kc)

    email_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def fake_send_email(*args, **kwargs) -> None:  # noqa: ANN002, ANN003
        email_calls.append((args, kwargs))

    monkeypatch.setattr(provision_operator, "send_email_via_ssh_proxy", fake_send_email)

    args = argparse.Namespace(
        id="viewer-example-001",
        name="Viewer Example",
        email="viewer@example.com",
        username="viewer.example",
        role="viewer",
        expires="2026-04-08T00:00:00Z",
        requester="ops@example.com",
        dry_run=False,
        skip_email=True,
    )

    provision_operator.provision(args, dry_run=False)

    assert created_user["id"] == "user-123"
    assert assigned_roles == ["platform-read"]
    assert assigned_groups == ["lv3-platform-viewers", "grafana-viewers"]
    assert (password_dir / "viewer.example-password.txt").exists()
    assert email_calls == []
