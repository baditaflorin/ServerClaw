#!/usr/bin/env python3
"""Verify shared-edge and Outline logout against the Authentik authority."""

from __future__ import annotations

import argparse
import re
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from controller_automation_toolkit import emit_cli_error


SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parents[1]


def discover_local_root(repo_root: Path) -> Path:
    direct_root = repo_root / ".local"
    if direct_root.exists():
        return direct_root
    if repo_root.parent.name == ".worktrees":
        shared_root = repo_root.parent.parent / ".local"
        if shared_root.exists():
            return shared_root
    return direct_root


DEFAULT_LOCAL_ROOT = discover_local_root(REPO_ROOT)
DEFAULT_PASSWORD_FILE = DEFAULT_LOCAL_ROOT / "authentik" / "bootstrap-password.txt"
DEFAULT_EDGE_URL = "https://home.localhost/"
DEFAULT_EDGE_LOGOUT_URL = "https://home.localhost/.well-known/lv3/session/logout"
DEFAULT_OUTLINE_OIDC_URL = "https://wiki.localhost/auth/oidc"
DEFAULT_LOGGED_OUT_URL = "https://ops.localhost/.well-known/lv3/session/logged-out"


class VerificationError(RuntimeError):
    """Raised when an Authentik browser verification does not meet its contract."""


