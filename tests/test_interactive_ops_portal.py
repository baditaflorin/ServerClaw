from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from scripts.ops_portal.app import PortalSettings, create_app, normalize_health


class FakeGatewayClient:
    def __init__(self) -> None:
        self.platform_health_tokens: list[str | None] = []
        self.agent_coordination_tokens: list[str | None] = []
        self.runbook_fetch_tokens: list[str | None] = []
        self.service_health_calls: list[dict[str, object]] = []
        self.deploy_calls: list[dict[str, object]] = []
        self.secret_calls: list[str] = []
        self.runbook_calls: list[dict[str, object]] = []
        self.search_calls: list[dict[str, object]] = []

    async def fetch_platform_health(self, token: str | None = None) -> dict[str, object]:
        self.platform_health_tokens.append(token)
        return {
            "services": [
                {"service_id": "grafana", "status": "healthy", "detail": "Dashboards are green"},
                {"service_id": "ops_portal", "status": "healthy", "detail": "Portal runtime is ready"},
            ]
        }

    async def fetch_agent_coordination(self, token: str | None = None) -> dict[str, object]:
        self.agent_coordination_tokens.append(token)
        return {
            "summary": {
                "count": 2,
                "active": 1,
                "blocked": 1,
                "escalated": 0,
                "completing": 0,
                "generated_at": "2026-03-25T09:00:00Z",
            },
            "entries": [
                {
                    "agent_id": "agent/observation-loop",
                    "session_label": "observation-loop wm-job-1",
                    "current_phase": "executing",
                    "current_target": "service:grafana",
                    "current_workflow_id": "platform-observation-loop",
                    "status": "active",
                    "progress_pct": 0.5,
                    "held_locks": ["service:grafana"],
                    "held_lanes": [],
                    "last_heartbeat": "2026-03-25T09:00:00Z",
                    "started_at": "2026-03-25T08:58:00Z",
                },
                {
                    "agent_id": "agent/triage-loop",
                    "session_label": "triage-loop wm-job-2",
                    "current_phase": "blocked",
                    "current_target": "service:keycloak",
                    "status": "blocked",
                    "blocked_reason": "waiting for operator approval",
                    "held_locks": [],
                    "held_lanes": ["lane:identity"],
                    "last_heartbeat": "2026-03-25T09:00:00Z",
                    "started_at": "2026-03-25T08:57:30Z",
                },
            ],
        }

    async def fetch_service_health(self, service_id: str, token: str | None = None) -> dict[str, object]:
        self.service_health_calls.append({"service_id": service_id, "token": token})
        return {"service": service_id, "status": "healthy", "detail": f"{service_id} responded in 320ms"}

    async def trigger_deploy(
        self,
        service_id: str,
        *,
        token: str | None = None,
        restart_only: bool = False,
        source: str = "portal",
    ) -> dict[str, object]:
        self.deploy_calls.append(
            {"service_id": service_id, "restart_only": restart_only, "source": source, "token": token}
        )
        return {"job_id": "job-123", "message": "Deployment accepted by gateway"}

    async def rotate_secret(self, service_id: str, *, token: str | None = None) -> dict[str, object]:
        self.secret_calls.append(f"{service_id}:{token}")
        return {"message": "Secret rotation accepted by gateway"}

    async def fetch_runbooks(
        self,
        *,
        token: str | None = None,
        delivery_surface: str = "ops_portal",
    ) -> dict[str, object]:
        self.runbook_fetch_tokens.append(token)
        return {
            "runbooks": [
                {
                    "id": "validation-gate-status",
                    "title": "Inspect validation gate status",
                    "description": "Show the current validation-gate summary through the shared runbook service.",
                    "owner_runbook": "docs/runbooks/validation-gate-status.yaml",
                    "live_impact": "repo_only",
                    "execution_class": "diagnostic",
                }
            ]
        }

    async def launch_runbook(
        self,
        runbook_id: str,
        *,
        token: str | None = None,
        parameters: dict[str, object] | None = None,
    ) -> dict[str, object]:
        self.runbook_calls.append({"runbook_id": runbook_id, "parameters": parameters or {}, "token": token})
        return {"status": "completed", "message": "Runbook completed successfully"}

    async def search(
        self,
        query: str,
        *,
        collection: str | None = None,
        token: str | None = None,
        limit: int = 8,
    ) -> dict[str, object]:
        self.search_calls.append({"query": query, "collection": collection, "limit": limit, "token": token})
        return {
            "expanded_query": query,
            "results": [
                {
                    "title": "Rotate Certificates",
                    "collection": "runbooks",
                    "score": 0.91,
                    "url": "docs/runbooks/rotate-certificates.md",
                    "snippet": "Renew the TLS certificate before it expires.",
                }
            ],
        }


