from __future__ import annotations

import importlib.util
import json
import stat
from pathlib import Path
from typing import Any

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "reconcile_authentik_oauth.py"
SPEC = importlib.util.spec_from_file_location("reconcile_authentik_oauth", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class FakeAPI:
    def __init__(self, *, providers: list[dict[str, Any]], applications: list[dict[str, Any]]) -> None:
        self.providers = providers
        self.applications = applications
        self.flows = [
            {"pk": "flow-auth", "slug": "default-provider-authorization-implicit-consent"},
            {"pk": "flow-invalid", "slug": "default-provider-invalidation-flow"},
        ]
        self.scopes = [
            {"pk": "scope-openid", "scope_name": "openid"},
            {"pk": "scope-profile", "scope_name": "profile"},
            {"pk": "scope-email", "scope_name": "email"},
        ]
        self.posts: list[tuple[str, dict[str, Any]]] = []
        self.patches: list[tuple[str, dict[str, Any]]] = []

    def list_all(self, path: str) -> list[dict[str, Any]]:
        return {
            MODULE.PROVIDERS_PATH: self.providers,
            MODULE.APPLICATIONS_PATH: self.applications,
            MODULE.FLOWS_PATH: self.flows,
            MODULE.SCOPE_MAPPINGS_PATH: self.scopes,
        }[path]

    def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.posts.append((path, dict(payload)))
        if path == MODULE.PROVIDERS_PATH:
            created = {**payload, "pk": 41, "client_secret": payload.get("client_secret", "generated-secret")}
            self.providers.append(created)
            return created
        created = {**payload, "pk": "application-uuid"}
        self.applications.append(created)
        return created

    def patch(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.patches.append((path, dict(payload)))
        if path.startswith(MODULE.PROVIDERS_PATH):
            provider = next(item for item in self.providers if path == f"{MODULE.PROVIDERS_PATH}{item['pk']}/")
            provider.update(payload)
            return dict(provider)
        application = next(item for item in self.applications if path == f"{MODULE.APPLICATIONS_PATH}{item['slug']}/")
        application.update(payload)
        return dict(application)


def manifest() -> dict[str, Any]:
    return {
        "version": 1,
        "clients": [
            {
                "id": "glitchtip",
                "enabled": True,
                "client_secret_file": "authentik/glitchtip-client-secret.txt",
                "application": {
                    "name": "GlitchTip",
                    "slug": "glitchtip",
                    "launch_url": "https://errors.example.com",
                },
                "provider": {
                    "name": "glitchtip",
                    "client_id": "glitchtip",
                    "client_type": "confidential",
                    "grant_types": ["authorization_code"],
                    "authorization_flow": "default-provider-authorization-implicit-consent",
                    "invalidation_flow": "default-provider-invalidation-flow",
                    "scopes": ["openid", "profile", "email"],
                    "redirect_uris": ["https://errors.example.com/accounts/oidc/authentik/login/callback/"],
                    "include_claims_in_id_token": True,
                    "sub_mode": "hashed_user_id",
                    "issuer_mode": "per_provider",
                },
            }
        ],
    }


def existing_provider() -> dict[str, Any]:
    return {
        "pk": 7,
        "name": "glitchtip",
        "authorization_flow": "flow-auth",
        "invalidation_flow": "flow-invalid",
        "property_mappings": [],
        "client_type": "confidential",
        "grant_types": [],
        "client_id": "random-live-client-id",
        "client_secret": "existing-secret",
        "include_claims_in_id_token": True,
        "redirect_uris": [
            {
                "matching_mode": "strict",
                "url": "https://errors.example.com/accounts/oidc/authentik/login/callback/",
                "redirect_uri_type": "authorization",
            }
        ],
        "sub_mode": "hashed_user_id",
        "issuer_mode": "per_provider",
    }


def existing_application() -> dict[str, Any]:
    return {
        "pk": "existing-application-uuid",
        "name": "GlitchTip",
        "slug": "glitchtip",
        "provider": 7,
        "meta_launch_url": "",
        "policy_engine_mode": "any",
    }


def test_manifest_resolves_identity_without_committing_deployment_values() -> None:
    loaded = MODULE.load_manifest(
        REPO_ROOT / "config" / "authentik" / "oauth-clients.yaml",
        variables={"platform_domain": "example.net"},
    )
    clients = {client["id"]: client for client in loaded["clients"]}
    assert clients["glitchtip"]["application"]["launch_url"] == "https://errors.example.net"
    assert clients["glitchtip"]["provider"]["redirect_uris"] == [
        "https://errors.example.net/accounts/oidc/authentik/login/callback/"
    ]
    assert clients["outline"]["application"]["launch_url"] == "https://wiki.example.net"
    assert clients["outline"]["provider"]["redirect_uris"] == ["https://wiki.example.net/auth/oidc.callback"]


def test_adopts_linked_provider_preserves_pk_and_secret_then_is_idempotent(tmp_path: Path) -> None:
    api = FakeAPI(providers=[existing_provider()], applications=[existing_application()])

    first = MODULE.reconcile_manifest(manifest(), api, apply=True, local_secret_root=tmp_path)

    assert first["changed"] is True
    assert first["clients"][0]["provider_pk"] == 7
    provider_patch = next(payload for path, payload in api.patches if path == f"{MODULE.PROVIDERS_PATH}7/")
    assert provider_patch["client_id"] == "glitchtip"
    assert provider_patch["property_mappings"] == ["scope-openid", "scope-profile", "scope-email"]
    assert "client_secret" not in provider_patch
    secret_file = tmp_path / "authentik" / "glitchtip-client-secret.txt"
    assert secret_file.read_text(encoding="utf-8").strip() == "existing-secret"
    assert stat.S_IMODE(secret_file.stat().st_mode) == 0o600

    api.patches.clear()
    second = MODULE.reconcile_manifest(manifest(), api, apply=True, local_secret_root=tmp_path)

    assert second["changed"] is False
    assert api.patches == []


def test_create_uses_existing_local_secret_without_logging_it(tmp_path: Path) -> None:
    secret_file = tmp_path / "authentik" / "glitchtip-client-secret.txt"
    secret_file.parent.mkdir(parents=True)
    secret_file.write_text("controller-generated-secret\n", encoding="utf-8")
    secret_file.chmod(0o600)
    api = FakeAPI(providers=[], applications=[])

    result = MODULE.reconcile_manifest(manifest(), api, apply=True, local_secret_root=tmp_path)

    provider_payload = api.posts[0][1]
    assert provider_payload["client_secret"] == "controller-generated-secret"
    assert "controller-generated-secret" not in json.dumps(result)
    assert result["clients"][0]["provider_pk"] == 41


def test_mismatched_secret_fails_without_overwrite(tmp_path: Path) -> None:
    secret_file = tmp_path / "authentik" / "glitchtip-client-secret.txt"
    secret_file.parent.mkdir(parents=True)
    secret_file.write_text("different-secret\n", encoding="utf-8")
    secret_file.chmod(0o600)
    api = FakeAPI(providers=[existing_provider()], applications=[existing_application()])

    with pytest.raises(MODULE.ReconcileError, match="does not match Authentik"):
        MODULE.reconcile_manifest(manifest(), api, apply=True, local_secret_root=tmp_path)

    assert secret_file.read_text(encoding="utf-8").strip() == "different-secret"
    assert api.posts == []
    assert api.patches == []


def test_linkage_conflict_fails_before_provider_patch(tmp_path: Path) -> None:
    application = {**existing_application(), "provider": 99}
    provider = {**existing_provider(), "client_id": "glitchtip"}
    api = FakeAPI(providers=[provider], applications=[application])

    with pytest.raises(MODULE.ReconcileError, match="different managed provider"):
        MODULE.reconcile_manifest(manifest(), api, apply=True, local_secret_root=tmp_path)

    assert api.posts == []
    assert api.patches == []


def test_shared_provider_fails_before_provider_patch(tmp_path: Path) -> None:
    other_application = {
        **existing_application(),
        "pk": "other-application-uuid",
        "slug": "other",
        "provider": 7,
    }
    api = FakeAPI(
        providers=[existing_provider()],
        applications=[existing_application(), other_application],
    )

    with pytest.raises(MODULE.ReconcileError, match="shared by another application"):
        MODULE.reconcile_manifest(manifest(), api, apply=True, local_secret_root=tmp_path)

    assert api.posts == []
    assert api.patches == []


def test_new_provider_secret_is_persisted_before_api_creation(tmp_path: Path) -> None:
    api = FakeAPI(providers=[], applications=[])

    result = MODULE.reconcile_manifest(manifest(), api, apply=True, local_secret_root=tmp_path)

    secret_path = tmp_path / "authentik" / "glitchtip-client-secret.txt"
    local_secret = secret_path.read_text(encoding="utf-8").strip()
    assert len(local_secret) >= 48
    assert api.posts[0][1]["client_secret"] == local_secret
    assert local_secret not in json.dumps(result)
    assert stat.S_IMODE(secret_path.stat().st_mode) == 0o600


def test_all_selected_clients_are_validated_before_any_mutation(tmp_path: Path) -> None:
    multi_client_manifest = manifest()
    second = json.loads(json.dumps(multi_client_manifest["clients"][0]))
    second["id"] = "outline"
    second["client_secret_file"] = "authentik/outline-client-secret.txt"
    second["application"].update(
        name="Outline",
        slug="outline",
        launch_url="https://wiki.example.com",
    )
    second["provider"].update(
        name="outline",
        client_id="outline",
        redirect_uris=["https://wiki.example.com/auth/oidc.callback"],
    )
    multi_client_manifest["clients"].append(second)

    outline_provider = {
        **existing_provider(),
        "pk": 8,
        "name": "outline",
        "client_id": "outline",
        "client_secret": "outline-live-secret",
    }
    outline_application = {
        **existing_application(),
        "pk": "outline-application-uuid",
        "name": "Outline",
        "slug": "outline",
        "provider": 8,
        "meta_launch_url": "https://wiki.example.com",
    }
    wrong_secret = tmp_path / "authentik" / "outline-client-secret.txt"
    wrong_secret.parent.mkdir(parents=True)
    wrong_secret.write_text("wrong-outline-secret\n", encoding="utf-8")
    wrong_secret.chmod(0o600)
    api = FakeAPI(
        providers=[existing_provider(), outline_provider],
        applications=[existing_application(), outline_application],
    )

    with pytest.raises(MODULE.ReconcileError, match="does not match Authentik"):
        MODULE.reconcile_manifest(
            multi_client_manifest,
            api,
            apply=True,
            local_secret_root=tmp_path,
        )

    assert api.posts == []
    assert api.patches == []


def test_secret_creation_refuses_concurrent_destination(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    secret_path = tmp_path / "authentik" / "glitchtip-client-secret.txt"
    real_link = MODULE.os.link

    def racing_link(source, destination) -> None:
        Path(destination).write_text("concurrent-secret\n", encoding="utf-8")
        real_link(source, destination)

    monkeypatch.setattr(MODULE.os, "link", racing_link)

    with pytest.raises(MODULE.ReconcileError, match="appeared concurrently"):
        MODULE._write_secret_atomic(secret_path, "planned-secret")

    assert secret_path.read_text(encoding="utf-8").strip() == "concurrent-secret"


def test_expect_no_change_uses_read_only_mode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    token_file = tmp_path / "token.txt"
    token_file.write_text("test-token\n", encoding="utf-8")
    captured: dict[str, object] = {}

    def fake_reconcile(manifest, api, *, apply, local_secret_root, selected_clients=None):
        captured["apply"] = apply
        return {"changed": False}

    monkeypatch.setattr(MODULE, "reconcile_manifest", fake_reconcile)

    assert (
        MODULE.main(
            [
                "--base-url",
                "https://id.example.com",
                "--platform-domain",
                "example.com",
                "--token-file",
                str(token_file),
                "--check",
                "--expect-no-change",
            ]
        )
        == 0
    )
    assert captured["apply"] is False

    with pytest.raises(MODULE.ReconcileError, match="cannot be combined"):
        MODULE.main(
            [
                "--base-url",
                "https://id.example.com",
                "--platform-domain",
                "example.com",
                "--token-file",
                str(token_file),
                "--apply",
                "--expect-no-change",
            ]
        )


def test_duplicate_application_slug_fails_before_mutation(tmp_path: Path) -> None:
    duplicate = {**existing_application(), "pk": "second-application-uuid"}
    api = FakeAPI(providers=[existing_provider()], applications=[existing_application(), duplicate])

    with pytest.raises(MODULE.ReconcileError, match="Multiple Authentik application"):
        MODULE.reconcile_manifest(manifest(), api, apply=True, local_secret_root=tmp_path)

    assert api.posts == []
    assert api.patches == []
