#!/usr/bin/env python3
"""Verify a fresh Authentik browser sign-in reaches LibreChat's chat session."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from gitea_authentik_e2e import DEFAULT_CA_FILE, DEFAULT_PASSWORD_FILE, DEFAULT_USERNAME, _import_ca, read_private_file
from session_logout_verify import authenticate_authentik_session


CALLBACK_PATH = "/oauth/openid/callback"
LOGIN_LABEL = "Login with Authentik"


class VerificationError(RuntimeError):
    """Raised when the fresh browser does not establish a LibreChat session."""


def normalize_base_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc:
        raise VerificationError("LibreChat base URL must be an absolute HTTPS URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise VerificationError("LibreChat base URL must not contain credentials, a query, or a fragment")
    if parsed.path not in {"", "/"}:
        raise VerificationError("LibreChat base URL must not contain an application path")
    return parsed._replace(path="", params="", query="", fragment="").geturl().rstrip("/")


def authenticated_chat_surface(
    *, final_host: str, app_host: str, composer_visible: bool, login_control_count: int
) -> bool:
    return final_host == app_host and composer_visible and login_control_count == 0


def _playwright_api():
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise VerificationError("Install Playwright with `uv run --with playwright`") from exc
    return sync_playwright, PlaywrightTimeoutError


def verify_login(
    *,
    base_url: str,
    username: str,
    password: str,
    root_ca_file: Path | None,
    timeout_ms: int = 30_000,
    headless: bool = True,
) -> dict[str, object]:
    base_url = normalize_base_url(base_url)
    app_host = (urlparse(base_url).hostname or "").lower()
    identity_host = f"id.{'.'.join(app_host.split('.')[1:])}" if app_host.count(".") >= 1 else ""
    if not identity_host:
        raise VerificationError("LibreChat host must be under the platform identity domain")

    sync_playwright, playwright_timeout_error = _playwright_api()
    callback_statuses: list[int] = []
    with tempfile.TemporaryDirectory(prefix="librechat-authentik-e2e-") as temp_dir:
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
                    if (parsed.hostname or "").lower() == app_host and parsed.path == CALLBACK_PATH:
                        callback_statuses.append(response.status)

                page.on("response", on_response)
                page.goto(base_url, wait_until="domcontentloaded", timeout=timeout_ms)
                if (urlparse(page.url).hostname or "").lower() != app_host:
                    raise VerificationError("LibreChat did not render its login page on the expected host")

                login_control = page.get_by_text(LOGIN_LABEL, exact=True)
                try:
                    login_control.first.wait_for(state="visible", timeout=min(timeout_ms, 15_000))
                except playwright_timeout_error:
                    actions = [
                        " ".join(label.split())[:60]
                        for label in page.locator("button, a").all_text_contents()
                        if any(word in label.casefold() for word in ("auth", "openid", "login", "sign in"))
                    ][:8]
                    suffix = f"; sign-in controls: {actions}" if actions else ""
                    raise VerificationError(f"LibreChat did not render its Authentik login option{suffix}")
                login_control.first.click(timeout=timeout_ms)
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
                # LibreChat can render the chat composer after its initial API
                # bootstrap. Avoid printing the page URL or any OAuth query data.
                try:
                    page.locator("textarea").first.wait_for(state="visible", timeout=timeout_ms)
                except playwright_timeout_error:
                    if callback_statuses and callback_statuses[-1] >= 500:
                        raise VerificationError(
                            f"LibreChat OIDC callback returned HTTP {callback_statuses[-1]}"
                        ) from None
                    raise VerificationError("LibreChat did not render an authenticated chat composer") from None

                login_count = page.get_by_text(LOGIN_LABEL, exact=True).count()
                if not authenticated_chat_surface(
                    final_host=(urlparse(page.url).hostname or "").lower(),
                    app_host=app_host,
                    composer_visible=page.locator("textarea").first.is_visible(),
                    login_control_count=login_count,
                ):
                    raise VerificationError("LibreChat did not establish an authenticated chat session")
                return {
                    "status": "ok",
                    "service": "librechat",
                    "provider": "Authentik",
                    "username": username,
                    "authenticated_session": True,
                    "tls_validation": "enabled",
                    "ca_trust_scope": "temporary Firefox profile" if root_ca_file else "system trust store",
                    "callback_status": callback_statuses[-1] if callback_statuses else None,
                }
            finally:
                context.close()


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
