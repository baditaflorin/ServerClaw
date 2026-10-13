from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "grafana_authentik_e2e.py"
SCRIPT_DIR = SCRIPT_PATH.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
SPEC = importlib.util.spec_from_file_location("grafana_authentik_e2e", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_grafana_base_url_is_https_origin_only() -> None:
    assert MODULE.normalize_base_url("https://grafana.example.com/") == "https://grafana.example.com"
    with pytest.raises(MODULE.VerificationError, match="HTTPS"):
        MODULE.normalize_base_url("http://grafana.example.com")
    with pytest.raises(MODULE.VerificationError, match="must not contain credentials"):
        MODULE.normalize_base_url("https://user:password@grafana.example.com")
    with pytest.raises(MODULE.VerificationError, match="must not contain credentials"):
        MODULE.normalize_base_url("https://grafana.example.com/?state=secret")


def test_grafana_user_profile_confirms_identity_and_server_non_admin() -> None:
    result = MODULE.verify_grafana_user(
        200,
        {"login": "gitea-e2e", "orgRole": None, "isGrafanaAdmin": False},
        username="gitea-e2e",
    )

    assert result == {"username": "gitea-e2e", "grafana_admin": False}


@pytest.mark.parametrize(
    "status,payload,message",
    [
        (401, {}, "authenticated user profile"),
        (200, [], "authenticated user profile"),
        (200, {"login": "another-user", "isGrafanaAdmin": False}, "different test identity"),
        (200, {"login": "gitea-e2e", "isGrafanaAdmin": True}, "not confirmed non-admin"),
        (200, {"login": "gitea-e2e", "isGrafanaAdmin": None}, "not confirmed non-admin"),
    ],
)
def test_grafana_user_profile_rejects_wrong_or_privileged_user(status: int, payload: object, message: str) -> None:
    with pytest.raises(MODULE.VerificationError, match=message):
        MODULE.verify_grafana_user(status, payload, username="gitea-e2e")


def test_grafana_org_membership_confirms_expected_viewer_role() -> None:
    result = MODULE.verify_grafana_org_memberships(
        200,
        [{"orgId": 1, "name": "Main Org.", "role": "Viewer"}],
    )

    assert result == {"org_role": "Viewer", "org_count": 1}


@pytest.mark.parametrize(
    "status,payload,message",
    [
        (401, [], "organization memberships"),
        (200, [], "no organization memberships"),
        (200, [{"orgId": 1, "name": "Main Org."}], "invalid organization membership"),
        (200, [{"orgId": 1, "name": "Main Org.", "role": "Editor"}], "expected Viewer"),
        (
            200,
            [{"orgId": 1, "name": "Main Org.", "role": "Viewer"}, {"orgId": 2, "role": "Admin"}],
            "elevated organization access",
        ),
    ],
)
def test_grafana_org_membership_rejects_missing_wrong_or_elevated_roles(
    status: int, payload: object, message: str
) -> None:
    with pytest.raises(MODULE.VerificationError, match=message):
        MODULE.verify_grafana_org_memberships(status, payload)


def test_grafana_org_membership_can_verify_operator_workspace_admin_role() -> None:
    result = MODULE.verify_grafana_org_memberships(
        200,
        [{"orgId": 1, "name": "Main Org.", "role": "Admin"}],
        expected_role="Admin",
    )

    assert result == {"org_role": "Admin", "org_count": 1}


def test_browser_contract_keeps_tls_strict_and_checks_workspace_membership() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")

    assert "ignore_https_errors=True" not in source
    assert "--ignore-certificate-errors" not in source
    assert 'OAUTH_PATH = "/login/generic_oauth"' in source
    assert 'USER_API_PATH = "/api/user"' in source
    assert 'USER_ORGS_API_PATH = "/api/user/orgs"' in source
    assert "verify_grafana_org_memberships" in source
    assert 'membership.get("role")' in source
    assert "Grafana OAuth callback status" in source
    assert "diagnostics redacted" in source
    assert "status: response.status" in source
    assert "expected-org-role" in source
