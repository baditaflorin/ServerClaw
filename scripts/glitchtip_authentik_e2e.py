#!/usr/bin/env python3
"""Verify a fresh Authentik browser login creates an authenticated GlitchTip session."""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from typing import Any

from gitea_authentik_e2e import (
    DEFAULT_CA_FILE,
    DEFAULT_PASSWORD_FILE,
    _import_ca,
    read_private_file,
)


DEFAULT_USERNAME = "gitea-e2e"
SESSION_PATH = "/_allauth/browser/v1/auth/session"
CALLBACK_PATH = "/accounts/oidc/authentik/login/callback/"
SAFE_AUTH_ERRORS = re.compile(r"^[a-z_]{1,48}$")


class VerificationError(RuntimeError):
    """Raised when the Authentik-to-GlitchTip browser session is incomplete."""


def normalize_base_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc:
        raise VerificationError("GlitchTip base URL must be an absolute HTTPS URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise VerificationError("GlitchTip base URL must not contain credentials, a query, or a fragment")
    if parsed.path not in {"", "/"}:
        raise VerificationError("GlitchTip base URL must not contain an application path")
    return parsed._replace(path="", params="", query="", fragment="").geturl().rstrip("/")


def parse_callback_error(location: str) -> str | None:
    """Return only a safe allauth error slug, never OAuth state or callback data."""
    parsed = urlparse(location)
    error = parse_qs(parsed.query).get("error", [""])[0]
    if not SAFE_AUTH_ERRORS.fullmatch(error):
        return None
    return error


def is_authenticated_session(status: int, payload: Any) -> bool:
    if status != 200 or not isinstance(payload, dict):
        return False
    meta = payload.get("meta")
    return isinstance(meta, dict) and meta.get("is_authenticated") is True


def _playwright_api():
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise VerificationError("Install Playwright with `uv run --with playwright`") from exc
    return sync_playwright, PlaywrightTimeoutError


def _identity_url(base_url: str) -> str:
    hostname = urlparse(base_url).hostname or ""
    labels = hostname.split(".")
    if len(labels) < 2:
        raise VerificationError("Could not derive the Authentik host from the GlitchTip hostname")
    return f"https://id.{'.'.join(labels[1:])}"


def verify_login(
    *,
    base_url: str,
    username: str,
    password: str,
    root_ca_file: Path | None,
    timeout_ms: int = 30_000,
    headless: bool = True,
) -> dict[str, Any]:
    """Complete a clean-browser Authentik flow and prove GlitchTip owns a live session."""
    base_url = normalize_base_url(base_url)
    identity_url = _identity_url(base_url)
    app_host = urlparse(base_url).hostname
    identity_host = urlparse(identity_url).hostname
    if not app_host or not identity_host or app_host == identity_host:
        raise VerificationError("GlitchTip and Authentik must use distinct HTTPS hosts")

    sync_playwright, playwright_timeout_error = _playwright_api()
    callback_errors: list[str] = []
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
                temporary_profile = tempfile.TemporaryDirectory(prefix="glitchtip-authentik-e2e-")
                profile = Path(temporary_profile.name) / "firefox-profile"
                profile.mkdir(mode=0o700)
                _import_ca(profile, root_ca_file)
                context = playwright.firefox.launch_persistent_context(
                    user_data_dir=str(profile),
                    headless=headless,
                )
                ca_scope = "temporary Firefox profile"

            page = context.new_page()

            def record_callback_error(response: Any) -> None:
                response_url = urlparse(response.url)
                if response_url.hostname != app_host or response_url.path != CALLBACK_PATH:
                    return
                location = response.headers.get("location", "")
                safe_error = parse_callback_error(location)
                if safe_error:
                    callback_errors.append(safe_error)

            page.on("response", record_callback_error)
            page.goto(f"{base_url}/login", wait_until="domcontentloaded", timeout=timeout_ms)
            try:
                page.get_by_role("button", name=re.compile(r"Log in with Authentik", re.IGNORECASE)).click(
                    timeout=timeout_ms
                )
                page.wait_for_url(re.compile(rf"https://{re.escape(identity_host)}/.*"), timeout=timeout_ms)
                from session_logout_verify import authenticate_authentik_session

                authenticate_authentik_session(
                    page,
                    username=username,
                    password=password,
                    timeout_milliseconds=timeout_ms,
                    playwright_timeout_error=playwright_timeout_error,
                )
            except Exception:
                # Browser exceptions can contain callback query strings or user input.
                if callback_errors:
                    raise VerificationError(
                        f"GlitchTip rejected Authentik sign-in (error={callback_errors[-1]})"
                    ) from None
                raise VerificationError(
                    "Authentik browser login or GlitchTip callback failed; diagnostics redacted"
                ) from None

            if urlparse(page.url).hostname != app_host:
                raise VerificationError("Authentik did not return the browser to GlitchTip")

            deadline = time.monotonic() + timeout_ms / 1000
            session_ok = False
            while time.monotonic() < deadline:
                if callback_errors:
                    raise VerificationError(f"GlitchTip rejected Authentik sign-in (error={callback_errors[-1]})")
                try:
                    result = page.evaluate(
                        """async (sessionPath) => {
                          const response = await fetch(sessionPath, {credentials: 'same-origin'});
                          let payload = null;
                          try { payload = await response.json(); } catch (_) {}
                          return {status: response.status, payload};
                        }""",
                        SESSION_PATH,
                    )
                except Exception:
                    result = None
                if isinstance(result, dict) and is_authenticated_session(
                    result.get("status", 0), result.get("payload")
                ):
                    session_ok = True
                    break
                page.wait_for_timeout(250)

            if not session_ok:
                if callback_errors:
                    raise VerificationError(f"GlitchTip rejected Authentik sign-in (error={callback_errors[-1]})")
                raise VerificationError("GlitchTip did not establish an authenticated browser session")

            if urlparse(page.url).path in {"/login", "/login/finalize"}:
                page.wait_for_timeout(1_000)
            final_path = urlparse(page.url).path or "/"
            if final_path in {"/login", "/login/finalize"}:
                raise VerificationError("GlitchTip authenticated a session but remained on its login screen")

            return {
                "status": "ok",
                "service": "glitchtip",
                "provider": "Authentik",
                "username": username,
                "authenticated_session": True,
                "final_path": final_path,
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
    parser.add_argument("--base-url", required=True)
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
            base_url=args.base_url,
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
