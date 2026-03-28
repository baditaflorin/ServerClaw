import asyncio
import base64
import json
import sqlite3
import sys
import time
from pathlib import Path
from unittest.mock import patch

import httpx
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from platform.circuit import MemoryCircuitStateBackend
from platform.degradation import DegradationStateStore
from platform.retry import RetryPolicy


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import api_gateway.main as gateway_main  # noqa: E402
from api_gateway.main import GatewayConfig, GatewayRuntime, NatsEventEmitter, create_app  # noqa: E402
from platform.use_cases.runbooks import RunbookRunStore, RunbookUseCaseService  # noqa: E402


def test_resolve_repo_root_supports_packaged_layout(tmp_path: Path) -> None:
    app_root = tmp_path / "app"
    platform_dir = app_root / "platform"
    platform_dir.mkdir(parents=True)
    (platform_dir / "__init__.py").write_text("", encoding="utf-8")

    script_path = app_root / "api_gateway" / "main.py"
    script_path.parent.mkdir(parents=True)
    script_path.write_text("# containerized gateway entrypoint\n", encoding="utf-8")

    assert gateway_main._resolve_repo_root(script_path) == app_root


def b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def sign_token(private_key: rsa.RSAPrivateKey, *, roles: list[str], issuer: str) -> str:
    header = {"alg": "RS256", "typ": "JWT", "kid": "test-key"}
    payload = {
        "sub": "user-123",
        "preferred_username": "ops",
        "iss": issuer,
        "exp": int(time.time()) + 3600,
        "realm_access": {"roles": roles},
    }
    header_b64 = b64url_encode(json.dumps(header, separators=(",", ":")).encode())
    payload_b64 = b64url_encode(json.dumps(payload, separators=(",", ":")).encode())
    signed = private_key.sign(
        f"{header_b64}.{payload_b64}".encode(),
        padding.PKCS1v15(),
        hashes.SHA256(),
    )
    return f"{header_b64}.{payload_b64}.{b64url_encode(signed)}"


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")


