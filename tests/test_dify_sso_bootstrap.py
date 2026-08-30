from __future__ import annotations

from typing import Any

from scripts.dify_sso_bootstrap import _bootstrap_sso, _build_ssh_tunnel_command


class FakeDifyClient:
    def __init__(self, *, setup_step: str, sso_setting: dict[str, Any] | None) -> None:
        self.setup_step = setup_step
        self.sso_setting = sso_setting
        self.setup_calls: list[dict[str, Any]] = []
        self.login_calls: list[dict[str, Any]] = []
        self.configure_calls: list[dict[str, Any]] = []

    def setup_status(self) -> dict[str, str]:
        return {"step": self.setup_step}

    def setup(self, **kwargs: Any) -> dict[str, str]:
        self.setup_calls.append(kwargs)
        self.setup_step = "finished"
        return {"result": "success"}

    def login(self, **kwargs: Any) -> dict[str, str]:
        self.login_calls.append(kwargs)
        return {"result": "success"}

    def get_sso_setting(self) -> dict[str, Any] | None:
        return self.sso_setting

    def configure_sso(self, **kwargs: Any) -> dict[str, str]:
        self.configure_calls.append(kwargs)
        return {"result": "success"}


def bootstrap(client: FakeDifyClient) -> dict:
    return _bootstrap_sso(
        client,  # type: ignore[arg-type]
        admin_email="operator@example.com",
        admin_name="Platform Operator",
        admin_password="admin-password",
        init_password="init-password",
        keycloak_client_id="dify",
        keycloak_client_secret="client-secret",
        keycloak_issuer_url="https://sso.example.com/realms/platform",
    )


def test_bootstrap_initializes_admin_before_reporting_unavailable_sso() -> None:
    client = FakeDifyClient(setup_step="not_started", sso_setting=None)

    result = bootstrap(client)

    assert result["action"] == "unavailable"
    assert result["changed"] is True
    assert result["admin_bootstrap"] == "configured"
    assert client.setup_calls[0]["init_password"] == "init-password"
    assert client.login_calls == [{"email": "operator@example.com", "password": "admin-password"}]


def test_bootstrap_is_unchanged_when_admin_and_sso_already_match() -> None:
    client = FakeDifyClient(
        setup_step="finished",
        sso_setting={
            "enabled": True,
            "type": "oidc",
            "client_id": "dify",
            "issuer_url": "https://sso.example.com/realms/platform",
        },
    )

    result = bootstrap(client)

    assert result["action"] == "already-configured"
    assert result["changed"] is False
    assert result["admin_bootstrap"] == "already-configured"
    assert client.configure_calls == []


def test_ssh_tunnel_command_forwards_only_the_runtime_loopback_port() -> None:
    command = _build_ssh_tunnel_command(
        ssh_host="10.10.10.20",
        ssh_user="ops",
        ssh_jump_host="203.0.113.10",
        ssh_jump_user="ops",
        ssh_jump_port=22,
        ssh_private_key_file="/tmp/bootstrap.id_ed25519",
        ssh_remote_port=8094,
        local_port=18094,
    )

    assert "127.0.0.1:18094:127.0.0.1:8094" in command
    assert command[-1] == "ops@10.10.10.20"
    proxy_option = next(value for value in command if value.startswith("ProxyCommand="))
    assert "ops@203.0.113.10" in proxy_option
    assert "-W %h:%p" in proxy_option
