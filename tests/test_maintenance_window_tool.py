from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import maintenance_window_tool as tool


def test_local_state_open_and_close(monkeypatch, tmp_path: Path):
    state_path = tmp_path / "maintenance-windows.json"
    monkeypatch.setenv(tool.MAINTENANCE_STATE_FILE_ENV, str(state_path))
    monkeypatch.setattr(tool, "emit_mutation_audit_event", lambda *args, **kwargs: None)

    opened = tool.open_window(
        service_id="grafana",
        reason="planned restart",
        duration_minutes=15,
    )
    assert opened["status"] == "opened"
    assert opened["window"]["service_id"] == "grafana"

    windows = tool.list_active_windows()
    assert list(windows) == ["maintenance/grafana"]

    closed = tool.close_window(service_id="grafana")
    assert closed["status"] == "closed"
    assert closed["closed_count"] == 1
    assert tool.list_active_windows() == {}


def test_suppress_finding_for_maintenance_marks_service_finding_suppressed():
    finding = {
        "check": "check-service-health",
        "severity": "critical",
        "summary": "1 of 42 service probes failed.",
        "details": [
            {
                "probe_id": "grafana-readiness",
                "service_id": "grafana",
                "ok": False,
            }
        ],
        "ts": "2026-03-23T10:00:00Z",
        "run_id": "00000000-0000-0000-0000-000000000080",
    }
    windows = {
        "maintenance/grafana": {
            "window_id": "11111111-1111-1111-1111-111111111111",
            "service_id": "grafana",
            "reason": "deploy",
            "opened_by": {"class": "operator", "id": "ops-linux"},
            "opened_at": "2026-03-23T09:50:00Z",
            "expected_duration_minutes": 30,
            "auto_close_at": "2026-03-23T10:20:00Z",
            "correlation_id": "deploy:grafana",
        }
    }

    suppressed = tool.suppress_finding_for_maintenance(finding, windows)

    assert suppressed["severity"] == "suppressed"
    assert suppressed["original_severity"] == "critical"
    assert suppressed["suppressed"] is True
    assert suppressed["maintenance_windows"][0]["service_id"] == "grafana"


def test_suppress_finding_for_maintenance_does_not_hide_security_checks():
    finding = {
        "check": "check-certificate-expiry",
        "severity": "critical",
        "summary": "A certificate is expiring.",
        "details": [
            {
                "certificate_id": "proxmox-ui",
                "status": "expiring_soon",
            }
        ],
        "ts": "2026-03-23T10:00:00Z",
        "run_id": "00000000-0000-0000-0000-000000000081",
    }
    windows = {
        "maintenance/all": {
            "window_id": "22222222-2222-2222-2222-222222222222",
            "service_id": "all",
            "reason": "broad maintenance",
            "opened_by": {"class": "operator", "id": "ops-linux"},
            "opened_at": "2026-03-23T09:50:00Z",
            "expected_duration_minutes": 30,
            "auto_close_at": "2026-03-23T10:20:00Z",
            "correlation_id": "deploy:all",
        }
    }

    result = tool.suppress_finding_for_maintenance(finding, windows)

    assert result["severity"] == "critical"
    assert "suppressed" not in result


def test_status_page_maintenance_title_uses_service_name():
    service_catalog = {
        "keycloak": {"name": "Keycloak"},
    }
    window = {
        "service_id": "keycloak",
    }

    assert tool.status_page_maintenance_title(window, service_catalog) == "Planned maintenance: Keycloak"


def test_resolve_status_page_monitor_names_for_all_uses_status_page_catalog(monkeypatch):
    monkeypatch.setattr(
        tool,
        "load_status_page_monitor_names",
        lambda: ["Grafana Public", "Keycloak OIDC Discovery"],
    )

    monitor_names = tool.resolve_status_page_monitor_names({"service_id": "all"}, {})

    assert monitor_names == ["Grafana Public", "Keycloak OIDC Discovery"]


def test_build_alertmanager_silence_uses_service_matcher():
    window = tool.build_maintenance_window(
        service_id="grafana",
        reason="deploy",
        duration_minutes=10,
        opened_by_class="operator",
        opened_by_id="ops-linux",
    )

    silence = tool.build_alertmanager_silence(window)

    assert silence["matchers"] == [{"name": "service", "value": "grafana", "isRegex": False}]
    assert silence["comment"] == "Maintenance window: deploy"
