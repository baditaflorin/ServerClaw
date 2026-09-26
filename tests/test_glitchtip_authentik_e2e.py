from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "glitchtip_authentik_e2e.py"
SPEC = importlib.util.spec_from_file_location("glitchtip_authentik_e2e", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_callback_error_parser_returns_only_a_safe_code() -> None:
    callback = "https://errors.example.com/login/finalize?error=signup_closed&error_process=login&state=secret-state"

    assert MODULE.parse_callback_error(callback) == "signup_closed"
    assert "secret-state" not in str(MODULE.parse_callback_error(callback))


@pytest.mark.parametrize(
    "location",
    [
        "https://errors.example.com/login/finalize?error=user%40example.com",
        "https://errors.example.com/login/finalize?error=invalid%20credentials",
        "https://errors.example.com/login/finalize?state=secret-state",
    ],
)
def test_callback_error_parser_never_returns_arbitrary_query_values(location: str) -> None:
    assert MODULE.parse_callback_error(location) is None


@pytest.mark.parametrize(
    "status,payload,expected",
    [
        (200, {"meta": {"is_authenticated": True}}, True),
        (200, {"meta": {"is_authenticated": False}}, False),
        (401, {"meta": {"is_authenticated": True}}, False),
        (200, [], False),
    ],
)
def test_authenticated_session_requires_success_and_explicit_identity(
    status: int, payload: object, expected: bool
) -> None:
    assert MODULE.is_authenticated_session(status, payload) is expected


def test_glitchtip_browser_contract_keeps_tls_strict_and_checks_authenticated_session() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")

    assert "ignore_https_errors=True" not in source
    assert "--ignore-certificate-errors" not in source
    assert "/_allauth/browser/v1/auth/session" in source
    assert 'meta.get("is_authenticated") is True' in source
    assert "GlitchTip rejected Authentik sign-in" in source
