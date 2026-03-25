import base64
import json
import sqlite3
import sys
import time
from pathlib import Path

import httpx
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from platform.retry import RetryPolicy


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from api_gateway.main import GatewayConfig, GatewayRuntime, create_app  # noqa: E402


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
                    "id": "postgres",
                    "name": "Postgres",
                    "description": "database",
                    "category": "data",
                    "lifecycle_status": "active",
                    "vm": "postgres-lv3",
                    "vmid": 150,
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
        tmp_path / "docs" / "runbooks" / "postgres-failover.md",
        "# Postgres Failover\n\nHandle the failover path.\n",
    )
    write_json(
        tmp_path / "receipts" / "drift-reports" / "2026-03-23-test.json",
        {"summary": {"status": "warn", "warn_count": 1, "critical_count": 0}},
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
        health_probe_catalog_path=tmp_path / "config" / "health-probe-catalog.json",
        workflow_catalog_path=tmp_path / "config" / "workflow-catalog.json",
        platform_vars_path=tmp_path / "inventory" / "group_vars" / "platform.yml",
        drift_receipts_dir=tmp_path / "receipts" / "drift-reports",
        jwks_url="http://jwks.test/jwks.json",
        issuer="https://sso.example.test/realms/lv3",
        expected_audience=None,
        nats_url=None,
        deploy_webhook_url=None,
        secret_rotation_webhook_url=None,
        openapi_include_upstreams=False,
        circuit_policy_path=tmp_path / "config" / "circuit-policies.yaml",
        graph_dsn=graph_dsn,
        world_state_dsn=world_state_dsn,
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
                    assert services.json()["count"] == 2

                    platform_health = await client.get("/v1/platform/health", headers=headers)
                    assert platform_health.status_code == 200
                    assert platform_health.json()["service_count"] == 2
                    assert platform_health.json()["source"] == "health_composite"

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
        finally:
            await runtime.close()

    import asyncio

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
                    assert second.headers["Retry-After"] == "60"
                    assert jwks_calls["count"] == 1
            finally:
                await runtime.close()

    import asyncio

    asyncio.run(run())
