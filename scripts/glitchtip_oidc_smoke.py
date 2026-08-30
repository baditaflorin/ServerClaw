#!/usr/bin/env python3
"""Verify GlitchTip's allauth headless OIDC redirect without logging secrets."""

from __future__ import annotations

import argparse
import base64
import json
import re
import secrets
import stat
import sys
from dataclasses import dataclass
from http import cookiejar
from pathlib import Path
from typing import Any
from urllib import error, parse, request


USER_AGENT = "lv3-glitchtip-oidc-smoke/1.0"
CONFIG_PATH = "/_allauth/browser/v1/config"
PROVIDER_REDIRECT_PATH = "/_allauth/browser/v1/auth/provider/redirect"


class OIDCSmokeError(RuntimeError):
    """Raised when the public OIDC redirect contract is incomplete."""


class NoRedirectHandler(request.HTTPRedirectHandler):
    """Return redirect responses to the verifier instead of following them."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        return None


@dataclass(frozen=True)
class ResponseSnapshot:
    status_code: int
    headers: dict[str, str]
    body: bytes


def normalize_base_url(value: str) -> str:
    parsed = parse.urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise OIDCSmokeError("base URL must be an absolute HTTP(S) URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise OIDCSmokeError("base URL must not contain credentials, a query, or a fragment")
    path = parsed.path.rstrip("/")
    if path not in {"", "/"}:
        raise OIDCSmokeError("base URL must not contain an application path")
    return parsed._replace(path="", params="", query="", fragment="").geturl().rstrip("/")


def normalize_issuer_url(value: str) -> str:
    parsed = parse.urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise OIDCSmokeError("issuer URL must be an absolute HTTP(S) URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise OIDCSmokeError("issuer URL must not contain credentials, a query, or a fragment")
    normalized_path = parsed.path.rstrip("/")
    return parsed._replace(path=normalized_path, params="", query="", fragment="").geturl()


def discovery_url_for_issuer(issuer_url: str) -> str:
    return f"{normalize_issuer_url(issuer_url)}/.well-known/openid-configuration"


def build_opener(jar: cookiejar.CookieJar) -> request.OpenerDirector:
    return request.build_opener(request.HTTPCookieProcessor(jar), NoRedirectHandler())


def fetch_response(
    opener: request.OpenerDirector,
    url: str,
    *,
    method: str = "GET",
    data: bytes | None = None,
    headers: dict[str, str] | None = None,
    timeout_seconds: float,
) -> ResponseSnapshot:
    request_headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    request_headers.update(headers or {})
    http_request = request.Request(url, data=data, headers=request_headers, method=method)
    try:
        with opener.open(http_request, timeout=timeout_seconds) as response:
            return ResponseSnapshot(
                status_code=response.getcode(),
                headers={key.lower(): value for key, value in response.headers.items()},
                body=response.read(),
            )
    except error.HTTPError as exc:
        return ResponseSnapshot(
            status_code=exc.code,
            headers={key.lower(): value for key, value in exc.headers.items()},
            body=exc.read(),
        )


def load_json(snapshot: ResponseSnapshot, *, label: str, expected_status: int = 200) -> dict[str, Any]:
    if snapshot.status_code != expected_status:
        raise OIDCSmokeError(f"{label} returned HTTP {snapshot.status_code}; expected {expected_status}")
    try:
        payload = json.loads(snapshot.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OIDCSmokeError(f"{label} did not return a JSON object") from exc
    if not isinstance(payload, dict):
        raise OIDCSmokeError(f"{label} did not return a JSON object")
    return payload


def find_cookie_value(jar: cookiejar.CookieJar, name: str) -> str | None:
    for cookie in jar:
        if cookie.name == name:
            return cookie.value
    return None


def select_provider(config: dict[str, Any], provider_id: str) -> dict[str, Any]:
    providers = config.get("data", {}).get("socialaccount", {}).get("providers", [])
    matches = [provider for provider in providers if isinstance(provider, dict) and provider.get("id") == provider_id]
    if len(matches) != 1:
        raise OIDCSmokeError(
            f"allauth config must advertise exactly one provider with id {provider_id!r}; found {len(matches)}"
        )
    provider = matches[0]
    flows = provider.get("flows", [])
    if "provider_redirect" not in flows:
        raise OIDCSmokeError(f"allauth provider {provider_id!r} does not advertise the provider_redirect flow")
    if not provider.get("client_id"):
        raise OIDCSmokeError(f"allauth provider {provider_id!r} does not advertise a client ID")
    return provider


def sanitized_url(value: str) -> str:
    parsed = parse.urlparse(value)
    return parsed._replace(query="", fragment="").geturl()


def validate_authorization_redirect(
    location: str,
    *,
    authorization_endpoint: str,
    expected_client_id: str,
    expected_callback_url: str,
) -> dict[str, str]:
    location_parts = parse.urlparse(location)
    authorization_parts = parse.urlparse(authorization_endpoint)
    if (location_parts.scheme, location_parts.netloc, location_parts.path) != (
        authorization_parts.scheme,
        authorization_parts.netloc,
        authorization_parts.path,
    ):
        raise OIDCSmokeError(
            "provider redirect did not target the discovery document's authorization endpoint "
            f"({sanitized_url(authorization_endpoint)})"
        )
    query = parse.parse_qs(location_parts.query)
    if query.get("client_id", [None])[0] != expected_client_id:
        raise OIDCSmokeError("provider redirect used an unexpected client ID")
    if query.get("redirect_uri", [None])[0] != expected_callback_url:
        raise OIDCSmokeError("provider redirect used an unexpected backend callback URL")
    if not query.get("state", [""])[0]:
        raise OIDCSmokeError("provider redirect did not include an OAuth state value")
    return {
        "authorization_endpoint": sanitized_url(authorization_endpoint),
        "callback_url": expected_callback_url,
    }


def _oauth_error(snapshot: ResponseSnapshot, *, label: str) -> str:
    if snapshot.status_code not in {400, 401}:
        raise OIDCSmokeError(f"{label} returned HTTP {snapshot.status_code}; expected an OAuth error response")
    try:
        payload = json.loads(snapshot.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OIDCSmokeError(f"{label} did not return an OAuth JSON error") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("error"), str):
        raise OIDCSmokeError(f"{label} did not return an OAuth JSON error")
    return payload["error"]


def verify_client_secret(
    opener: request.OpenerDirector,
    *,
    token_endpoint: str,
    auth_methods: list[str],
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    timeout_seconds: float,
) -> None:
    if not client_secret:
        raise OIDCSmokeError("OIDC client secret file is empty")
    if "client_secret_basic" in auth_methods:
        selected_method = "client_secret_basic"
    elif "client_secret_post" in auth_methods:
        selected_method = "client_secret_post"
    else:
        raise OIDCSmokeError("OIDC discovery does not advertise a supported confidential-client auth method")

    def probe(secret_value: str, *, label: str) -> str:
        form = {
            "grant_type": "authorization_code",
            "code": "lv3-deliberately-invalid-authorization-code",
            "redirect_uri": redirect_uri,
            "client_id": client_id,
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        if selected_method == "client_secret_basic":
            encoded_id = parse.quote(client_id, safe="")
            encoded_secret = parse.quote(secret_value, safe="")
            credentials = base64.b64encode(f"{encoded_id}:{encoded_secret}".encode()).decode("ascii")
            headers["Authorization"] = f"Basic {credentials}"
        else:
            form["client_secret"] = secret_value
        snapshot = fetch_response(
            opener,
            token_endpoint,
            method="POST",
            data=parse.urlencode(form).encode("utf-8"),
            headers=headers,
            timeout_seconds=timeout_seconds,
        )
        return _oauth_error(snapshot, label=label)

    accepted_error = probe(client_secret, label="OIDC token endpoint accepted-client probe")
    rejected_error = probe(
        f"invalid-{secrets.token_urlsafe(24)}",
        label="OIDC token endpoint rejected-client probe",
    )
    if accepted_error != "invalid_grant":
        raise OIDCSmokeError(
            "OIDC token endpoint did not accept the configured client before rejecting the invalid code"
        )
    if rejected_error != "invalid_client":
        raise OIDCSmokeError("OIDC token endpoint did not reject the deliberately invalid client secret")


def verify_oidc_redirect(
    *,
    base_url: str,
    provider_id: str,
    issuer_url: str,
    expected_client_id: str | None = None,
    callback_url: str | None = None,
    client_secret: str | None = None,
    timeout_seconds: float = 30.0,
    opener: request.OpenerDirector | None = None,
    jar: cookiejar.CookieJar | None = None,
) -> dict[str, Any]:
    if not re.fullmatch(r"[A-Za-z0-9._~-]+", provider_id):
        raise OIDCSmokeError("provider ID contains unsupported URL path characters")
    normalized_base = normalize_base_url(base_url)
    normalized_issuer = normalize_issuer_url(issuer_url)
    expected_discovery_url = discovery_url_for_issuer(normalized_issuer)
    frontend_callback_url = callback_url or f"{normalized_base}/login"
    callback_parts = parse.urlparse(frontend_callback_url)
    base_parts = parse.urlparse(normalized_base)
    if (callback_parts.scheme, callback_parts.netloc) != (base_parts.scheme, base_parts.netloc):
        raise OIDCSmokeError("frontend callback URL must use the GlitchTip origin")

    cookie_jar = jar if jar is not None else cookiejar.CookieJar()
    http_opener = opener if opener is not None else build_opener(cookie_jar)

    config_snapshot = fetch_response(
        http_opener,
        f"{normalized_base}{CONFIG_PATH}",
        timeout_seconds=timeout_seconds,
    )
    config = load_json(config_snapshot, label="GlitchTip allauth config")
    provider = select_provider(config, provider_id)
    configured_discovery_url = provider.get("openid_configuration_url")
    if configured_discovery_url != expected_discovery_url:
        raise OIDCSmokeError(
            "allauth provider discovery URL is not the normalized issuer discovery URL: "
            f"expected {expected_discovery_url}, found {configured_discovery_url!r}"
        )
    configured_client_id = str(provider["client_id"])
    if expected_client_id is not None and configured_client_id != expected_client_id:
        raise OIDCSmokeError("allauth provider advertises an unexpected client ID")

    discovery_snapshot = fetch_response(
        http_opener,
        expected_discovery_url,
        timeout_seconds=timeout_seconds,
    )
    discovery = load_json(discovery_snapshot, label="OIDC discovery document")
    if normalize_issuer_url(str(discovery.get("issuer", ""))) != normalized_issuer:
        raise OIDCSmokeError("OIDC discovery document advertises an unexpected issuer")
    authorization_endpoint = str(discovery.get("authorization_endpoint", ""))
    if not authorization_endpoint:
        raise OIDCSmokeError("OIDC discovery document has no authorization endpoint")

    csrf_token = find_cookie_value(cookie_jar, "csrftoken")
    if not csrf_token:
        raise OIDCSmokeError("GlitchTip allauth config did not set the browser CSRF cookie")
    form = parse.urlencode(
        {
            "provider": provider_id,
            "process": "login",
            "callback_url": frontend_callback_url,
        }
    ).encode("utf-8")
    redirect_snapshot = fetch_response(
        http_opener,
        f"{normalized_base}{PROVIDER_REDIRECT_PATH}",
        method="POST",
        data=form,
        headers={
            "Accept": "text/html,application/xhtml+xml",
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": normalized_base,
            "Referer": f"{normalized_base}/login",
            "X-CSRFToken": csrf_token,
        },
        timeout_seconds=timeout_seconds,
    )
    if redirect_snapshot.status_code != 302:
        raise OIDCSmokeError(
            f"GlitchTip headless provider redirect returned HTTP {redirect_snapshot.status_code}; expected 302"
        )
    location = redirect_snapshot.headers.get("location", "")
    if not location:
        raise OIDCSmokeError("GlitchTip headless provider redirect omitted the Location header")
    backend_callback_url = f"{normalized_base}/accounts/oidc/{provider_id}/login/callback/"
    redirect_summary = validate_authorization_redirect(
        location,
        authorization_endpoint=authorization_endpoint,
        expected_client_id=configured_client_id,
        expected_callback_url=backend_callback_url,
    )
    token_endpoint = str(discovery.get("token_endpoint", ""))
    client_secret_verified = False
    if client_secret is not None:
        if not token_endpoint:
            raise OIDCSmokeError("OIDC discovery document has no token endpoint")
        token_parts = parse.urlparse(token_endpoint)
        issuer_parts = parse.urlparse(normalized_issuer)
        if (token_parts.scheme, token_parts.netloc) != (issuer_parts.scheme, issuer_parts.netloc):
            raise OIDCSmokeError("OIDC token endpoint does not use the issuer origin")
        methods = discovery.get("token_endpoint_auth_methods_supported", ["client_secret_basic"])
        if not isinstance(methods, list) or not all(isinstance(item, str) for item in methods):
            raise OIDCSmokeError("OIDC discovery advertises invalid token endpoint auth methods")
        verify_client_secret(
            http_opener,
            token_endpoint=token_endpoint,
            auth_methods=methods,
            client_id=configured_client_id,
            client_secret=client_secret,
            redirect_uri=backend_callback_url,
            timeout_seconds=timeout_seconds,
        )
        client_secret_verified = True
    return {
        "status": "ok",
        "provider_id": provider_id,
        "issuer": normalized_issuer,
        "discovery_url": expected_discovery_url,
        "authorization_endpoint": redirect_summary["authorization_endpoint"],
        "backend_callback_url": redirect_summary["callback_url"],
        "frontend_callback_url": frontend_callback_url,
        "token_endpoint": sanitized_url(token_endpoint) if token_endpoint else None,
        "client_secret_verified": client_secret_verified,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify GlitchTip's allauth headless OIDC redirect without authenticating."
    )
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--provider-id", required=True)
    parser.add_argument("--issuer-url", required=True)
    parser.add_argument("--expected-client-id")
    parser.add_argument("--callback-url")
    parser.add_argument(
        "--client-secret-file",
        type=Path,
        help="Read the confidential-client secret from this 0600 file and prove it at the token endpoint",
    )
    parser.add_argument("--request-timeout-seconds", type=float, default=30.0)
    return parser


if __name__ == "__main__":
    args = build_parser().parse_args()
    try:
        client_secret = None
        if args.client_secret_file is not None:
            metadata = args.client_secret_file.stat()
            if not stat.S_ISREG(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) != 0o600:
                raise OIDCSmokeError("OIDC client secret file must be a regular 0600 file")
            client_secret = args.client_secret_file.read_text(encoding="utf-8").strip()
        result = verify_oidc_redirect(
            base_url=args.base_url,
            provider_id=args.provider_id,
            issuer_url=args.issuer_url,
            expected_client_id=args.expected_client_id,
            callback_url=args.callback_url,
            client_secret=client_secret,
            timeout_seconds=args.request_timeout_seconds,
        )
    except (OIDCSmokeError, error.URLError, TimeoutError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, sort_keys=True), file=sys.stderr)
        raise SystemExit(1)
    print(json.dumps(result, indent=2, sort_keys=True))
