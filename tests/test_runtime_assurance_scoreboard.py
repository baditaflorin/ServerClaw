from __future__ import annotations

from scripts.ops_portal.runtime_assurance import build_runtime_assurance_models


def test_runtime_assurance_builder_promotes_direct_receipt_evidence_to_pass() -> None:
    services = [
        {
            "id": "grafana",
            "name": "Grafana",
            "category": "observability",
            "lifecycle_status": "active",
            "vm": "monitoring",
            "public_url": "https://grafana.example.com",
            "subdomain": "grafana.example.com",
            "runbook": "docs/runbooks/monitoring-stack.md",
            "adr": "0011",
            "environments": {
                "production": {
                    "status": "active",
                    "url": "https://grafana.example.com",
                    "subdomain": "grafana.example.com",
                }
            },
        }
    ]
    publications = [
        {
            "service_id": "grafana",
            "environment": "production",
            "status": "active",
            "fqdn": "grafana.example.com",
            "publication": {"access_model": "upstream-auth"},
            "adapter": {"repo_route_service_id": "grafana", "tls": {"provider": "letsencrypt"}},
        }
    ]
    health_payload = {
        "services": [
            {
                "service_id": "grafana",
                "status": "healthy",
                "composite_status": "healthy",
                "reason": "healthy probe result",
                "computed_at": "2026-03-25T09:00:00Z",
                "signals": [
                    {
                        "name": "health_probe",
                        "value": "healthy",
                        "score": 1.0,
                        "weight": 0.4,
                        "reason": "healthy probe result",
                    }
                ],
            }
        ]
    }
    receipts = [
        {
            "receipt_id": "receipt-grafana",
            "_environment": "production",
            "_matched_services": ["grafana"],
            "_normalized_text": "grafana playwright login logout tls https certificate loki queryability smoke",
            "recorded_on": "2026-03-24T18:00:00Z",
            "verification": [{"check": "smoke", "result": "pass"}],
        }
    ]

    rows, summary = build_runtime_assurance_models(services, publications, health_payload, receipts)

    assert summary["pass_count"] == 1
    assert rows[0]["overall_state"] == "pass"
    by_dimension = {dimension["id"]: dimension for dimension in rows[0]["dimensions"]}
    assert by_dimension["existence"]["state"] == "pass"
    assert by_dimension["runtime_health"]["state"] == "pass"
    assert by_dimension["route_truth"]["state"] == "pass"
    assert by_dimension["auth_journey"]["state"] == "pass"
    assert by_dimension["tls_posture"]["state"] == "pass"
    assert by_dimension["log_queryability"]["state"] == "pass"
    assert by_dimension["smoke"]["state"] == "pass"


def test_runtime_assurance_builder_keeps_missing_proof_visible() -> None:
    services = [
        {
            "id": "keycloak",
            "name": "Keycloak",
            "category": "access",
            "lifecycle_status": "active",
            "vm": "docker-runtime",
            "public_url": "https://sso.example.com",
            "subdomain": "sso.example.com",
            "runbook": "docs/runbooks/configure-keycloak.md",
            "adr": "0056",
            "environments": {
                "production": {
                    "status": "active",
                    "url": "https://sso.example.com",
                    "subdomain": "sso.example.com",
                }
            },
        }
    ]
    publications = [
        {
            "service_id": "keycloak",
            "environment": "production",
            "status": "active",
            "fqdn": "sso.example.com",
            "publication": {"access_model": "upstream-auth"},
            "adapter": {"repo_route_service_id": "keycloak", "tls": {"provider": "letsencrypt"}},
        }
    ]
    health_payload = {
        "services": [
            {
                "service_id": "keycloak",
                "status": "degraded",
                "composite_status": "degraded",
                "reason": "open incident inc-1",
                "computed_at": "2026-03-25T09:00:00Z",
                "signals": [
                    {
                        "name": "health_probe",
                        "value": "degraded",
                        "score": 0.5,
                        "weight": 0.4,
                        "reason": "service probe is degraded",
                    }
                ],
            }
        ]
    }

    rows, summary = build_runtime_assurance_models(services, publications, health_payload, [])

    assert summary["pass_count"] == 0
    assert rows[0]["overall_state"] == "degraded"
    by_dimension = {dimension["id"]: dimension for dimension in rows[0]["dimensions"]}
    assert by_dimension["existence"]["state"] == "pass"
    assert by_dimension["runtime_health"]["state"] == "degraded"
    assert by_dimension["route_truth"]["state"] == "pass"
    assert by_dimension["auth_journey"]["state"] == "degraded"
    assert by_dimension["tls_posture"]["state"] == "degraded"
    assert by_dimension["log_queryability"]["state"] == "unknown"
    assert by_dimension["smoke"]["state"] == "unknown"


