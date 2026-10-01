from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "gitea_authentik_e2e.py"
SPEC = importlib.util.spec_from_file_location("gitea_authentik_e2e", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_prepare_password_is_private_and_never_printed(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "authentik" / "gitea-e2e-initial-password.txt"
    assert MODULE.prepare_password_file(path) is True
    secret = path.read_text(encoding="utf-8").strip()
    assert secret
    assert path.stat().st_mode & 0o777 == 0o600
    assert MODULE.prepare_password_file(path) is False
    assert path.read_text(encoding="utf-8").strip() == secret
    assert secret not in capsys.readouterr().out


def test_private_file_reader_rejects_symlinks(tmp_path: Path) -> None:
    target = tmp_path / "real-secret"
    target.write_text("not-for-output", encoding="utf-8")
    target.chmod(0o600)
    link = tmp_path / "secret-link"
    link.symlink_to(target)

    with pytest.raises(MODULE.VerificationError, match="symlink"):
        MODULE.read_private_file(link, label="test password")


def test_private_file_reader_rejects_group_or_world_readable_files(tmp_path: Path) -> None:
    path = tmp_path / "weak-secret"
    path.write_text("not-for-output", encoding="utf-8")
    path.chmod(0o640)

    with pytest.raises(MODULE.VerificationError, match="permissions"):
        MODULE.read_private_file(path, label="test password")


class FakePage:
    def __init__(self, response: dict[str, object]) -> None:
        self.response = response
        self.script = ""

    def evaluate(self, script: str, argument: str) -> dict[str, object]:
        self.script = script
        self.argument = argument
        return self.response

    def locator(self, selector: str) -> FakeLocator:
        self.selector = selector
        return FakeLocator()

    def wait_for_function(self, script: str, *, arg: str, timeout: int) -> None:
        self.wait_script = script
        self.wait_argument = arg
        assert timeout == 10_000


class FakeLocator:
    def wait_for(self, *, state: str, timeout: int) -> None:
        assert state == "visible"
        assert timeout == 10_000


def test_browser_session_proves_expected_non_admin_user() -> None:
    page = FakePage({"status": 200, "login": "gitea-e2e", "is_admin": False, "session_login": "gitea-e2e"})
    MODULE.verify_authenticated_user(page, username="gitea-e2e")
    assert "querySelectorAll('.gt-ellipsis')" in page.script
    assert "node.textContent.trim() === expectedLogin" in page.script
    assert "fetch(`/api/v1/users/${encodeURIComponent(sessionLogin)}`" in page.script
    assert "credentials: 'same-origin'" in page.script
    assert page.argument == "gitea-e2e"
    assert "querySelectorAll('.gt-ellipsis')" in page.wait_script
    assert "node.textContent.trim() === expectedLogin" in page.wait_script
    assert page.wait_argument == "gitea-e2e"


def test_authentik_browser_errors_are_redacted(monkeypatch: pytest.MonkeyPatch) -> None:
    import session_logout_verify

    def fail_with_sensitive_url(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("authorization failed at https://id.example.net/flow/?state=do-not-log")

    monkeypatch.setattr(session_logout_verify, "authenticate_authentik_session", fail_with_sensitive_url)
    with pytest.raises(MODULE.VerificationError, match="diagnostics were redacted") as caught:
        MODULE.complete_authentik_login(
            object(),
            username="gitea-e2e",
            password="not-for-output",
            timeout_ms=1000,
            playwright_timeout_error=TimeoutError,
        )
    assert "do-not-log" not in str(caught.value)
    assert "not-for-output" not in str(caught.value)


@pytest.mark.parametrize(
    "response, message",
    [
        ({"status": 401}, "not authenticated"),
        (
            {"status": 200, "login": "gitea-e2e", "is_admin": False, "session_login": "someone-else"},
            "requested account",
        ),
        (
            {"status": 200, "login": "someone-else", "is_admin": False, "session_login": "gitea-e2e"},
            "different account",
        ),
        ({"status": 200, "login": "gitea-e2e", "is_admin": True, "session_login": "gitea-e2e"}, "non-admin"),
        ({"status": 200, "login": "gitea-e2e", "session_login": "gitea-e2e"}, "non-admin"),
    ],
)
def test_browser_session_rejects_wrong_or_privileged_user(response: dict[str, object], message: str) -> None:
    with pytest.raises(MODULE.VerificationError, match=message):
        MODULE.verify_authenticated_user(FakePage(response), username="gitea-e2e")


def test_e2e_manifest_limits_the_test_identity_to_non_admin_consumer_groups() -> None:
    import yaml

    manifest = yaml.safe_load((REPO_ROOT / "config/authentik/test-identities.yaml").read_text(encoding="utf-8"))
    assert manifest["groups"] == []
    assert len(manifest["users"]) == 1
    user = manifest["users"][0]
    assert user["username"] == "gitea-e2e"
    assert user["groups"] == ["gitea-users", "grafana-viewers"]
    assert user["provisioning"] == "create_if_missing"
    assert user["type"] == "internal"
    assert "is_admin" not in user
    assert "platform-admins" not in user["groups"]
    assert "authentik Admins" not in user["groups"]
    assert "grafana-admins" not in user["groups"]


def test_tls_validation_is_not_disabled() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    assert "ignore_https_errors=True" not in source
    assert "--ignore-certificate-errors" not in source
    assert '"tls_validation": "enabled"' in source
