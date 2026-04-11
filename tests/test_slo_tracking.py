import sys
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import generate_slo_rules  # noqa: E402
from slo_tracking import build_slo_status_entries, load_slo_catalog  # noqa: E402


def test_slo_catalog_loads_expected_entries() -> None:
    catalog = load_slo_catalog()
    assert len(catalog["slos"]) >= 9
    assert any(entry["indicator"] == "latency" for entry in catalog["slos"])
    assert any(entry["service_id"] == "homepage" for entry in catalog["slos"])


def test_generated_slo_assets_are_current() -> None:
    assert generate_slo_rules.outputs_match(load_slo_catalog())


def test_slo_status_entries_map_budget_to_health() -> None:
    def fake_query(expr: str) -> float:
        if expr.endswith(":budget_remaining"):
            return 0.62
        if expr.endswith(":burn_rate_1h"):
            return 0.8
        if expr.endswith(":time_to_budget_exhaustion_days"):
            return 23.4
        if ":success_ratio_" in expr:
            return 0.995
        raise AssertionError(expr)

    entries = build_slo_status_entries(query_fn=fake_query, prometheus_url="")
    assert entries
    assert entries[0]["metrics_available"] is True
    assert entries[0]["status"] == "healthy"


def test_slo_status_entries_include_latest_k6_receipt_signal(tmp_path: Path) -> None:
    (tmp_path / "config").mkdir(parents=True)
    (tmp_path / "versions").mkdir(parents=True)
    (tmp_path / "receipts" / "k6").mkdir(parents=True)
    (tmp_path / "config" / "slo-catalog.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "review_note": "test",
                "slos": [
                    {
                        "id": "keycloak-latency",
                        "service_id": "keycloak",
                        "indicator": "latency",
                        "objective_percent": 95.0,
                        "window_days": 30,
                        "target_url": "https://sso.example.com/realms/lv3/.well-known/openid-configuration",
                        "probe_module": "http_2xx_follow_redirects",
                        "latency_threshold_ms": 500,
                        "description": "Latency SLO",
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "config" / "service-capability-catalog.json").write_text(
        json.dumps(
            {
                "services": [
                    {
                        "id": "keycloak",
                        "name": "Keycloak",
                    },
                    {
                        "id": "grafana",
                        "name": "Grafana",
                        "public_url": "https://grafana.example.com",
                    },
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "versions" / "stack.yaml").write_text("platform_version: 0.0.1\nobserved_state: {}\n", encoding="utf-8")
    (tmp_path / "receipts" / "k6" / "load-keycloak-20260331T070000Z.json").write_text(
        json.dumps(
            {
                "service_id": "keycloak",
                "scenario": "load",
                "recorded_on": "2026-03-31",
                "recorded_at": "2026-03-31T07:00:00Z",
                "result": "passed",
                "metrics": {
                    "request_count": 40,
                    "error_rate": 0.0,
                    "http_req_duration_p95_ms": 210.0,
                    "http_req_duration_avg_ms": 120.0,
                },
                "slo_assessment": {
                    "error_budget_remaining_pct": 92.0,
                    "error_budget_consumed_pct": 8.0,
                    "latency_threshold_passed": True,
                },
                "regression": {
                    "checked": True,
                    "regressed": False,
                    "regression_ratio": 0.05,
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    entries = build_slo_status_entries(
        prometheus_url="",
        grafana_url="https://grafana.example.com",
        catalog_path=tmp_path / "config" / "slo-catalog.json",
        service_catalog_path=tmp_path / "config" / "service-capability-catalog.json",
        stack_path=tmp_path / "versions" / "stack.yaml",
    )

    assert entries[0]["k6"]["current_signal"]["scenario"] == "load"
    assert entries[0]["k6"]["current_signal"]["receipt_path"] == "receipts/k6/load-keycloak-20260331T070000Z.json"
    assert entries[0]["k6"]["current_signal"]["error_budget_remaining_pct"] == 92.0
