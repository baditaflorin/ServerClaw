from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "token_lifecycle.py"
SPEC = importlib.util.spec_from_file_location("token_lifecycle", SCRIPT_PATH)
token_lifecycle = importlib.util.module_from_spec(SPEC)
assert SPEC is not None
assert SPEC.loader is not None
sys.modules[SPEC.name] = token_lifecycle
SPEC.loader.exec_module(token_lifecycle)


def write_json_yaml(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def make_policy(path: Path) -> Path:
    return write_json_yaml(
        path,
        {
            "schema_version": "1.0.0",
            "token_classes": [
                {
                    "class": "windmill_api_token",
                    "max_ttl_days": 30,
                    "warning_window_days": 7,
                    "enforcement_grace_days": 7,
                    "rotation_trigger": "scheduled_monthly",
                    "storage": "openbao",
                    "revocation_workflow": "rotate-windmill-token",
                    "on_exposure": "immediate_revocation",
                },
                {
                    "class": "platform_cli_token",
                    "max_ttl_days": 7,
                    "warning_window_days": 1,
                    "enforcement_grace_days": 0,
                    "rotation_trigger": "automatic_at_expiry",
                    "storage": "local_keychain",
                    "revocation_workflow": "rotate-platform-cli-token",
                    "on_exposure": "immediate_revocation_plus_session_invalidation",
                },
            ],
        },
    )


def make_hook_script(path: Path) -> Path:
    path.write_text(
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "import json",
                "import sys",
                "from pathlib import Path",
                "action = sys.argv[1]",
                "token_id = sys.argv[2]",
                "log_path = Path(sys.argv[3])",
                "log_path.parent.mkdir(parents=True, exist_ok=True)",
                "with log_path.open('a', encoding='utf-8') as handle:",
                "    handle.write(f'{action}:{token_id}\\n')",
                "payload = {'action': action, 'token_id': token_id}",
                "if action == 'audit_usage':",
                "    payload['earliest_use'] = '2026-03-20T00:00:00Z'",
                "if action == 'rotate':",
                "    payload['new_token_issued'] = True",
                "if action == 'revoke':",
                "    payload['revoked'] = True",
                "if action == 'invalidate_sessions':",
                "    payload['sessions_invalidated'] = True",
                "print(json.dumps(payload))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def make_inventory(path: Path, hook_script: Path, log_path: Path) -> Path:
    return write_json_yaml(
        path,
        {
            "schema_version": "1.0.0",
            "tokens": [
                {
                    "id": "windmill-stale-token",
                    "token_class": "windmill_api_token",
                    "owner_service": "windmill",
                    "subject": "windmill-superadmin",
                    "issued_at": "2026-02-01T00:00:00Z",
                    "storage_ref": "windmill_superadmin_secret",
                    "permissions": ["workspace_admin"],
                    "workflows": {
                        "rotate": "rotate-windmill-token",
                        "exposure_response": "token-exposure-response",
                    },
                    "hooks": {
                        "rotate": {
                            "kind": "command",
                            "command": ["python3", str(hook_script), "rotate", "{{ token_id }}", str(log_path)],
                        },
                        "revoke": {
                            "kind": "command",
                            "command": ["python3", str(hook_script), "revoke", "{{ token_id }}", str(log_path)],
                        },
                        "audit_usage": {
                            "kind": "command",
                            "command": ["python3", str(hook_script), "audit_usage", "{{ token_id }}", str(log_path)],
                        },
                    },
                },
                {
                    "id": "platform-cli-token",
                    "token_class": "platform_cli_token",
                    "owner_service": "ops_portal",
                    "subject": "local-platform-cli",
                    "issued_at": "2026-03-24T00:00:00Z",
                    "storage_ref": ".config/lv3/token",
                    "permissions": ["gateway_api"],
                    "workflows": {
                        "rotate": "rotate-platform-cli-token",
                        "exposure_response": "token-exposure-response",
                    },
                    "hooks": {
                        "rotate": {
                            "kind": "command",
                            "command": ["python3", str(hook_script), "rotate", "{{ token_id }}", str(log_path)],
                        },
                        "revoke": {
                            "kind": "command",
                            "command": ["python3", str(hook_script), "revoke", "{{ token_id }}", str(log_path)],
                        },
                        "invalidate_sessions": {
                            "kind": "command",
                            "command": [
                                "python3",
                                str(hook_script),
                                "invalidate_sessions",
                                "{{ token_id }}",
                                str(log_path),
                            ],
                        },
                    },
                },
            ],
        },
    )


@pytest.fixture()
def token_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    policy_path = make_policy(tmp_path / "config" / "token-policy.yaml")
    hook_script = make_hook_script(tmp_path / "hook.py")
    inventory_path = make_inventory(tmp_path / "config" / "token-inventory.yaml", hook_script, tmp_path / "hook.log")
    ledger_path = tmp_path / ".local" / "state" / "ledger" / "ledger.events.jsonl"
    monkeypatch.setattr(token_lifecycle, "DEFAULT_LEDGER_FILE", ledger_path)
    return {
        "policy": policy_path,
        "inventory": inventory_path,
        "hook_log": tmp_path / "hook.log",
        "receipt_dir": tmp_path / "receipts" / "token-lifecycle",
        "incident_dir": tmp_path / "receipts" / "security-incidents",
        "ledger": ledger_path,
    }


def test_audit_reports_warning_and_expired_tokens(token_repo: dict[str, Path]) -> None:
    report = token_lifecycle.run_audit(
        policy_path=token_repo["policy"],
        inventory_path=token_repo["inventory"],
        receipt_dir=token_repo["receipt_dir"],
        now=token_lifecycle.parse_timestamp("2026-03-30T00:00:00Z"),
        execute_remediations=False,
        dry_run=True,
    )

    assert report["summary"]["total"] == 2
    assert report["summary"]["warning"] == 1
    assert report["summary"]["expired"] == 1
    assert (token_repo["receipt_dir"] / "20260330T000000Z-audit-token-inventory.json").is_file()


def test_audit_executes_rotation_hook_for_overdue_token(token_repo: dict[str, Path]) -> None:
    report = token_lifecycle.run_audit(
        policy_path=token_repo["policy"],
        inventory_path=token_repo["inventory"],
        receipt_dir=token_repo["receipt_dir"],
        now=token_lifecycle.parse_timestamp("2026-03-30T00:00:00Z"),
        execute_remediations=True,
        dry_run=False,
    )

    assert report["remediations"][0]["result"]["status"] == "ok"
    assert "rotate:windmill-stale-token" in token_repo["hook_log"].read_text(encoding="utf-8")
    ledger_lines = token_repo["ledger"].read_text(encoding="utf-8").splitlines()
    assert any('"event_type": "secret.rotated"' in line for line in ledger_lines)
    assert any('"event_type": "secret.audited"' in line for line in ledger_lines)


def test_exposure_response_executes_revoke_rotate_and_session_invalidation(token_repo: dict[str, Path]) -> None:
    report = token_lifecycle.run_exposure_response(
        token_id="platform-cli-token",
        policy_path=token_repo["policy"],
        inventory_path=token_repo["inventory"],
        incident_dir=token_repo["incident_dir"],
        now=token_lifecycle.parse_timestamp("2026-03-30T00:00:00Z"),
        exposure_source="git_diff",
        notes="token printed in debug output",
        dry_run=False,
    )

    assert report["status"] == "completed"
    assert (token_repo["incident_dir"] / f"{report['incident_id']}.json").is_file()
    hook_log = token_repo["hook_log"].read_text(encoding="utf-8")
    assert "revoke:platform-cli-token" in hook_log
    assert "rotate:platform-cli-token" in hook_log
    assert "invalidate_sessions:platform-cli-token" in hook_log


def test_exposure_response_blocks_when_revoke_hook_is_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    policy_path = make_policy(tmp_path / "config" / "token-policy.yaml")
    hook_script = make_hook_script(tmp_path / "hook.py")
    inventory_path = write_json_yaml(
        tmp_path / "config" / "token-inventory.yaml",
        {
            "schema_version": "1.0.0",
            "tokens": [
                {
                    "id": "platform-cli-token",
                    "token_class": "platform_cli_token",
                    "owner_service": "ops_portal",
                    "subject": "local-platform-cli",
                    "issued_at": "2026-03-24T00:00:00Z",
                    "storage_ref": ".config/lv3/token",
                    "workflows": {
                        "rotate": "rotate-platform-cli-token",
                        "exposure_response": "token-exposure-response",
                    },
                    "hooks": {
                        "rotate": {
                            "kind": "command",
                            "command": [
                                "python3",
                                str(hook_script),
                                "rotate",
                                "{{ token_id }}",
                                str(tmp_path / "hook.log"),
                            ],
                        }
                    },
                }
            ],
        },
    )
    ledger_path = tmp_path / ".local" / "state" / "ledger" / "ledger.events.jsonl"
    monkeypatch.setattr(token_lifecycle, "DEFAULT_LEDGER_FILE", ledger_path)

    report = token_lifecycle.run_exposure_response(
        token_id="platform-cli-token",
        policy_path=policy_path,
        inventory_path=inventory_path,
        incident_dir=tmp_path / "receipts" / "security-incidents",
        now=token_lifecycle.parse_timestamp("2026-03-30T00:00:00Z"),
        exposure_source="mattermost",
        dry_run=False,
    )

    assert report["status"] == "blocked"
    revocation_step = next(step for step in report["steps"] if step["id"] == "immediate-revocation")
    assert revocation_step["result"]["status"] == "blocked"
