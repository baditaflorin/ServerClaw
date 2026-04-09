#!/usr/bin/env python3

from __future__ import annotations

import argparse
import time
from dataclasses import dataclass
from http import cookiejar
from pathlib import Path
from urllib import error, parse, request
from urllib.parse import urlparse

from controller_automation_toolkit import emit_cli_error
from sync_docs_to_outline import KeycloakLoginFormParser


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
DEFAULT_PASSWORD_FILE = DEFAULT_LOCAL_ROOT / "keycloak" / "outline.automation-password.txt"
DEFAULT_EDGE_URL = "https://home.localhost/"
DEFAULT_EDGE_LOGOUT_URL = "https://home.localhost/.well-known/lv3/session/logout"
DEFAULT_OUTLINE_OIDC_URL = "https://wiki.localhost/auth/oidc"
DEFAULT_OUTLINE_LOGOUT_URL = "https://wiki.localhost/logout"
DEFAULT_LOGGED_OUT_URL = "https://ops.localhost/.well-known/lv3/session/logged-out"
DEFAULT_SHARED_PROXY_COOKIE_NAME = "_lv3_ops_portal_proxy"
DEFAULT_OUTLINE_SESSION_COOKIE_NAME = "accessToken"


class VerificationError(RuntimeError):
    pass


