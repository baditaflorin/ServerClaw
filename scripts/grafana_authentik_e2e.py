#!/usr/bin/env python3
"""Verify Grafana grants the Authentik test identity its configured Viewer role."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from gitea_authentik_e2e import (
    DEFAULT_CA_FILE,
    DEFAULT_PASSWORD_FILE,
    _import_ca,
    read_private_file,
)


DEFAULT_USERNAME = "gitea-e2e"
USER_API_PATH = "/api/user"


class VerificationError(RuntimeError):
    """Raised when Grafana does not establish the expected least-privilege session."""


def verify_grafana_user(status: int, payload: Any, *, username: str) -> dict[str, Any]:
    if status != 200 or not isinstance(payload, dict):
        raise VerificationError("Grafana did not return an authenticated user profile")
    if payload.get("login") != username:
        raise VerificationError("Grafana authenticated a different test identity")
    if payload.get("isGrafanaAdmin") is not False:
        raise VerificationError("Grafana test identity is not confirmed non-admin")
    if payload.get("orgRole") != "Viewer":
        raise VerificationError("Grafana test identity does not have the expected Viewer role")
    return {"login": username, "org_role": "Viewer", "is_admin": False}


def _playwright_api():
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise VerificationError("Install Playwright with `uv run --with playwright`") from exc
    return sync_playwright, PlaywrightTimeoutError


def verify_login(
    *,
    platform_domain: str,
    username: str,
    password: str,
    root_ca_file: Path | None,
    timeout_ms: int = 30_000,
    headless: bool = True,
) -> dict[str, Any]:
    domain = platform_domain.strip().lower().strip(".")
    if not domain or "/" in domain or ":" in domain or "@" in domain:
        raise VerificationError("platform domain must be a hostname without a scheme or path")
    base_url = f"https://grafana.{domain}"
    identity_host = f"id.{domain}"
    app_host = f"grafana.{domain}"
    sync_playwright, playwright_timeout_error = _playwright_api()
    temporary_profile: tempfile.TemporaryDirectory[str] | None = None
    browser = None
    context = None
    try:
        with sync_playwright() as playwright:
            if root_ca_file is None:
                browser = playwright.chromium.launch(headless=headless)
                context = browser.new_context()
                ca_scope = "system trust store"
            else:
                temporary_profile = tempfile.TemporaryDirectory(prefix="grafana-authentik-e2e-")
                profile = Path(temporary_profile.name) / "firefox-profile"
                profile.mkdir(mode=0o700)
                _import_ca(profile, root_ca_file)
                context = playwright.firefox.launch_persistent_context(
                    user_data_dir=str(profile),
                    headless=headless,
                )
                ca_scope = "temporary Firefox profile"

            page = context.new_page()
            try:
                page.goto(f"{base_url}/login/generic_oauth", wait_until="domcontentloaded", timeout=timeout_ms)
                if urlparse(page.url).hostname != identity_host:
                    raise VerificationError("Grafana did not redirect the fresh session to Authentik")

                from session_logout_verify import authenticate_authentik_session

                authenticate_authentik_session(
                    page,
                    username=username,
                    password=password,
                    timeout_milliseconds=timeout_ms,
                    playwright_timeout_error=playwright_timeout_error,
                )
            except VerificationError:
                raise
            except Exception:
                # Browser exceptions can contain OAuth state, codes, or credentials.
                raise VerificationError("Grafana Authentik browser flow failed; diagnostics redacted") from None

            if urlparse(page.url).hostname != app_host:
                raise VerificationError("Authentik did not return the browser to Grafana")

            deadline = time.monotonic() + timeout_ms / 1000
            profile_result = None
            while time.monotonic() < deadline:
                try:
                    response = page.evaluate(
                        """async (userPath) => {
                          const response = await fetch(userPath, {credentials: 'same-origin'});
                          let payload = null;
                          try { payload = await response.json(); } catch (_) {}
                          return {status: response.status, payload};
                        }""",
                        USER_API_PATH,
                    )
                except Exception:
                    response = None
                if isinstance(response, dict) and response.get("status") == 200:
                    profile_result = response
                    break
                page.wait_for_timeout(250)

            if profile_result is None:
                raise VerificationError("Grafana did not establish an authenticated browser session")
            verified = verify_grafana_user(
                profile_result.get("status", 0),
                profile_result.get("payload"),
                username=username,
            )
            return {
                "status": "ok",
                "service": "grafana",
                "provider": "Authentik",
                **verified,
                "tls_validation": "enabled",
                "ca_trust_scope": ca_scope,
            }
    finally:
        if context is not None:
            try:
                context.close()
            except Exception:
                pass
        if browser is not None:
            try:
                browser.close()
            except Exception:
                pass
        if temporary_profile is not None:
            temporary_profile.cleanup()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--platform-domain", required=True)
    parser.add_argument("--username", default=DEFAULT_USERNAME)
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
        password = read_private_file(args.password_file, label="test password")
        result = verify_login(
            platform_domain=args.platform_domain,
            username=args.username,
            password=password,
            root_ca_file=args.root_ca_file,
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
