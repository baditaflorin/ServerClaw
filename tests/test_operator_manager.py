from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

import operator_manager
from platform.operator_access import TailscaleApiAdapter


TEST_KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOVJGGbg4OQjkLUMokPgKjl9LnBciBCgGHaWvTO3zxer test@example"


class FakeBackend:
    def ensure_prerequisites(self) -> dict[str, str]:
        return {"status": "ok"}

    def onboard_operator(self, operator: dict, bootstrap_password: str) -> dict:
        return {
            "keycloak": {"status": "active", "username": operator["keycloak"]["username"]},
            "openbao": {"status": "active", "entity_name": operator["openbao"]["entity_name"]},
            "step_ca": {"status": "ok", "principal": operator["ssh"]["principal"]},
            "tailscale": {"status": "ok", "login_email": operator["tailscale"]["login_email"]},
            "mattermost": {"status": "ok"},
            "audit": {"status": "ok"},
            "bootstrap_password": bootstrap_password,
        }

    def offboard_operator(self, operator: dict, reason: str | None) -> dict:
        return {
            "keycloak": {"status": "disabled", "username": operator["keycloak"]["username"]},
            "openbao": {"status": "disabled", "entity_name": operator["openbao"]["entity_name"]},
            "step_ca": {"status": "ok", "principal": operator["ssh"]["principal"]},
            "tailscale": {"status": "ok"},
            "mattermost": {"status": "ok"},
            "audit": {"status": "ok", "reason": reason or ""},
        }

    def recover_totp(self, operator: dict) -> dict:
        return {
            "keycloak": {
                "status": "totp-reset",
                "username": operator["keycloak"]["username"],
                "required_actions": ["CONFIGURE_TOTP"],
                "failure_counters_cleared": True,
            },
            "audit": {"status": "ok"},
        }

    def reset_password(self, operator: dict, password: str, *, temporary: bool) -> dict:
        return {
            "keycloak": {
                "status": "password-reset",
                "username": operator["keycloak"]["username"],
                "temporary": temporary,
                "required_actions": ["UPDATE_PASSWORD"] if temporary else [],
                "failure_counters_cleared": True,
            },
            "audit": {"status": "ok"},
        }

    def update_operator_notes(self, operator: dict, notes_markdown: str) -> dict:
        return {
            "status": "ok",
            "operator_id": operator["id"],
            "notes_present": bool(notes_markdown.strip()),
            "note_length": len(notes_markdown.strip()),
            "audit": {"status": "ok"},
        }

    def inventory_operator(self, operator: dict, state: dict, offline: bool) -> dict:
        return {"operator": operator, "state": state, "offline": offline}

    def quarterly_review(self, review: dict) -> dict:
        return {"status": "ok", "flagged_count": review["flagged_count"]}


