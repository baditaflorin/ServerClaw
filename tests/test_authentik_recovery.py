from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "authentik_recovery.py"
SPEC = importlib.util.spec_from_file_location("authentik_recovery", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class FakeAPI:
    def __init__(self, resources: dict[str, list[dict[str, Any]]]) -> None:
        self.resources = resources
        self.posts: list[tuple[str, dict[str, Any]]] = []

    def list_all(self, path: str) -> list[dict[str, Any]]:
        return self.resources[path]

    def post_no_content(self, path: str, payload: dict[str, Any]) -> int:
        self.posts.append((path, payload))
        return 204


def resources() -> dict[str, list[dict[str, Any]]]:
    return {
        MODULE.FLOW_INSTANCES_PATH: [
            {"pk": "flow-1", "slug": MODULE.DEFAULT_RECOVERY_FLOW_SLUG, "designation": "recovery"}
        ],
        MODULE.BRANDS_PATH: [{"pk": "brand-1", "default": True, "flow_recovery": "flow-1"}],
        MODULE.IDENTIFICATION_STAGES_PATH: [
            {
                "pk": "identification-1",
                "name": MODULE.DEFAULT_IDENTIFICATION_STAGE,
                "recovery_flow": "flow-1",
            }
        ],
        MODULE.EMAIL_STAGES_PATH: [{"pk": "email-1", "name": MODULE.DEFAULT_EMAIL_STAGE, "use_global_settings": True}],
        MODULE.USERS_PATH: [{"pk": 101, "email": "operator@example.com", "is_active": True, "type": "internal"}],
    }


def test_check_requires_flow_brand_login_and_global_smtp_bindings() -> None:
    result = MODULE.check_recovery_contract(FakeAPI(resources()))

    assert result == {
        "check": "authentik_recovery_flow",
        "result": "pass",
        "recovery_flow_present": True,
        "default_brand_bound": True,
        "login_recovery_link_bound": True,
        "global_smtp_enabled": True,
    }


def test_check_rejects_unbound_default_brand() -> None:
    state = resources()
    state[MODULE.BRANDS_PATH][0]["flow_recovery"] = "other-flow"

    with pytest.raises(MODULE.RecoveryError, match="default brand"):
        MODULE.check_recovery_contract(FakeAPI(state))


def test_send_email_uses_configured_operator_without_reporting_email(tmp_path: Path) -> None:
    identity_file = tmp_path / "identity.yml"
    identity_file.write_text("platform_operator_email: operator@example.com\n", encoding="utf-8")
    identity_file.chmod(0o600)
    api = FakeAPI(resources())

    result = MODULE.send_recovery_email(api, identity_file=identity_file)

    assert result == {
        "check": "authentik_recovery_email",
        "result": "accepted",
        "recipient": "platform_operator",
        "status": 204,
    }
    assert api.posts == [
        (
            f"{MODULE.USERS_PATH}101/recovery_email/",
            {"email_stage": "email-1"},
        )
    ]
    assert "operator@example.com" not in str(result)


def test_send_email_rejects_inactive_operator(tmp_path: Path) -> None:
    identity_file = tmp_path / "identity.yml"
    identity_file.write_text("platform_operator_email: operator@example.com\n", encoding="utf-8")
    identity_file.chmod(0o600)
    state = resources()
    state[MODULE.USERS_PATH][0]["is_active"] = False

    with pytest.raises(MODULE.RecoveryError, match="inactive"):
        MODULE.send_recovery_email(FakeAPI(state), identity_file=identity_file)


def test_send_email_rejects_a_non_private_identity_file(tmp_path: Path) -> None:
    identity_file = tmp_path / "identity.yml"
    identity_file.write_text("platform_operator_email: operator@example.com\n", encoding="utf-8")
    identity_file.chmod(0o644)

    with pytest.raises(MODULE.RecoveryError, match="must not be group- or world-readable"):
        MODULE.send_recovery_email(FakeAPI(resources()), identity_file=identity_file)
