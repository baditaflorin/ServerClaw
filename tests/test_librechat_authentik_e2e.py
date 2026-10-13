from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "librechat_authentik_e2e.py"
SCRIPT_DIR = SCRIPT_PATH.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
SPEC = importlib.util.spec_from_file_location("librechat_authentik_e2e", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_librechat_base_url_is_https_origin_only() -> None:
    assert MODULE.normalize_base_url("https://chat.example.com/") == "https://chat.example.com"
    with pytest.raises(MODULE.VerificationError, match="HTTPS"):
        MODULE.normalize_base_url("http://chat.example.com")
    with pytest.raises(MODULE.VerificationError, match="must not contain credentials"):
        MODULE.normalize_base_url("https://user:password@chat.example.com")
    with pytest.raises(MODULE.VerificationError, match="must not contain credentials"):
        MODULE.normalize_base_url("https://chat.example.com/?state=secret")


@pytest.mark.parametrize(
    "final_host,app_host,composer_visible,login_count,expected",
    [
        ("chat.example.com", "chat.example.com", True, 0, True),
        ("id.example.com", "chat.example.com", True, 0, False),
        ("chat.example.com", "chat.example.com", False, 0, False),
        ("chat.example.com", "chat.example.com", True, 1, False),
    ],
)
def test_authenticated_chat_surface_requires_app_host_and_composer(
    final_host: str, app_host: str, composer_visible: bool, login_count: int, expected: bool
) -> None:
    assert (
        MODULE.authenticated_chat_surface(
            final_host=final_host,
            app_host=app_host,
            composer_visible=composer_visible,
            login_control_count=login_count,
        )
        is expected
    )


def test_browser_contract_keeps_tls_strict_and_redacts_callback_data() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")

    assert "ignore_https_errors=True" not in source
    assert "--ignore-certificate-errors" not in source
    assert 'CALLBACK_PATH = "/oauth/openid/callback"' in source
    assert "LibreChat OIDC callback returned HTTP" in source