def normalize_url(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path.rstrip("/") or "/"
    return parsed._replace(path=path, query="", fragment="").geturl()


def assert_response_host(current_url: str, *, expected_host: str, label: str) -> None:
    if urlparse(current_url).hostname != expected_host:
        raise VerificationError(f"{label} should land on {expected_host}, landed on {current_url}")


def load_playwright_sync_api():
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover - exercised only in live verification
        raise VerificationError(
            "Browser verification requires Playwright. "
            "Run `uv run --with playwright python scripts/session_logout_verify.py ...`."
        ) from exc
    return sync_playwright, PlaywrightTimeoutError


def _authentik_identifier(page):
    return page.get_by_label("Email or Username", exact=True)


def _authentik_password(page):
    """Return the visible Authentik password field.

    Authentik's flow UI keeps a compatibility form with a hidden password
    input in the document while the active stage renders its field inside a
    component.  Combining both locators with ``or_`` can select that hidden
    input first, making a browser verification submit an empty password.
    The labelled locator is dynamic, so returning it without an eager
    ``count`` check lets ``wait_for`` below wait for the active stage to
    render.
    """
    return page.get_by_label("Password", exact=True).first


def _authentik_submit(page):
    return page.get_by_role("button", name=re.compile(r"^(log in|continue)$", re.IGNORECASE)).first


def authentik_login_page_present(page) -> bool:
    try:
        return _authentik_identifier(page).is_visible()
    except Exception:
        return False


def assert_page_requires_authentik_login(
    page,
    *,
    label: str,
    timeout_milliseconds: int,
    playwright_timeout_error,
) -> None:
    try:
        _authentik_identifier(page).wait_for(state="visible", timeout=timeout_milliseconds)
    except playwright_timeout_error as exc:
        raise VerificationError(f"{label} should require a fresh Authentik login, landed on {page.url}") from exc


def authenticate_authentik_session(
    page,
    *,
    username: str,
    password: str,
    timeout_milliseconds: int,
    playwright_timeout_error,
) -> None:
    """Complete Authentik's normal identifier/password flow when a login is needed."""
    identifier = _authentik_identifier(page)
    try:
        identifier.wait_for(state="visible", timeout=timeout_milliseconds)
    except playwright_timeout_error:
        return

    identifier.fill(username, timeout=timeout_milliseconds)
    _authentik_submit(page).click(timeout=timeout_milliseconds)

    password_input = _authentik_password(page)
    try:
        password_input.wait_for(state="visible", timeout=timeout_milliseconds)
    except playwright_timeout_error as exc:
        raise VerificationError("Authentik did not present the password stage after accepting the identifier") from exc
    password_input.fill(password, timeout=timeout_milliseconds)
    identity_host = urlparse(page.url).hostname or ""
    _authentik_submit(page).click(timeout=timeout_milliseconds)
    # Authentik submits the password stage through its flow API and only then
    # navigates to the relying party callback.  Starting the next ``goto``
    # immediately can cancel that still-in-flight navigation with Chromium's
    # ``ERR_ABORTED`` even though the credentials were accepted.  Wait until
    # the authentication-flow URL has been replaced, bounded by the caller's
    # verification timeout.
    deadline = time.monotonic() + (timeout_milliseconds / 1000)
    while time.monotonic() < deadline:
        current = urlparse(page.url)
        # Wait through both Authentik's flow API redirect and the relying
        # party's authorization-code callback.  Leaving Authentik alone is
        # not sufficient: navigating again while oauth2-proxy is still
        # setting its session cookies can discard the just-created session.
        callback_in_flight = current.path.startswith("/oauth2/callback") or current.path.startswith("/oauth2/sign_in")
        if current.hostname and current.hostname != identity_host and not callback_in_flight:
            page.wait_for_timeout(500)
            break
        page.wait_for_timeout(250)
    else:
        raise VerificationError(f"Authentik login did not complete a relying-party callback, landed on {page.url}")
    if authentik_login_page_present(page):
        raise VerificationError("Authentik login remained visible after submitting the supplied operator credential")


def wait_for_logged_out_destination(
    page,
    *,
    expected_url: str,
    timeout_milliseconds: int,
) -> None:
    deadline = time.monotonic() + (timeout_milliseconds / 1000)
    while time.monotonic() < deadline:
        if normalize_url(page.url) == normalize_url(expected_url):
            return
        page.wait_for_timeout(250)
    raise VerificationError(f"Logout should finish on {expected_url}, landed on {page.url}")


def wait_for_outline_logout_completion(
    page,
    *,
    expected_url: str,
    timeout_milliseconds: int,
) -> None:
    """Accept Authentik's provider-scoped logout confirmation page.

    Authentik deliberately renders a confirmation page for RP-initiated
    provider logout instead of automatically navigating to the requested
    post-logout URI.  The page title and query parameter are the authoritative
    proof that the Outline provider session was invalidated.  Continue the
    verification at the shared logged-out endpoint so the following fresh-login
    assertions exercise the same browser context.
    """
    deadline = time.monotonic() + (timeout_milliseconds / 1000)
    expected = normalize_url(expected_url)
    while time.monotonic() < deadline:
        if normalize_url(page.url) == expected:
            return

        current = urlparse(page.url)
        title = ""
        try:
            title = page.title()
        except Exception:
            pass
        query_redirects = parse_qs(current.query).get("post_logout_redirect_uri", [])
        provider_confirmation = (
            current.hostname is not None
            and current.path.startswith("/if/flow/")
            and "provider-invalidation-flow" in current.path
            and title.lower().startswith("you've logged out of ")
            and any(normalize_url(candidate) == expected for candidate in query_redirects)
        )
        if provider_confirmation:
            page.goto(expected_url, wait_until="domcontentloaded", timeout=timeout_milliseconds)
            if normalize_url(page.url) == expected:
                return
        page.wait_for_timeout(250)
    raise VerificationError(f"Logout should finish on {expected_url}, landed on {page.url}")


def trigger_outline_ui_logout(page, *, timeout_milliseconds: int, playwright_timeout_error) -> None:
    try:
        page.get_by_label("Account").last.click(timeout=timeout_milliseconds)
    except playwright_timeout_error as exc:
        raise VerificationError("Outline account menu was not available before logout verification") from exc
    try:
        page.get_by_text("Log out", exact=True).click(timeout=timeout_milliseconds)
    except playwright_timeout_error as exc:
        raise VerificationError("Outline account menu did not expose the Log out action") from exc


def verify_edge_logout(
    page,
    *,
    edge_url: str,
    edge_logout_url: str,
    logged_out_url: str,
    username: str,
    password: str,
    timeout_milliseconds: int,
    playwright_timeout_error,
) -> None:
    page.goto(edge_url, wait_until="domcontentloaded", timeout=timeout_milliseconds)
    authenticate_authentik_session(
        page,
        username=username,
        password=password,
        timeout_milliseconds=timeout_milliseconds,
        playwright_timeout_error=playwright_timeout_error,
    )
    page.goto(edge_url, wait_until="domcontentloaded", timeout=timeout_milliseconds)
    assert_response_host(page.url, expected_host=urlparse(edge_url).hostname or "", label="Shared edge login")

    page.goto(edge_logout_url, wait_until="domcontentloaded", timeout=timeout_milliseconds)
    wait_for_logged_out_destination(page, expected_url=logged_out_url, timeout_milliseconds=timeout_milliseconds)

    page.goto(edge_url, wait_until="domcontentloaded", timeout=timeout_milliseconds)
    assert_page_requires_authentik_login(
        page,
        label="Post-logout shared edge request",
        timeout_milliseconds=timeout_milliseconds,
        playwright_timeout_error=playwright_timeout_error,
    )


def verify_outline_logout(
    page,
    *,
    edge_url: str,
    outline_oidc_url: str,
    logged_out_url: str,
    username: str,
    password: str,
    timeout_milliseconds: int,
    playwright_timeout_error,
) -> None:
    page.goto(edge_url, wait_until="domcontentloaded", timeout=timeout_milliseconds)
    authenticate_authentik_session(
        page,
        username=username,
        password=password,
        timeout_milliseconds=timeout_milliseconds,
        playwright_timeout_error=playwright_timeout_error,
    )
    page.goto(outline_oidc_url, wait_until="networkidle", timeout=timeout_milliseconds)
    authenticate_authentik_session(
        page,
        username=username,
        password=password,
        timeout_milliseconds=timeout_milliseconds,
        playwright_timeout_error=playwright_timeout_error,
    )
    outline_host = urlparse(outline_oidc_url).hostname or ""
    assert_response_host(page.url, expected_host=outline_host, label="Outline login")

    trigger_outline_ui_logout(
        page,
        timeout_milliseconds=timeout_milliseconds,
        playwright_timeout_error=playwright_timeout_error,
    )
    wait_for_outline_logout_completion(page, expected_url=logged_out_url, timeout_milliseconds=timeout_milliseconds)

    for target, label in (
        (edge_url, "Post-logout shared edge request"),
        (outline_oidc_url, "Post-logout Outline OIDC request"),
    ):
        page.goto(target, wait_until="domcontentloaded", timeout=timeout_milliseconds)
        assert_page_requires_authentik_login(
            page,
            label=label,
            timeout_milliseconds=timeout_milliseconds,
            playwright_timeout_error=playwright_timeout_error,
        )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify shared edge and Outline logout flows against Authentik.")
    parser.add_argument("--username", default="akadmin", help="Authentik username used for verification.")
    parser.add_argument(
        "--password-file",
        type=Path,
        default=DEFAULT_PASSWORD_FILE,
        help="File containing the Authentik verification password.",
    )
    parser.add_argument("--edge-url", default=DEFAULT_EDGE_URL)
    parser.add_argument("--edge-logout-url", default=DEFAULT_EDGE_LOGOUT_URL)
    parser.add_argument("--outline-oidc-url", default=DEFAULT_OUTLINE_OIDC_URL)
    parser.add_argument("--logged-out-url", default=DEFAULT_LOGGED_OUT_URL)
    parser.add_argument("--timeout-seconds", type=float, default=60.0)
    parser.add_argument("--skip-edge", action="store_true", help="Skip the shared edge verification path.")
    parser.add_argument("--skip-outline", action="store_true", help="Skip the Outline browser verification path.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.skip_edge and args.skip_outline:
            raise ValueError("at least one verification target must remain enabled")
        if not args.password_file.is_file():
            raise FileNotFoundError(f"password file not found: {args.password_file}")
        password = args.password_file.read_text(encoding="utf-8").strip()
        if not password:
            raise ValueError(f"password file is empty: {args.password_file}")

        sync_playwright, playwright_timeout_error = load_playwright_sync_api()
        timeout_milliseconds = int(args.timeout_seconds * 1000)
        results: list[str] = []
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(ignore_https_errors=False)
            page = context.new_page()
            if not args.skip_edge:
                verify_edge_logout(
                    page,
                    edge_url=args.edge_url,
                    edge_logout_url=args.edge_logout_url,
                    logged_out_url=args.logged_out_url,
                    username=args.username,
                    password=password,
                    timeout_milliseconds=timeout_milliseconds,
                    playwright_timeout_error=playwright_timeout_error,
                )
                results.append(f"verified shared edge logout via {args.edge_url}")
            if not args.skip_outline:
                verify_outline_logout(
                    page,
                    edge_url=args.edge_url,
                    outline_oidc_url=args.outline_oidc_url,
                    logged_out_url=args.logged_out_url,
                    username=args.username,
                    password=password,
                    timeout_milliseconds=timeout_milliseconds,
                    playwright_timeout_error=playwright_timeout_error,
                )
                results.append(f"verified Outline logout via {args.outline_oidc_url}")
            context.close()
            browser.close()
        for line in results:
            print(line)
        return 0
    except Exception as exc:
        return emit_cli_error("session logout verification", exc)


if __name__ == "__main__":
    raise SystemExit(main())