@pytest.fixture()
def portal_client(tmp_path: Path) -> tuple[TestClient, FakeGatewayClient]:
    data_root = tmp_path / "data"
    (data_root / "config").mkdir(parents=True)
    (data_root / "receipts" / "live-applies").mkdir(parents=True)
    (data_root / "receipts" / "drift-reports").mkdir(parents=True)

    (data_root / "config" / "service-capability-catalog.json").write_text(
        json.dumps(
            {
                "services": [
                    {
                        "id": "grafana",
                        "name": "Grafana",
                        "description": "Metrics and dashboards.",
                        "category": "observability",
                        "lifecycle_status": "active",
                        "public_url": "https://grafana.lv3.org",
                        "dashboard_url": "https://grafana.lv3.org/d/platform",
                        "runbook": "docs/runbooks/monitoring-stack.md",
                        "adr": "0011",
                    },
                    {
                        "id": "keycloak",
                        "name": "Keycloak",
                        "description": "Identity provider.",
                        "category": "access",
                        "lifecycle_status": "active",
                        "public_url": "https://sso.lv3.org",
                        "runbook": "docs/runbooks/configure-keycloak.md",
                        "adr": "0056",
                    },
                    {
                        "id": "ops_portal",
                        "name": "Platform Operations Portal",
                        "description": "Interactive control surface.",
                        "category": "access",
                        "lifecycle_status": "planned",
                        "public_url": "https://ops.lv3.org",
                        "internal_url": "http://10.10.10.20:8092",
                        "runbook": "docs/runbooks/ops-portal-down.md",
                        "adr": "0093",
                    },
                ]
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (data_root / "config" / "subdomain-exposure-registry.json").write_text(
        json.dumps(
            {
                "schema_version": "2.0.0",
                "zone_name": "lv3.org",
                "publications": [
                    {
                        "fqdn": "grafana.lv3.org",
                        "service_id": "grafana",
                        "environment": "production",
                        "status": "active",
                        "owner_adr": "0011",
                        "publication": {
                            "delivery_model": "shared-edge",
                            "access_model": "open",
                            "audience": "public",
                        },
                        "adapter": {
                            "dns": {"target": "65.108.75.123", "target_port": 443, "record_type": "A"},
                            "routing": {"mode": "edge", "source": "service_topology", "kind": "proxy"},
                            "edge_auth": {
                                "provider": "none",
                                "unauthenticated_paths": [],
                                "unauthenticated_prefix_paths": [],
                            },
                            "repo_route_service_id": "grafana",
                            "repo_route_metadata": {},
                            "tls": {
                                "provider": "letsencrypt",
                                "cert_path": "/etc/letsencrypt/live/lv3-edge/",
                                "auto_renew": True,
                            },
                        },
                        "live_tracking_expected": True,
                        "notes": "Published through the shared edge.",
                    },
                    {
                        "fqdn": "ops.lv3.org",
                        "service_id": "ops_portal",
                        "environment": "production",
                        "status": "active",
                        "owner_adr": "0093",
                        "publication": {
                            "delivery_model": "shared-edge",
                            "access_model": "platform-sso",
                            "audience": "operator",
                        },
                        "adapter": {
                            "dns": {"target": "65.108.75.123", "target_port": 443, "record_type": "A"},
                            "routing": {"mode": "edge", "source": "service_topology", "kind": "proxy"},
                            "edge_auth": {
                                "provider": "oauth2_proxy",
                                "unauthenticated_paths": [],
                                "unauthenticated_prefix_paths": [],
                            },
                            "repo_route_service_id": "ops_portal",
                            "repo_route_metadata": {},
                            "tls": {
                                "provider": "letsencrypt",
                                "cert_path": "/etc/letsencrypt/live/lv3-edge/",
                                "auto_renew": True,
                            },
                        },
                        "live_tracking_expected": True,
                        "notes": "Authenticated operator entrypoint.",
                    },
                ],
                "summary": {
                    "catalog_total": 2,
                    "active_total": 2,
                    "active_public_total": 2,
                    "active_private_total": 0,
                    "planned_total": 0,
                    "shared_edge_total": 2,
                    "platform_sso_total": 1,
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (data_root / "config" / "capability-contract-catalog.json").write_text(
        json.dumps(
            {
                "capabilities": [
                    {
                        "id": "identity_provider",
                        "name": "Identity Provider",
                        "summary": "Authenticate operators through a contract-first OIDC surface.",
                        "review_cadence": "quarterly",
                        "migration_expectations": {
                            "export_formats": ["realm export JSON"],
                            "fallback_behaviour": "Existing sessions continue until expiry while new logins fail closed."
                        },
                        "current_selection": {
                            "product_name": "Keycloak",
                            "service_id": "keycloak",
                            "selection_adr": "0056",
                            "runbook": "docs/runbooks/configure-keycloak.md"
                        }
                    }
                ]
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (data_root / "config" / "workflow-catalog.json").write_text(
        json.dumps(
            {
                "workflows": {
                    "rotate-secret": {
                        "description": "Rotate one service secret.",
                        "lifecycle_status": "active",
                        "live_impact": "service_change",
                        "owner_runbook": "docs/runbooks/rotate-secrets.md",
                    },
                    "validate": {
                        "description": "Repo-only validation.",
                        "lifecycle_status": "active",
                        "live_impact": "repo_only",
                    },
                }
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (data_root / "changelog.md").write_text(
        "# Changelog\n\n## Unreleased\n- Added the interactive ops portal runtime.\n",
        encoding="utf-8",
    )
    (data_root / "receipts" / "live-applies" / "2026-03-23-ops-portal.json").write_text(
        json.dumps(
            {
                "receipt_id": "receipt-ops-portal",
                "summary": "Applied ops portal runtime",
                "workflow_id": "live-apply-service service=ops_portal env=production",
                "recorded_on": "2026-03-23T18:00:00Z",
                "recorded_by": "ops",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (data_root / "receipts" / "drift-reports" / "latest.json").write_text(
        json.dumps(
            {
                "generated_at": "2026-03-23T18:30:00Z",
                "summary": {"status": "warn", "unsuppressed_count": 1},
                "records": [
                    {
                        "service": "grafana",
                        "source": "ansible",
                        "severity": "warn",
                        "detail": "Dashboard permissions drifted",
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    settings = PortalSettings(
        gateway_url="http://gateway.invalid",
        session_secret="test-secret",
        static_api_token="test-token",
        service_catalog_path=data_root / "config" / "service-capability-catalog.json",
        publication_registry_path=data_root / "config" / "subdomain-exposure-registry.json",
        workflow_catalog_path=data_root / "config" / "workflow-catalog.json",
        changelog_path=data_root / "changelog.md",
        live_applies_dir=data_root / "receipts" / "live-applies",
        drift_receipts_dir=data_root / "receipts" / "drift-reports",
        maintenance_windows_path=None,
        docs_base_url="https://docs.lv3.org",
        grafana_logs_url="https://grafana.lv3.org/explore?service={service}",
    )
    gateway = FakeGatewayClient()
    app = create_app(settings, gateway_client=gateway)
    return TestClient(app), gateway


def test_dashboard_renders_all_major_sections(portal_client: tuple[TestClient, FakeGatewayClient]) -> None:
    client, gateway = portal_client

    response = client.get("/")

    assert response.status_code == 200
    assert "Interactive Ops Portal" in response.text
    assert "Platform Overview" in response.text
    assert "Deployment Console" in response.text
    assert "Agent Coordination" in response.text
    assert "agent/observation-loop" in response.text
    assert "Search Fabric" in response.text
    assert "Runbook Launcher" in response.text
    assert "Recent Live Applies" in response.text
    assert "shared-edge / platform-sso" in response.text
    assert "ops.lv3.org · operator · shared-edge · platform-sso" in response.text
    assert "Capability Contracts" in response.text
    assert "Identity Provider" in response.text
    assert "Keycloak" in response.text
    assert gateway.platform_health_tokens == ["test-token"]
    assert gateway.agent_coordination_tokens == ["test-token"]
    assert gateway.runbook_fetch_tokens == ["test-token"]


def test_dashboard_uses_same_origin_static_stylesheet(portal_client: tuple[TestClient, FakeGatewayClient]) -> None:
    client, _gateway = portal_client

    response = client.get("/")

    assert response.status_code == 200
    assert '<link rel="stylesheet" href="/static/portal.css">' in response.text


def test_health_check_action_returns_fragment(portal_client: tuple[TestClient, FakeGatewayClient]) -> None:
    client, gateway = portal_client

    response = client.post("/actions/services/grafana/health-check")

    assert response.status_code == 200
    assert "grafana responded in 320ms" in response.text
    assert "Health check: grafana" in response.text
    assert gateway.service_health_calls == [{"service_id": "grafana", "token": "test-token"}]


def test_deploy_action_records_gateway_call(portal_client: tuple[TestClient, FakeGatewayClient]) -> None:
    client, gateway = portal_client

    response = client.post("/actions/services/grafana/deploy")

    assert response.status_code == 200
    assert "Deployment accepted by gateway" in response.text
    assert gateway.deploy_calls == [
        {"service_id": "grafana", "restart_only": False, "source": "portal", "token": "test-token"}
    ]


def test_runbook_action_accepts_json_parameters(portal_client: tuple[TestClient, FakeGatewayClient]) -> None:
    client, gateway = portal_client

    response = client.post("/actions/runbooks/validation-gate-status", data={"parameters": '{"service":"grafana"}'})

    assert response.status_code == 200
    assert "Runbook completed successfully" in response.text
    assert gateway.runbook_calls == [
        {"runbook_id": "validation-gate-status", "parameters": {"service": "grafana"}, "token": "test-token"}
    ]


def test_search_action_renders_results(portal_client: tuple[TestClient, FakeGatewayClient]) -> None:
    client, gateway = portal_client

    response = client.post("/actions/search", data={"query": "tls cert expires", "collection": "runbooks"})

    assert response.status_code == 200
    assert "Rotate Certificates" in response.text
    assert gateway.search_calls == [{"query": "tls cert expires", "collection": "runbooks", "limit": 8, "token": "test-token"}]


def test_dashboard_keeps_runbooks_visible_when_agent_coordination_degrades(
    portal_client: tuple[TestClient, FakeGatewayClient],
) -> None:
    client, gateway = portal_client
    coordination_failed = {"value": False}

    async def degraded_coordination(token: str | None = None) -> dict[str, object]:
        gateway.agent_coordination_tokens.append(token)
        coordination_failed["value"] = True
        raise RuntimeError("coordination unavailable")

    async def ordering_sensitive_runbooks(
        *,
        token: str | None = None,
        delivery_surface: str = "ops_portal",
    ) -> dict[str, object]:
        gateway.runbook_fetch_tokens.append(token)
        if coordination_failed["value"]:
            raise RuntimeError("runbook delivery was poisoned by the previous failure")
        return {
            "runbooks": [
                {
                    "id": "validation-gate-status",
                    "title": "Inspect validation gate status",
                    "description": "Show the current validation-gate summary through the shared runbook service.",
                    "owner_runbook": "docs/runbooks/validation-gate-status.yaml",
                    "live_impact": "repo_only",
                    "execution_class": "diagnostic",
                }
            ]
        }

    gateway.fetch_agent_coordination = degraded_coordination  # type: ignore[method-assign]
    gateway.fetch_runbooks = ordering_sensitive_runbooks  # type: ignore[method-assign]

    response = client.get("/")

    assert response.status_code == 200
    assert "validation-gate-status" in response.text
    assert "Agent coordination data is degraded: coordination unavailable" in response.text
    assert gateway.runbook_fetch_tokens == ["test-token"]
    assert gateway.agent_coordination_tokens == ["test-token"]


def test_runbooks_partial_surfaces_gateway_warning(portal_client: tuple[TestClient, FakeGatewayClient]) -> None:
    client, gateway = portal_client

    async def degraded_runbooks(
        *,
        token: str | None = None,
        delivery_surface: str = "ops_portal",
    ) -> dict[str, object]:
        gateway.runbook_fetch_tokens.append(token)
        raise RuntimeError("runbook index unavailable")

    gateway.fetch_runbooks = degraded_runbooks  # type: ignore[method-assign]

    response = client.get("/partials/runbooks")

    assert response.status_code == 200
    assert "Runbook launcher data is degraded: runbook index unavailable" in response.text
    assert gateway.runbook_fetch_tokens == ["test-token"]


def test_normalize_health_accepts_service_id_list_payload() -> None:
    services = [{"id": "grafana"}, {"id": "ops_portal"}]
    payload = {
        "services": [
            {"service_id": "grafana", "status": "healthy", "detail": "Dashboards are green"},
            {"service_id": "ops_portal", "status": "degraded", "detail": "Maintenance window"},
        ]
    }

    result = normalize_health(payload, services)

    assert result["grafana"]["status"] == "healthy"
    assert result["ops_portal"]["detail"] == "Maintenance window"
