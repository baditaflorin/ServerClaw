#!/usr/bin/env python3
"""Verify a fresh non-admin Authentik sign-in reaches Grafana as Viewer."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from gitea_authentik_e2e import (
    DEFAULT_CA_FILE,
    DEFAULT_PASSWORD_FILE,
    DEFAULT_USERNAME,
    _import_ca,
    read_private_file,
)
from session_logout_verify import authenticate_authentik_session


OAUTH_PATH = "/login/generic_oauth"
USER_API_PATH = "/api/user"
USER_ORGS_API_PATH = "/api/user/orgs"
DEFAULT_EXPECTED_ORG_ROLE = "Viewer"


class VerificationError(RuntimeError):
    """Raised when a fresh browser does not establish a Grafana Viewer session."""


def normalize_base_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc:
        raise VerificationError("Grafana base URL must be an absolute HTTPS URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise VerificationError("Grafana base URL must not contain credentials, a query, or a fragment")
    if parsed.path not in {"", "/"}:
        raise VerificationError("Grafana base URL must not contain an application path")
    return parsed._replace(path="", params="", query="", fragment="").geturl().rstrip("/")


def verify_grafana_user(status: int, payload: object, *, username: str) -> dict[str, object]:
    if status != 200 or not isinstance(payload, dict):
        raise VerificationError("Grafana did not return an authenticated user profile")
    if payload.get("login") != username:
        raise VerificationError("Grafana authenticated a different test identity")
    if payload.get("isGrafanaAdmin") is not False:
        raise VerificationError("Grafana test identity is not confirmed non-admin")
    return {"username": username, "grafana_admin": False}


def verify_grafana_org_memberships(
    status: int,
    payload: object,
    *,
    expected_role: str = DEFAULT_EXPECTED_ORG_ROLE,
) -> dict[str, object]:
    """Check workspace membership roles from Grafana's dedicated API."""
    if status != 200 or not isinstance(payload, list):
        raise VerificationError("Grafana did not return organization memberships for the authenticated user")
    if not payload:
        raise VerificationError("Grafana user has no organization memberships")

    roles: list[str] = []
    for membership in payload:
        if not isinstance(membership, dict) or not isinstance(membership.get("role"), str):
            raise VerificationError("Grafana returned an invalid organization membership")
        roles.append(membership["role"])

    if expected_role not in roles:
        raise VerificationError(f"Grafana user does not have the expected {expected_role} organization role")
    if expected_role == "Viewer" and any(role != "Viewer" for role in roles):
        raise VerificationError("Grafana Viewer test identity has elevated organization access")

    return {"org_role": expected_role, "org_count": len(roles)}


def _playwright_api():
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise VerificationError("Install Playwright with `uv run --with playwright`") from exc
    return sync_playwright, PlaywrightTimeoutError


