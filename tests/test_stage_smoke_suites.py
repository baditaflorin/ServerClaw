from __future__ import annotations

import json
from pathlib import Path

import stage_smoke_suites


def write_repo_files(repo_root: Path, service_catalog: dict, smoke_catalog: dict) -> None:
    (repo_root / "config").mkdir(parents=True, exist_ok=True)
    (repo_root / "docs" / "schema").mkdir(parents=True, exist_ok=True)
    (repo_root / "config" / "service-capability-catalog.json").write_text(
        json.dumps(service_catalog, indent=2) + "\n",
        encoding="utf-8",
    )
    (repo_root / "config" / "stage-smoke-suites.json").write_text(
        json.dumps(smoke_catalog, indent=2) + "\n",
        encoding="utf-8",
    )
    (repo_root / "docs" / "schema" / "stage-smoke-suites.schema.json").write_text(
        (stage_smoke_suites.SCHEMA_PATH).read_text(encoding="utf-8"),
        encoding="utf-8",
    )


def test_validate_stage_smoke_catalog_rejects_cross_service_binding(tmp_path: Path) -> None:
    write_repo_files(
        tmp_path,
        {
            "services": [
                {
                    "id": "windmill",
                    "environments": {
                        "production": {
                            "status": "active",
                            "url": "http://windmill",
                            "stage_ready": True,
                            "smoke_suite_ids": ["production-api-gateway-operator-path"],
                        }
                    },
                },
                {
                    "id": "api_gateway",
                    "environments": {
                        "production": {
                            "status": "active",
                            "url": "https://api.lv3.org",
                        }
                    },
                },
            ]
        },
        {
            "$schema": "docs/schema/stage-smoke-suites.schema.json",
            "schema_version": "1.0.0",
            "suites": [
                {
                    "id": "production-api-gateway-operator-path",
                    "service_id": "api_gateway",
                    "environment": "production",
                    "description": "Gateway smoke.",
                    "runner": "integration_suite",
                    "mode": "gate",
                    "targets": ["tests/integration/test_platform_api.py::test_health_endpoint_reports_service_states"],
                }
            ],
        },
    )

    try:
        stage_smoke_suites.validate_stage_smoke_catalog(
            stage_smoke_suites.load_stage_smoke_catalog(tmp_path / "config" / "stage-smoke-suites.json"),
            stage_smoke_suites.load_service_catalog(tmp_path / "config" / "service-capability-catalog.json"),
        )
    except ValueError as exc:
        assert "owned by service 'api_gateway'" in str(exc)
    else:  # pragma: no cover - defensive
        raise AssertionError("expected cross-service smoke binding to fail")


def test_run_stage_smoke_suites_writes_aggregate_and_receipt_payload(monkeypatch, tmp_path: Path) -> None:
    write_repo_files(
        tmp_path,
        {
            "services": [
                {
                    "id": "windmill",
                    "environments": {
                        "production": {
                            "status": "active",
                            "url": "http://windmill",
                            "stage_ready": True,
                            "smoke_suite_ids": ["production-windmill-primary-path"],
                        }
                    },
                }
            ]
        },
        {
            "$schema": "docs/schema/stage-smoke-suites.schema.json",
            "schema_version": "1.0.0",
            "suites": [
                {
                    "id": "production-windmill-primary-path",
                    "service_id": "windmill",
                    "environment": "production",
                    "description": "Windmill smoke.",
                    "runner": "integration_suite",
                    "mode": "gate",
                    "targets": ["tests/integration/test_deployment.py::test_windmill_version_endpoint_reports_version"],
                    "required_service_ids": ["windmill"],
                }
            ],
        },
    )

    def fake_run_suite(**kwargs):
        assert kwargs["selection"] == ["tests/integration/test_deployment.py::test_windmill_version_endpoint_reports_version"]
        assert kwargs["required_service_ids"] == ["windmill"]
        return 0, {
            "status": "passed",
            "executed_at": "2026-03-29T12:00:00Z",
            "summary": {"passed": 1, "failed": 0, "skipped": 0, "total": 1},
            "targets": {"windmill_url": "http://windmill"},
            "tests": [],
        }

    monkeypatch.setattr(stage_smoke_suites.integration_suite, "run_suite", fake_run_suite)

    report_file = tmp_path / "receipts" / "live-applies" / "evidence" / "windmill-smoke.json"
    exit_code, payload = stage_smoke_suites.run_stage_smoke_suites(
        repo_root=tmp_path,
        suite_ids=["production-windmill-primary-path"],
        service_id="windmill",
        environment="production",
        report_file=report_file,
    )

    assert exit_code == 0
    assert payload["status"] == "passed"
    assert payload["receipt_smoke_suites"][0]["suite_id"] == "production-windmill-primary-path"
    assert report_file.exists()
