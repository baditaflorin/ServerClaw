import base64
import json
import sqlite3
import sys
import time
from pathlib import Path

import httpx
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa


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
        tmp_path / "inventory" / "group_vars" / "platform.yml",
        "platform_service_topology:\n  windmill:\n    urls:\n      internal: http://10.10.10.20:8000\n",
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
        graph_dsn=graph_dsn,
        world_state_dsn=world_state_dsn,
    )
    token = sign_token(private_key, roles=["platform-operator"], issuer=config.issuer or "")
    return config, token


def test_gateway_proxy_and_platform_endpoints(tmp_path: Path) -> None:
    def upstream(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok"})
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
            app.state.runtime = runtime
            try:
                transport_app = httpx.ASGITransport(app=app)
                async with httpx.AsyncClient(transport=transport_app, base_url="http://gateway.test") as client:
                    headers = {"Authorization": f"Bearer {token}"}
                    health = await client.get("/v1/health", headers=headers)
                    assert health.status_code == 200
                    assert health.json()["status"] == "healthy"

                    services = await client.get("/v1/platform/services", headers=headers)
                    assert services.status_code == 200
                    assert services.json()["count"] == 1

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

                    proxied = await client.get("/v1/windmill/api/version", headers=headers)
                    assert proxied.status_code == 200
                    assert proxied.json()["path"] == "/api/version"
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
