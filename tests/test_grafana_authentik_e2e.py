from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = REPO_ROOT / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
SCRIPT_PATH = SCRIPT_DIR / "grafana_authentik_e2e.py"
SPEC = importlib.util.spec_from_file_location("grafana_authentik_e2e", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_grafana_session_proves_expected_non_admin_viewer() -> None:
    result = MODULE.verify_grafana_user(
        200,
        {"login": "gitea-e2e", "isGrafanaAdmin": False, "orgRole": "Viewer"},
        username="gitea-e2e",
    )

    assert result == {"login": "gitea-e2e", "org_role": "Viewer", "is_admin": False}


@pytest.mark.parametrize(
    "status,payload,message",
    [
        (401, {}, "authenticated user profile"),
        (200, {"login": "another-user", "isGrafanaAdmin": False, "orgRole": "Viewer"}, "different test identity"),
        (200, {"login": "gitea-e2e", "isGrafanaAdmin": True, "orgRole": "Admin"}, "non-admin"),
        (200, {"login": "gitea-e2e", "isGrafanaAdmin": False, "orgRole": "Editor"}, "Viewer role"),
    ],
)
def test_grafana_session_rejects_wrong_or_privileged_users(
    status: int, payload: dict[str, object], message: str
) -> None:
    with pytest.raises(MODULE.VerificationError, match=message):
        MODULE.verify_grafana_user(status, payload, username="gitea-e2e")


def test_grafana_browser_contract_keeps_tls_strict_and_checks_viewer_role() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")

    assert "ignore_https_errors=True" not in source
    assert "--ignore-certificate-errors" not in source
    assert 'USER_API_PATH = "/api/user"' in source
    assert 'payload.get("orgRole") != "Viewer"' in source
    assert 'payload.get("isGrafanaAdmin") is not False' in source
