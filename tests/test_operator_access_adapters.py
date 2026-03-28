from __future__ import annotations

import operator_manager
from platform.operator_access import KeycloakAdminAdapter, OpenBaoIdentityAdapter


def test_keycloak_adapter_inventory_translates_provider_payloads() -> None:
    calls: list[str] = []

    def fake_request(url: str, **kwargs):
        calls.append(url)
        if url.endswith("/realms/master/protocol/openid-connect/token"):
            return {"access_token": "bootstrap-token"}
        if "users?username=alice&exact=true" in url:
            return [{"id": "user-1", "username": "alice", "enabled": False, "email": "alice@example.com"}]
        raise AssertionError(f"unexpected request: {url} {kwargs}")

    adapter = KeycloakAdminAdapter(
        base_url="https://sso.example.test",
        realm="lv3",
        bootstrap_admin="bootstrap-admin",
        bootstrap_password_loader=lambda: "secret",
        request=fake_request,
    )

    payload = adapter.inventory_user("alice", email_fallback="fallback@example.com")

    assert payload == {
        "status": "disabled",
        "username": "alice",
        "email": "alice@example.com",
    }
    assert calls[0].endswith("/realms/master/protocol/openid-connect/token")


def test_openbao_adapter_inventory_translates_provider_payloads() -> None:
    def fake_request(url: str, **kwargs):
        assert url.endswith("/v1/identity/entity/name/alice")
        assert kwargs["headers"] == {"X-Vault-Token": "root-token"}
        return {"data": {"id": "entity-1", "disabled": True, "policies": ["platform-admin"]}}

    adapter = OpenBaoIdentityAdapter(
        base_url="http://openbao.example.test",
        root_token_loader=lambda: "root-token",
        request=fake_request,
    )

    payload = adapter.inventory_entity("alice", policies_fallback=["platform-read"])

    assert payload == {
        "status": "disabled",
        "entity_name": "alice",
        "entity_id": "entity-1",
        "policies": ["platform-admin"],
    }


def test_openbao_adapter_inventory_reports_missing_entities() -> None:
    adapter = OpenBaoIdentityAdapter(
        base_url="http://openbao.example.test",
        root_token_loader=lambda: "root-token",
        request=lambda *args, **kwargs: {"errors": []},
    )

    payload = adapter.inventory_entity("alice", policies_fallback=["platform-read"])

    assert payload == {
        "status": "missing",
        "entity_name": "alice",
        "entity_id": "",
        "policies": ["platform-read"],
    }


def test_live_backend_inventory_uses_port_contracts() -> None:
    class FakeIdentityDirectory:
        def ensure_role(self, role_name: str, *, description: str):
            raise AssertionError("not used")

        def ensure_group(self, group_name: str):
            raise AssertionError("not used")

        def ensure_user(self, operator, *, bootstrap_password: str):
            raise AssertionError("not used")

        def disable_user(self, username: str):
            raise AssertionError("not used")

        def recover_totp(self, username: str):
            raise AssertionError("not used")

        def reset_password(self, username: str, *, password: str, temporary: bool):
            raise AssertionError("not used")

        def inventory_user(self, username: str, *, email_fallback: str):
            assert username == "alice"
            return {"status": "active", "username": username, "email": email_fallback}

    class FakeSecretAuthority:
        def ensure_policy(self, policy_name: str, document: str):
            raise AssertionError("not used")

        def ensure_entity(self, operator):
            raise AssertionError("not used")

        def inventory_entity(self, entity_name: str, *, policies_fallback):
            assert entity_name == "alice"
            return {"status": "active", "entity_name": entity_name, "policies": list(policies_fallback)}

    class FakeSSHCertificates:
        def register_principal(self, operator, *, enabled: bool):
            raise AssertionError("not used")

        def revoke_principal(self, operator, *, enabled: bool):
            raise AssertionError("not used")

    class FakeMeshNetwork:
        def invite(self, operator):
            raise AssertionError("not used")

        def remove(self, operator):
            raise AssertionError("not used")

        def inventory(self, operator):
            return {"status": "connected", "devices": [{"id": "device-1"}]}

    class FakeNotifications:
        def post_text(self, text: str):
            raise AssertionError("not used")

    backend = operator_manager.LiveBackend(
        actor_class="operator",
        actor_id="tester",
        identity_directory=FakeIdentityDirectory(),
        secret_authority=FakeSecretAuthority(),
        ssh_certificates=FakeSSHCertificates(),
        mesh_network=FakeMeshNetwork(),
        notifications=FakeNotifications(),
    )

    payload = backend.inventory_operator(
        {
            "id": "alice-example",
            "name": "Alice Example",
            "email": "alice@example.com",
            "role": "operator",
            "keycloak": {"username": "alice"},
            "openbao": {"entity_name": "alice", "policies": ["platform-operator"]},
            "ssh": {"principal": "alice", "certificate_ttl_hours": 24},
            "tailscale": {"login_email": "alice@example.com"},
        },
        state={"step_ca": {"status": "cached"}},
        offline=False,
    )

    assert payload["keycloak"]["status"] == "active"
    assert payload["openbao"]["entity_name"] == "alice"
    assert payload["tailscale"]["status"] == "connected"
    assert payload["step_ca"]["status"] == "cached"