def _verify_login(
    *,
    base_url: str,
    username: str,
    password: str,
    root_ca_file: Path | None,
    expected_org_role: str = DEFAULT_EXPECTED_ORG_ROLE,
    timeout_ms: int = 30_000,
    headless: bool = True,
) -> dict[str, object]:
    base_url = normalize_base_url(base_url)
    app_host = (urlparse(base_url).hostname or "").lower()
    identity_host = f"id.{'.'.join(app_host.split('.')[1:])}" if app_host.count(".") >= 1 else ""
    if not identity_host:
        raise VerificationError("Grafana host must be under the platform identity domain")

    sync_playwright, playwright_timeout_error = _playwright_api()
    callback_statuses: list[int] = []
    with tempfile.TemporaryDirectory(prefix="grafana-authentik-e2e-") as temp_dir:
        profile = Path(temp_dir) / "firefox-profile"
        profile.mkdir(mode=0o700)
        if root_ca_file is not None:
            _import_ca(profile, root_ca_file)
        with sync_playwright() as playwright:
            context = playwright.firefox.launch_persistent_context(
                user_data_dir=str(profile),
                headless=headless,
            )
            try:
                page = context.new_page()

                def on_response(response) -> None:
                    parsed = urlparse(response.url)
                    if (parsed.hostname or "").lower() == app_host and parsed.path == OAUTH_PATH:
                        callback_statuses.append(response.status)

                page.on("response", on_response)
                page.goto(f"{base_url}/login", wait_until="domcontentloaded", timeout=timeout_ms)
                if (urlparse(page.url).hostname or "").lower() != app_host:
                    raise VerificationError("Grafana did not render the login page on the expected host")

                # Grafana renders this link with a relative href
                # ("login/generic_oauth") on /login, even though the
                # resolved browser URL is /login/generic_oauth. Accept both
                # forms while keeping the callback target exact.
                oauth_link = page.locator(f'a[href="{OAUTH_PATH}"], a[href="{OAUTH_PATH.lstrip("/")}"]')
                try:
                    oauth_link.first.wait_for(state="visible", timeout=min(timeout_ms, 15_000))
                except playwright_timeout_error:
                    raise VerificationError("Grafana did not render its Authentik OAuth login option") from None
                oauth_link.first.click(timeout=timeout_ms)
                page.wait_for_url(
                    lambda url: (urlparse(url).hostname or "").lower() == identity_host,
                    timeout=timeout_ms,
                )
                authenticate_authentik_session(
                    page,
                    username=username,
                    password=password,
                    timeout_milliseconds=timeout_ms,
                    playwright_timeout_error=playwright_timeout_error,
                )
                page.wait_for_url(
                    lambda url: (urlparse(url).hostname or "").lower() == app_host,
                    timeout=timeout_ms,
                )

                user_result = page.evaluate(
                    """async (userPath) => {
                      const response = await fetch(userPath, {
                        credentials: 'same-origin',
                        cache: 'no-store'
                      });
                      return {
                        status: response.status,
                        user: response.ok ? await response.json() : null
                      };
                    }""",
                    USER_API_PATH,
                )
                if user_result.get("status") != 200:
                    status = callback_statuses[-1] if callback_statuses else "unknown"
                    raise VerificationError(
                        f"Grafana OAuth callback status {status}; user profile returned HTTP {user_result.get('status')}"
                    )
                org_result = page.evaluate(
                    """async (orgsPath) => {
                      const response = await fetch(orgsPath, {
                        credentials: 'same-origin',
                        cache: 'no-store'
                      });
                      let payload = null;
                      try { payload = await response.json(); } catch (_) {}
                      return {status: response.status, payload};
                    }""",
                    USER_ORGS_API_PATH,
                )
                verified_user = verify_grafana_user(
                    user_result.get("status", 0), user_result.get("user"), username=username
                )
                verified_orgs = verify_grafana_org_memberships(
                    org_result.get("status", 0),
                    org_result.get("payload"),
                    expected_role=expected_org_role,
                )

                return {
                    "status": "ok",
                    "service": "grafana",
                    "provider": "Authentik",
                    **verified_user,
                    **verified_orgs,
                    "authenticated_session": True,
                    "tls_validation": "enabled",
                    "ca_trust_scope": "temporary Firefox profile" if root_ca_file else "system trust store",
                }
            finally:
                try:
                    context.close()
                except Exception:
                    pass


def verify_login(
    *,
    base_url: str,
    username: str,
    password: str,
    root_ca_file: Path | None,
    expected_org_role: str = DEFAULT_EXPECTED_ORG_ROLE,
    timeout_ms: int = 30_000,
    headless: bool = True,
) -> dict[str, object]:
    try:
        return _verify_login(
            base_url=base_url,
            username=username,
            password=password,
            root_ca_file=root_ca_file,
            expected_org_role=expected_org_role,
            timeout_ms=timeout_ms,
            headless=headless,
        )
    except VerificationError:
        raise
    except Exception:
        # Browser/HTTP exceptions can contain OAuth codes, state, or credentials.
        raise VerificationError("Grafana Authentik browser flow failed; diagnostics redacted") from None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    url_group = parser.add_mutually_exclusive_group(required=True)
    url_group.add_argument("--base-url")
    url_group.add_argument("--platform-domain", help="legacy convenience alias for https://grafana.<domain>")
    parser.add_argument("--username", default=DEFAULT_USERNAME)
    parser.add_argument(
        "--expected-org-role",
        choices=("Viewer", "Editor", "Admin"),
        default=DEFAULT_EXPECTED_ORG_ROLE,
        help="expected role inside Grafana's own workspace (not an external-company role)",
    )
    parser.add_argument("--password-file", type=Path, default=DEFAULT_PASSWORD_FILE)
    parser.add_argument(
        "--root-ca-file",
        type=Path,
        default=DEFAULT_CA_FILE if DEFAULT_CA_FILE.is_file() else None,
        help="optional private root CA; trusted only in a temporary Firefox profile",
    )
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
        if args.platform_domain and any(char in args.platform_domain for char in "/:@?#"):
            raise VerificationError("platform domain must be a hostname without a scheme or path")
        base_url = args.base_url or f"https://grafana.{args.platform_domain}"
        password = read_private_file(args.password_file, label="test password")
        result = verify_login(
            base_url=base_url,
            username=args.username,
            password=password,
            root_ca_file=args.root_ca_file,
            expected_org_role=args.expected_org_role,
            timeout_ms=args.timeout_ms,
            headless=args.headless,
        )
        print(json.dumps(result, sort_keys=True))
        return 0
    except (OSError, VerificationError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