class NoRedirectHandler(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


@dataclass(frozen=True)
class ResponseSnapshot:
    status_code: int
    final_url: str
    headers: dict[str, str]
    body: str


def build_opener(jar: cookiejar.CookieJar, *, follow_redirects: bool) -> request.OpenerDirector:
    handlers: list[object] = [request.HTTPCookieProcessor(jar)]
    if not follow_redirects:
        handlers.append(NoRedirectHandler())
    opener = request.build_opener(*handlers)
    opener.addheaders = [("User-Agent", "lv3-session-logout-verify/1.0")]
    return opener


def fetch_response(
    opener: request.OpenerDirector,
    url: str,
    *,
    method: str = "GET",
    data: bytes | None = None,
    headers: dict[str, str] | None = None,
    timeout_seconds: float,
) -> ResponseSnapshot:
    req = request.Request(url, data=data, method=method)
    for header_name, header_value in (headers or {}).items():
        req.add_header(header_name, header_value)
    try:
        with opener.open(req, timeout=timeout_seconds) as response:  # noqa: S310
            return ResponseSnapshot(
                status_code=response.getcode(),
                final_url=response.geturl(),
                headers={key.lower(): value for key, value in response.headers.items()},
                body=response.read().decode("utf-8", errors="replace"),
            )
    except error.HTTPError as exc:
        return ResponseSnapshot(
            status_code=exc.code,
            final_url=exc.geturl(),
            headers={key.lower(): value for key, value in exc.headers.items()},
            body=exc.read().decode("utf-8", errors="replace"),
        )


def normalize_url(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path.rstrip("/") or "/"
    return parsed._replace(path=path, query="", fragment="").geturl()


def keycloak_login_form_present(body: str) -> bool:
    return 'id="kc-form-login"' in body


def keycloak_logout_confirmation_present(current_url: str, body: str) -> bool:
    parsed = urlparse(current_url)
    return parsed.path.endswith("/protocol/openid-connect/logout") and "Do you want to log out?" in body


def assert_protected_redirect(snapshot: ResponseSnapshot, *, label: str) -> None:
    location = snapshot.headers.get("location", "")
    if snapshot.status_code != 302 or "/oauth2/sign_in" not in location:
        raise VerificationError(
            f"{label} should redirect to the oauth2-proxy sign-in challenge, "
            f"found HTTP {snapshot.status_code} with location={location!r}"
        )


def assert_logged_out_destination(snapshot: ResponseSnapshot, *, expected_url: str, label: str) -> None:
    if normalize_url(snapshot.final_url) != normalize_url(expected_url):
        raise VerificationError(
            f"{label} should finish on {expected_url}, landed on {snapshot.final_url}"
        )


def assert_response_host(snapshot: ResponseSnapshot, *, expected_host: str, label: str) -> None:
    if urlparse(snapshot.final_url).hostname != expected_host:
        raise VerificationError(f"{label} should land on {expected_host}, landed on {snapshot.final_url}")


def authenticate_keycloak_session(
    opener: request.OpenerDirector,
    *,
    start_url: str,
    username: str,
    password: str,
    timeout_seconds: float,
) -> ResponseSnapshot:
    initial = fetch_response(opener, start_url, timeout_seconds=timeout_seconds)
    parser = KeycloakLoginFormParser()
    parser.feed(initial.body)
    if not parser.form_action:
        if keycloak_login_form_present(initial.body):
            raise VerificationError(
                f"unable to parse the Keycloak login form when starting at {start_url}"
            )
        return initial
    form_fields = dict(parser.hidden_fields)
    form_fields["username"] = username
    form_fields["password"] = password
    login_url = parse.urljoin(initial.final_url, parser.form_action)
    authenticated = fetch_response(
        opener,
        login_url,
        method="POST",
        data=parse.urlencode(form_fields).encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout_seconds=timeout_seconds,
    )
    if keycloak_login_form_present(authenticated.body):
        raise VerificationError(f"Keycloak login form remained visible after authenticating against {start_url}")
    return authenticated


def find_cookie_value(jar: cookiejar.CookieJar, name: str, *, domain_contains: str | None = None) -> str | None:
    for cookie in jar:
        if cookie.name != name:
            continue
        if domain_contains and domain_contains not in cookie.domain:
            continue
        return cookie.value
    return None


def cookie_to_playwright_cookie(cookie: cookiejar.Cookie) -> dict[str, object]:
    playwright_cookie: dict[str, object] = {
        "name": cookie.name,
        "value": cookie.value,
        "domain": cookie.domain,
        "path": cookie.path,
        "secure": cookie.secure,
    }
    if cookie.expires is not None:
        playwright_cookie["expires"] = cookie.expires
    rest = {str(key).lower(): value for key, value in cookie._rest.items()}
    if "httponly" in rest:
        playwright_cookie["httpOnly"] = True
    same_site = rest.get("samesite")
    if same_site:
        playwright_cookie["sameSite"] = str(same_site).capitalize()
    return playwright_cookie


def playwright_cookie_to_cookie(cookie: dict[str, object]) -> cookiejar.Cookie:
    expires = cookie.get("expires")
    expires_value = int(expires) if expires not in (-1, None) else None
    return cookiejar.Cookie(
        version=0,
        name=str(cookie["name"]),
        value=str(cookie["value"]),
        port=None,
        port_specified=False,
        domain=str(cookie["domain"]),
        domain_specified=True,
        domain_initial_dot=str(cookie["domain"]).startswith("."),
        path=str(cookie.get("path", "/")),
        path_specified=True,
        secure=bool(cookie.get("secure", False)),
        expires=expires_value,
        discard=expires_value is None,
        comment=None,
        comment_url=None,
        rest={
            "HttpOnly": cookie.get("httpOnly", False),
            "SameSite": cookie.get("sameSite"),
        },
        rfc2109=False,
    )


def submit_keycloak_logout_confirmation(
    page,  # noqa: ANN001 - imported lazily from Playwright
    *,
    timeout_milliseconds: int,
) -> ResponseSnapshot:
    # Headless Playwright clicks do not reliably advance the Keycloak logout form,
    # so submit the exact live form over HTTP and then sync the resulting cookie
    # state back into the browser context before resuming browser assertions.
    form_state = page.locator("form").evaluate(
        "form => ({ action: form.action, method: form.method || 'POST', "
        "body: new URLSearchParams(new FormData(form)).toString() })"
    )
    jar = cookiejar.CookieJar()
    for browser_cookie in page.context.cookies():
        jar.set_cookie(playwright_cookie_to_cookie(browser_cookie))
    snapshot = fetch_response(
        build_opener(jar, follow_redirects=True),
        form_state["action"],
        method=str(form_state["method"]).upper(),
        data=str(form_state["body"]).encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout_seconds=timeout_milliseconds / 1000,
    )
    page.context.clear_cookies()
    remaining_cookies = [cookie_to_playwright_cookie(cookie) for cookie in jar]
    if remaining_cookies:
        page.context.add_cookies(remaining_cookies)
    page.goto(snapshot.final_url, wait_until="domcontentloaded", timeout=timeout_milliseconds)
    return snapshot


def load_playwright_sync_api():
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover - exercised only in live verification
        raise VerificationError(
            "Outline browser verification requires Playwright. "
            "Run `uv run --with playwright python scripts/session_logout_verify.py ...`."
        ) from exc
    return sync_playwright, PlaywrightTimeoutError


def assert_page_requires_keycloak_login(
    page,  # noqa: ANN001 - imported lazily from Playwright
    *,
    label: str,
    timeout_milliseconds: int,
    playwright_timeout_error,
) -> None:
    try:
        page.wait_for_selector("#kc-form-login", timeout=timeout_milliseconds)
    except playwright_timeout_error as exc:
        raise VerificationError(f"{label} should require a fresh Keycloak login, landed on {page.url}") from exc


def trigger_outline_ui_logout(
    page,  # noqa: ANN001 - imported lazily from Playwright
    *,
    outline_logout_url: str,
    timeout_milliseconds: int,
    playwright_timeout_error,
) -> None:
    try:
        page.get_by_label("Account").last.click(timeout=timeout_milliseconds)
    except playwright_timeout_error as exc:
        raise VerificationError(
            "Outline account menu was not available before logout verification "
            f"(legacy logout URL: {outline_logout_url})"
        ) from exc
    try:
        page.get_by_text("Log out", exact=True).click(timeout=timeout_milliseconds)
    except playwright_timeout_error as exc:
        raise VerificationError(
            "Outline account menu did not expose the Log out action "
            f"(legacy logout URL: {outline_logout_url})"
        ) from exc


def wait_for_logged_out_destination(
    page,  # noqa: ANN001 - imported lazily from Playwright
    *,
    expected_url: str,
    timeout_milliseconds: int,
    playwright_timeout_error,  # noqa: ANN001
) -> None:
    deadline = time.monotonic() + (timeout_milliseconds / 1000)
    while time.monotonic() < deadline:
        current_url = page.url
        if normalize_url(current_url) == normalize_url(expected_url):
            return
        body = page.locator("body").inner_text(timeout=timeout_milliseconds)
        if keycloak_logout_confirmation_present(current_url, body):
            snapshot = submit_keycloak_logout_confirmation(
                page,
                timeout_milliseconds=timeout_milliseconds,
            )
            if normalize_url(snapshot.final_url) != normalize_url(expected_url):
                raise VerificationError(
                    f"Keycloak logout confirmation should finish on {expected_url}, "
                    f"landed on {snapshot.final_url}"
                )
        page.wait_for_timeout(500)
    raise VerificationError(f"Outline logout should finish on {expected_url}, landed on {page.url}")


def verify_edge_logout(
    *,
    edge_url: str,
    edge_logout_url: str,
    logged_out_url: str,
    username: str,
    password: str,
    timeout_seconds: float,
) -> None:
    jar = cookiejar.CookieJar()
    browser = build_opener(jar, follow_redirects=True)
    probe = build_opener(jar, follow_redirects=False)

    assert_protected_redirect(
        fetch_response(probe, edge_url, timeout_seconds=timeout_seconds),
        label="Unauthenticated edge request",
    )
    authenticated = authenticate_keycloak_session(
        browser,
        start_url=edge_url,
        username=username,
        password=password,
        timeout_seconds=timeout_seconds,
    )
    assert_response_host(
        authenticated,
        expected_host=urlparse(edge_url).hostname or "",
        label="Shared edge login",
    )
    if not find_cookie_value(jar, DEFAULT_SHARED_PROXY_COOKIE_NAME):
        raise VerificationError("Shared edge login did not produce the oauth2-proxy session cookie")
    protected = fetch_response(browser, edge_url, timeout_seconds=timeout_seconds)
    if protected.status_code != 200:
        raise VerificationError(
            f"Shared edge should return HTTP 200 after login, found {protected.status_code} at {protected.final_url}"
        )
    logout = fetch_response(browser, edge_logout_url, timeout_seconds=timeout_seconds)
    assert_logged_out_destination(logout, expected_url=logged_out_url, label="Shared edge logout")
    assert_protected_redirect(
        fetch_response(probe, edge_url, timeout_seconds=timeout_seconds),
        label="Post-logout edge request",
    )


def verify_outline_logout(
    *,
    edge_url: str,
    outline_oidc_url: str,
    outline_logout_url: str,
    logged_out_url: str,
    username: str,
    password: str,
    timeout_seconds: float,
) -> None:
    jar = cookiejar.CookieJar()
    browser = build_opener(jar, follow_redirects=True)
    probe = build_opener(jar, follow_redirects=False)

    assert_protected_redirect(
        fetch_response(probe, edge_url, timeout_seconds=timeout_seconds),
        label="Unauthenticated edge request",
    )
    edge_authenticated = authenticate_keycloak_session(
        browser,
        start_url=edge_url,
        username=username,
        password=password,
        timeout_seconds=timeout_seconds,
    )
    assert_response_host(
        edge_authenticated,
        expected_host=urlparse(edge_url).hostname or "",
        label="Shared edge bootstrap login",
    )
    if not find_cookie_value(jar, DEFAULT_SHARED_PROXY_COOKIE_NAME):
        raise VerificationError("Shared edge bootstrap login did not produce the oauth2-proxy session cookie")

    outline_authenticated = authenticate_keycloak_session(
        browser,
        start_url=outline_oidc_url,
        username=username,
        password=password,
        timeout_seconds=timeout_seconds,
    )
    assert_response_host(
        outline_authenticated,
        expected_host=urlparse(outline_oidc_url).hostname or "",
        label="Outline login",
    )
    outline_host = urlparse(outline_oidc_url).hostname or ""
    if not find_cookie_value(jar, DEFAULT_OUTLINE_SESSION_COOKIE_NAME, domain_contains=outline_host):
        raise VerificationError("Outline login did not produce the Outline application session cookie")

    sync_playwright, playwright_timeout_error = load_playwright_sync_api()
    timeout_milliseconds = int(timeout_seconds * 1000)
    with sync_playwright() as playwright:
        browser_context = playwright.chromium.launch(headless=True)
        context = browser_context.new_context(ignore_https_errors=False)
        context.add_cookies([cookie_to_playwright_cookie(cookie) for cookie in jar])
        page = context.new_page()

        page.goto(outline_oidc_url, wait_until="networkidle", timeout=timeout_milliseconds)
        if urlparse(page.url).hostname != outline_host or keycloak_login_form_present(page.content()):
            raise VerificationError(f"Outline browser bootstrap did not land on an authenticated wiki page: {page.url}")

        trigger_outline_ui_logout(
            page,
            outline_logout_url=outline_logout_url,
            timeout_milliseconds=timeout_milliseconds,
            playwright_timeout_error=playwright_timeout_error,
        )
        wait_for_logged_out_destination(
            page,
            expected_url=logged_out_url,
            timeout_milliseconds=timeout_milliseconds,
            playwright_timeout_error=playwright_timeout_error,
        )

        page.goto(edge_url, wait_until="domcontentloaded", timeout=timeout_milliseconds)
        assert_page_requires_keycloak_login(
            page,
            label="Post-logout shared edge request",
            timeout_milliseconds=timeout_milliseconds,
            playwright_timeout_error=playwright_timeout_error,
        )

        page.goto(outline_oidc_url, wait_until="domcontentloaded", timeout=timeout_milliseconds)
        assert_page_requires_keycloak_login(
            page,
            label="Post-logout Outline OIDC request",
            timeout_milliseconds=timeout_milliseconds,
            playwright_timeout_error=playwright_timeout_error,
        )

        browser_context.close()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify shared edge and Outline logout flows against the live LV3 platform."
    )
    parser.add_argument("--username", default="outline.automation", help="Keycloak username used for verification.")
    parser.add_argument(
        "--password-file",
        type=Path,
        default=DEFAULT_PASSWORD_FILE,
        help="File containing the verification password.",
    )
    parser.add_argument("--edge-url", default=DEFAULT_EDGE_URL)
    parser.add_argument("--edge-logout-url", default=DEFAULT_EDGE_LOGOUT_URL)
    parser.add_argument("--outline-oidc-url", default=DEFAULT_OUTLINE_OIDC_URL)
    parser.add_argument("--outline-logout-url", default=DEFAULT_OUTLINE_LOGOUT_URL)
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
        if not args.password_file.exists():
            raise FileNotFoundError(f"password file not found: {args.password_file}")
        password = args.password_file.read_text(encoding="utf-8").strip()
        if not password:
            raise ValueError(f"password file is empty: {args.password_file}")

        results: list[str] = []
        if not args.skip_edge:
            verify_edge_logout(
                edge_url=args.edge_url,
                edge_logout_url=args.edge_logout_url,
                logged_out_url=args.logged_out_url,
                username=args.username,
                password=password,
                timeout_seconds=args.timeout_seconds,
            )
            results.append(f"verified shared edge logout via {args.edge_url}")
        if not args.skip_outline:
            verify_outline_logout(
                edge_url=args.edge_url,
                outline_oidc_url=args.outline_oidc_url,
                outline_logout_url=args.outline_logout_url,
                logged_out_url=args.logged_out_url,
                username=args.username,
                password=password,
                timeout_seconds=args.timeout_seconds,
            )
            results.append(f"verified Outline logout via {args.outline_oidc_url}")
        for line in results:
            print(line)
        return 0
    except Exception as exc:  # noqa: BLE001
        return emit_cli_error("session logout verification", exc)


if __name__ == "__main__":
    raise SystemExit(main())
