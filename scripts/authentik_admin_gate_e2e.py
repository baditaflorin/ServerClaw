#!/usr/bin/env python3
"""Verify shared-edge admin gates deny the managed non-admin test identity."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import yaml

from gitea_authentik_e2e import (
    DEFAULT_CA_FILE,
    DEFAULT_PASSWORD_FILE,
    DEFAULT_USERNAME,
    _import_ca,
    read_private_file,
)


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
TEST_IDENTITY_MANIFEST = REPO_ROOT / "config" / "authentik" / "test-identities.yaml"
ADMIN_APPS = ("ops", "repo-intake")
SHARED_PROXY_CLIENT_ID = "ops-portal-oauth"
CALLBACK_PATH = "/oauth2/callback"
EXPECTED_DENIAL_STATUS = 403


class VerificationError(RuntimeError):
    """Raised when a protected application does not enforce its admin gate."""


def assert_non_admin_identity(manifest: dict[str, Any], *, username: str) -> None:
    users = manifest.get("users")
    if not isinstance(users, list):
        raise VerificationError("test identity manifest has no users list")
    matching = [user for user in users if isinstance(user, dict) and user.get("username") == username]
    if len(matching) != 1:
        raise VerificationError("expected exactly one managed non-admin test identity")
    groups = matching[0].get("groups")
    if not isinstance(groups, list) or any("admin" in str(group).casefold() for group in groups):
        raise VerificationError("the configured browser test identity must not have an admin group")


def verify_admin_denial_trace(
    *,
    service: str,
    authorize_requests: list[dict[str, str]],
    callback_responses: list[dict[str, Any]],
    server_errors: list[dict[str, Any]],
    expected_callback_host: str,
) -> dict[str, Any]:
    if service not in ADMIN_APPS:
        raise VerificationError("unsupported admin-gated service")
    unique_authorize_requests = {
        (item.get("client_id", ""), item.get("redirect_host", ""), item.get("redirect_path", ""))
        for item in authorize_requests
    }
    if unique_authorize_requests != {(SHARED_PROXY_CLIENT_ID, expected_callback_host, CALLBACK_PATH)}:
        raise VerificationError("the shared admin proxy used an unexpected Authentik client or callback")
    matching_callbacks = [
        item
        for item in callback_responses
        if item.get("host") == expected_callback_host and item.get("path") == CALLBACK_PATH
    ]
    if not matching_callbacks or matching_callbacks[-1].get("status") != EXPECTED_DENIAL_STATUS:
        raise VerificationError("the non-admin browser identity was not denied at the shared proxy callback")
    if server_errors:
        raise VerificationError("the admin-gated sign-in path returned a server error")
    return {
        "status": "expected_denial",
        "service": service,
        "provider_client_id": SHARED_PROXY_CLIENT_ID,
        "callback_path": CALLBACK_PATH,
        "http_status": EXPECTED_DENIAL_STATUS,
        "identity_is_non_admin": True,
        "server_errors": 0,
        "tls_validation": "enabled",
    }


def _playwright_api():
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise VerificationError("Install Playwright with `uv run --with playwright`") from exc
    return sync_playwright, PlaywrightTimeoutError


def verify_service(
    *,
    service: str,
    platform_domain: str,
    username: str,
    password: str,
    root_ca_file: Path,
    timeout_ms: int = 30_000,
    headless: bool = True,
) -> dict[str, Any]:
    if service not in ADMIN_APPS:
        raise VerificationError("unsupported admin-gated service")
    domain = platform_domain.strip().lower().strip(".")
    if not domain or "/" in domain or ":" in domain or "@" in domain:
        raise VerificationError("platform domain must be a hostname without a scheme or path")
    app_host = f"{service}.{domain}"
    identity_host = f"id.{domain}"
    callback_host = f"ops.{domain}"
    sync_playwright, playwright_timeout_error = _playwright_api()
    with tempfile.TemporaryDirectory(prefix="authentik-admin-gate-e2e-") as tmp:
        profile = Path(tmp) / "firefox-profile"
        profile.mkdir(mode=0o700)
        _import_ca(profile, root_ca_file)
        with sync_playwright() as playwright:
            context = playwright.firefox.launch_persistent_context(
                user_data_dir=str(profile),
                headless=headless,
            )
            try:
                page = context.new_page()
                authorize_requests: list[dict[str, str]] = []
                callback_responses: list[dict[str, Any]] = []
                server_errors: list[dict[str, Any]] = []

                def on_request(request: Any) -> None:
                    parsed = urlparse(request.url)
                    if parsed.hostname != identity_host or parsed.path != "/application/o/authorize/":
                        return
                    query = parse_qs(parsed.query)
                    redirect = urlparse(query.get("redirect_uri", [""])[0])
                    authorize_requests.append(
                        {
                            "client_id": query.get("client_id", [""])[0],
                            "redirect_host": redirect.hostname or "",
                            "redirect_path": redirect.path or "",
                        }
                    )

                def on_response(response: Any) -> None:
                    parsed = urlparse(response.url)
                    host = (parsed.hostname or "").lower()
                    if parsed.path == CALLBACK_PATH:
                        callback_responses.append({"status": response.status, "host": host, "path": parsed.path})
                    if host in {app_host, callback_host} and response.status >= 500:
                        server_errors.append({"status": response.status, "host": host, "path": parsed.path})

                page.on("request", on_request)
                page.on("response", on_response)
                try:
                    page.goto(f"https://{app_host}/", wait_until="domcontentloaded", timeout=timeout_ms)
                    if (urlparse(page.url).hostname or "").lower() != identity_host:
                        raise VerificationError("the admin-gated service did not start a fresh Authentik flow")
                    from session_logout_verify import authenticate_authentik_session

                    authenticate_authentik_session(
                        page,
                        username=username,
                        password=password,
                        timeout_milliseconds=timeout_ms,
                        playwright_timeout_error=playwright_timeout_error,
                    )
                    page.wait_for_timeout(500)
                except VerificationError:
                    # Continue to the sanitized trace check: an expected access
                    # denial ends on the oauth2-proxy callback with HTTP 403.
                    pass
                except Exception:
                    raise VerificationError(
                        "browser flow failed; URL, OAuth state, and callback code redacted"
                    ) from None
                return verify_admin_denial_trace(
                    service=service,
                    authorize_requests=authorize_requests,
                    callback_responses=callback_responses,
                    server_errors=server_errors,
                    expected_callback_host=callback_host,
                )
            finally:
                context.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--platform-domain", required=True)
    parser.add_argument("--username", default=DEFAULT_USERNAME)
    parser.add_argument("--password-file", type=Path, default=DEFAULT_PASSWORD_FILE)
    parser.add_argument("--root-ca-file", type=Path, default=DEFAULT_CA_FILE)
    parser.add_argument("--service", choices=("all", *ADMIN_APPS), default="all")
    parser.add_argument("--timeout-ms", type=int, default=30_000)
    headless = parser.add_mutually_exclusive_group()
    headless.add_argument("--headed", action="store_false", dest="headless", default=True)
    headless.add_argument("--headless", action="store_true", dest="headless")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.timeout_ms < 1_000:
            raise VerificationError("timeout must be at least 1000 milliseconds")
        manifest = yaml.safe_load(TEST_IDENTITY_MANIFEST.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            raise VerificationError("test identity manifest is invalid")
        assert_non_admin_identity(manifest, username=args.username)
        password = read_private_file(args.password_file, label="test password")
        services = ADMIN_APPS if args.service == "all" else (args.service,)
        results = [
            verify_service(
                service=service,
                platform_domain=args.platform_domain,
                username=args.username,
                password=password,
                root_ca_file=args.root_ca_file,
                timeout_ms=args.timeout_ms,
                headless=args.headless,
            )
            for service in services
        ]
        print(json.dumps(results, sort_keys=True))
        return 0
    except (OSError, VerificationError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
