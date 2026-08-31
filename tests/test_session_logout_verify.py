import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import session_logout_verify  # noqa: E402


def test_discover_local_root_prefers_shared_repo_root_for_worktrees(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    worktree_root = repo_root / ".worktrees" / "ws-0491"
    (repo_root / ".local").mkdir(parents=True)
    worktree_root.mkdir(parents=True)

    assert session_logout_verify.discover_local_root(worktree_root) == repo_root / ".local"


def test_normalize_url_ignores_trailing_slashes_and_queries() -> None:
    assert (
        session_logout_verify.normalize_url("https://ops.example.com/.well-known/lv3/session/logged-out/?next=1")
        == "https://ops.example.com/.well-known/lv3/session/logged-out"
    )


def test_assert_response_host_rejects_unexpected_host() -> None:
    with pytest.raises(session_logout_verify.VerificationError, match="should land"):
        session_logout_verify.assert_response_host(
            "https://id.example.com/if/flow/default-authentication-flow/",
            expected_host="home.example.com",
            label="shared edge login",
        )


def test_assert_page_requires_authentik_login_raises_when_identifier_never_appears() -> None:
    class FakeTimeoutError(Exception):
        pass

    class FakeLocator:
        def wait_for(self, *, state: str, timeout: int) -> None:
            assert state == "visible"
            assert timeout == 1_000
            raise FakeTimeoutError("identifier missing")

    class FakePage:
        url = "https://home.example.com/"

        def get_by_label(self, label: str, *, exact: bool):
            assert label == "Email or Username"
            assert exact is True
            return FakeLocator()

    with pytest.raises(session_logout_verify.VerificationError, match="fresh Authentik login"):
        session_logout_verify.assert_page_requires_authentik_login(
            FakePage(),
            label="home request",
            timeout_milliseconds=1_000,
            playwright_timeout_error=FakeTimeoutError,
        )


def test_outline_logout_accepts_authentik_provider_confirmation_and_continues() -> None:
    expected = "https://ops.example.com/.well-known/lv3/session/logged-out"

    class FakePage:
        url = (
            "https://id.example.com/if/flow/default-provider-invalidation-flow/"
            "?post_logout_redirect_uri=https%3A%2F%2Fops.example.com%2F.well-known%2Flv3%2Fsession%2Flogged-out"
        )

        def title(self) -> str:
            return "You've logged out of Outline. - authentik"

        def goto(self, target: str, *, wait_until: str, timeout: int) -> None:
            assert wait_until == "domcontentloaded"
            assert timeout == 1_000
            self.url = target

        def wait_for_timeout(self, _milliseconds: int) -> None:
            raise AssertionError("provider confirmation should be accepted without polling")

    page = FakePage()
    session_logout_verify.wait_for_outline_logout_completion(page, expected_url=expected, timeout_milliseconds=1_000)
    assert page.url == expected


def test_parse_args_defaults_to_authentik_bootstrap_credential() -> None:
    args = session_logout_verify.parse_args([])

    assert args.username == "akadmin"
    assert args.password_file == session_logout_verify.DEFAULT_LOCAL_ROOT / "authentik" / "bootstrap-password.txt"


def test_main_rejects_no_verification_target(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        session_logout_verify, "parse_args", lambda _argv: type("Args", (), {"skip_edge": True, "skip_outline": True})()
    )

    assert session_logout_verify.main([]) == 2
