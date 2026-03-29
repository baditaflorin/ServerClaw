import sys
from http import cookiejar
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import session_logout_verify  # noqa: E402


def test_discover_local_root_prefers_shared_repo_root_for_worktrees(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    worktree_root = repo_root / ".worktrees" / "ws-0248"
    (repo_root / ".local").mkdir(parents=True)
    worktree_root.mkdir(parents=True)

    assert session_logout_verify.discover_local_root(worktree_root) == repo_root / ".local"


def test_normalize_url_ignores_trailing_slashes_and_queries() -> None:
    assert session_logout_verify.normalize_url("https://ops.lv3.org/.well-known/lv3/session/logged-out/?next=1") == (
        "https://ops.lv3.org/.well-known/lv3/session/logged-out"
    )


def test_assert_protected_redirect_accepts_relative_oauth2_proxy_challenges() -> None:
    snapshot = session_logout_verify.ResponseSnapshot(
        status_code=302,
        final_url="https://home.lv3.org/",
        headers={"location": "/oauth2/sign_in?rd=https%3A%2F%2Fhome.lv3.org%2F"},
        body="",
    )

    session_logout_verify.assert_protected_redirect(snapshot, label="shared edge")


def test_keycloak_logout_confirmation_present_matches_prompt_page() -> None:
    assert session_logout_verify.keycloak_logout_confirmation_present(
        "https://sso.lv3.org/realms/lv3/protocol/openid-connect/logout?client_id=outline",
        "LV3 CONTROL PLANE\nDo you want to log out?\n",
    )


def test_keycloak_logout_confirmation_present_rejects_non_prompt_pages() -> None:
    assert not session_logout_verify.keycloak_logout_confirmation_present(
        "https://ops.lv3.org/.well-known/lv3/session/logged-out",
        "You are logged out",
    )


def test_find_cookie_value_filters_by_name_and_domain() -> None:
    jar = cookiejar.CookieJar()
    jar.set_cookie(
        cookiejar.Cookie(
            version=0,
            name="accessToken",
            value="outline-session",
            port=None,
            port_specified=False,
            domain="wiki.lv3.org",
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
    )

    assert session_logout_verify.find_cookie_value(jar, "accessToken") == "outline-session"
    assert session_logout_verify.find_cookie_value(jar, "accessToken", domain_contains="wiki.lv3.org") == "outline-session"
    assert session_logout_verify.find_cookie_value(jar, "accessToken", domain_contains="home.lv3.org") is None


def test_cookie_to_playwright_cookie_preserves_security_attributes() -> None:
    cookie = cookiejar.Cookie(
        version=0,
        name="_lv3_ops_portal_proxy",
        value="proxy-session",
        port=None,
        port_specified=False,
        domain=".lv3.org",
        domain_specified=True,
        domain_initial_dot=True,
        path="/",
        path_specified=True,
        secure=True,
        expires=1_900_000_000,
        discard=False,
        comment=None,
        comment_url=None,
        rest={"HttpOnly": None, "SameSite": "Lax"},
        rfc2109=False,
    )

    assert session_logout_verify.cookie_to_playwright_cookie(cookie) == {
        "name": "_lv3_ops_portal_proxy",
        "value": "proxy-session",
        "domain": ".lv3.org",
        "path": "/",
        "secure": True,
        "expires": 1_900_000_000,
        "httpOnly": True,
        "sameSite": "Lax",
    }


def test_playwright_cookie_to_cookie_preserves_security_attributes() -> None:
    cookie = session_logout_verify.playwright_cookie_to_cookie(
        {
            "name": "_lv3_ops_portal_proxy",
            "value": "proxy-session",
            "domain": ".lv3.org",
            "path": "/",
            "secure": True,
            "expires": 1_900_000_000,
            "httpOnly": True,
            "sameSite": "Lax",
        }
    )

    assert cookie.name == "_lv3_ops_portal_proxy"
    assert cookie.value == "proxy-session"
    assert cookie.domain == ".lv3.org"
    assert cookie.path == "/"
    assert cookie.secure is True
    assert cookie.expires == 1_900_000_000
    assert cookie.discard is False
    assert cookie._rest == {"HttpOnly": True, "SameSite": "Lax"}


def test_assert_page_requires_keycloak_login_raises_when_form_never_appears() -> None:
    class FakeTimeoutError(Exception):
        pass

    class FakePage:
        url = "https://home.lv3.org/"

        def wait_for_selector(self, selector: str, timeout: int) -> None:
            raise FakeTimeoutError(f"{selector} missing after {timeout}")

    with pytest.raises(session_logout_verify.VerificationError):
        session_logout_verify.assert_page_requires_keycloak_login(
            FakePage(),
            label="home request",
            timeout_milliseconds=1_000,
            playwright_timeout_error=FakeTimeoutError,
        )


def test_wait_for_logged_out_destination_confirms_keycloak_prompt() -> None:
    expected_url = "https://ops.lv3.org/.well-known/lv3/session/logged-out"
    calls: list[int] = []

    class FakePage:
        def __init__(self) -> None:
            self.url = "https://sso.lv3.org/realms/lv3/protocol/openid-connect/logout?client_id=outline"

        def locator(self, selector: str):  # noqa: ANN201
            assert selector == "body"

            class FakeBodyLocator:
                def inner_text(self, timeout: int) -> str:
                    assert timeout == 1_000
                    return "LV3 CONTROL PLANE\nDo you want to log out?\n"

            return FakeBodyLocator()

        def wait_for_timeout(self, timeout: int) -> None:
            assert timeout == 500

    def fake_submit_keycloak_logout_confirmation(page: object, *, timeout_milliseconds: int):  # type: ignore[no-untyped-def]
        assert isinstance(page, FakePage)
        assert timeout_milliseconds == 1_000
        calls.append(timeout_milliseconds)
        page.url = expected_url
        return session_logout_verify.ResponseSnapshot(
            status_code=200,
            final_url=expected_url,
            headers={},
            body="Signed out",
        )

    page = FakePage()
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        session_logout_verify,
        "submit_keycloak_logout_confirmation",
        fake_submit_keycloak_logout_confirmation,
    )

    try:
        session_logout_verify.wait_for_logged_out_destination(
            page,
            expected_url=expected_url,
            timeout_milliseconds=1_000,
            playwright_timeout_error=RuntimeError,
        )
    finally:
        monkeypatch.undo()

    assert page.url == expected_url
    assert calls == [1_000]


def test_authenticate_keycloak_session_accepts_existing_sso_session(monkeypatch: pytest.MonkeyPatch) -> None:
    expected = session_logout_verify.ResponseSnapshot(
        status_code=200,
        final_url="https://wiki.lv3.org/collection/architecture/recent",
        headers={},
        body="<html><title>Outline</title></html>",
    )
    calls: list[str] = []

    def fake_fetch_response(*args, **kwargs):  # type: ignore[no-untyped-def]
        calls.append(kwargs.get("method", "GET"))
        return expected

    monkeypatch.setattr(session_logout_verify, "fetch_response", fake_fetch_response)

    actual = session_logout_verify.authenticate_keycloak_session(
        object(),  # type: ignore[arg-type]
        start_url="https://wiki.lv3.org/auth/oidc",
        username="outline.automation",
        password="secret",
        timeout_seconds=60,
    )

    assert actual == expected
    assert calls == ["GET"]


def test_authenticate_keycloak_session_raises_for_unparseable_keycloak_form(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    login_page = session_logout_verify.ResponseSnapshot(
        status_code=200,
        final_url="https://sso.lv3.org/realms/lv3/protocol/openid-connect/auth",
        headers={},
        body='<html><form id="kc-form-login"></form></html>',
    )

    monkeypatch.setattr(session_logout_verify, "fetch_response", lambda *args, **kwargs: login_page)

    with pytest.raises(session_logout_verify.VerificationError, match="unable to parse the Keycloak login form"):
        session_logout_verify.authenticate_keycloak_session(
            object(),  # type: ignore[arg-type]
            start_url="https://wiki.lv3.org/auth/oidc",
            username="outline.automation",
            password="secret",
            timeout_seconds=60,
        )
