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
    worktree_root = repo_root / ".worktrees" / "ws-0491"
    (repo_root / ".local").mkdir(parents=True)
    worktree_root.mkdir(parents=True)

    assert provision_operator.discover_local_root(worktree_root, repo_root) == repo_root / ".local"


def test_discover_local_root_ignores_worktree_shadow_local_dir(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    worktree_root = repo_root / ".worktrees" / "ws-0491"
    (repo_root / ".local").mkdir(parents=True)
    (worktree_root / ".local" / "authentik").mkdir(parents=True)

    assert provision_operator.discover_local_root(worktree_root, repo_root) == repo_root / ".local"


def test_repo_path_routes_dot_local_to_shared_checkout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    worktree_root = repo_root / ".worktrees" / "ws-0491"
    shared_local = repo_root / ".local"
    worktree_root.mkdir(parents=True)
    shared_local.mkdir(parents=True)

    monkeypatch.setattr(provision_operator, "REPO_ROOT", worktree_root)
    monkeypatch.setattr(provision_operator, "COMMON_REPO_ROOT", repo_root)
    monkeypatch.setattr(provision_operator, "LOCAL_ROOT", shared_local)

    assert provision_operator.repo_path(".local", "authentik", "bootstrap-token.txt") == (
        shared_local / "authentik" / "bootstrap-token.txt"
    )
    assert provision_operator.repo_path("config", "operators.yaml") == worktree_root / "config" / "operators.yaml"


def test_role_definitions_align_with_operator_manager() -> None:
    for role_name, expected in operator_manager.ROLE_DEFINITIONS.items():
        observed = provision_operator.ROLE_DEFINITIONS[role_name]
        assert tuple(observed["groups"]) == expected.authentik_groups
        assert tuple(observed["openbao_policies"]) == expected.openbao_policies


def test_configured_url_prefers_authentik_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LV3_AUTHENTIK_URL", "http://127.0.0.1:19000/")
    assert provision_operator.configured_url("LV3_AUTHENTIK_URL", provision_operator.DEFAULT_AUTHENTIK_URL) == (
        "http://127.0.0.1:19000"
    )


def test_configured_url_falls_back_to_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LV3_HEADSCALE_URL", raising=False)
    assert (
        provision_operator.configured_url("LV3_HEADSCALE_URL", provision_operator.DEFAULT_HEADSCALE_URL)
        == provision_operator.DEFAULT_HEADSCALE_URL
    )


def test_read_authentik_bootstrap_token_prefers_env_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    token_file = tmp_path / "bootstrap-token.txt"
    token_file.write_text("stale-file-token\n", encoding="utf-8")

    monkeypatch.setattr(provision_operator, "AUTHENTIK_TOKEN_FILE", token_file)
    monkeypatch.setenv("LV3_AUTHENTIK_BOOTSTRAP_TOKEN", "live-runtime-token")

    assert provision_operator.read_authentik_bootstrap_token() == "live-runtime-token"


def test_read_mail_gateway_api_key_prefers_env_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    key_file = tmp_path / "platform-transactional-gateway-api-key.txt"
    key_file.write_text("stale-file-key\n", encoding="utf-8")

    monkeypatch.setattr(provision_operator, "MAIL_GATEWAY_KEY_FILE", key_file)
    monkeypatch.setenv("LV3_MAIL_GATEWAY_API_KEY", "live-runtime-key")

    assert provision_operator.read_mail_gateway_api_key() == "live-runtime-key"


def test_resolve_identity_env_override_drives_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PLATFORM_DOMAIN", "acme.example")
    domain, prefix = provision_operator._resolve_identity()
    assert (domain, prefix) == ("acme.example", "acme")


def test_render_service_lines_substitutes_domain(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    catalog = tmp_path / "service-capability-catalog.json"
    catalog.write_text(
        '{"services": ['
        '{"id": "authentik", "name": "Authentik", "category": "access", "public_url": "https://id.example.com"},'
        '{"id": "nginx_edge", "name": "NGINX", "category": "access", "public_url": "https://nginx.example.com"},'
        '{"id": "ollama", "name": "Ollama", "category": "automation", "public_url": null}'
        "]}",
        encoding="utf-8",
    )
    monkeypatch.setattr(provision_operator, "SERVICE_CATALOG_PATH", catalog)
    rendered = provision_operator.render_service_lines("acme.example")
    assert "https://id.acme.example" in rendered
    assert "example.com" not in rendered
    assert "NGINX" not in rendered
    assert "Ollama" not in rendered


def test_build_email_payload_uses_authentik_urls(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(provision_operator, "PLATFORM_DOMAIN", "acme.example")
    monkeypatch.setattr(provision_operator, "DEFAULT_AUTHENTIK_URL", "https://id.acme.example")
    monkeypatch.setattr(
        provision_operator, "render_service_lines", lambda _domain: "  Authentik  https://id.acme.example"
    )
    payload = provision_operator.build_email_payload(
        to_email="new@example.com",
        cc_email="ops@example.com",
        first_name="New",
        username="new.user",
        password="secret",
        role="admin",
        expiry="2026-09-06T00:00:00Z",
        requester_email="ops@example.com",
        headscale_authkey="hskey-xyz",
        ca_fingerprint="abc123",
    )
    assert payload["to"] == ["new@example.com"]
    assert payload["cc"] == ["ops@example.com"]
    assert "https://id.acme.example/if/user/" in payload["text"]
    assert "acme.example" in payload["subject"]


def test_provision_skip_email_creates_authentik_user_and_groups(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    password_dir = tmp_path / ".local" / "authentik"
    password_dir.mkdir(parents=True)
    monkeypatch.setattr(provision_operator, "PASSWORD_DIR", password_dir)
    monkeypatch.setattr(provision_operator, "read_authentik_bootstrap_token", lambda: "api-token")

    requests: list[tuple[str, str, object]] = []
    created_user = {"pk": 7, "groups": ["group-read", "group-grafana"]}

    def fake_api(method: str, path: str, token: str, body=None):  # noqa: ANN001
        assert token == "api-token"
        requests.append((method, path, body))
        if method == "GET" and path.startswith("/core/users/?"):
            return 200, {"results": [], "pagination": {"next": None}}
        if method == "GET" and path.startswith("/core/groups/?"):
            return 200, {
                "results": [
                    {"name": "platform-read", "pk": "group-read"},
                    {"name": "grafana-viewers", "pk": "group-grafana"},
                ],
                "pagination": {"next": None},
            }
        if method == "POST" and path == "/core/users/":
            assert body["groups"] == ["group-read", "group-grafana"]
            return 201, {"pk": created_user["pk"]}
        if method == "POST" and path == "/core/users/7/set_password/":
            assert isinstance(body, dict) and body["password"]
            return 204, None
        if method == "GET" and path == "/core/users/7/":
            return 200, {"pk": 7, "groups": created_user["groups"]}
        raise AssertionError(f"unexpected Authentik call: {method} {path}")

    monkeypatch.setattr(provision_operator, "authentik_api", fake_api)
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

    assert (password_dir / "viewer.example-password.txt").is_file()
    assert any(method == "POST" and path == "/core/users/" for method, path, _body in requests)
    assert all("keycloak" not in path for _method, path, _body in requests)
