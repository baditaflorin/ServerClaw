from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = REPO_ROOT / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
SCRIPT_PATH = SCRIPT_DIR / "harbor_authentik_e2e.py"
SPEC = importlib.util.spec_from_file_location("harbor_authentik_e2e", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_harbor_session_proves_expected_non_admin_identity() -> None:
    result = MODULE.verify_harbor_user(
        200,
        {"username": "gitea-e2e", "sysadmin_flag": False, "admin_role_in_auth": False},
        username="gitea-e2e",
    )

    assert result == {"username": "gitea-e2e", "is_admin": False}


@pytest.mark.parametrize(
    "status,payload,message",
    [
        (401, {}, "authenticated user profile"),
        (200, {"username": "another-user", "sysadmin_flag": False}, "different test identity"),
        (200, {"username": "gitea-e2e", "sysadmin_flag": True}, "non-admin"),
        (200, {"username": "gitea-e2e", "sysadmin_flag": False, "admin_role_in_auth": True}, "Authentik claims"),
    ],
)
def test_harbor_session_rejects_wrong_or_privileged_users(
    status: int,
    payload: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(MODULE.VerificationError, match=message):
        MODULE.verify_harbor_user(status, payload, username="gitea-e2e")


def test_harbor_browser_contract_keeps_tls_strict_and_checks_non_admin_profile() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")

    assert "ignore_https_errors=True" not in source
    assert "--ignore-certificate-errors" not in source
    assert 'CURRENT_USER_API_PATH = "/api/v2.0/users/current"' in source
    assert 'payload.get("sysadmin_flag") is not False' in source