def test_runtime_assurance_builder_handles_missing_health_entry_without_crashing() -> None:
    services = [
        {
            "id": "ops_portal",
            "name": "Operations Portal",
            "category": "operations",
            "lifecycle_status": "active",
            "vm": "docker-runtime",
            "public_url": "https://ops.example.com",
            "subdomain": "ops.example.com",
            "runbook": "docs/runbooks/platform-operations-portal.md",
            "adr": "0235",
            "environments": {
                "production": {
                    "status": "active",
                    "url": "https://ops.example.com",
                    "subdomain": "ops.example.com",
                }
            },
        }
    ]
    publications = [
        {
            "service_id": "ops_portal",
            "environment": "production",
            "status": "active",
            "fqdn": "ops.example.com",
            "publication": {"access_model": "upstream-auth"},
            "adapter": {"repo_route_service_id": "ops_portal", "tls": {"provider": "letsencrypt"}},
        }
    ]
    health_payload = {"services": []}

    rows, summary = build_runtime_assurance_models(services, publications, health_payload, [])

    assert summary["unknown_count"] == 1
    assert rows[0]["overall_state"] == "unknown"
    by_dimension = {dimension["id"]: dimension for dimension in rows[0]["dimensions"]}
    assert by_dimension["existence"]["state"] == "unknown"
    assert by_dimension["runtime_health"]["state"] == "unknown"
    assert by_dimension["route_truth"]["state"] == "unknown"
    assert by_dimension["auth_journey"]["state"] == "unknown"
    assert by_dimension["tls_posture"]["state"] == "unknown"
    assert by_dimension["log_queryability"]["state"] == "unknown"
    assert by_dimension["smoke"]["state"] == "unknown"


def test_runtime_assurance_builder_uses_explicit_smoke_suite_override() -> None:
    services = [
        {
            "id": "ops_portal",
            "name": "Operations Portal",
            "category": "access",
            "lifecycle_status": "active",
            "vm": "docker-runtime",
            "public_url": "https://ops.example.com",
            "subdomain": "ops.example.com",
            "runbook": "docs/runbooks/ops-portal-down.md",
            "adr": "0251",
            "environments": {
                "production": {
                    "status": "active",
                    "url": "https://ops.example.com",
                    "subdomain": "ops.example.com",
                    "smoke_suites": [
                        {
                            "id": "portal-overview",
                            "name": "Portal overview",
                            "description": "Verify the overview partial renders.",
                            "required_verification_checks": ["runtime assurance", "smoke"],
                        }
                    ],
                }
            },
        }
    ]
    publications = [
        {
            "service_id": "ops_portal",
            "environment": "production",
            "status": "active",
            "fqdn": "ops.example.com",
            "publication": {"access_model": "upstream-auth"},
            "adapter": {"repo_route_service_id": "ops_portal", "tls": {"provider": "letsencrypt"}},
        }
    ]
    health_payload = {
        "services": [
            {
                "service_id": "ops_portal",
                "status": "healthy",
                "composite_status": "healthy",
                "reason": "healthy probe result",
                "computed_at": "2026-03-25T09:00:00Z",
                "signals": [
                    {
                        "name": "health_probe",
                        "value": "healthy",
                        "score": 1.0,
                        "weight": 0.4,
                        "reason": "healthy probe result",
                    }
                ],
            }
        ]
    }
    receipts = [
        {
            "receipt_id": "generic-smoke",
            "_environment": "production",
            "_matched_services": ["ops_portal"],
            "_normalized_text": "ops portal smoke",
            "recorded_at": "2026-03-25T11:00:00Z",
            "verification": [{"check": "Smoke", "result": "pass", "observed": "Generic smoke only."}],
        },
        {
            "receipt_id": "portal-overview",
            "_environment": "production",
            "_matched_services": ["ops_portal"],
            "_normalized_text": "ops portal runtime assurance smoke",
            "recorded_at": "2026-03-25T10:00:00Z",
            "verification": [
                {
                    "check": "Runtime assurance smoke",
                    "result": "pass",
                    "observed": "Overview rendered successfully.",
                }
            ],
        },
    ]

    rows, _summary = build_runtime_assurance_models(services, publications, health_payload, receipts)

    by_dimension = {dimension["id"]: dimension for dimension in rows[0]["dimensions"]}
    assert by_dimension["smoke"]["state"] == "pass"
    assert by_dimension["smoke"]["last_verified"] == "2026-03-25T10:00:00Z"
    assert "portal-overview" in by_dimension["smoke"]["detail"]
