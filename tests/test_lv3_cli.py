from __future__ import annotations

import json
import sqlite3
import sys
import types
from pathlib import Path

import pytest

import lv3_cli
from platform.conflict import IntentConflictRegistry


def prepare_agent_state_db(path: Path) -> Path:
    connection = sqlite3.connect(path)
    connection.execute(
        """
        CREATE TABLE agent_state (
            state_id TEXT,
            agent_id TEXT NOT NULL,
            task_id TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            context_id TEXT,
            written_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            version INTEGER NOT NULL DEFAULT 1,
            UNIQUE(agent_id, task_id, key)
        )
        """
    )
    connection.commit()
    connection.close()
    return path


@pytest.fixture()
def minimal_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "config").mkdir()
    (tmp_path / "docs" / "adr").mkdir(parents=True)
    (tmp_path / "docs" / "runbooks").mkdir(parents=True)
    (tmp_path / "inventory").mkdir()
    (tmp_path / "receipts" / "live-applies").mkdir(parents=True)
    (tmp_path / "receipts" / "dr-table-top-reviews").mkdir(parents=True)
    (tmp_path / "tests" / "fixtures").mkdir(parents=True)
    (tmp_path / "versions").mkdir()
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "incident_triage.py").write_text(
        """
def build_report(payload):
    return {
        "affected_service": payload["service_id"],
        "hypotheses": [{"rank": 1, "id": "resource-exhaustion", "auto_check": True, "cheapest_first_action": "check pressure"}],
        "auto_check_result": {"status": "executed", "type": "metric_query"},
    }
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "Makefile").write_text(
        "\n".join(
            [
                "drift-report:",
                "remote-lint:",
                "remote-validate:",
                "remote-pre-push:",
                "remote-exec:",
                "rotate-secret:",
                "promote:",
                "capacity-report:",
                "fixture-up:",
                "fixture-down:",
                "fixture-list:",
                "",
            ]
        )
    )
    (tmp_path / "inventory" / "hosts.yml").write_text(
        """
all:
  children:
    lv3_guests:
      hosts:
        monitoring-lv3:
          ansible_host: 10.10.10.40
        docker-runtime-lv3:
          ansible_host: 10.10.10.20
        nginx-lv3:
          ansible_host: 10.10.10.10
        netbox-lv3:
          ansible_host: 10.10.10.30
""".strip()
        + "\n"
    )
    (tmp_path / "config" / "service-capability-catalog.json").write_text(
        json.dumps(
            {
                "services": [
                    {
                        "id": "grafana",
                        "name": "Grafana",
                        "vm": "monitoring-lv3",
                        "lifecycle_status": "active",
                        "internal_url": "http://127.0.0.1:18080/health",
                        "health_probe_id": "grafana",
                        "environments": {"production": {"status": "active", "url": "http://127.0.0.1:18080/health"}},
                    },
                    {
                        "id": "windmill",
                        "name": "Windmill",
                        "vm": "docker-runtime-lv3",
                        "lifecycle_status": "active",
                        "internal_url": "http://127.0.0.1:18081",
                        "health_probe_id": "windmill",
                        "environments": {"production": {"status": "active", "url": "http://127.0.0.1:18081"}},
                    },
                    {
                        "id": "ops_portal",
                        "name": "Ops Portal",
                        "vm": "nginx-lv3",
                        "lifecycle_status": "planned",
                        "public_url": "https://ops.lv3.org",
                        "environments": {"production": {"status": "planned", "url": "https://ops.lv3.org"}},
                    },
                    {
                        "id": "netbox",
                        "name": "NetBox",
                        "vm": "netbox-lv3",
                        "lifecycle_status": "active",
                        "internal_url": "http://127.0.0.1:18082",
                        "health_probe_id": "netbox",
                        "environments": {"production": {"status": "active", "url": "http://127.0.0.1:18082"}},
                    },
                ]
            },
            indent=2,
        )
        + "\n"
    )
    (tmp_path / "config" / "health-probe-catalog.json").write_text(
        json.dumps(
            {
                "services": {
                    "grafana": {"readiness": {"validate_tls": True}},
                    "windmill": {"readiness": {"validate_tls": True}},
                    "netbox": {"readiness": {"validate_tls": True}},
                }
            },
            indent=2,
        )
        + "\n"
    )
    (tmp_path / "config" / "dependency-graph.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "nodes": [
                    {
                        "id": "grafana",
                        "service": "grafana",
                        "name": "Grafana",
                        "vm": "monitoring-lv3",
                        "tier": 1,
                    },
                    {
                        "id": "windmill",
                        "service": "windmill",
                        "name": "Windmill",
                        "vm": "docker-runtime-lv3",
                        "tier": 2,
                    },
                    {
                        "id": "ops_portal",
                        "service": "ops_portal",
                        "name": "Ops Portal",
                        "vm": "nginx-lv3",
                        "tier": 1,
                    },
                    {
                        "id": "netbox",
                        "service": "netbox",
                        "name": "NetBox",
                        "vm": "netbox-lv3",
                        "tier": 1,
                    },
                ],
                "edges": [
                    {
                        "from": "windmill",
                        "to": "grafana",
                        "type": "hard",
                        "description": "Synthetic test edge.",
                    }
                ],
            },
            indent=2,
        )
        + "\n"
    )
    (tmp_path / "config" / "controller-local-secrets.json").write_text(
        json.dumps(
            {
                "secrets": {
                    "windmill_superadmin_secret": {"path": str(tmp_path / "windmill-token.txt")},
                }
            },
            indent=2,
        )
        + "\n"
    )
    (tmp_path / "config" / "workflow-catalog.json").write_text(
        json.dumps(
            {
                "workflows": {
                    "windmill_healthcheck": {"description": "Healthcheck"},
                    "operator-onboard": {"description": "Operator onboarding", "live_impact": "guest_live"},
                    "operator-offboard": {"description": "Operator offboarding", "live_impact": "guest_live"},
                    "converge-netbox": {"description": "NetBox converge", "live_impact": "guest_live"},
                    "disaster-recovery-runbook": {"description": "DR runbook"},
                    "validate": {"description": "Validate repository", "live_impact": "repo_only"},
                }
            },
            indent=2,
        )
        + "\n"
    )
    (tmp_path / "config" / "command-catalog.json").write_text(
        json.dumps(
            {
                "commands": {
                    "converge-netbox": {
                        "description": "Deploy the NetBox service.",
                        "workflow_id": "deploy-and-promote",
                    }
                }
            },
            indent=2,
        )
        + "\n"
    )
    (tmp_path / "config" / "disaster-recovery-targets.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "platform_target": {"rto_minutes": 240, "rpo_hours": 24},
                "review_policy": {"table_top_interval_days": 90, "live_drill_interval_days": 365},
                "offsite_backup": {"strategy": "vm160", "storage_id": "lv3-backup-offsite"},
                "scenarios": [
                    {"id": "host", "name": "Host loss", "rto_minutes": 240, "rpo_hours": 24, "notes": "restore vm160"}
                ],
            },
            indent=2,
        )
        + "\n"
    )
    (tmp_path / "versions" / "stack.yaml").write_text(
        """
repo_version: 0.96.0
platform_version: 0.40.0
backups:
  control_plane_recovery:
    latest_restore_drill:
      checked_at: 2026-03-23T08:00:00Z
      result: pass
""".strip()
        + "\n"
    )
    (tmp_path / "docs" / "adr" / "0093-interactive-ops-portal.md").write_text(
        "- Status: Proposed\n- Implementation Status: Not Implemented\n"
    )
    (tmp_path / "docs" / "adr" / "0094-developer-portal-and-documentation-site.md").write_text(
        "- Status: Proposed\n- Implementation Status: Not Implemented\n"
    )
    (tmp_path / "docs" / "adr" / "0109-public-status-page.md").write_text(
        "- Status: Proposed\n- Implementation Status: Not Implemented\n"
    )
    (tmp_path / "docs" / "runbooks" / "rotate-certificates.md").write_text(
        "# Rotate Certificates\n\nRenew the TLS certificate before it expires.\n"
    )
    (tmp_path / "receipts" / "dr-table-top-reviews" / "2026-03-23-review.json").write_text(
        json.dumps({"reviewed_on": "2026-03-23", "result": "completed_with_gaps"}) + "\n"
    )
    (tmp_path / "windmill-token.txt").write_text("secret-token\n")
    (tmp_path / "tests" / "fixtures" / "docker-host-fixture.yml").write_text("{}\n")
    (tmp_path / "receipts" / "live-applies" / "2026-03-23-grafana.json").write_text(
        json.dumps({"summary": "grafana deploy", "workflow_id": "converge-grafana"}) + "\n"
    )
    monkeypatch.setattr(lv3_cli, "REPO_ROOT", tmp_path)
    return tmp_path


def test_help_lists_command_groups(capsys: pytest.CaptureFixture[str], minimal_repo: Path) -> None:
    exit_code = lv3_cli.main(["--help"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "deploy" in captured.out
    assert "status" in captured.out
    assert "open" in captured.out
    assert "operator" in captured.out


def test_deploy_dry_run_prints_remote_exec_route(
    capsys: pytest.CaptureFixture[str], minimal_repo: Path
) -> None:
    exit_code = lv3_cli.main(["deploy", "grafana", "--dry-run"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "build server" in captured.out
    assert "make remote-exec" in captured.out
    assert "live-apply-service service=grafana env=production" in captured.out


def test_open_dry_run_uses_catalog_url(
    capsys: pytest.CaptureFixture[str], minimal_repo: Path
) -> None:
    exit_code = lv3_cli.main(["open", "ops_portal", "--dry-run"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "https://ops.lv3.org" in captured.out


def test_logs_dry_run_builds_loki_query(
    capsys: pytest.CaptureFixture[str], minimal_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LV3_LOKI_URL", "http://loki.example/query_range")
    exit_code = lv3_cli.main(["logs", "windmill", "--since", "2h", "--dry-run"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "http://loki.example/query_range" in captured.out
    assert "query=%7Bservice%3D%22windmill%22%7D" in captured.out


def test_run_dry_run_redacts_token(
    capsys: pytest.CaptureFixture[str], minimal_repo: Path
) -> None:
    exit_code = lv3_cli.main(["run", "windmill_healthcheck", "--args", "probe=manual", "--dry-run"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Compiled intent:" in captured.out
    assert "budgeted scheduler" in captured.out
    assert "<redacted>" in captured.out
    assert "secret-token" not in captured.out


def test_run_dry_run_compiles_natural_language_instruction(
    capsys: pytest.CaptureFixture[str], minimal_repo: Path
) -> None:
    exit_code = lv3_cli.main(["run", "deploy", "netbox", "--dry-run"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "Compiled Intent:" in captured.out
    assert "action: deploy" in captured.out
    assert "Dispatch Workflow: converge-netbox" in captured.out
    ledger_path = minimal_repo / ".local" / "state" / "ledger" / "ledger.events.jsonl"
    events = [json.loads(line) for line in ledger_path.read_text().splitlines()]
    assert events[-1]["event_type"] == "intent.compiled"


def test_run_parse_error_is_clean(
    capsys: pytest.CaptureFixture[str], minimal_repo: Path
) -> None:
    exit_code = lv3_cli.main(["run", "dploy", "netbox"])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "PARSE_ERROR" in captured.err
    ledger_path = minimal_repo / ".local" / "state" / "ledger" / "ledger.events.jsonl"
    events = [json.loads(line) for line in ledger_path.read_text().splitlines()]
    assert events[-1]["event_type"] == "intent.rejected"


def test_run_requires_approval_and_writes_lifecycle_events(
    minimal_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, dict[str, str]]] = []

    monkeypatch.setattr(lv3_cli, "prompt_for_intent_approval", lambda: True)
    monkeypatch.setattr(
        lv3_cli,
        "run_windmill_request",
        lambda workflow_name, payload, **_kwargs: calls.append((workflow_name, payload)) or 0,
    )

    exit_code = lv3_cli.main(["run", "deploy", "netbox"])

    assert exit_code == 0
    assert calls == [("converge-netbox", {"service": "netbox", "target": "netbox"})]
    ledger_path = minimal_repo / ".local" / "state" / "ledger" / "ledger.events.jsonl"
    event_types = [json.loads(line)["event_type"] for line in ledger_path.read_text().splitlines()]
    assert event_types == ["intent.compiled", "intent.approved"]


def test_intent_check_reports_clear_status(
    capsys: pytest.CaptureFixture[str], minimal_repo: Path
) -> None:
    exit_code = lv3_cli.main(["intent", "check", "deploy", "netbox"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "Resource claims:" in captured.out
    assert "Conflict check: CLEAR" in captured.out


def test_intent_check_reports_conflict(
    capsys: pytest.CaptureFixture[str], minimal_repo: Path
) -> None:
    registry = IntentConflictRegistry(repo_root=minimal_repo)
    registry.register_intent(
        {"workflow_id": "converge-netbox", "arguments": {"service": "netbox"}, "target_service_id": "netbox"},
        actor_intent_id="intent-existing",
        actor="agent:test",
        ttl_seconds=120,
    )

    exit_code = lv3_cli.main(["intent", "check", "deploy", "netbox"])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "Conflict check: CONFLICT" in captured.out
    assert "intent-existing" in captured.out


def test_vm_list_uses_inventory(
    capsys: pytest.CaptureFixture[str], minimal_repo: Path
) -> None:
    exit_code = lv3_cli.main(["vm", "list"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "monitoring-lv3" in captured.out
    assert "10.10.10.40" in captured.out


def test_completion_suggests_services(minimal_repo: Path) -> None:
    candidates = lv3_cli.completion_candidates(["lv3", "open"], "g")
    assert candidates == ["grafana"]


def test_loop_start_outputs_resolved_run(capsys: pytest.CaptureFixture[str], minimal_repo: Path) -> None:
    exit_code = lv3_cli.main(["loop", "start", "--trigger", "manual", "--service", "netbox"])
    captured = capsys.readouterr()

    assert exit_code == 0
    payload = json.loads(captured.out)
    assert payload["service_id"] == "netbox"
    assert payload["current_state"] == "RESOLVED"


def test_diff_dry_run_uses_drift_report_target(
    capsys: pytest.CaptureFixture[str], minimal_repo: Path
) -> None:
    exit_code = lv3_cli.main(["diff", "--env", "production", "--dry-run"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "make drift-report ENV=production" in captured.out


def test_fixture_list_dry_run_prints_make_target(
    capsys: pytest.CaptureFixture[str], minimal_repo: Path
) -> None:
    exit_code = lv3_cli.main(["fixture", "list", "--dry-run"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "make fixture-list" in captured.out


def test_capacity_dry_run_prints_make_target(
    capsys: pytest.CaptureFixture[str], minimal_repo: Path
) -> None:
    exit_code = lv3_cli.main(["capacity", "--format", "json", "--no-live-metrics", "--dry-run"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "make capacity-report FORMAT=json NO_LIVE_METRICS=true" in captured.out


def test_validate_service_dry_run_uses_local_completeness_command(
    capsys: pytest.CaptureFixture[str], minimal_repo: Path
) -> None:
    exit_code = lv3_cli.main(["validate", "--service", "grafana", "--dry-run"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "ADR 0107 completeness check" in captured.out
    assert "scripts/validate_service_completeness.py --service grafana" in captured.out


def test_search_command_returns_catalog_match(capsys: pytest.CaptureFixture[str], minimal_repo: Path) -> None:
    exit_code = lv3_cli.main(["search", "converge netbox", "--collection", "command_catalog"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "converge-netbox" in captured.out


def test_impact_command_prints_dependency_summary(
    capsys: pytest.CaptureFixture[str], minimal_repo: Path
) -> None:
    exit_code = lv3_cli.main(["impact", "windmill"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Service: Windmill" in captured.out
    assert "Hard: Grafana" in captured.out


def test_fixture_completion_suggests_fixture_names(minimal_repo: Path) -> None:
    candidates = lv3_cli.completion_candidates(["lv3", "fixture", "create", "d"], "d")
    assert candidates == ["docker-host"]


def test_fixture_create_dry_run_passes_lifecycle_parameters(
    capsys: pytest.CaptureFixture[str], minimal_repo: Path
) -> None:
    exit_code = lv3_cli.main(
        [
            "fixture",
            "create",
            "docker-host",
            "--purpose",
            "adr-0106-test",
            "--owner",
            "codex",
            "--lifetime-hours",
            "1",
            "--policy",
            "integration-test",
            "--dry-run",
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "make fixture-up" in captured.out
    assert "PURPOSE=adr-0106-test" in captured.out
    assert "OWNER=codex" in captured.out
    assert "LIFETIME_HOURS=1.0" in captured.out
    assert "EPHEMERAL_POLICY=integration-test" in captured.out


def test_fixture_destroy_dry_run_accepts_vmid(
    capsys: pytest.CaptureFixture[str], minimal_repo: Path
) -> None:
    exit_code = lv3_cli.main(["fixture", "destroy", "--vmid", "910", "--dry-run"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "make fixture-down" in captured.out
    assert "VMID=910" in captured.out

def test_release_status_is_forwarded_to_release_manager(
    minimal_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []

    fake_module = types.SimpleNamespace(main=lambda argv: calls.append(argv) or 0)
    monkeypatch.setitem(sys.modules, "release_manager", fake_module)

    exit_code = lv3_cli.main(["release", "status", "--json"])

    assert exit_code == 0
    assert calls == [["status", "--json"]]
    assert calls == [["status", "--json"]]


def test_operator_add_dry_run_uses_windmill_workflow(
    capsys: pytest.CaptureFixture[str], minimal_repo: Path
) -> None:
    exit_code = lv3_cli.main(
        [
            "operator",
            "add",
            "--name",
            "Alice Example",
            "--email",
            "alice@example.com",
            "--role",
            "operator",
            "--ssh-key",
            "@/tmp/alice.pub",
            "--dry-run",
        ]
    )
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "budgeted scheduler" in captured.out
    assert "operator-onboard" in captured.out
    assert "alice@example.com" in captured.out


def test_operator_inventory_dry_run_prints_local_script_route(
    capsys: pytest.CaptureFixture[str], minimal_repo: Path
) -> None:
    exit_code = lv3_cli.main(["operator", "inventory", "--id", "florin-badita", "--offline", "--dry-run"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "controller local operator access inventory" in captured.out
    assert "scripts/operator_access_inventory.py" in captured.out


def test_operator_add_viewer_dry_run_does_not_require_ssh_key(
    capsys: pytest.CaptureFixture[str], minimal_repo: Path
) -> None:
    exit_code = lv3_cli.main(
        [
            "operator",
            "add",
            "--name",
            "Viewer Example",
            "--email",
            "viewer@example.com",
            "--role",
            "viewer",
            "--dry-run",
        ]
    )
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "operator-onboard" in captured.out
    assert "viewer@example.com" in captured.out

def test_validate_completion_suggests_services(minimal_repo: Path) -> None:
    candidates = lv3_cli.completion_candidates(["lv3", "validate", "--service"], "g")
    assert candidates == ["grafana"]


def test_agent_state_show_prints_rows(
    capsys: pytest.CaptureFixture[str], minimal_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = prepare_agent_state_db(minimal_repo / "agent-state.sqlite3")
    client = lv3_cli.AgentStateClient(
        agent_id="agent/triage-loop",
        task_id="incident:inc-2026-03-24-001",
        dsn=f"sqlite:///{db_path}",
    )
    client.write("hypothesis.1", {"confidence": 0.85, "id": "recent-deployment"})
    monkeypatch.setenv("LV3_AGENT_STATE_DSN", f"sqlite:///{db_path}")

    exit_code = lv3_cli.main(
        [
            "agent",
            "state",
            "show",
            "--agent",
            "agent/triage-loop",
            "--task",
            "incident:inc-2026-03-24-001",
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "hypothesis.1" in captured.out
    assert "recent-deployment" in captured.out


def test_agent_state_delete_removes_key(
    capsys: pytest.CaptureFixture[str], minimal_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = prepare_agent_state_db(minimal_repo / "agent-state.sqlite3")
    client = lv3_cli.AgentStateClient(
        agent_id="agent/triage-loop",
        task_id="incident:inc-2026-03-24-001",
        dsn=f"sqlite:///{db_path}",
    )
    client.write("question_queue.1", {"question": "Rotate the password now?"})
    monkeypatch.setenv("LV3_AGENT_STATE_DSN", f"sqlite:///{db_path}")

    exit_code = lv3_cli.main(
        [
            "agent",
            "state",
            "delete",
            "--agent",
            "agent/triage-loop",
            "--task",
            "incident:inc-2026-03-24-001",
            "--key",
            "question_queue.1",
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "Deleted question_queue.1" in captured.out
    assert client.read("question_queue.1") is None


def test_agent_state_verify_reports_integrity_match(
    capsys: pytest.CaptureFixture[str], minimal_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = prepare_agent_state_db(minimal_repo / "agent-state.sqlite3")
    client = lv3_cli.AgentStateClient(
        agent_id="agent/runbook-executor",
        task_id="runbook-run:run-abc-123",
        dsn=f"sqlite:///{db_path}",
        checkpoint_publisher=None,
    )
    checkpoint = client.checkpoint({"resume_at": "verify-health"})
    monkeypatch.setenv("LV3_AGENT_STATE_DSN", f"sqlite:///{db_path}")

    exit_code = lv3_cli.main(
        [
            "agent",
            "state",
            "verify",
            "--agent",
            "agent/runbook-executor",
            "--task",
            "runbook-run:run-abc-123",
            "--digest",
            str(checkpoint["state_digest"]),
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "Integrity: ok" in captured.out
