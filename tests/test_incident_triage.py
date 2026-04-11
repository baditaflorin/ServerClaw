from __future__ import annotations

import json
import sys
from pathlib import Path

import incident_triage


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def write_yaml(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def configure_repo(monkeypatch, tmp_path: Path) -> None:
    write_json(
        tmp_path / "config" / "service-capability-catalog.json",
        {
            "services": [
                {
                    "id": "netbox",
                    "name": "NetBox",
                    "vm": "docker-runtime-lv3",
                    "public_url": "https://netbox.lv3.org",
                }
            ]
        },
    )
    write_json(
        tmp_path / "config" / "certificate-catalog.json",
        {
            "certificates": [
                {
                    "id": "netbox-edge",
                    "service_id": "netbox",
                    "material": {"not_after": "2026-03-30T00:00:00Z"},
                }
            ]
        },
    )
    write_json(
        tmp_path / "config" / "dependency-graph.json",
        {
            "nodes": [{"id": "postgres"}, {"id": "netbox"}],
            "edges": [{"from": "postgres", "to": "netbox", "kind": "database"}],
        },
    )
    write_yaml(
        tmp_path / "config" / "triage-rules.yaml",
        """
schema_version: "1.0.0"
rule_table_version: "0.1.0"
rules:
  - id: recent-deployment-regression
    description: recent deploy
    conditions:
      all:
        - signal: service_health_probe_failing
          value: true
        - signal: recent_deployment_within_2h
          value: true
    hypothesis: Recent deploy broke {{ affected_service }}
    confidence: 0.85
    discriminating_checks:
      - type: log_query
        query: 'service="{{ affected_service }}" error'
        window: 15m
    cheapest_first_action: Review deployment receipt for {{ deployment_actor }}
    auto_check: false
  - id: tls-cert-expiry
    description: cert expiry
    conditions:
      all:
        - signal: service_health_probe_failing
          value: true
        - signal: tls_cert_expiry_days
          lte: 7
    hypothesis: TLS expiry broke {{ affected_service }}
    confidence: 0.9
    discriminating_checks:
      - type: cert_check
        target: "{{ affected_service }}"
    cheapest_first_action: Renew cert for {{ affected_service }}
    auto_check: true
""".strip()
        + "\n",
    )
    write_yaml(
        tmp_path / "config" / "triage-auto-check-allowlist.yaml",
        """
schema_version: "1.0.0"
allowed_check_types:
  - cert_check
  - log_query
""".strip()
        + "\n",
    )
    write_json(
        tmp_path / "receipts" / "live-applies" / "2026-03-24-netbox.json",
        {
            "receipt_id": "r-1",
            "recorded_by": "codex/adr-0113-workstream",
            "summary": "netbox deploy",
            "applied_on": "2026-03-24T11:00:00Z",
        },
    )
    audit_path = tmp_path / ".local" / "state" / "mutation-audit" / "mutation-audit.jsonl"
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(
        json.dumps(
            {
                "ts": "2026-03-24T11:10:00Z",
                "actor": {"class": "agent", "id": "codex"},
                "surface": "manual",
                "action": "drift.detected",
                "target": "service:netbox",
                "outcome": "success",
                "correlation_id": "drift-1",
                "evidence_ref": "",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(incident_triage, "RULES_PATH", tmp_path / "config" / "triage-rules.yaml")
    monkeypatch.setattr(
        incident_triage, "AUTO_CHECK_ALLOWLIST_PATH", tmp_path / "config" / "triage-auto-check-allowlist.yaml"
    )
    monkeypatch.setattr(
        incident_triage, "SERVICE_CATALOG_PATH", tmp_path / "config" / "service-capability-catalog.json"
    )
    monkeypatch.setattr(incident_triage, "CERTIFICATE_CATALOG_PATH", tmp_path / "config" / "certificate-catalog.json")
    monkeypatch.setattr(incident_triage, "DEPENDENCY_GRAPH_PATH", tmp_path / "config" / "dependency-graph.json")
    monkeypatch.setattr(incident_triage, "LIVE_APPLY_RECEIPTS_DIR", tmp_path / "receipts" / "live-applies")
    monkeypatch.setenv("LV3_MUTATION_AUDIT_FILE", str(audit_path))
    monkeypatch.setattr(
        incident_triage,
        "utc_now",
        lambda: incident_triage.parse_timestamp("2026-03-24T12:00:00Z"),
    )


def test_build_report_prefers_recent_deployment_rule(monkeypatch, tmp_path: Path) -> None:
    configure_repo(monkeypatch, tmp_path)

    report = incident_triage.build_report(
        {
            "service_id": "netbox",
            "alert_name": "netbox_health_probe_failed",
            "status": "firing",
            "logs": [{"line": "ERROR startup failed", "labels": {"level": "error"}}],
            "certificate": {"tls_cert_expiry_days": 14},
        }
    )

    assert report["affected_service"] == "netbox"
    assert report["hypotheses"][0]["id"] == "recent-deployment-regression"
    assert report["signal_set"]["recent_deployment_within_2h"] is True
    assert report["signal_set"]["deployment_actor"] == "codex/adr-0113-workstream"


def test_build_report_ignores_unreadable_receipts(monkeypatch, tmp_path: Path) -> None:
    configure_repo(monkeypatch, tmp_path)
    invalid_receipt = tmp_path / "receipts" / "live-applies" / "2026-03-24-invalid.json"
    invalid_receipt.write_bytes(b'{"receipt_id":"broken","\xa3":1}\n')

    report = incident_triage.build_report(
        {
            "service_id": "netbox",
            "alert_name": "netbox_health_probe_failed",
            "status": "firing",
            "logs": [{"line": "ERROR startup failed", "labels": {"level": "error"}}],
            "certificate": {"tls_cert_expiry_days": 14},
        }
    )

    assert report["hypotheses"][0]["id"] == "recent-deployment-regression"
    assert report["signal_set"]["recent_deployment_within_2h"] is True


def test_build_report_runs_allowlisted_auto_check(monkeypatch, tmp_path: Path) -> None:
    configure_repo(monkeypatch, tmp_path)

    report = incident_triage.build_report(
        {
            "service_id": "netbox",
            "alert_name": "netbox_health_probe_failed",
            "status": "firing",
            "certificate": {"tls_cert_expiry_days": 3},
            "logs": [],
        }
    )

    assert report["hypotheses"][0]["id"] == "tls-cert-expiry"
    assert report["auto_check_result"]["status"] == "executed"
    assert report["auto_check_result"]["type"] == "cert_check"


def test_emit_triage_report_writes_report_and_audit(monkeypatch, tmp_path: Path) -> None:
    configure_repo(monkeypatch, tmp_path)
    report = incident_triage.build_report(
        {
            "service_id": "netbox",
            "alert_name": "netbox_health_probe_failed",
            "status": "firing",
            "certificate": {"tls_cert_expiry_days": 3},
            "logs": [],
        }
    )

    captured = {}

    def fake_emit(event, *, context, stderr=sys.stderr, file_path=None, loki_url=None, loki_labels=None):
        captured["event"] = event
        captured["context"] = context
        return True

    monkeypatch.setattr(incident_triage, "emit_event_best_effort", fake_emit)
    result = incident_triage.emit_triage_report(
        report, emit_audit=True, mattermost_webhook_url=None, report_dir=tmp_path / "reports"
    )

    written = Path(result["report_path"])
    assert written.exists()
    assert captured["event"]["action"] == "triage.report_created"
    assert result["mattermost_posted"] is False


def test_build_report_adds_web_search_references_for_unclassified_incident(monkeypatch, tmp_path: Path) -> None:
    configure_repo(monkeypatch, tmp_path)
    captured: dict[str, str] = {}

    def fake_search(query: str, *, max_results: int = 3):
        captured["query"] = query
        return [{"title": "Known bug", "url": "https://example.com/issue", "content": "match"}]

    monkeypatch.setattr(incident_triage, "search_web_references", fake_search)

    report = incident_triage.build_report(
        {
            "service_id": "netbox",
            "alert_name": "netbox_unknown_failure",
            "status": "resolved",
            "logs": [{"line": "fatal redirect_uri mismatch during startup", "labels": {"level": "error"}}],
        }
    )

    assert report["hypotheses"][0]["id"] == "unclassified-incident"
    assert report["web_search_references"][0]["url"] == "https://example.com/issue"
    assert "redirect_uri mismatch" in captured["query"]
