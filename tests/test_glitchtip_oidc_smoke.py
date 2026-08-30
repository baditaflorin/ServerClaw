from __future__ import annotations

import json
from http import cookiejar
from typing import Any
from urllib import parse, request

import pytest

import glitchtip_oidc_smoke


class FakeResponse:
    def __init__(self, status: int, body: dict[str, Any] | bytes, headers: dict[str, str] | None = None) -> None:
        self._status = status
        self._body = json.dumps(body).encode("utf-8") if isinstance(body, dict) else body
        self.headers = headers or {}

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def getcode(self) -> int:
        return self._status

    def read(self) -> bytes:
        return self._body


class FakeOpener:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = responses
        self.requests: list[request.Request] = []

    def open(self, http_request: request.Request, timeout: float = 0) -> FakeResponse:
        self.requests.append(http_request)
        return self.responses.pop(0)


def make_cookie(name: str, value: str) -> cookiejar.Cookie:
    return cookiejar.Cookie(
        version=0,
        name=name,
        value=value,
        port=None,
        port_specified=False,
        domain="errors.example.com",
        domain_specified=True,
        domain_initial_dot=False,
        path="/",
        path_specified=True,
        secure=True,
        expires=None,
        discard=True,
        comment=None,
        comment_url=None,
        rest={},
        rfc2109=False,
    )


def test_verify_oidc_redirect_uses_headless_form_and_sanitizes_output() -> None:
    base_url = "https://errors.example.com"
    issuer_url = "https://id.example.com/application/o/glitchtip"
    client_id = "public-client-id"
    authorization_endpoint = "https://id.example.com/application/o/authorize/"
    backend_callback = f"{base_url}/accounts/oidc/authentik/login/callback/"
    location = (
        authorization_endpoint
        + "?"
        + parse.urlencode(
            {
                "client_id": client_id,
                "redirect_uri": backend_callback,
                "response_type": "code",
                "state": "sensitive-oauth-state",
            }
        )
    )
    config = {
        "data": {
            "socialaccount": {
                "providers": [
                    {
                        "id": "authentik",
                        "name": "Authentik",
                        "client_id": client_id,
                        "openid_configuration_url": (f"{issuer_url}/.well-known/openid-configuration"),
                        "flows": ["provider_redirect", "provider_token"],
                    }
                ]
            }
        }
    }
    discovery = {
        "issuer": f"{issuer_url}/",
        "authorization_endpoint": authorization_endpoint,
    }
    opener = FakeOpener(
        [
            FakeResponse(200, config),
            FakeResponse(200, discovery),
            FakeResponse(302, b"", {"Location": location}),
        ]
    )
    jar = cookiejar.CookieJar()
    jar.set_cookie(make_cookie("csrftoken", "csrf-value"))

    result = glitchtip_oidc_smoke.verify_oidc_redirect(
        base_url=base_url,
        provider_id="authentik",
        issuer_url=f"{issuer_url}/",
        expected_client_id=client_id,
        timeout_seconds=12,
        opener=opener,  # type: ignore[arg-type]
        jar=jar,
    )

    assert result == {
        "status": "ok",
        "provider_id": "authentik",
        "issuer": issuer_url,
        "discovery_url": f"{issuer_url}/.well-known/openid-configuration",
        "authorization_endpoint": authorization_endpoint,
        "backend_callback_url": backend_callback,
        "frontend_callback_url": f"{base_url}/login",
        "token_endpoint": None,
        "client_secret_verified": False,
    }
    assert "sensitive-oauth-state" not in json.dumps(result)
    redirect_request = opener.requests[2]
    assert redirect_request.get_method() == "POST"
    assert parse.parse_qs(redirect_request.data.decode("utf-8")) == {
        "provider": ["authentik"],
        "process": ["login"],
        "callback_url": [f"{base_url}/login"],
    }
    headers = {key.lower(): value for key, value in redirect_request.header_items()}
    assert headers["x-csrftoken"] == "csrf-value"
    assert headers["origin"] == base_url


def test_verify_oidc_redirect_rejects_non_normalized_discovery_metadata() -> None:
    issuer_url = "https://id.example.com/application/o/glitchtip"
    config = {
        "data": {
            "socialaccount": {
                "providers": [
                    {
                        "id": "authentik",
                        "client_id": "public-client-id",
                        "openid_configuration_url": (f"{issuer_url}//.well-known/openid-configuration"),
                        "flows": ["provider_redirect"],
                    }
                ]
            }
        }
    }
    opener = FakeOpener([FakeResponse(200, config)])

    with pytest.raises(glitchtip_oidc_smoke.OIDCSmokeError, match="normalized issuer discovery URL"):
        glitchtip_oidc_smoke.verify_oidc_redirect(
            base_url="https://errors.example.com",
            provider_id="authentik",
            issuer_url=issuer_url,
            opener=opener,  # type: ignore[arg-type]
            jar=cookiejar.CookieJar(),
        )


def test_validate_authorization_redirect_rejects_wrong_callback_without_echoing_query() -> None:
    with pytest.raises(glitchtip_oidc_smoke.OIDCSmokeError, match="unexpected backend callback URL") as exc_info:
        glitchtip_oidc_smoke.validate_authorization_redirect(
            "https://id.example.com/application/o/authorize/?"
            + parse.urlencode(
                {
                    "client_id": "public-client-id",
                    "redirect_uri": "https://attacker.example/callback",
                    "state": "sensitive-oauth-state",
                }
            ),
            authorization_endpoint="https://id.example.com/application/o/authorize/",
            expected_client_id="public-client-id",
            expected_callback_url="https://errors.example.com/accounts/oidc/authentik/login/callback/",
        )

    assert "sensitive-oauth-state" not in str(exc_info.value)


def test_verify_client_secret_distinguishes_accepted_client_from_rejected_secret() -> None:
    opener = FakeOpener(
        [
            FakeResponse(400, {"error": "invalid_grant"}),
            FakeResponse(401, {"error": "invalid_client"}),
        ]
    )

    glitchtip_oidc_smoke.verify_client_secret(
        opener,  # type: ignore[arg-type]
        token_endpoint="https://id.example.com/application/o/token/",
        auth_methods=["client_secret_basic"],
        client_id="glitchtip",
        client_secret="configured-secret",
        redirect_uri="https://errors.example.com/accounts/oidc/authentik/login/callback/",
        timeout_seconds=10,
    )

    first_headers = {key.lower(): value for key, value in opener.requests[0].header_items()}
    second_headers = {key.lower(): value for key, value in opener.requests[1].header_items()}
    assert first_headers["authorization"].startswith("Basic ")
    assert second_headers["authorization"].startswith("Basic ")
    assert first_headers["authorization"] != second_headers["authorization"]
    assert b"configured-secret" not in (opener.requests[0].data or b"")


def test_verify_client_secret_rejects_ambiguous_token_errors() -> None:
    opener = FakeOpener(
        [
            FakeResponse(400, {"error": "invalid_client"}),
            FakeResponse(401, {"error": "invalid_client"}),
        ]
    )

    with pytest.raises(glitchtip_oidc_smoke.OIDCSmokeError, match="did not accept the configured client"):
        glitchtip_oidc_smoke.verify_client_secret(
            opener,  # type: ignore[arg-type]
            token_endpoint="https://id.example.com/application/o/token/",
            auth_methods=["client_secret_basic"],
            client_id="glitchtip",
            client_secret="wrong-secret",
            redirect_uri="https://errors.example.com/accounts/oidc/authentik/login/callback/",
            timeout_seconds=10,
        )
