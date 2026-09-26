#!/usr/bin/env python3
"""Verify Outline Authentik sign-in, realtime WebSockets, and app-local logout."""

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
    _playwright_api,
    read_private_file,
)


DEFAULT_USERNAME = "gitea-e2e"
AUTH_INFO_PATH = "/api/auth.info"
REALTIME_PATH = "/realtime/?EIO=4&transport=websocket"
LOGOUT_FLOW_PATH = "/if/flow/default-provider-invalidation-flow/"


class VerificationError(RuntimeError):
    """Raised when Outline does not complete its authenticated browser contract."""


def normalize_base_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc:
        raise VerificationError("Outline base URL must be an absolute HTTPS URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise VerificationError("Outline base URL must not contain credentials, a query, or a fragment")
    if parsed.path not in {"", "/"}:
        raise VerificationError("Outline base URL must not contain an application path")
    return parsed._replace(path="", params="", query="", fragment="").geturl().rstrip("/")


def verify_auth_info(status: int, payload: Any) -> None:
    if status != 200 or not isinstance(payload, dict) or not isinstance(payload.get("data"), dict):
        raise VerificationError("Outline did not establish an authenticated browser session")


def verify_realtime_result(result: Any) -> None:
    if not isinstance(result, dict) or result.get("engine_open_packet") is not True:
        raise VerificationError("Outline realtime WebSocket did not complete its Engine.IO handshake")


def _identity_url(base_url: str) -> str:
    hostname = urlparse(base_url).hostname or ""
    labels = hostname.split(".")
    if len(labels) < 2:
        raise VerificationError("Could not derive the Authentik host from the Outline hostname")
    return f"https://id.{'.'.join(labels[1:])}"


def _browser_auth_info(page: Any, *, timeout_ms: int) -> dict[str, Any]:
    result = page.evaluate(
        """async ({path, timeoutMs}) => {
          const controller = new AbortController();
          const timer = setTimeout(() => controller.abort(), timeoutMs);
          try {
            const response = await fetch(path, {
              method: 'POST',
              credentials: 'same-origin',
              headers: {
                'Accept': 'application/json',
                'Content-Type': 'application/json'
              },
              body: '{}',
              signal: controller.signal
            });
            let payload = null;
            try { payload = await response.json(); } catch (_) {}
            return {status: response.status, payload};
          } finally {
            clearTimeout(timer);
          }
        }""",
        {"path": AUTH_INFO_PATH, "timeoutMs": timeout_ms},
    )
    if not isinstance(result, dict):
        raise VerificationError("Outline auth.info returned an invalid response")
    verify_auth_info(result.get("status", 0), result.get("payload"))
    return result


def _verify_realtime(page: Any, *, timeout_ms: int) -> None:
    result = page.evaluate(
        """async ({path, timeoutMs}) => await new Promise((resolve) => {
          let settled = false;
          const socket = new WebSocket(
            `${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}${path}`
          );
          const timer = setTimeout(() => finish(false), timeoutMs);
          function finish(engineOpenPacket) {
            if (settled) return;
            settled = true;
            clearTimeout(timer);
            try { socket.close(); } catch (_) {}
            resolve({engine_open_packet: engineOpenPacket});
          }
          socket.addEventListener('message', (event) => {
            const data = typeof event.data === 'string' ? event.data : '';
            if (!data.startsWith('0{')) return finish(false);
            try {
              JSON.parse(data.slice(1));
              finish(true);
            } catch (_) {
              finish(false);
            }
          }, {once: true});
          socket.addEventListener('error', () => finish(false), {once: true});
          socket.addEventListener('close', () => finish(false), {once: true});
        })""",
        {"path": REALTIME_PATH, "timeoutMs": timeout_ms},
    )
    verify_realtime_result(result)


def _wait_for_logout_card(page: Any, *, identity_host: str, timeout_ms: int) -> None:
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        current = urlparse(page.url)
        try:
            title = page.title().lower()
        except Exception:
            title = ""
        if (
            current.hostname == identity_host
            and current.path.startswith(LOGOUT_FLOW_PATH)
            and title.startswith("you've logged out of outline")
        ):
            return
        page.wait_for_timeout(100)
    raise VerificationError("Outline logout did not reach Authentik's provider logout confirmation")


def _verify_outline_session_is_cleared(page: Any, *, base_url: str, timeout_ms: int) -> None:
    try:
        response = page.request.post(
            f"{base_url}{AUTH_INFO_PATH}",
            data={},
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            timeout=timeout_ms,
        )
    except Exception:
        raise VerificationError("Could not verify Outline's app-local session after logout") from None
    if response.status != 401:
        raise VerificationError("Outline app-local session remained valid after its logout action")


def verify_login_logout(
    *,
    base_url: str,
    username: str,
    password: str,
    root_ca_file: Path | None,
    timeout_ms: int = 30_000,
    headless: bool = True,
) -> dict[str, Any]:
    """Use a clean TLS-valid browser to prove Outline auth and realtime end to end."""
    base_url = normalize_base_url(base_url)
    app_host = urlparse(base_url).hostname or ""
    identity_host = urlparse(_identity_url(base_url)).hostname or ""
    if not app_host or not identity_host or app_host == identity_host:
        raise VerificationError("Outline and Authentik must use distinct HTTPS hosts")

    sync_playwright, playwright_timeout_error = _playwright_api()
    from session_logout_verify import authenticate_authentik_session, trigger_outline_ui_logout

    temporary_profile: tempfile.TemporaryDirectory[str] | None = None
    browser = None
    context = None
    ca_scope = "system trust store"
    try:
        with sync_playwright() as playwright:
            if root_ca_file is None:
                browser = playwright.chromium.launch(headless=headless)
                context = browser.new_context()
            else:
                temporary_profile = tempfile.TemporaryDirectory(prefix="outline-authentik-e2e-")
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
                page.goto(f"{base_url}/auth/oidc", wait_until="domcontentloaded", timeout=timeout_ms)
                if urlparse(page.url).hostname == identity_host:
                    authenticate_authentik_session(
                        page,
                        username=username,
                        password=password,
                        timeout_milliseconds=timeout_ms,
                        playwright_timeout_error=playwright_timeout_error,
                    )
                if urlparse(page.url).hostname != app_host:
                    raise VerificationError("Authentik did not return the browser to Outline")
                _browser_auth_info(page, timeout_ms=timeout_ms)
                _verify_realtime(page, timeout_ms=min(timeout_ms, 10_000))

                trigger_outline_ui_logout(
                    page,
                    timeout_milliseconds=timeout_ms,
                    playwright_timeout_error=playwright_timeout_error,
                )
                _wait_for_logout_card(page, identity_host=identity_host, timeout_ms=timeout_ms)
                _verify_outline_session_is_cleared(page, base_url=base_url, timeout_ms=timeout_ms)

                # Authentik provider logout ends the Outline session but leaves
                # its central SSO session active, so reopening Outline may
                # silently establish a new app session without another prompt.
                page.goto(f"{base_url}/auth/oidc", wait_until="domcontentloaded", timeout=timeout_ms)
                if urlparse(page.url).hostname == identity_host:
                    authenticate_authentik_session(
                        page,
                        username=username,
                        password=password,
                        timeout_milliseconds=timeout_ms,
                        playwright_timeout_error=playwright_timeout_error,
                    )
                if urlparse(page.url).hostname != app_host:
                    raise VerificationError("Outline did not reopen through the retained Authentik session")
                _browser_auth_info(page, timeout_ms=timeout_ms)
                _verify_realtime(page, timeout_ms=min(timeout_ms, 10_000))
            except VerificationError:
                raise
            except Exception:
                raise VerificationError(
                    "Outline Authentik browser flow failed; detailed diagnostics redacted"
                ) from None

            return {
                "status": "ok",
                "service": "outline",
                "provider": "Authentik",
                "username": username,
                "authenticated_session": True,
                "realtime_websocket": "connected",
                "app_logout_clears_session": True,
                "authentik_sso_reentry": "successful",
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
        result = verify_login_logout(
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