def write_yaml(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def test_gateway_runtime_compose_mounts_config_at_app_path() -> None:
    template = (
        REPO_ROOT
        / "collections"
        / "ansible_collections"
        / "lv3"
        / "platform"
        / "roles"
        / "api_gateway_runtime"
        / "templates"
        / "docker-compose.yml.j2"
    ).read_text(encoding="utf-8")

    assert "/app/config:ro" in template


def test_gateway_runtime_uses_memory_circuit_backend(tmp_path: Path) -> None:
    config, _ = make_repo(tmp_path, "http://127.0.0.1:8000")
    runtime = GatewayRuntime(config)

    try:
        assert isinstance(runtime.circuit_registry.backend, MemoryCircuitStateBackend)
    finally:
        asyncio.run(runtime.close())


def prepare_graph_db(path: Path) -> str:
    connection = sqlite3.connect(path)
    connection.execute(
        """
        CREATE TABLE graph_nodes (
            id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            label TEXT NOT NULL,
            tier INTEGER,
            metadata TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE graph_edges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_node TEXT NOT NULL,
            to_node TEXT NOT NULL,
            edge_kind TEXT NOT NULL,
            metadata TEXT NOT NULL
        )
        """
    )
    connection.executemany(
        "INSERT INTO graph_nodes (id, kind, label, tier, metadata) VALUES (?, ?, ?, ?, ?)",
        [
            ("service:postgres", "service", "Postgres", 1, json.dumps({"service_id": "postgres"})),
            ("service:windmill", "service", "Windmill", 2, json.dumps({"service_id": "windmill"})),
            ("host:docker-runtime-lv3", "host", "docker-runtime-lv3", None, json.dumps({})),
        ],
    )
    connection.executemany(
        "INSERT INTO graph_edges (from_node, to_node, edge_kind, metadata) VALUES (?, ?, ?, ?)",
        [
            ("service:windmill", "service:postgres", "depends_on", json.dumps({"source": "test"})),
            ("service:windmill", "host:docker-runtime-lv3", "hosted_on", json.dumps({"source": "test"})),
        ],
    )
    connection.commit()
    connection.close()
    return f"sqlite:///{path}"


def prepare_world_state_db(path: Path) -> str:
    connection = sqlite3.connect(path)
    connection.execute(
        """
        CREATE TABLE world_state_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            surface TEXT NOT NULL,
            collected_at TEXT NOT NULL,
            data TEXT NOT NULL,
            stale INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE world_state_current_view (
            surface TEXT PRIMARY KEY,
            data TEXT NOT NULL,
            collected_at TEXT NOT NULL,
            stale INTEGER NOT NULL DEFAULT 0,
            is_expired INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    payload = {
        "services": [
            {"service_id": "postgres", "status": "degraded"},
            {"service_id": "windmill", "status": "ok"},
        ]
    }
    connection.execute(
        "INSERT INTO world_state_current_view (surface, data, collected_at, stale, is_expired) VALUES (?, ?, ?, ?, ?)",
        ("service_health", json.dumps(payload), "2026-03-24T10:00:00+00:00", 0, 0),
    )
    connection.commit()
    connection.close()
    return f"sqlite:///{path}"


def make_repo(tmp_path: Path, upstream_base: str) -> tuple[GatewayConfig, str]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_numbers = private_key.public_key().public_numbers()

    write_json(
        tmp_path / "config" / "service-capability-catalog.json",
        {
            "services": [
                {
                    "id": "api_gateway",
                    "name": "Platform API Gateway",
                    "description": "Unified platform gateway",
                    "category": "automation",
                    "lifecycle_status": "active",
                    "vm": "docker-runtime-lv3",
                    "exposure": "edge-published",
                    "internal_url": "http://10.10.10.20:8083",
                    "public_url": "https://api.lv3.org",
                    "subdomain": "api.lv3.org",
                    "health_probe_id": "api_gateway",
                    "adr": "0092",
                    "runbook": "docs/runbooks/configure-api-gateway.md",
                    "degradation_modes": [
                        {
                            "dependency": "keycloak",
                            "dependency_type": "soft",
                            "degraded_behaviour": "Use cached JWKS for up to 300 seconds.",
                            "degraded_for_seconds_max": 300,
                            "recovery_signal": "successful JWKS refresh",
                            "tested_by": "fault:keycloak-unavailable",
                        },
                        {
                            "dependency": "nats",
                            "dependency_type": "soft",
                            "degraded_behaviour": "Buffer gateway events in a local outbox.",
                            "degraded_for_seconds_max": -1,
                            "recovery_signal": "successful outbox flush",
                            "tested_by": "fault:nats-unavailable",
                        },
                    ],
                    "environments": {
                        "production": {
                            "status": "active",
                            "url": "https://api.lv3.org",
                            "subdomain": "api.lv3.org",
                        }
                    },
                },
                {
                    "id": "postgres",
                    "name": "Postgres",
                    "description": "database",
                    "category": "data",
                    "lifecycle_status": "active",
                    "vm": "postgres-lv3",
                    "vmid": 150,
                    "exposure": "private-only",
                    "internal_url": "postgres://10.10.10.55:5432",
                    "health_probe_id": "postgres",
                    "adr": "0098",
                    "runbook": "docs/runbooks/postgres-failover.md",
                    "tags": ["database"],
                    "environments": {"production": {"status": "active", "url": "postgres://10.10.10.55:5432"}},
                },
                {
                    "id": "windmill",
                    "name": "Windmill",
                    "description": "workflow runtime",
                    "category": "automation",
                    "lifecycle_status": "active",
                    "vm": "docker-runtime-lv3",
                    "exposure": "private-only",
                    "internal_url": upstream_base,
                    "health_probe_id": "windmill",
                    "adr": "0044",
                    "runbook": "docs/runbooks/configure-windmill.md",
                    "tags": ["workflow"],
                    "environments": {"production": {"status": "active", "url": upstream_base}},
                }
            ]
        },
    )
    write_json(
        tmp_path / "config" / "workflow-catalog.json",
        {
            "workflows": {
                "deploy-and-promote": {"description": "deploy service"},
                "rotate-secret": {"description": "rotate secret"},
                "gate-status": {
                    "description": "show validation gate status",
                    "execution_class": "diagnostic",
                    "live_impact": "repo_only",
                    "lifecycle_status": "active",
                },
            }
        },
    )
    write_json(
        tmp_path / "config" / "dependency-graph.json",
        {
            "schema_version": "1.0.0",
            "nodes": [{"id": "windmill", "tier": 2}],
            "edges": [],
        },
    )
    write_json(
        tmp_path / "config" / "command-catalog.json",
        {
            "commands": {
                "converge-netbox": {
                    "description": "deploy netbox",
                    "workflow_id": "deploy-and-promote",
                }
            }
        },
    )
    write_json(
        tmp_path / "config" / "environment-topology.json",
        {
            "schema_version": "1.0.0",
            "environments": [
                {
                    "id": "production",
                    "name": "Production",
                    "status": "active",
                    "base_domain": "lv3.org",
                }
            ],
        },
    )
    write_json(
        tmp_path / "config" / "subdomain-exposure-registry.json",
        {
            "schema_version": "2.0.0",
            "publications": [
                {
                    "fqdn": "api.lv3.org",
                    "service_id": "api_gateway",
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
    )
    write_json(
        tmp_path / "config" / "runtime-assurance-matrix.json",
        {
            "schema_version": "1.0.0",
            "dimensions": {
                "declared_runtime": {
                    "title": "Declared Runtime",
                    "description": "The service has a current runtime witness."
                },
                "health": {
                    "title": "Health",
                    "description": "The live health composite reports the service."
                },
                "route": {
                    "title": "Route",
                    "description": "The declared route matches a live surface."
                },
                "tls": {
                    "title": "TLS",
                    "description": "The service has HTTPS proof where required."
                },
                "smoke": {
                    "title": "Smoke",
                    "description": "A recent governed smoke receipt exists."
                },
                "browser_journey": {
                    "title": "Browser Journey",
                    "description": "A recent browser journey receipt exists."
                },
                "log_queryability": {
                    "title": "Log Queryability",
                    "description": "A recent log-query receipt exists."
                },
            },
            "profiles": {
                "private_service": {
                    "title": "Private Service",
                    "description": "Private non-browser service",
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
                "private_browser_surface": {
                    "title": "Private Browser Surface",
                    "description": "Private browser service",
                    "dimension_classes": {
                        "declared_runtime": "required",
                        "health": "required",
                        "route": "required",
                        "tls": "n_a",
                        "smoke": "required",
                        "browser_journey": "required",
                        "log_queryability": "best_effort",
                    },
                },
                "edge_informational_surface": {
                    "title": "Edge Informational Surface",
                    "description": "Edge informational service",
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
                "edge_api_surface": {
                    "title": "Edge API Surface",
                    "description": "Published API surface",
                    "dimension_classes": {
                        "declared_runtime": "required",
                        "health": "required",
                        "route": "required",
                        "tls": "required",
                        "smoke": "required",
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
            "service_overrides": {
                "api_gateway": {"profile": "edge_api_surface"}
            },
            "freshness_days_by_dimension": {
                "smoke": 30,
                "browser_journey": 30,
                "log_queryability": 45,
            },
        },
    )
    write_yaml(
        tmp_path / "config" / "error-codes.yaml",
        """schema_version: 1.0.0
error_codes:
  AUTH_TOKEN_MISSING:
    http_status: 401
    severity: warn
    category: authentication
    retry_advice: none
    description: Bearer token is required for this endpoint.
    context_fields: [header]
  AUTH_TOKEN_INVALID:
    http_status: 401
    severity: warn
    category: authentication
    retry_advice: none
    description: Bearer token could not be validated.
    context_fields: [reason]
  AUTH_TOKEN_EXPIRED:
    http_status: 401
    severity: info
    category: authentication
    retry_advice: none
    description: Bearer token has expired.
    context_fields: [reason]
  AUTH_INSUFFICIENT_ROLE:
    http_status: 403
    severity: warn
    category: authentication
    retry_advice: none
    description: Caller identity is authenticated but lacks the required role.
    context_fields: [required_role, subject, service_id]
  INPUT_SCHEMA_INVALID:
    http_status: 422
    severity: warn
    category: input
    retry_advice: none
    description: Request payload or parameters failed validation.
    context_fields: [field_path, error_type, validation_message]
  INPUT_UNKNOWN_SERVICE:
    http_status: 404
    severity: info
    category: input
    retry_advice: none
    description: Requested platform service is not defined.
    context_fields: [service_id]
  INPUT_UNKNOWN_WORKFLOW:
    http_status: 404
    severity: info
    category: input
    retry_advice: none
    description: Requested workflow is not defined.
    context_fields: [workflow_id]
  INPUT_UNKNOWN_COMMAND:
    http_status: 404
    severity: info
    category: input
    retry_advice: none
    description: Requested command is not defined.
    context_fields: [command_id]
  INPUT_UNKNOWN_GATEWAY_ROUTE:
    http_status: 404
    severity: info
    category: input
    retry_advice: none
    description: Requested gateway route is not registered.
    context_fields: [path]
  INFRA_RUNTIME_UNAVAILABLE:
    http_status: 503
    severity: error
    category: infrastructure
    retry_advice: backoff
    retry_after_s: 30
    description: Required runtime dependency is unavailable or not configured.
    context_fields: [dependency, detail]
  INFRA_DEPENDENCY_DOWN:
    http_status: 503
    severity: error
    category: infrastructure
    retry_advice: backoff
    retry_after_s: 30
    description: Upstream dependency request failed.
    context_fields: [dependency, detail]
  INTERNAL_UNEXPECTED_ERROR:
    http_status: 500
    severity: error
    category: internal
    retry_advice: manual
    description: Unexpected internal error.
    context_fields: [detail]
""",
    )
    write_json(
        tmp_path / "config" / "api-gateway-catalog.json",
        {
            "schema_version": "1.0.0",
            "services": [
                {
                    "id": "windmill",
                    "name": "Windmill",
                    "upstream": upstream_base,
                    "gateway_prefix": "/v1/windmill",
                    "auth": "keycloak_jwt",
                    "required_role": "platform-operator",
                    "strip_prefix": True,
                    "timeout_seconds": 5,
                    "healthcheck_path": "/health",
                }
            ],
        },
    )
    write_yaml(
        tmp_path / "config" / "circuit-policies.yaml",
        """
schema_version: 1.0.0
circuits:
  - name: keycloak
    service: Keycloak OIDC / JWKS
    failure_threshold: 5
    recovery_window_s: 30
    success_threshold: 2
    timeout_s: 10
  - name: windmill
    service: Windmill workflow engine
    failure_threshold: 5
    recovery_window_s: 60
    success_threshold: 2
    timeout_s: 15
  - name: nats
    service: NATS event bus
    failure_threshold: 10
    recovery_window_s: 10
    success_threshold: 3
    timeout_s: 2
""".strip()
        + "\n",
    )
    write_yaml(
        tmp_path / "inventory" / "group_vars" / "platform.yml",
        "platform_service_topology:\n  windmill:\n    urls:\n      internal: http://10.10.10.20:8000\n",
    )
    write_yaml(
        tmp_path / "config" / "search-synonyms.yaml",
        "schema_version: 1.0.0\ngroups: []\n",
    )
    write_yaml(
        tmp_path / "docs" / "runbooks" / "configure-windmill.md",
        "# Configure Windmill\n\nDeploy service runtime.\n",
    )
    write_yaml(
        tmp_path / "docs" / "runbooks" / "configure-api-gateway.md",
        "# Configure API Gateway\n\nDeploy service runtime.\n",
    )
    write_yaml(
        tmp_path / "docs" / "runbooks" / "postgres-failover.md",
        "# Postgres Failover\n\nHandle the failover path.\n",
    )
    write_yaml(
        tmp_path / "docs" / "runbooks" / "validation-gate-status.yaml",
        """id: validation-gate-status
title: Inspect validation gate status
automation:
  eligible: true
  description: Show the current validation-gate summary through the shared runbook service.
  delivery_surfaces:
    - api_gateway
steps:
  - id: summarize-gate
    type: diagnostic
    workflow_id: gate-status
    params: {}
    success_condition: "result != None"
    on_failure: escalate
""",
    )
    write_json(
        tmp_path / "receipts" / "drift-reports" / "2026-03-23-test.json",
        {"summary": {"status": "warn", "warn_count": 1, "critical_count": 0}},
    )
    write_json(
        tmp_path / "receipts" / "live-applies" / "2026-03-23-windmill-runtime-assurance.json",
        {
            "receipt_id": "receipt-windmill-runtime-assurance",
            "summary": "Applied windmill production smoke and log query verification",
            "workflow_id": "live-apply-service service=windmill env=production",
            "recorded_on": "2026-03-23T18:15:00Z",
            "verification": [
                {"check": "smoke test", "observed": "Smoke test passed", "result": "pass"},
                {"check": "log query", "observed": "Loki log query succeeded", "result": "pass"},
            ],
            "notes": [
                "windmill smoke check and log query proof recorded for production",
            ],
        },
    )
    graph_dsn = prepare_graph_db(tmp_path / "graph.sqlite3")
    world_state_dsn = prepare_world_state_db(tmp_path / "world-state.sqlite3")
    write_json(
        tmp_path / "jwks.json",
        {
            "keys": [
                {
                    "kid": "test-key",
                    "kty": "RSA",
                    "alg": "RS256",
                    "n": b64url_encode(public_numbers.n.to_bytes((public_numbers.n.bit_length() + 7) // 8, "big")),
                    "e": b64url_encode(public_numbers.e.to_bytes((public_numbers.e.bit_length() + 7) // 8, "big")),
                }
            ]
        },
    )

    config = GatewayConfig(
        repo_root=tmp_path,
        catalog_path=tmp_path / "config" / "api-gateway-catalog.json",
        service_catalog_path=tmp_path / "config" / "service-capability-catalog.json",
        error_registry_path=tmp_path / "config" / "error-codes.yaml",
        health_probe_catalog_path=tmp_path / "config" / "health-probe-catalog.json",
        workflow_catalog_path=tmp_path / "config" / "workflow-catalog.json",
        platform_vars_path=tmp_path / "inventory" / "group_vars" / "platform.yml",
        drift_receipts_dir=tmp_path / "receipts" / "drift-reports",
        jwks_url="http://jwks.test/jwks.json",
        issuer="https://sso.example.test/realms/lv3",
        expected_audience=None,
        nats_url=None,
        nats_username=None,
        nats_password=None,
        deploy_webhook_url=None,
        secret_rotation_webhook_url=None,
        windmill_base_url=upstream_base,
        windmill_token="windmill-superadmin",
        runbook_runs_dir=tmp_path / "data" / "runbooks" / "runs",
        circuit_policy_path=tmp_path / "config" / "circuit-policies.yaml",
        degradation_state_path=tmp_path / "data" / "degradation-state.json",
        nats_outbox_path=tmp_path / "data" / "nats-outbox.jsonl",
        openapi_include_upstreams=False,
        graph_dsn=graph_dsn,
        world_state_dsn=world_state_dsn,
        keycloak_retry_after_seconds=30,
    )
    token = sign_token(private_key, roles=["platform-operator"], issuer=config.issuer or "")
    return config, token


def test_gateway_proxy_and_platform_endpoints(tmp_path: Path) -> None:
    def upstream(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok"})
        return httpx.Response(
            200,
            json={
                "path": request.url.path,
                "method": request.method,
                "trace_id": request.headers.get("X-Trace-Id"),
            },
        )

    def jwks(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=json.loads((tmp_path / "jwks.json").read_text()))

    transport = httpx.MockTransport(lambda request: upstream(request) if request.url.host == "upstream.test" else jwks(request))
    config, token = make_repo(tmp_path, "http://upstream.test")
    app = create_app(config)

    async def run() -> None:
        async with httpx.AsyncClient(transport=transport) as runtime_client:
            runtime = GatewayRuntime(config)
            await runtime.http_client.aclose()
            runtime.http_client = runtime_client
            runtime.verifier._client = runtime_client
            app.state.runtime = runtime
            try:
                transport_app = httpx.ASGITransport(app=app)
                async with httpx.AsyncClient(transport=transport_app, base_url="http://gateway.test") as client:
                    headers = {"Authorization": f"Bearer {token}", "X-Trace-Id": "trace-test-123"}
                    health = await client.get("/v1/health", headers=headers)
                    assert health.status_code == 200
                    assert health.json()["status"] == "healthy"
                    assert health.headers["X-Trace-Id"] == "trace-test-123"

                    services = await client.get("/v1/platform/services", headers=headers)
                    assert services.status_code == 200
                    assert services.json()["count"] == 3
                    api_gateway_service = next(item for item in services.json()["services"] if item["id"] == "api_gateway")
                    assert api_gateway_service["active_degradations"] == []

                    platform_health = await client.get("/v1/platform/health", headers=headers)
                    assert platform_health.status_code == 200
                    assert platform_health.json()["service_count"] == 3
                    assert platform_health.json()["source"] == "health_composite"

                    runtime_assurance = await client.get("/v1/platform/runtime-assurance", headers=headers)
                    assert runtime_assurance.status_code == 200
                    assert runtime_assurance.json()["summary"]["total"] == 3
                    windmill_assurance = next(
                        item
                        for item in runtime_assurance.json()["entries"]
                        if item["service_id"] == "windmill"
                    )
                    assert windmill_assurance["overall_status"] == "pass"
                    assert windmill_assurance["profile_id"] == "private_service"

                    postgres_health = await client.get("/v1/platform/health/postgres", headers=headers)
                    assert postgres_health.status_code == 200
                    assert postgres_health.json()["status"] == "degraded"
                    assert postgres_health.json()["composite_status"] == "degraded"

                    drift = await client.get("/v1/platform/drift", headers=headers)
                    assert drift.status_code == 200
                    assert drift.json()["status"] == "warn"

                    topology = await client.get("/v1/platform/topology", headers=headers)
                    assert topology.status_code == 200
                    assert "windmill" in topology.json()["service_topology"]

                    agents = await client.get("/v1/platform/agents", headers=headers)
                    assert agents.status_code == 200
                    assert agents.json()["summary"]["count"] == 0

                    graph_nodes = await client.get("/v1/graph/nodes", headers=headers)
                    assert graph_nodes.status_code == 200
                    assert graph_nodes.json()["count"] == 3

                    descendants = await client.get("/v1/graph/nodes/service:postgres/descendants", headers=headers)
                    assert descendants.status_code == 200
                    assert descendants.json()["nodes"] == ["service:windmill"]

                    ancestors = await client.get("/v1/graph/nodes/service:windmill/ancestors", headers=headers)
                    assert ancestors.status_code == 200
                    assert "service:postgres" in ancestors.json()["nodes"]

                    graph_health = await client.get("/v1/graph/nodes/service:windmill/health", headers=headers)
                    assert graph_health.status_code == 200
                    assert graph_health.json()["derived_status"] == "degraded"

                    path_response = await client.get(
                        "/v1/graph/path",
                        params={"from_node": "service:windmill", "to_node": "service:postgres"},
                        headers=headers,
                    )
                    assert path_response.status_code == 200
                    assert path_response.json()["path"] == ["service:windmill", "service:postgres"]

                    search = await client.get("/v1/search?q=deploy", headers=headers)
                    assert search.status_code == 200
                    assert search.json()["results"]

                    proxied = await client.get("/v1/windmill/api/version", headers=headers)
                    assert proxied.status_code == 200
                    assert proxied.json()["path"] == "/api/version"
                    assert proxied.json()["trace_id"] == "trace-test-123"
            finally:
                await runtime.close()

    import asyncio

    asyncio.run(run())


def test_gateway_enters_and_surfaces_keycloak_degraded_mode(tmp_path: Path) -> None:
    jwks_online = {"value": True}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "upstream.test":
            return httpx.Response(200, json={"status": "ok"})
        if jwks_online["value"]:
            return httpx.Response(200, json=json.loads((tmp_path / "jwks.json").read_text()))
        raise httpx.ConnectError("keycloak unavailable", request=request)

    transport = httpx.MockTransport(handler)
    config, token = make_repo(tmp_path, "http://upstream.test")
    app = create_app(config)

    async def run() -> None:
        async with httpx.AsyncClient(transport=transport) as runtime_client:
            runtime = GatewayRuntime(config)
            await runtime.http_client.aclose()
            runtime.http_client = runtime_client
            runtime.verifier._client = runtime_client
            runtime._runbook_service = RunbookUseCaseService(
                repo_root=config.repo_root,
                workflow_runner=type(
                    "FakeRunner",
                    (),
                    {
                        "run_workflow": staticmethod(
                            lambda workflow_id, payload, timeout_seconds=None: (
                                windmill_calls.append(workflow_id) or {"summary": "gate ok", "checks": []}
                            )
                        )
                    },
                )(),
                store=RunbookRunStore(config.runbook_runs_dir),
            )
            app.state.runtime = runtime
            try:
                transport_app = httpx.ASGITransport(app=app)
                async with httpx.AsyncClient(transport=transport_app, base_url="http://gateway.test") as client:
                    headers = {"Authorization": f"Bearer {token}"}
                    ok = await client.get("/v1/platform/services", headers=headers)
                    assert ok.status_code == 200

                    runtime.verifier._jwks_cache_expiry = time.time() + 10
                    jwks_online["value"] = False

                    degraded = await client.get("/v1/platform/services", headers=headers)
                    assert degraded.status_code == 200
                    api_gateway_service = next(
                        item for item in degraded.json()["services"] if item["id"] == "api_gateway"
                    )
                    assert api_gateway_service["active_degradations"][0]["dependency"] == "keycloak"

                    active = await client.get("/v1/platform/degradations", headers=headers)
                    assert active.status_code == 200
                    assert active.json()["degradation_count"] == 1
                    assert active.json()["services"]["api_gateway"][0]["dependency"] == "keycloak"

                    platform_health = await client.get("/v1/platform/health", headers=headers)
                    assert platform_health.status_code == 200
                    assert platform_health.json()["status"] == "degraded"
                    assert platform_health.json()["degraded_service_count"] == 1

                    runtime.verifier._jwks_cache_expiry = time.time() - 1
                    failed = await client.get("/v1/platform/services", headers=headers)
                    assert failed.status_code == 503
                    assert failed.headers["Retry-After"] == "30"
                    assert failed.json()["error"]["code"] == "INFRA_RUNTIME_UNAVAILABLE"
                    assert failed.json()["error"]["context"]["dependency"] == "keycloak"
                    assert failed.json()["error"]["context"]["detail"]["error_code"] == "GATE_CIRCUIT_OPEN"
            finally:
                await runtime.close()

    asyncio.run(run())


def test_nats_emitter_buffers_and_flushes_outbox(tmp_path: Path) -> None:
    emitter = NatsEventEmitter(
        "nats://127.0.0.1:4222",
        outbox_path=tmp_path / "nats-outbox.jsonl",
        degradation_store=DegradationStateStore(tmp_path / "degradation-state.json"),
        degradation_mode={
            "dependency": "nats",
            "dependency_type": "soft",
            "degraded_behaviour": "Buffer events in a local outbox.",
            "degraded_for_seconds_max": -1,
            "recovery_signal": "successful outbox flush",
            "tested_by": "fault:nats-unavailable",
        },
    )
    publish_calls = {"count": 0}

    def fake_publish(
        host: str,
        port: int,
        subject: str,
        payload: bytes,
        *,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        publish_calls["count"] += 1
        if publish_calls["count"] == 1:
            raise OSError("nats unavailable")

    with patch.object(emitter, "_publish", side_effect=fake_publish):
        asyncio.run(
            emitter.emit(
                "platform.api.request",
                {
                    "request_id": "one",
                    "method": "GET",
                    "path": "/v1/platform/services",
                    "status_code": 200,
                    "latency_ms": 12.3,
                    "caller_identity": "ops",
                    "caller_roles": ["platform-operator"],
                },
            )
        )
        assert emitter._outbox_path.exists()
        assert emitter._degradation_store.active_for_service("api_gateway")

        asyncio.run(
            emitter.emit(
                "platform.api.request",
                {
                    "request_id": "two",
                    "method": "GET",
                    "path": "/v1/platform/services",
                    "status_code": 200,
                    "latency_ms": 10.1,
                    "caller_identity": "ops",
                    "caller_roles": ["platform-operator"],
                },
            )
        )
        assert not emitter._outbox_path.exists()
        assert not emitter._degradation_store.active_for_service("api_gateway")


def test_nats_emitter_sends_credentials_in_connect_frame() -> None:
    sent_frames: list[bytes] = []

    class FakeSocket:
        def sendall(self, data: bytes) -> None:
            sent_frames.append(data)

        def __enter__(self) -> "FakeSocket":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    with patch.object(gateway_main.socket, "create_connection", return_value=FakeSocket()):
        gateway_main.NatsEventEmitter._publish(
            "127.0.0.1",
            4222,
            "platform.api.request",
            b'{"ok":true}',
            username="jetstream-admin",
            password="secret-value",
        )

    assert sent_frames[0] == b'CONNECT {"verbose":false,"user":"jetstream-admin","pass":"secret-value"}\r\n'
    assert sent_frames[1] == b'PUB platform.api.request 11\r\n{"ok":true}\r\n'


def test_gateway_deploy_forwards_trace_id_to_webhook(tmp_path: Path) -> None:
    received_payloads: list[dict[str, object]] = []

    def upstream(request: httpx.Request) -> httpx.Response:
        if request.url.host == "jwks.test":
            return httpx.Response(200, json=json.loads((tmp_path / "jwks.json").read_text()))
        if request.url.host == "deploy-hook.test":
            received_payloads.append(json.loads(request.content.decode()))
            return httpx.Response(202, json={"queued": True})
        return httpx.Response(200, json={"status": "ok"})

    transport = httpx.MockTransport(upstream)
    config, token = make_repo(tmp_path, "http://upstream.test")
    config = GatewayConfig(
        **{
            **config.__dict__,
            "deploy_webhook_url": "http://deploy-hook.test/deploy",
        }
    )
    app = create_app(config)

    async def run() -> None:
        async with httpx.AsyncClient(transport=transport) as runtime_client:
            runtime = GatewayRuntime(config)
            await runtime.http_client.aclose()
            runtime.http_client = runtime_client
            runtime.verifier._client = runtime_client
            runtime._runbook_service = RunbookUseCaseService(
                repo_root=config.repo_root,
                workflow_runner=type(
                    "FakeRunner",
                    (),
                    {
                        "run_workflow": staticmethod(
                            lambda workflow_id, payload, timeout_seconds=None: (
                                windmill_calls.append(workflow_id) or {"summary": "gate ok", "checks": []}
                            )
                        )
                    },
                )(),
                store=RunbookRunStore(config.runbook_runs_dir),
            )
            app.state.runtime = runtime
            try:
                transport_app = httpx.ASGITransport(app=app)
                async with httpx.AsyncClient(transport=transport_app, base_url="http://gateway.test") as client:
                    response = await client.post(
                        "/v1/platform/deploy",
                        headers={"Authorization": f"Bearer {token}", "X-Trace-Id": "trace-webhook-123"},
                        json={"service_id": "windmill", "environment": "production", "execute": True},
                    )
                    assert response.status_code == 202
                    assert received_payloads[0]["trace_id"] == "trace-webhook-123"
            finally:
                await runtime.close()

    import asyncio

    asyncio.run(run())


def test_gateway_runbook_routes_use_shared_service(tmp_path: Path) -> None:
    windmill_calls: list[str] = []

    def upstream(request: httpx.Request) -> httpx.Response:
        if request.url.host == "jwks.test":
            return httpx.Response(200, json=json.loads((tmp_path / "jwks.json").read_text()))
        if request.url.path.startswith("/api/w/lv3/jobs/run_wait_result/p/"):
            windmill_calls.append(request.url.path)
            return httpx.Response(200, json={"summary": "gate ok", "checks": []})
        return httpx.Response(200, json={"status": "ok"})

    transport = httpx.MockTransport(upstream)
    config, token = make_repo(tmp_path, "http://upstream.test")
    app = create_app(config)

    async def run() -> None:
        async with httpx.AsyncClient(transport=transport) as runtime_client:
            runtime = GatewayRuntime(config)
            await runtime.http_client.aclose()
            runtime.http_client = runtime_client
            runtime.verifier._client = runtime_client
            runtime._runbook_service = RunbookUseCaseService(
                repo_root=config.repo_root,
                workflow_runner=type(
                    "FakeRunner",
                    (),
                    {
                        "run_workflow": staticmethod(
                            lambda workflow_id, payload, timeout_seconds=None: (
                                windmill_calls.append(workflow_id) or {"summary": "gate ok", "checks": []}
                            )
                        )
                    },
                )(),
                store=RunbookRunStore(config.runbook_runs_dir),
            )
            app.state.runtime = runtime
            try:
                transport_app = httpx.ASGITransport(app=app)
                async with httpx.AsyncClient(transport=transport_app, base_url="http://gateway.test") as client:
                    listing = await client.get(
                        "/v1/platform/runbooks",
                        headers={"Authorization": f"Bearer {token}"},
                    )
                    assert listing.status_code == 200
                    assert listing.json()["runbooks"][0]["id"] == "validation-gate-status"

                    execute = await client.post(
                        "/v1/platform/runbooks/execute",
                        headers={"Authorization": f"Bearer {token}"},
                        json={"runbook_id": "validation-gate-status"},
                    )
                    assert execute.status_code == 200
                    payload = execute.json()
                    assert payload["status"] == "completed"
                    assert payload["runbook_id"] == "validation-gate-status"

                    status = await client.get(
                        f"/v1/platform/runbooks/{payload['run_id']}",
                        headers={"Authorization": f"Bearer {token}"},
                    )
                    assert status.status_code == 200
                    assert status.json()["status"] == "completed"
                    assert windmill_calls == ["gate-status"]
            finally:
                await runtime.close()

    import asyncio

    asyncio.run(run())


def test_gateway_runbook_routes_enforce_delivery_surface_allowlist(tmp_path: Path) -> None:
    def upstream(request: httpx.Request) -> httpx.Response:
        if request.url.host == "jwks.test":
            return httpx.Response(200, json=json.loads((tmp_path / "jwks.json").read_text()))
        return httpx.Response(200, json={"status": "ok"})

    transport = httpx.MockTransport(upstream)
    config, token = make_repo(tmp_path, "http://upstream.test")
    app = create_app(config)

    async def run() -> None:
        async with httpx.AsyncClient(transport=transport) as runtime_client:
            runtime = GatewayRuntime(config)
            await runtime.http_client.aclose()
            runtime.http_client = runtime_client
            runtime.verifier._client = runtime_client
            runtime._runbook_service = RunbookUseCaseService(
                repo_root=config.repo_root,
                workflow_runner=type(
                    "FakeRunner",
                    (),
                    {"run_workflow": staticmethod(lambda workflow_id, payload, timeout_seconds=None: {"status": "ok"})},
                )(),
                store=RunbookRunStore(config.runbook_runs_dir),
            )
            app.state.runtime = runtime
            try:
                transport_app = httpx.ASGITransport(app=app)
                async with httpx.AsyncClient(transport=transport_app, base_url="http://gateway.test") as client:
                    response = await client.post(
                        "/v1/platform/runbooks/execute",
                        headers={"Authorization": f"Bearer {token}"},
                        json={"runbook_id": "validation-gate-status", "delivery_surface": "ops_portal"},
                    )
                    assert response.status_code == 403
            finally:
                await runtime.close()

    import asyncio

    asyncio.run(run())


def test_gateway_requires_bearer_token(tmp_path: Path) -> None:
    config, _token = make_repo(tmp_path, "http://upstream.test")
    app = create_app(config)

    async def run() -> None:
        runtime = GatewayRuntime(config)
        app.state.runtime = runtime
        transport_app = httpx.ASGITransport(app=app)
        try:
            async with httpx.AsyncClient(transport=transport_app, base_url="http://gateway.test") as client:
                response = await client.get("/v1/health")
                assert response.status_code == 401
                payload = response.json()["error"]
                assert payload["code"] == "AUTH_TOKEN_MISSING"
                assert payload["context"]["header"] == "Authorization"
        finally:
            await runtime.close()

    import asyncio

    asyncio.run(run())


def test_gateway_validation_errors_use_canonical_envelope(tmp_path: Path) -> None:
    def jwks(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=json.loads((tmp_path / "jwks.json").read_text()))

    transport = httpx.MockTransport(jwks)
    config, token = make_repo(tmp_path, "http://upstream.test")
    app = create_app(config)

    async def run() -> None:
        runtime: GatewayRuntime | None = None
        try:
            async with httpx.AsyncClient(transport=transport) as runtime_client:
                runtime = GatewayRuntime(config)
                await runtime.http_client.aclose()
                runtime.http_client = runtime_client
                runtime.verifier._client = runtime_client
                app.state.runtime = runtime
                transport_app = httpx.ASGITransport(app=app)
                async with httpx.AsyncClient(transport=transport_app, base_url="http://gateway.test") as client:
                    response = await client.get("/v1/search?q=a", headers={"Authorization": f"Bearer {token}"})
                    assert response.status_code == 422
                    payload = response.json()["error"]
                    assert payload["code"] == "INPUT_SCHEMA_INVALID"
                    assert payload["context"]["field_path"].startswith("query.q")
        finally:
            if runtime is not None:
                await runtime.close()

    asyncio.run(run())


def test_gateway_request_events_do_not_block_platform_reads(tmp_path: Path) -> None:
    def upstream(request: httpx.Request) -> httpx.Response:
        if request.url.host == "jwks.test":
            return httpx.Response(200, json=json.loads((tmp_path / "jwks.json").read_text()))
        return httpx.Response(200, json={"status": "ok"})

    transport = httpx.MockTransport(upstream)
    config, token = make_repo(tmp_path, "http://upstream.test")
    app = create_app(config)

    async def run() -> None:
        class SlowEmitter:
            async def emit(self, _subject: str, _payload: dict[str, object]) -> None:
                await gateway_main.asyncio.sleep(5)

        async with httpx.AsyncClient(transport=transport) as runtime_client:
            runtime = GatewayRuntime(config)
            await runtime.http_client.aclose()
            runtime.http_client = runtime_client
            runtime.verifier._client = runtime_client
            runtime.event_emitter = SlowEmitter()
            app.state.runtime = runtime
            try:
                transport_app = httpx.ASGITransport(app=app)
                async with httpx.AsyncClient(transport=transport_app, base_url="http://gateway.test") as client:
                    started = time.perf_counter()
                    response = await client.get("/v1/platform/services", headers={"Authorization": f"Bearer {token}"})
                    elapsed = time.perf_counter() - started
                    assert response.status_code == 200
                    assert elapsed < 2
            finally:
                await runtime.close()

    import asyncio

    asyncio.run(run())


def test_gateway_dify_tools_route_requires_valid_api_key(tmp_path: Path) -> None:
    config, _token = make_repo(tmp_path, "http://upstream.test")
    config = GatewayConfig(
        **{
            **config.__dict__,
            "dify_tools_api_key": "expected-dify-key",
        }
    )
    app = create_app(config)

    async def run() -> None:
        runtime = GatewayRuntime(config)
        app.state.runtime = runtime
        transport_app = httpx.ASGITransport(app=app)
        try:
            async with httpx.AsyncClient(transport=transport_app, base_url="http://gateway.test") as client:
                missing = await client.post("/v1/dify-tools/get-platform-status", json={})
                assert missing.status_code == 401
                assert missing.json()["error"]["code"] == "AUTH_TOKEN_MISSING"

                wrong = await client.post(
                    "/v1/dify-tools/get-platform-status",
                    headers={"X-LV3-Dify-Api-Key": "wrong-key"},
                    json={},
                )
                assert wrong.status_code == 401
                assert wrong.json()["error"]["code"] == "AUTH_TOKEN_INVALID"
        finally:
            await runtime.close()

    asyncio.run(run())


def test_gateway_dify_tools_route_dispatches_and_returns_structured_content(tmp_path: Path) -> None:
    config, _token = make_repo(tmp_path, "http://upstream.test")
    config = GatewayConfig(
        **{
            **config.__dict__,
            "dify_tools_api_key": "expected-dify-key",
        }
    )
    app = create_app(config)

    async def run() -> None:
        runtime = GatewayRuntime(config)
        app.state.runtime = runtime
        transport_app = httpx.ASGITransport(app=app)
        try:
            with patch.object(gateway_main, "load_agent_tool_registry", return_value=({"tools": []}, {})), patch.object(
                gateway_main,
                "call_tool",
                return_value=(
                    {
                        "tool": "get-platform-status",
                        "structuredContent": {"status": "ok", "source": "dify"},
                        "content": [],
                        "isError": False,
                    },
                    {"outcome": "success"},
                ),
            ) as call_tool_mock:
                async with httpx.AsyncClient(transport=transport_app, base_url="http://gateway.test") as client:
                    response = await client.post(
                        "/v1/dify-tools/get-platform-status",
                        headers={"X-LV3-Dify-Api-Key": "expected-dify-key"},
                        json={"include_details": True},
                    )
                    assert response.status_code == 200
                    assert response.json() == {"status": "ok", "source": "dify"}
                    call_tool_mock.assert_called_once_with(
                        {"tools": []},
                        "get-platform-status",
                        {"include_details": True},
                        actor_class="service_identity",
                    )
        finally:
            await runtime.close()

    asyncio.run(run())


def test_gateway_retries_safe_proxy_reads(tmp_path: Path) -> None:
    upstream_calls = {"count": 0}

    def upstream(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok"})
        if request.url.path == "/api/version":
            upstream_calls["count"] += 1
            if upstream_calls["count"] < 3:
                raise httpx.ConnectTimeout("timed out", request=request)
            return httpx.Response(200, json={"path": request.url.path, "method": request.method})
        return httpx.Response(200, json={"path": request.url.path, "method": request.method})

    def jwks(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=json.loads((tmp_path / "jwks.json").read_text()))

    transport = httpx.MockTransport(lambda request: upstream(request) if request.url.host == "upstream.test" else jwks(request))
    config, token = make_repo(tmp_path, "http://upstream.test")
    app = create_app(config)

    async def run() -> None:
        async with httpx.AsyncClient(transport=transport) as runtime_client:
            runtime = GatewayRuntime(config)
            await runtime.http_client.aclose()
            runtime.http_client = runtime_client
            runtime.verifier._client = runtime_client
            runtime.verifier._retry_policy = RetryPolicy(
                max_attempts=4,
                base_delay_s=0.0,
                max_delay_s=0.0,
                multiplier=2.0,
                jitter=False,
                transient_max=2,
            )
            runtime.internal_api_retry_policy = RetryPolicy(
                max_attempts=4,
                base_delay_s=0.0,
                max_delay_s=0.0,
                multiplier=2.0,
                jitter=False,
                transient_max=2,
            )
            app.state.runtime = runtime
            try:
                transport_app = httpx.ASGITransport(app=app)
                async with httpx.AsyncClient(transport=transport_app, base_url="http://gateway.test") as client:
                    response = await client.get(
                        "/v1/windmill/api/version",
                        headers={"Authorization": f"Bearer {token}"},
                    )
                    assert response.status_code == 200
                    assert response.json()["path"] == "/api/version"
            finally:
                await runtime.close()

    import asyncio

    asyncio.run(run())
    assert upstream_calls["count"] == 3


def test_resolve_repo_root_supports_repo_layout(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    script_path = repo_root / "scripts" / "api_gateway" / "main.py"
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text("# test\n", encoding="utf-8")
    (repo_root / "platform").mkdir(parents=True, exist_ok=True)
    (repo_root / "platform" / "__init__.py").write_text("", encoding="utf-8")

    assert gateway_main._resolve_repo_root(script_path) == repo_root


def test_gateway_runtime_root_exposes_scripts_tree(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    scripts_root = repo_root / "scripts"
    script_path = scripts_root / "api_gateway" / "main.py"
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text("# test\n", encoding="utf-8")
    (repo_root / "platform").mkdir(parents=True, exist_ok=True)
    (repo_root / "platform" / "__init__.py").write_text("", encoding="utf-8")

    resolved_root = gateway_main._resolve_repo_root(script_path)

    assert resolved_root / "scripts" == scripts_root


def test_gateway_returns_retry_after_when_keycloak_circuit_is_open(tmp_path: Path) -> None:
    jwks_calls = {"count": 0}

    def upstream(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "ok"})

    def jwks(_request: httpx.Request) -> httpx.Response:
        jwks_calls["count"] += 1
        return httpx.Response(503, json={"error": "keycloak restarting"})

    transport = httpx.MockTransport(lambda request: upstream(request) if request.url.host == "upstream.test" else jwks(request))
    config, token = make_repo(tmp_path, "http://upstream.test")
    write_yaml(
        tmp_path / "config" / "circuit-policies.yaml",
        """
schema_version: 1.0.0
circuits:
  - name: keycloak
    service: Keycloak OIDC / JWKS
    failure_threshold: 1
    recovery_window_s: 60
    success_threshold: 1
    timeout_s: 10
""".strip()
        + "\n",
    )
    app = create_app(config)

    async def run() -> None:
        async with httpx.AsyncClient(transport=transport) as runtime_client:
            runtime = GatewayRuntime(config)
            await runtime.http_client.aclose()
            runtime.http_client = runtime_client
            runtime.verifier._client = runtime_client
            app.state.runtime = runtime
            try:
                transport_app = httpx.ASGITransport(app=app)
                async with httpx.AsyncClient(transport=transport_app, base_url="http://gateway.test") as client:
                    headers = {"Authorization": f"Bearer {token}"}
                    first = await client.get("/v1/health", headers=headers)
                    second = await client.get("/v1/health", headers=headers)

                    assert first.status_code == 503
                    assert second.status_code == 503
                    assert int(second.headers["Retry-After"]) in {59, 60}
                    assert jwks_calls["count"] == 1
            finally:
                await runtime.close()

    import asyncio

    asyncio.run(run())