@pytest.fixture()
def roster_paths(tmp_path: Path) -> tuple[Path, Path]:
    roster_path = tmp_path / "config" / "operators.yaml"
    roster_path.parent.mkdir(parents=True)
    roster_path.write_text(
        yaml.safe_dump(
            {
                "$schema": "config/schemas/operators.schema.json",
                "schema_version": "1.0.0",
                "operators": [],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    state_dir = tmp_path / ".local" / "state" / "operator-access"
    return roster_path, state_dir


def test_repo_operator_roster_validates() -> None:
    roster = yaml.safe_load(operator_manager.ROSTER_PATH.read_text(encoding="utf-8"))
    normalized = operator_manager.validate_operator_roster(roster)
    assert normalized["operators"][0]["id"] == "florin-badita"


def test_service_url_prefers_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LV3_OPENBAO_URL", "http://127.0.0.1:8201/")
    assert operator_manager.service_url("openbao") == "http://127.0.0.1:8201"


def test_onboard_writes_roster_and_state(roster_paths: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    roster_path, state_dir = roster_paths
    monkeypatch.setattr(operator_manager, "select_backend", lambda **kwargs: FakeBackend())

    payload = operator_manager.onboard(
        roster_path=roster_path,
        state_dir=state_dir,
        name="Alice Example",
        email="alice@example.com",
        role="operator",
        ssh_key=TEST_KEY,
        actor_id="tester",
        actor_class="operator",
        operator_id=None,
        keycloak_username=None,
        ssh_key_name="laptop",
        tailscale_login_email=None,
        tailscale_device_name="alice-mbp",
        bootstrap_password="Bootstrap123",
        dry_run=False,
    )

    saved = yaml.safe_load(roster_path.read_text(encoding="utf-8"))
    assert payload["operator"]["id"] == "alice-example"
    assert saved["operators"][0]["keycloak"]["username"] == "alice"
    state = json.loads((state_dir / "alice-example.json").read_text(encoding="utf-8"))
    assert state["keycloak"]["username"] == "alice"
    assert state["last_operation"] == "onboard"


def test_viewer_onboard_does_not_require_or_store_ssh_key(
    roster_paths: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    roster_path, state_dir = roster_paths
    monkeypatch.setattr(operator_manager, "select_backend", lambda **kwargs: FakeBackend())

    payload = operator_manager.onboard(
        roster_path=roster_path,
        state_dir=state_dir,
        name="Viewer Example",
        email="viewer@example.com",
        role="viewer",
        ssh_key="",
        actor_id="tester",
        actor_class="operator",
        operator_id=None,
        keycloak_username=None,
        ssh_key_name="laptop",
        tailscale_login_email=None,
        tailscale_device_name=None,
        bootstrap_password="Bootstrap123",
        dry_run=False,
    )

    assert payload["operator"]["ssh"]["public_keys"] == []
    saved = yaml.safe_load(roster_path.read_text(encoding="utf-8"))
    assert saved["operators"][0]["ssh"]["public_keys"] == []


def test_offboard_marks_operator_inactive(roster_paths: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    roster_path, state_dir = roster_paths
    monkeypatch.setattr(operator_manager, "select_backend", lambda **kwargs: FakeBackend())
    onboarded = operator_manager.onboard(
        roster_path=roster_path,
        state_dir=state_dir,
        name="Alice Example",
        email="alice@example.com",
        role="operator",
        ssh_key=TEST_KEY,
        actor_id="tester",
        actor_class="operator",
        operator_id=None,
        keycloak_username=None,
        ssh_key_name="laptop",
        tailscale_login_email=None,
        tailscale_device_name=None,
        bootstrap_password="Bootstrap123",
        dry_run=False,
    )

    payload = operator_manager.offboard(
        roster_path=roster_path,
        state_dir=state_dir,
        operator_id=onboarded["operator"]["id"],
        actor_id="tester",
        actor_class="operator",
        reason="contract ended",
        dry_run=False,
    )

    saved = yaml.safe_load(roster_path.read_text(encoding="utf-8"))
    operator = saved["operators"][0]
    assert operator["status"] == "inactive"
    assert operator["audit"]["offboarded_by"] == "tester"
    state = json.loads((state_dir / "alice-example.json").read_text(encoding="utf-8"))
    assert state["last_operation"] == "offboard"
    assert payload["result"]["keycloak"]["status"] == "disabled"


def test_recover_totp_persists_state(roster_paths: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    roster_path, state_dir = roster_paths
    monkeypatch.setattr(operator_manager, "select_backend", lambda **kwargs: FakeBackend())
    onboarded = operator_manager.onboard(
        roster_path=roster_path,
        state_dir=state_dir,
        name="Alice Example",
        email="alice@example.com",
        role="operator",
        ssh_key=TEST_KEY,
        actor_id="tester",
        actor_class="operator",
        operator_id=None,
        keycloak_username=None,
        ssh_key_name="laptop",
        tailscale_login_email=None,
        tailscale_device_name=None,
        bootstrap_password="Bootstrap123",
        dry_run=False,
    )

    payload = operator_manager.recover_totp(
        roster_path=roster_path,
        state_dir=state_dir,
        operator_id=onboarded["operator"]["id"],
        actor_id="tester",
        actor_class="operator",
        dry_run=False,
    )

    state = json.loads((state_dir / "alice-example.json").read_text(encoding="utf-8"))
    assert state["last_operation"] == "recover-totp"
    assert state["keycloak"]["status"] == "totp-reset"
    assert payload["result"]["keycloak"]["required_actions"] == ["CONFIGURE_TOTP"]


def test_reset_password_persists_state(roster_paths: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    roster_path, state_dir = roster_paths
    monkeypatch.setattr(operator_manager, "select_backend", lambda **kwargs: FakeBackend())
    onboarded = operator_manager.onboard(
        roster_path=roster_path,
        state_dir=state_dir,
        name="Alice Example",
        email="alice@example.com",
        role="operator",
        ssh_key=TEST_KEY,
        actor_id="tester",
        actor_class="operator",
        operator_id=None,
        keycloak_username=None,
        ssh_key_name="laptop",
        tailscale_login_email=None,
        tailscale_device_name=None,
        bootstrap_password="Bootstrap123",
        dry_run=False,
    )

    payload = operator_manager.reset_password(
        roster_path=roster_path,
        state_dir=state_dir,
        operator_id=onboarded["operator"]["id"],
        actor_id="tester",
        actor_class="operator",
        password="NewPassword123",
        temporary=True,
        dry_run=False,
    )

    state = json.loads((state_dir / "alice-example.json").read_text(encoding="utf-8"))
    assert state["last_operation"] == "reset-password"
    assert state["keycloak"]["status"] == "password-reset"
    assert payload["result"]["keycloak"]["required_actions"] == ["UPDATE_PASSWORD"]


def test_update_notes_persists_markdown_and_review_audit(
    roster_paths: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    roster_path, state_dir = roster_paths
    monkeypatch.setattr(operator_manager, "select_backend", lambda **kwargs: FakeBackend())
    onboarded = operator_manager.onboard(
        roster_path=roster_path,
        state_dir=state_dir,
        name="Alice Example",
        email="alice@example.com",
        role="operator",
        ssh_key=TEST_KEY,
        actor_id="tester",
        actor_class="operator",
        operator_id=None,
        keycloak_username=None,
        ssh_key_name="laptop",
        tailscale_login_email=None,
        tailscale_device_name=None,
        bootstrap_password="Bootstrap123",
        dry_run=False,
    )

    payload = operator_manager.update_notes(
        roster_path=roster_path,
        state_dir=state_dir,
        operator_id=onboarded["operator"]["id"],
        actor_id="reviewer",
        actor_class="operator",
        notes_markdown="## Shift handoff\n\n- Check `wiki.lv3.org`\n- [x] Review alerts",
        dry_run=False,
    )

    saved = yaml.safe_load(roster_path.read_text(encoding="utf-8"))
    operator = saved["operators"][0]
    assert operator["notes"] == "## Shift handoff\n\n- Check `wiki.lv3.org`\n- [x] Review alerts"
    assert operator["audit"]["last_reviewed_by"] == "reviewer"
    state = json.loads((state_dir / "alice-example.json").read_text(encoding="utf-8"))
    assert state["last_operation"] == "update-notes"
    assert payload["changed"] is True
    assert payload["result"]["notes_present"] is True


def test_update_notes_can_clear_existing_markdown(
    roster_paths: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    roster_path, state_dir = roster_paths
    monkeypatch.setattr(operator_manager, "select_backend", lambda **kwargs: FakeBackend())
    onboarded = operator_manager.onboard(
        roster_path=roster_path,
        state_dir=state_dir,
        name="Alice Example",
        email="alice@example.com",
        role="operator",
        ssh_key=TEST_KEY,
        actor_id="tester",
        actor_class="operator",
        operator_id=None,
        keycloak_username=None,
        ssh_key_name="laptop",
        tailscale_login_email=None,
        tailscale_device_name=None,
        bootstrap_password="Bootstrap123",
        dry_run=False,
    )
    operator_manager.update_notes(
        roster_path=roster_path,
        state_dir=state_dir,
        operator_id=onboarded["operator"]["id"],
        actor_id="reviewer",
        actor_class="operator",
        notes_markdown="Existing notes",
        dry_run=False,
    )

    payload = operator_manager.update_notes(
        roster_path=roster_path,
        state_dir=state_dir,
        operator_id=onboarded["operator"]["id"],
        actor_id="reviewer",
        actor_class="operator",
        notes_markdown="   \n",
        dry_run=False,
    )

    saved = yaml.safe_load(roster_path.read_text(encoding="utf-8"))
    assert "notes" not in saved["operators"][0]
    assert payload["result"]["notes_present"] is False


def test_quarterly_review_flags_stale_operator(
    roster_paths: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    roster_path, _state_dir = roster_paths
    monkeypatch.setattr(operator_manager, "select_backend", lambda **kwargs: FakeBackend())
    roster_path.write_text(
        yaml.safe_dump(
            {
                "$schema": "config/schemas/operators.schema.json",
                "schema_version": "1.0.0",
                "operators": [
                    {
                        "id": "alice-example",
                        "name": "Alice Example",
                        "email": "alice@example.com",
                        "role": "viewer",
                        "status": "active",
                        "keycloak": {
                            "username": "alice",
                            "realm_roles": ["platform-read"],
                            "groups": ["lv3-platform-viewers", "grafana-viewers"],
                            "enabled": True,
                        },
                        "ssh": {
                            "principal": "alice",
                            "certificate_ttl_hours": 24,
                            "public_keys": [],
                        },
                        "openbao": {
                            "entity_name": "alice",
                            "policies": ["platform-read"],
                        },
                        "tailscale": {
                            "login_email": "alice@example.com",
                            "tags": ["tag:platform-operator"],
                        },
                        "audit": {
                            "onboarded_at": "2026-03-01T00:00:00Z",
                            "onboarded_by": "tester",
                            "last_seen_at": "2026-01-01T00:00:00Z",
                        },
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    payload = operator_manager.quarterly_review(
        roster_path=roster_path,
        actor_id="tester",
        actor_class="operator",
        dry_run=False,
        warning_days=45,
        inactive_days=60,
    )

    assert payload["flagged_count"] == 1
    assert payload["operators"][0]["flagged"] is True


def test_live_backend_skips_tailscale_remove_when_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = TailscaleApiAdapter(
        api_key_loader=lambda: None,
        tailnet_loader=lambda: None,
        invite_endpoint_loader=lambda: "",
    )

    payload = adapter.remove(
        {
            "tailscale": {
                "login_email": "alice@example.com",
                "device_name": "alice-mbp",
            }
        }
    )

    assert payload["status"] == "skipped"
    assert "TAILSCALE_API_KEY or TAILSCALE_TAILNET" in payload["reason"]


def test_keycloak_bootstrap_password_prefers_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KEYCLOAK_BOOTSTRAP_PASSWORD", "EnvBootstrap123")

    assert operator_manager.load_keycloak_bootstrap_password() == "EnvBootstrap123"


def test_openbao_root_token_reads_env_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENBAO_INIT_JSON", json.dumps({"root_token": "s.test-root-token"}))

    assert operator_manager.load_openbao_root_token() == "s.test-root-token"
