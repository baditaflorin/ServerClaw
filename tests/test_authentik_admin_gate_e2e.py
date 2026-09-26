from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = REPO_ROOT / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
SCRIPT_PATH = SCRIPT_DIR / "authentik_admin_gate_e2e.py"
SPEC = importlib.util.spec_from_file_location("authentik_admin_gate_e2e", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def valid_trace() -> dict[str, object]:
    return {
        "service": "repo-intake",
        "authorize_requests": [
            {
                "client_id": MODULE.SHARED_PROXY_CLIENT_ID,
                "redirect_host": "ops.example.com",
                "redirect_path": MODULE.CALLBACK_PATH,
            }
        ],
        "callback_responses": [{"status": 403, "host": "ops.example.com", "path": MODULE.CALLBACK_PATH}],
        "server_errors": [],
        "expected_callback_host": "ops.example.com",
    }


def test_non_admin_boundary_accepts_expected_shared_proxy_denial() -> None:
    result = MODULE.verify_admin_denial_trace(**valid_trace())

    assert result == {
        "status": "expected_denial",
        "service": "repo-intake",
        "provider_client_id": "ops-portal-oauth",
        "callback_path": "/oauth2/callback",
        "http_status": 403,
        "identity_is_non_admin": True,
        "server_errors": 0,
        "tls_validation": "enabled",
    }


@pytest.mark.parametrize(
    "field,replacement,message",
    [
        ("authorize_requests", [], "unexpected Authentik client or callback"),
        ("callback_responses", [], "not denied"),
        ("server_errors", [{"status": 502}], "server error"),
    ],
)
def test_non_admin_boundary_rejects_callback_mismatch_or_server_failure(
    field: str, replacement: list[dict[str, object]], message: str
) -> None:
    trace = valid_trace()
    trace[field] = replacement

    with pytest.raises(MODULE.VerificationError, match=message):
        MODULE.verify_admin_denial_trace(**trace)


def test_non_admin_identity_assertion_rejects_admin_group() -> None:
    with pytest.raises(MODULE.VerificationError, match="must not have an admin group"):
        MODULE.assert_non_admin_identity(
            {"users": [{"username": "gitea-e2e", "groups": ["gitea-users", "platform-admins"]}]},
            username="gitea-e2e",
        )


def test_browser_harness_redacts_oauth_query_values_and_enforces_tls() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")

    assert "ignore_https_errors=True" not in source
    assert "--ignore-certificate-errors" not in source
    assert "request.url" in source
    print_lines = [line.casefold() for line in source.splitlines() if "print(" in line]
    assert all("url" not in line and "state" not in line and "code" not in line for line in print_lines)


def test_authentik_identity_manifest_keeps_e2e_user_out_of_admin_groups() -> None:
    manifest = yaml.safe_load((REPO_ROOT / "config" / "authentik" / "test-identities.yaml").read_text())

    MODULE.assert_non_admin_identity(manifest, username="gitea-e2e")
