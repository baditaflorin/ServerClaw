from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3

import pytest

import lv3_cli
import scripts.risk_scorer.context as risk_context
from scripts.risk_scorer import assemble_context, compile_workflow_intent, score_intent
from scripts.risk_scorer.dimensions import (
    criticality_score,
    failure_rate_score,
    fanout_score,
    maintenance_score,
    recency_score,
    rollback_score,
    surface_score,
)
from scripts.risk_scorer.engine import classify


@pytest.fixture()
def risk_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "config").mkdir()
    (tmp_path / "receipts" / "live-applies").mkdir(parents=True)

    (tmp_path / "config" / "service-capability-catalog.json").write_text(
        json.dumps(
            {
                "services": [
                    {
                        "id": "windmill",
                        "name": "Windmill",
                        "vm": "docker-runtime-lv3",
                        "lifecycle_status": "active",
                        "internal_url": "http://127.0.0.1:18081",
                        "environments": {"production": {"status": "active", "url": "http://127.0.0.1:18081"}},
                    },
                    {
                        "id": "proxmox_ui",
                        "name": "Proxmox UI",
                        "vm": "proxmox_florin",
                        "lifecycle_status": "active",
                        "public_url": "https://proxmox.lv3.org",
                        "category": "access",
                        "exposure": "informational-only",
                        "environments": {"production": {"status": "active", "url": "https://proxmox.lv3.org"}},
                    },
                    {
                        "id": "openbao",
                        "name": "OpenBao",
                        "vm": "docker-runtime-lv3",
                        "lifecycle_status": "active",
                        "internal_url": "https://10.10.10.20:8200",
                        "category": "security",
                        "environments": {"production": {"status": "active", "url": "https://10.10.10.20:8200"}},
                    },
                    {
                        "id": "uptime_kuma",
                        "name": "Uptime Kuma",
                        "vm": "docker-runtime-lv3",
                        "lifecycle_status": "active",
                        "public_url": "https://uptime.lv3.org",
                        "category": "observability",
                        "environments": {"production": {"status": "active", "url": "https://uptime.lv3.org"}},
                    },
                ]
            },
            indent=2,
        )
        + "\n"
    )
    (tmp_path / "config" / "workflow-catalog.json").write_text(
        json.dumps(
            {
                "workflows": {
                    "configure-network": {"description": "Configure host networking.", "live_impact": "host_live"},
                    "rotate-secret": {"description": "Rotate one managed secret.", "live_impact": "guest_live"},
                    "restart-uptime-kuma": {"description": "Restart Uptime Kuma.", "live_impact": "guest_live"},
                    "windmill_healthcheck": {"description": "Healthcheck.", "live_impact": "repo_only"},
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
                "nodes": [{"id": "openbao"}, {"id": "windmill"}],
                "edges": [{"from": "openbao", "to": "windmill"}],
            },
            indent=2,
        )
        + "\n"
    )
    (tmp_path / "config" / "secret-catalog.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "secrets": [
                    {"id": "openbao_controller_approle", "owner_service": "openbao"},
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
    (tmp_path / "config" / "risk-scoring-weights.yaml").write_text(
        """
version: 1.0.0
weights:
  target_criticality: 1.0
  dependency_fanout: 1.0
  historical_failure: 1.0
  mutation_surface: 1.0
  rollback_confidence: 1.0
  maintenance_window: 1.0
  active_incident: 1.0
  recency: 1.0
  stale_context_penalty: 1.0
classification_thresholds:
  low: 25
  medium: 50
  high: 75
approval_thresholds:
  auto_run_below: 25
  soft_gate_below: 50
  hard_gate_below: 75
  block_above: 75
defaults:
  expected_change_count: 5
  failure_lookback: 10
  hours_since_last_mutation_if_unknown: 72
  stale_context_penalty: 10
""".strip()
        + "\n"
    )
    (tmp_path / "config" / "risk-scoring-overrides.yaml").write_text(
        """
version: 1.0.0
default_host_service: proxmox_ui
service_tiers:
  proxmox_ui: critical
  openbao: critical
  uptime_kuma: medium
  windmill: low
downstream_count_fallbacks:
  proxmox_ui: 8
  openbao: 7
  uptime_kuma: 1
  windmill: 0
workflow_defaults:
  configure-network:
    target_service: proxmox_ui
    rollback_verified: false
    expected_change_count: 14
  rotate-secret:
    rollback_verified: false
    expected_change_count: 7
  restart-uptime-kuma:
    target_service: uptime_kuma
    rollback_verified: true
    expected_change_count: 2
active_incidents: []
recent_failure_rate_overrides: {}
""".strip()
        + "\n"
    )
    (tmp_path / "receipts" / "live-applies" / "2026-03-23-uptime.json").write_text(
        json.dumps(
            {
                "workflow_id": "restart-uptime-kuma",
                "recorded_on": "2026-03-23",
                "summary": "Restarted uptime kuma",
                "targets": [{"name": "uptime_kuma"}],
                "verification": [{"result": "pass"}],
            }
        )
        + "\n"
    )
    (tmp_path / "receipts" / "live-applies" / "2026-03-23-openbao-rotate.json").write_text(
        json.dumps(
            {
                "workflow_id": "rotate-secret",
                "recorded_on": "2026-03-23T12:00:00Z",
                "summary": "Rotated secret for openbao",
                "targets": [{"name": "openbao"}],
                "verification": [{"result": "pass"}],
            }
        )
        + "\n"
    )
    (tmp_path / "windmill-token.txt").write_text("secret-token\n")
    monkeypatch.setattr(lv3_cli, "REPO_ROOT", tmp_path)
    return tmp_path


def test_dimension_functions_cover_expected_ranges() -> None:
    assert criticality_score("critical") == 30.0
    assert fanout_score(0) == 0.0
    assert fanout_score(7) == 20.0
    assert failure_rate_score(0.5) == 7.5
    assert surface_score(2) == 2.0
    assert rollback_score(False) == 10.0
    assert maintenance_score(True) == -15.0
    assert recency_score(0.5) == 5.0


def test_classification_thresholds_are_stable() -> None:
    assert classify(24.9).value == "LOW"
    assert classify(25).value == "MEDIUM"
    assert classify(50).value == "HIGH"
    assert classify(75).value == "CRITICAL"


def test_stale_context_penalty_applies_when_overrides_are_missing(risk_repo: Path) -> None:
    intent = compile_workflow_intent(
        "rotate-secret",
        {"secret_id": "openbao_controller_approle"},
        repo_root=risk_repo,
    )
    fresh_context = assemble_context(intent, repo_root=risk_repo)
    fresh_score = score_intent(intent, fresh_context, repo_root=risk_repo)

    os.remove(risk_repo / "config" / "risk-scoring-overrides.yaml")
    stale_context = assemble_context(intent, repo_root=risk_repo)
    stale_score = score_intent(intent, stale_context, repo_root=risk_repo)

    assert stale_context.stale is True
    assert stale_score.dimension_breakdown["stale_context_penalty"] == 10.0
    assert "stale_context_penalty" not in fresh_score.dimension_breakdown


def test_maintenance_window_lowers_score(risk_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    intent = compile_workflow_intent("restart-uptime-kuma", {}, repo_root=risk_repo)
    outside_context = assemble_context(intent, repo_root=risk_repo)
    outside_score = score_intent(intent, outside_context, repo_root=risk_repo)

    monkeypatch.setattr(
        risk_context,
        "list_active_windows_best_effort",
        lambda: {
            "maintenance/all": {
                "service_id": "all",
                "reason": "planned restart",
            }
        },
    )
    inside_context = assemble_context(intent, repo_root=risk_repo)
    inside_score = score_intent(intent, inside_context, repo_root=risk_repo)

    assert inside_context.in_maintenance_window is True
    assert inside_score.score < outside_score.score


def test_graph_client_supplies_downstream_count_when_graph_dsn_is_set(
    risk_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph_path = risk_repo / "graph.sqlite3"
    connection = sqlite3.connect(graph_path)
    connection.execute(
        "CREATE TABLE graph_nodes (id TEXT PRIMARY KEY, kind TEXT NOT NULL, label TEXT NOT NULL, tier INTEGER, metadata TEXT NOT NULL)"
    )
    connection.execute(
        "CREATE TABLE graph_edges (id INTEGER PRIMARY KEY AUTOINCREMENT, from_node TEXT NOT NULL, to_node TEXT NOT NULL, edge_kind TEXT NOT NULL, metadata TEXT NOT NULL)"
    )
    connection.executemany(
        "INSERT INTO graph_nodes (id, kind, label, tier, metadata) VALUES (?, ?, ?, ?, ?)",
        [
            ("service:openbao", "service", "OpenBao", 1, '{"service_id":"openbao"}'),
            ("service:windmill", "service", "Windmill", 2, '{"service_id":"windmill"}'),
        ],
    )
    connection.execute(
        "INSERT INTO graph_edges (from_node, to_node, edge_kind, metadata) VALUES (?, ?, ?, ?)",
        ("service:windmill", "service:openbao", "depends_on", '{"source":"test"}'),
    )
    connection.commit()
    connection.close()
    monkeypatch.setenv("LV3_GRAPH_DSN", f"sqlite:///{graph_path}")

    intent = compile_workflow_intent(
        "rotate-secret",
        {"secret_id": "openbao_controller_approle"},
        repo_root=risk_repo,
    )
    context = assemble_context(intent, repo_root=risk_repo)

    assert context.downstream_count == 1


def test_lv3_run_dry_run_prints_compiled_intent(capsys: pytest.CaptureFixture[str], risk_repo: Path) -> None:
    exit_code = lv3_cli.main(["run", "windmill_healthcheck", "--dry-run"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Compiled intent:" in captured.out
    assert "risk_score:" in captured.out
    assert "<redacted>" in captured.out


def test_lv3_run_blocks_critical_workflow_without_override(capsys: pytest.CaptureFixture[str], risk_repo: Path) -> None:
    exit_code = lv3_cli.main(["run", "configure-network"])
    captured = capsys.readouterr()
    assert exit_code == 2
    assert "Risk gate BLOCK" in captured.err
