import json
from pathlib import Path

from scripts.runtime_assurance import build_runtime_assurance_report, validate_runtime_assurance_catalog


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def matrix_catalog() -> dict:
    return {
        "schema_version": "1.0.0",
        "dimensions": {
            "declared_runtime": {"title": "Declared Runtime", "description": "Runtime witness exists."},
            "health": {"title": "Health", "description": "Health evidence exists."},
            "route": {"title": "Route", "description": "Route evidence exists."},
            "tls": {"title": "TLS", "description": "TLS evidence exists."},
            "smoke": {"title": "Smoke", "description": "Smoke evidence exists."},
            "browser_journey": {"title": "Browser Journey", "description": "Browser evidence exists."},
            "log_queryability": {"title": "Log Queryability", "description": "Log evidence exists."},
        },
        "profiles": {
            "edge_browser_surface": {
                "title": "Edge Browser Surface",
                "description": "Interactive browser service",
                "dimension_classes": {
                    "declared_runtime": "required",
                    "health": "required",
                    "route": "required",
                    "tls": "required",
                    "smoke": "required",
                    "browser_journey": "required",
                    "log_queryability": "best_effort",
                },
            },
            "private_service": {
                "title": "Private Service",
                "description": "Private service",
                "dimension_classes": {
                    "declared_runtime": "required",
                    "health": "required",
                    "route": "required",
                    "tls": "n_a",
                    "smoke": "required",
                    "browser_journey": "n_a",
                    "log_queryability": "best_effort",
                },
            },
            "edge_informational_surface": {
                "title": "Edge Informational Surface",
                "description": "Informational edge service",
                "dimension_classes": {
                    "declared_runtime": "required",
                    "health": "required",
                    "route": "required",
                    "tls": "required",
                    "smoke": "best_effort",
                    "browser_journey": "n_a",
                    "log_queryability": "best_effort",
                },
            },
        },
        "default_profile_by_exposure": {
            "edge-published": "edge_browser_surface",
            "edge-static": "edge_informational_surface",
            "informational-only": "edge_informational_surface",
            "private-only": "private_service",
        },
        "service_overrides": {},
        "freshness_days_by_dimension": {
            "smoke": 30,
            "browser_journey": 30,
            "log_queryability": 45,
        },
    }


def test_validate_runtime_assurance_catalog_uses_supplied_environment_topology() -> None:
    catalog = matrix_catalog()
    service_catalog = {
        "services": [
            {
                "id": "preview_console",
                "name": "Preview Console",
                "lifecycle_status": "active",
                "exposure": "edge-published",
                "environments": {
                    "qa": {
                        "status": "active",
                        "url": "https://preview.qa.example.test",
                        "subdomain": "preview.qa.example.test",
                    }
                },
            }
        ]
    }
    environment_topology = {
        "schema_version": "1.0.0",
        "environments": [{"id": "qa", "name": "QA", "status": "active"}],
    }

    validate_runtime_assurance_catalog(
        catalog,
        service_catalog=service_catalog,
        environment_topology=environment_topology,
    )


def test_build_runtime_assurance_report_matches_browser_and_log_receipts(tmp_path: Path) -> None:
    write_json(
        tmp_path / "receipts" / "live-applies" / "2026-03-29-ops-portal-runtime-assurance.json",
        {
            "receipt_id": "receipt-ops-portal-runtime-assurance",
            "summary": "Applied ops_portal production browser smoke and logs verification",
            "workflow_id": "live-apply-service service=ops_portal env=production",
            "recorded_on": "2026-03-29T10:15:00Z",
            "verification": [
                {"check": "smoke test", "observed": "Smoke test passed", "result": "pass"},
                {"check": "browser journey", "observed": "Playwright sign-in and logout completed", "result": "pass"},
                {"check": "log query", "observed": "Grafana logs query through Loki succeeded", "result": "pass"},
            ],
            "notes": [
                "Playwright sign-in and logout completed for ops_portal.",
                "Grafana logs query through Loki succeeded for ops_portal.",
            ],
        },
    )

    report = build_runtime_assurance_report(
        repo_root=tmp_path,
        catalog=matrix_catalog(),
        service_catalog={
            "services": [
                {
                    "id": "ops_portal",
                    "name": "Platform Operations Portal",
                    "lifecycle_status": "active",
                    "exposure": "edge-published",
                    "public_url": "https://ops.lv3.org",
                    "runbook": "docs/runbooks/platform-operations-portal.md",
                    "adr": "0244",
                    "environments": {
                        "production": {
                            "status": "active",
                            "url": "https://ops.lv3.org",
                            "subdomain": "ops.lv3.org",
                        }
                    },
                }
            ]
        },
        environment_topology={
            "schema_version": "1.0.0",
            "environments": [{"id": "production", "name": "Production", "status": "active"}],
        },
        publication_registry={
            "schema_version": "2.0.0",
            "publications": [
                {
                    "fqdn": "ops.lv3.org",
                    "service_id": "ops_portal",
                    "environment": "production",
                    "status": "active",
                    "publication": {
                        "delivery_model": "shared-edge",
                        "access_model": "platform-sso",
                        "audience": "operator",
                    },
                    "adapter": {
                        "tls": {
                            "provider": "letsencrypt",
                            "cert_path": "/etc/letsencrypt/live/lv3-edge/fullchain.pem",
                        }
                    },
                }
            ],
        },
        health_payload={
            "services": [
                {
                    "service_id": "ops_portal",
                    "status": "healthy",
                    "composite_status": "healthy",
                    "reason": "Portal runtime answered the governed health composite.",
                    "computed_at": "2026-03-29T10:20:00Z",
                }
            ]
        },
    )

    assert report["summary"] == {"total": 1, "pass": 1, "degraded": 0, "failed": 0, "unknown": 0}
    entry = report["entries"][0]
    assert entry["service_id"] == "ops_portal"
    assert entry["overall_status"] == "pass"
    browser_dimension = next(item for item in entry["dimensions"] if item["id"] == "browser_journey")
    log_dimension = next(item for item in entry["dimensions"] if item["id"] == "log_queryability")
    assert browser_dimension["status"] == "pass"
    assert log_dimension["status"] == "pass"
