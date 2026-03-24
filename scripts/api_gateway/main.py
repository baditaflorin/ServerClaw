from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import socket
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from api_gateway_catalog import load_api_gateway_catalog
from platform.graph import DependencyGraphClient, NodeNotFoundError
from platform.world_state.client import SurfaceNotFoundError, WorldStateClient, WorldStateUnavailable
from platform.world_state.materializer import SQLITE_CURRENT_VIEW_NAME, SQLITE_SNAPSHOTS_TABLE_NAME
from platform.world_state.workers import collect_service_health

try:
    from search_fabric import SearchClient
except ImportError:  # pragma: no cover - packaged import path
    from scripts.search_fabric import SearchClient


REPO_ROOT = Path(__file__).resolve().parents[2]


def b64url_decode(value: str) -> bytes:
    padding_len = (-len(value)) % 4
    return base64.urlsafe_b64decode(value + ("=" * padding_len))


def json_file(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text())


def yaml_file(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    import yaml

    return yaml.safe_load(path.read_text())


def extract_roles(claims: dict[str, Any]) -> set[str]:
    roles: set[str] = set()
    realm_access = claims.get("realm_access", {})
    if isinstance(realm_access, dict):
        for role in realm_access.get("roles", []):
            if isinstance(role, str) and role.strip():
                roles.add(role)
    resource_access = claims.get("resource_access", {})
    if isinstance(resource_access, dict):
        for resource_claims in resource_access.values():
            if not isinstance(resource_claims, dict):
                continue
            for role in resource_claims.get("roles", []):
                if isinstance(role, str) and role.strip():
                    roles.add(role)
    for group in claims.get("groups", []):
        if isinstance(group, str) and group.strip():
            roles.add(group.lstrip("/"))
    return roles


class DeployRequest(BaseModel):
    service_id: str = Field(min_length=2)
    environment: str = Field(default="production", pattern="^(production|staging)$")
    execute: bool = False
    parameters: dict[str, Any] = Field(default_factory=dict)


class SecretRotationRequest(BaseModel):
    secret_id: str = Field(min_length=2)
    execute: bool = False
    parameters: dict[str, Any] = Field(default_factory=dict)


@dataclass(frozen=True)
class GatewayService:
    id: str
    name: str
    upstream: str
    gateway_prefix: str
    required_role: str
    strip_prefix: bool
    timeout_seconds: int
    auth: str
    forward_authorization: bool = False
    healthcheck_path: str = "/"
    openapi_path: str | None = None
    upstream_auth_env_var: str | None = None


@dataclass(frozen=True)
class GatewayConfig:
    repo_root: Path
    catalog_path: Path
    service_catalog_path: Path
    health_probe_catalog_path: Path
    workflow_catalog_path: Path
    platform_vars_path: Path
    drift_receipts_dir: Path
    jwks_url: str
    issuer: str | None
    expected_audience: str | None
    nats_url: str | None
    deploy_webhook_url: str | None
    secret_rotation_webhook_url: str | None
    openapi_include_upstreams: bool
    graph_dsn: str | None = None
    world_state_dsn: str | None = None
    clock_skew_seconds: int = 30


class KeycloakJWTVerifier:
    def __init__(
        self,
        *,
        jwks_url: str,
        issuer: str | None,
        expected_audience: str | None,
        clock_skew_seconds: int,
        client: httpx.AsyncClient,
    ) -> None:
        self._jwks_url = jwks_url
        self._issuer = issuer
        self._expected_audience = expected_audience
        self._clock_skew_seconds = clock_skew_seconds
        self._client = client
        self._jwks_cache: dict[str, Any] | None = None
        self._jwks_cache_expiry = 0.0
        self._lock = asyncio.Lock()

    async def _load_jwks(self) -> dict[str, Any]:
        now = time.time()
        if self._jwks_cache is not None and now < self._jwks_cache_expiry:
            return self._jwks_cache

        async with self._lock:
            now = time.time()
            if self._jwks_cache is not None and now < self._jwks_cache_expiry:
                return self._jwks_cache
            response = await self._client.get(self._jwks_url, timeout=10)
            response.raise_for_status()
            self._jwks_cache = response.json()
            self._jwks_cache_expiry = now + 300
            return self._jwks_cache

    async def verify(self, token: str) -> dict[str, Any]:
        try:
            header_b64, payload_b64, signature_b64 = token.split(".")
        except ValueError as exc:
            raise HTTPException(status_code=401, detail="invalid bearer token format") from exc

        try:
            header = json.loads(b64url_decode(header_b64))
            claims = json.loads(b64url_decode(payload_b64))
        except (ValueError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=401, detail="invalid bearer token encoding") from exc

        alg = header.get("alg")
        kid = header.get("kid")
        if alg != "RS256" or not isinstance(kid, str) or not kid:
            raise HTTPException(status_code=401, detail="unsupported bearer token header")

        jwks = await self._load_jwks()
        keys = jwks.get("keys", [])
        key = next((item for item in keys if isinstance(item, dict) and item.get("kid") == kid), None)
        if key is None:
            raise HTTPException(status_code=401, detail="unknown bearer token signing key")
        if key.get("kty") != "RSA":
            raise HTTPException(status_code=401, detail="unsupported bearer token key type")

        try:
            public_key = rsa.RSAPublicNumbers(
                e=int.from_bytes(b64url_decode(key["e"]), "big"),
                n=int.from_bytes(b64url_decode(key["n"]), "big"),
            ).public_key()
            public_key.verify(
                b64url_decode(signature_b64),
                f"{header_b64}.{payload_b64}".encode(),
                padding.PKCS1v15(),
                hashes.SHA256(),
            )
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=401, detail="invalid bearer token signature") from exc

        now = int(time.time())
        exp = claims.get("exp")
        if not isinstance(exp, int) or exp < now - self._clock_skew_seconds:
            raise HTTPException(status_code=401, detail="expired bearer token")
        nbf = claims.get("nbf")
        if isinstance(nbf, int) and nbf > now + self._clock_skew_seconds:
            raise HTTPException(status_code=401, detail="bearer token not active yet")

        if self._issuer and claims.get("iss") != self._issuer:
            raise HTTPException(status_code=401, detail="unexpected token issuer")

        if self._expected_audience:
            audience = claims.get("aud")
            if isinstance(audience, str):
                valid_audience = audience == self._expected_audience
            elif isinstance(audience, list):
                valid_audience = self._expected_audience in audience
            else:
                valid_audience = False
            if not valid_audience:
                raise HTTPException(status_code=401, detail="unexpected token audience")

        return claims


class NatsEventEmitter:
    def __init__(self, nats_url: str | None) -> None:
        self._parsed = urlparse(nats_url) if nats_url else None

    async def emit(self, subject: str, payload: dict[str, Any]) -> None:
        if self._parsed is None:
            return
        host = self._parsed.hostname or "127.0.0.1"
        port = self._parsed.port or 4222
        encoded = json.dumps(payload, separators=(",", ":")).encode()
        await asyncio.to_thread(self._publish, host, port, subject, encoded)

    @staticmethod
    def _publish(host: str, port: int, subject: str, payload: bytes) -> None:
        with socket.create_connection((host, port), timeout=3) as sock:
            sock.sendall(b'CONNECT {"verbose":false}\r\n')
            sock.sendall(f"PUB {subject} {len(payload)}\r\n".encode() + payload + b"\r\n")


class GatewayRuntime:
    def __init__(self, config: GatewayConfig) -> None:
        self.config = config
        self.catalog_payload, normalized_catalog = load_api_gateway_catalog(
            config.catalog_path,
            service_catalog_path=config.service_catalog_path,
        )
        self.services = [GatewayService(**service) for service in normalized_catalog]
        self.service_by_prefix = sorted(self.services, key=lambda service: len(service.gateway_prefix), reverse=True)
        self.http_client = httpx.AsyncClient(follow_redirects=False)
        self.search_client = SearchClient(config.repo_root)
        self.verifier = KeycloakJWTVerifier(
            jwks_url=config.jwks_url,
            issuer=config.issuer,
            expected_audience=config.expected_audience,
            clock_skew_seconds=config.clock_skew_seconds,
            client=self.http_client,
        )
        self.event_emitter = NatsEventEmitter(config.nats_url)
        self.graph_client = (
            DependencyGraphClient(dsn=config.graph_dsn, world_state_dsn=config.world_state_dsn or config.graph_dsn)
            if config.graph_dsn
            else None
        )

    async def close(self) -> None:
        await self.http_client.aclose()

    def primary_service_catalog(self) -> dict[str, Any]:
        return json_file(self.config.service_catalog_path, {"services": []})

    def workflow_catalog(self) -> dict[str, Any]:
        return json_file(self.config.workflow_catalog_path, {"workflows": {}})

    def platform_vars(self) -> dict[str, Any]:
        return yaml_file(self.config.platform_vars_path, {})

    def world_state_client(self) -> WorldStateClient:
        kwargs: dict[str, Any] = {}
        if (self.config.world_state_dsn or "").startswith("sqlite:///"):
            kwargs["current_view_name"] = SQLITE_CURRENT_VIEW_NAME
            kwargs["snapshots_table_name"] = SQLITE_SNAPSHOTS_TABLE_NAME
        return WorldStateClient(repo_root=self.config.repo_root, dsn=self.config.world_state_dsn, **kwargs)

    def drift_receipt(self) -> tuple[Path | None, dict[str, Any] | None]:
        if not self.config.drift_receipts_dir.exists():
            return None, None
        paths = sorted(self.config.drift_receipts_dir.glob("*.json"))
        if not paths:
            return None, None
        path = paths[-1]
        return path, json.loads(path.read_text())

    def upstream_token(self, service: GatewayService) -> str | None:
        if not service.upstream_auth_env_var:
            return None
        value = os.environ.get(service.upstream_auth_env_var, "").strip()
        return value or None

    def match_service(self, path: str) -> tuple[GatewayService, str] | None:
        full_path = "/" + path.lstrip("/")
        for service in self.service_by_prefix:
            if full_path == service.gateway_prefix or full_path.startswith(service.gateway_prefix + "/"):
                if service.strip_prefix:
                    upstream_path = full_path[len(service.gateway_prefix) :] or "/"
                else:
                    upstream_path = full_path
                if not upstream_path.startswith("/"):
                    upstream_path = "/" + upstream_path
                return service, upstream_path
        return None

    async def aggregate_service_health(self, service: GatewayService) -> dict[str, Any]:
        url = urljoin(service.upstream + "/", service.healthcheck_path.lstrip("/"))
        headers: dict[str, str] = {}
        token = self.upstream_token(service)
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            response = await self.http_client.get(url, timeout=service.timeout_seconds, headers=headers)
            healthy = 200 <= response.status_code < 400
            body: Any
            try:
                body = response.json()
            except Exception:  # noqa: BLE001
                body = response.text[:500]
            return {
                "service_id": service.id,
                "gateway_prefix": service.gateway_prefix,
                "upstream": service.upstream,
                "status": "healthy" if healthy else "unhealthy",
                "http_status": response.status_code,
                "details": body,
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "service_id": service.id,
                "gateway_prefix": service.gateway_prefix,
                "upstream": service.upstream,
                "status": "unreachable",
                "error": str(exc),
            }

    def collect_platform_health(self) -> dict[str, Any]:
        try:
            payload = self.world_state_client().get("service_health", allow_stale=True)
            source = "world_state"
        except (SurfaceNotFoundError, WorldStateUnavailable, OSError, RuntimeError):
            payload = collect_service_health(self.config.repo_root)
            source = "live_probe"

        catalog = self.primary_service_catalog()
        items = payload.get("services", []) if isinstance(payload, dict) else []
        services_by_id = {
            str(item.get("service_id") or item.get("id")): item
            for item in items
            if isinstance(item, dict) and (item.get("service_id") or item.get("id"))
        }

        services: list[dict[str, Any]] = []
        for service in catalog.get("services", []):
            if not isinstance(service, dict) or service.get("lifecycle_status") != "active":
                continue
            service_id = str(service.get("id"))
            health = services_by_id.get(service_id, {})
            status = str(health.get("status", "unknown"))
            detail = (
                health.get("detail")
                or health.get("error")
                or (
                    f"HTTP {health['http_status']}"
                    if isinstance(health, dict) and health.get("http_status") is not None
                    else "No live health data"
                )
            )
            services.append(
                {
                    "service_id": service_id,
                    "name": service.get("name", service_id),
                    "status": status,
                    "detail": str(detail),
                    "vm": service.get("vm"),
                    "vmid": service.get("vmid"),
                    "public_url": service.get("public_url"),
                    "internal_url": service.get("internal_url"),
                    "uptime_monitor_name": service.get("uptime_monitor_name"),
                    "probe_source": health.get("probe_source"),
                    "probe_kind": health.get("probe_kind"),
                    "http_status": health.get("http_status"),
                }
            )

        statuses = {item["status"] for item in services}
        overall = "healthy"
        if any(status in {"down", "error", "failed"} for status in statuses):
            overall = "degraded"
        elif any(status in {"degraded", "warn", "warning", "unhealthy", "unreachable"} for status in statuses):
            overall = "degraded"
        elif statuses and statuses == {"unknown"}:
            overall = "unknown"

        return {
            "status": overall,
            "service_count": len(services),
            "services": services,
            "source": source,
        }


def build_config() -> GatewayConfig:
    repo_root = Path(os.environ.get("LV3_GATEWAY_REPO_ROOT", REPO_ROOT))
    return GatewayConfig(
        repo_root=repo_root,
        catalog_path=Path(os.environ.get("LV3_GATEWAY_CATALOG_PATH", repo_root / "config" / "api-gateway-catalog.json")),
        service_catalog_path=Path(
            os.environ.get("LV3_GATEWAY_SERVICE_CATALOG_PATH", repo_root / "config" / "service-capability-catalog.json")
        ),
        health_probe_catalog_path=Path(
            os.environ.get("LV3_GATEWAY_HEALTH_PROBE_CATALOG_PATH", repo_root / "config" / "health-probe-catalog.json")
        ),
        workflow_catalog_path=Path(
            os.environ.get("LV3_GATEWAY_WORKFLOW_CATALOG_PATH", repo_root / "config" / "workflow-catalog.json")
        ),
        platform_vars_path=Path(
            os.environ.get("LV3_GATEWAY_PLATFORM_VARS_PATH", repo_root / "inventory" / "group_vars" / "platform.yml")
        ),
        drift_receipts_dir=Path(
            os.environ.get("LV3_GATEWAY_DRIFT_RECEIPTS_DIR", repo_root / "receipts" / "drift-reports")
        ),
        jwks_url=os.environ.get(
            "KEYCLOAK_JWKS_URL",
            "https://sso.lv3.org/realms/lv3/protocol/openid-connect/certs",
        ),
        issuer=os.environ.get("KEYCLOAK_ISSUER_URL", "https://sso.lv3.org/realms/lv3"),
        expected_audience=os.environ.get("KEYCLOAK_EXPECTED_AUDIENCE") or None,
        nats_url=os.environ.get("NATS_URL") or None,
        deploy_webhook_url=os.environ.get("LV3_GATEWAY_DEPLOY_WEBHOOK_URL") or None,
        secret_rotation_webhook_url=os.environ.get("LV3_GATEWAY_SECRET_ROTATION_WEBHOOK_URL") or None,
        graph_dsn=os.environ.get("LV3_GATEWAY_GRAPH_DSN")
        or os.environ.get("LV3_GRAPH_DSN")
        or os.environ.get("WORLD_STATE_DSN")
        or None,
        world_state_dsn=os.environ.get("LV3_GATEWAY_WORLD_STATE_DSN")
        or os.environ.get("WORLD_STATE_DSN")
        or None,
        openapi_include_upstreams=os.environ.get("LV3_GATEWAY_INCLUDE_UPSTREAM_OPENAPI", "false").lower()
        in {"1", "true", "yes"},
    )


def subject_from_claims(claims: dict[str, Any]) -> str:
    return str(claims.get("preferred_username") or claims.get("client_id") or claims.get("sub") or "unknown")


def has_required_role(identity: dict[str, Any], required_role: str) -> bool:
    roles = identity["roles"]
    if required_role in roles:
        return True
    if required_role == "platform-read" and "platform-operator" in roles:
        return True
    return False


async def require_identity(request: Request) -> dict[str, Any]:
    header = request.headers.get("Authorization", "").strip()
    if not header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = header.split(" ", 1)[1].strip()
    legacy_platform_context_token = os.environ.get("LV3_GATEWAY_PLATFORM_CONTEXT_LEGACY_TOKEN", "").strip()
    if legacy_platform_context_token and token == legacy_platform_context_token:
        identity = {
            "claims": {"sub": "platform-context-legacy-token"},
            "roles": {"platform-read", "platform-operator"},
            "subject": "platform-context-legacy-token",
            "token": token,
        }
        request.state.identity = identity
        return identity
    runtime: GatewayRuntime = request.app.state.runtime
    claims = await runtime.verifier.verify(token)
    identity = {
        "claims": claims,
        "roles": extract_roles(claims),
        "subject": subject_from_claims(claims),
        "token": token,
    }
    request.state.identity = identity
    return identity


async def emit_request_event(
    request: Request,
    *,
    identity: dict[str, Any] | None,
    status_code: int,
    started_at: float,
) -> None:
    runtime: GatewayRuntime = request.app.state.runtime
    payload = {
        "request_id": getattr(request.state, "request_id", ""),
        "method": request.method,
        "path": request.url.path,
        "status_code": status_code,
        "latency_ms": round((time.perf_counter() - started_at) * 1000, 3),
        "caller_identity": identity["subject"] if identity else "anonymous",
        "caller_roles": sorted(identity["roles"]) if identity else [],
    }
    try:
        await runtime.event_emitter.emit("platform.api.request", payload)
    except Exception:  # noqa: BLE001
        return


def require_graph_runtime(runtime: GatewayRuntime) -> DependencyGraphClient:
    if runtime.graph_client is None:
        raise HTTPException(status_code=503, detail="dependency graph runtime is not configured")
    return runtime.graph_client


def create_app(config: GatewayConfig | None = None) -> FastAPI:
    gateway_config = config or build_config()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        runtime = GatewayRuntime(gateway_config)
        app.state.runtime = runtime
        try:
            yield
        finally:
            await runtime.close()

    app = FastAPI(
        title="LV3 Platform API Gateway",
        version="1.0.0",
        description="Unified authenticated front door for LV3 platform APIs.",
        lifespan=lifespan,
    )

    @app.middleware("http")
    async def inject_request_id(request: Request, call_next):
        request.state.request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        response = await call_next(request)
        response.headers["X-Gateway-Request-ID"] = request.state.request_id
        return response

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/v1/health")
    async def gateway_health(
        request: Request,
        identity: dict[str, Any] = Depends(require_identity),
    ) -> dict[str, Any]:
        started_at = time.perf_counter()
        if not has_required_role(identity, "platform-read"):
            raise HTTPException(status_code=403, detail="missing required role 'platform-read'")
        runtime: GatewayRuntime = request.app.state.runtime
        health = await asyncio.gather(
            *(runtime.aggregate_service_health(service) for service in runtime.services)
        )
        overall = "healthy" if all(item["status"] == "healthy" for item in health) else "degraded"
        await emit_request_event(request, identity=identity, status_code=200, started_at=started_at)
        return {
            "status": overall,
            "service_count": len(health),
            "services": health,
        }

    @app.get("/v1/platform/health")
    async def platform_health(
        request: Request,
        identity: dict[str, Any] = Depends(require_identity),
    ) -> dict[str, Any]:
        started_at = time.perf_counter()
        if not has_required_role(identity, "platform-read"):
            raise HTTPException(status_code=403, detail="missing required role 'platform-read'")
        runtime: GatewayRuntime = request.app.state.runtime
        payload = await asyncio.to_thread(runtime.collect_platform_health)
        await emit_request_event(request, identity=identity, status_code=200, started_at=started_at)
        return payload

    @app.get("/v1/platform/health/{service_id}")
    async def platform_service_health(
        service_id: str,
        request: Request,
        identity: dict[str, Any] = Depends(require_identity),
    ) -> dict[str, Any]:
        started_at = time.perf_counter()
        if not has_required_role(identity, "platform-read"):
            raise HTTPException(status_code=403, detail="missing required role 'platform-read'")
        runtime: GatewayRuntime = request.app.state.runtime
        payload = await asyncio.to_thread(runtime.collect_platform_health)
        for service in payload["services"]:
            if service["service_id"] == service_id:
                await emit_request_event(request, identity=identity, status_code=200, started_at=started_at)
                return service
        raise HTTPException(status_code=404, detail=f"unknown service '{service_id}'")

    @app.get("/v1/platform/services")
    async def platform_services(
        request: Request,
        identity: dict[str, Any] = Depends(require_identity),
    ) -> dict[str, Any]:
        started_at = time.perf_counter()
        if not has_required_role(identity, "platform-read"):
            raise HTTPException(status_code=403, detail="missing required role 'platform-read'")
        runtime: GatewayRuntime = request.app.state.runtime
        catalog = runtime.primary_service_catalog()
        gateway_services = {service.id: service for service in runtime.services}
        services = []
        for service in catalog.get("services", []):
            if not isinstance(service, dict):
                continue
            item = dict(service)
            gateway = gateway_services.get(item.get("id"))
            if gateway:
                item["gateway_prefix"] = gateway.gateway_prefix
            services.append(item)
        await emit_request_event(request, identity=identity, status_code=200, started_at=started_at)
        return {"count": len(services), "services": services}

    @app.get("/v1/platform/drift")
    async def platform_drift(
        request: Request,
        identity: dict[str, Any] = Depends(require_identity),
    ) -> dict[str, Any]:
        started_at = time.perf_counter()
        if not has_required_role(identity, "platform-read"):
            raise HTTPException(status_code=403, detail="missing required role 'platform-read'")
        runtime: GatewayRuntime = request.app.state.runtime
        path, payload = runtime.drift_receipt()
        await emit_request_event(request, identity=identity, status_code=200, started_at=started_at)
        if payload is None:
            return {"status": "unknown", "summary": None, "receipt_path": None}
        return {
            "status": payload.get("summary", {}).get("status", "unknown"),
            "summary": payload.get("summary"),
            "receipt_path": str(path.relative_to(runtime.config.repo_root)) if path else None,
        }

    @app.get("/v1/platform/topology")
    async def platform_topology(
        request: Request,
        identity: dict[str, Any] = Depends(require_identity),
    ) -> dict[str, Any]:
        started_at = time.perf_counter()
        if not has_required_role(identity, "platform-read"):
            raise HTTPException(status_code=403, detail="missing required role 'platform-read'")
        runtime: GatewayRuntime = request.app.state.runtime
        platform_vars = runtime.platform_vars()
        await emit_request_event(request, identity=identity, status_code=200, started_at=started_at)
        return {
            "guest_catalog": platform_vars.get("platform_guest_catalog", {}),
            "service_topology": platform_vars.get("platform_service_topology", {}),
            "public_edge": platform_vars.get("public_edge_service_topology", {}),
        }

    @app.get("/v1/search")
    async def platform_search(
        request: Request,
        q: str = Query(min_length=2),
        collection: str | None = Query(default=None),
        limit: int = Query(default=10, ge=1, le=25),
        identity: dict[str, Any] = Depends(require_identity),
    ) -> dict[str, Any]:
        started_at = time.perf_counter()
        if not has_required_role(identity, "platform-read"):
            raise HTTPException(status_code=403, detail="missing required role 'platform-read'")
        runtime: GatewayRuntime = request.app.state.runtime
        payload = runtime.search_client.query(q, collection=collection, limit=limit)
        await emit_request_event(request, identity=identity, status_code=200, started_at=started_at)
        return payload

    @app.get("/v1/platform/search")
    async def platform_search_legacy(
        request: Request,
        q: str = Query(min_length=2),
        collection: str | None = Query(default=None),
        limit: int = Query(default=10, ge=1, le=25),
        identity: dict[str, Any] = Depends(require_identity),
    ) -> dict[str, Any]:
        return await platform_search(request, q=q, collection=collection, limit=limit, identity=identity)

    @app.get("/v1/graph/nodes")
    async def graph_nodes(
        request: Request,
        identity: dict[str, Any] = Depends(require_identity),
    ) -> dict[str, Any]:
        started_at = time.perf_counter()
        if not has_required_role(identity, "platform-read"):
            raise HTTPException(status_code=403, detail="missing required role 'platform-read'")
        runtime: GatewayRuntime = request.app.state.runtime
        graph_client = require_graph_runtime(runtime)
        nodes = graph_client.list_nodes()
        await emit_request_event(request, identity=identity, status_code=200, started_at=started_at)
        return {"count": len(nodes), "nodes": nodes}

    @app.get("/v1/graph/nodes/{node_id:path}/descendants")
    async def graph_descendants(
        node_id: str,
        request: Request,
        identity: dict[str, Any] = Depends(require_identity),
    ) -> dict[str, Any]:
        started_at = time.perf_counter()
        if not has_required_role(identity, "platform-read"):
            raise HTTPException(status_code=403, detail="missing required role 'platform-read'")
        runtime: GatewayRuntime = request.app.state.runtime
        graph_client = require_graph_runtime(runtime)
        try:
            descendants = graph_client.descendants(node_id)
        except NodeNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        await emit_request_event(request, identity=identity, status_code=200, started_at=started_at)
        return {"node_id": node_id, "count": len(descendants), "nodes": descendants}

    @app.get("/v1/graph/nodes/{node_id:path}/ancestors")
    async def graph_ancestors(
        node_id: str,
        request: Request,
        identity: dict[str, Any] = Depends(require_identity),
    ) -> dict[str, Any]:
        started_at = time.perf_counter()
        if not has_required_role(identity, "platform-read"):
            raise HTTPException(status_code=403, detail="missing required role 'platform-read'")
        runtime: GatewayRuntime = request.app.state.runtime
        graph_client = require_graph_runtime(runtime)
        try:
            ancestors = graph_client.ancestors(node_id)
        except NodeNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        await emit_request_event(request, identity=identity, status_code=200, started_at=started_at)
        return {"node_id": node_id, "count": len(ancestors), "nodes": ancestors}

    @app.get("/v1/graph/nodes/{node_id:path}/health")
    async def graph_health(
        node_id: str,
        request: Request,
        identity: dict[str, Any] = Depends(require_identity),
    ) -> dict[str, Any]:
        started_at = time.perf_counter()
        if not has_required_role(identity, "platform-read"):
            raise HTTPException(status_code=403, detail="missing required role 'platform-read'")
        runtime: GatewayRuntime = request.app.state.runtime
        graph_client = require_graph_runtime(runtime)
        try:
            payload = graph_client.node_health(node_id)
        except NodeNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        await emit_request_event(request, identity=identity, status_code=200, started_at=started_at)
        return payload

    @app.get("/v1/graph/path")
    async def graph_path(
        from_node: str,
        to_node: str,
        request: Request,
        identity: dict[str, Any] = Depends(require_identity),
    ) -> dict[str, Any]:
        started_at = time.perf_counter()
        if not has_required_role(identity, "platform-read"):
            raise HTTPException(status_code=403, detail="missing required role 'platform-read'")
        runtime: GatewayRuntime = request.app.state.runtime
        graph_client = require_graph_runtime(runtime)
        try:
            path_nodes = graph_client.path(from_node, to_node)
        except NodeNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        await emit_request_event(request, identity=identity, status_code=200, started_at=started_at)
        return {
            "from_node": from_node,
            "to_node": to_node,
            "path": path_nodes,
            "hop_count": max(len(path_nodes) - 1, 0),
        }

    @app.post("/v1/platform/deploy", status_code=202)
    async def platform_deploy(
        body: DeployRequest,
        request: Request,
        identity: dict[str, Any] = Depends(require_identity),
    ) -> dict[str, Any]:
        started_at = time.perf_counter()
        if not has_required_role(identity, "platform-operator"):
            raise HTTPException(status_code=403, detail="missing required role 'platform-operator'")
        runtime: GatewayRuntime = request.app.state.runtime
        workflow = runtime.workflow_catalog().get("workflows", {}).get("deploy-and-promote")
        if workflow is None:
            raise HTTPException(status_code=500, detail="deploy-and-promote workflow missing from catalog")

        response_payload = {
            "request_id": request.state.request_id,
            "workflow_id": "deploy-and-promote",
            "service_id": body.service_id,
            "environment": body.environment,
            "queued": False,
            "mode": "reference",
            "parameters": body.parameters,
            "workflow": workflow,
        }
        if body.execute and runtime.config.deploy_webhook_url:
            webhook_payload = {
                "workflow_id": "deploy-and-promote",
                "service_id": body.service_id,
                "environment": body.environment,
                "requested_by": identity["subject"],
                "parameters": body.parameters,
            }
            webhook_response = await runtime.http_client.post(
                runtime.config.deploy_webhook_url,
                json=webhook_payload,
                timeout=15,
            )
            response_payload["queued"] = 200 <= webhook_response.status_code < 300
            response_payload["mode"] = "executed"
            response_payload["webhook_status"] = webhook_response.status_code

        await emit_request_event(request, identity=identity, status_code=202, started_at=started_at)
        return response_payload

    @app.post("/v1/platform/secrets/rotate", status_code=202)
    async def platform_rotate_secret(
        body: SecretRotationRequest,
        request: Request,
        identity: dict[str, Any] = Depends(require_identity),
    ) -> dict[str, Any]:
        started_at = time.perf_counter()
        if not has_required_role(identity, "platform-operator"):
            raise HTTPException(status_code=403, detail="missing required role 'platform-operator'")
        runtime: GatewayRuntime = request.app.state.runtime
        workflow = runtime.workflow_catalog().get("workflows", {}).get("rotate-secret")
        if workflow is None:
            raise HTTPException(status_code=500, detail="rotate-secret workflow missing from catalog")

        response_payload = {
            "request_id": request.state.request_id,
            "workflow_id": "rotate-secret",
            "secret_id": body.secret_id,
            "queued": False,
            "mode": "reference",
            "parameters": body.parameters,
            "workflow": workflow,
        }
        if body.execute and runtime.config.secret_rotation_webhook_url:
            webhook_payload = {
                "workflow_id": "rotate-secret",
                "secret_id": body.secret_id,
                "requested_by": identity["subject"],
                "parameters": body.parameters,
            }
            webhook_response = await runtime.http_client.post(
                runtime.config.secret_rotation_webhook_url,
                json=webhook_payload,
                timeout=15,
            )
            response_payload["queued"] = 200 <= webhook_response.status_code < 300
            response_payload["mode"] = "executed"
            response_payload["webhook_status"] = webhook_response.status_code

        await emit_request_event(request, identity=identity, status_code=202, started_at=started_at)
        return response_payload

    @app.get("/v1/openapi.json")
    async def gateway_openapi(
        request: Request,
        identity: dict[str, Any] = Depends(require_identity),
    ) -> JSONResponse:
        started_at = time.perf_counter()
        if not has_required_role(identity, "platform-read"):
            raise HTTPException(status_code=403, detail="missing required role 'platform-read'")
        runtime: GatewayRuntime = request.app.state.runtime
        schema = app.openapi()
        schema["x-lv3-gateway-catalog"] = runtime.catalog_payload

        if runtime.config.openapi_include_upstreams:
            upstream_schemas: dict[str, Any] = {}
            for service in runtime.services:
                if not service.openapi_path:
                    continue
                url = urljoin(service.upstream + "/", service.openapi_path.lstrip("/"))
                headers: dict[str, str] = {}
                token = runtime.upstream_token(service)
                if token:
                    headers["Authorization"] = f"Bearer {token}"
                try:
                    response = await runtime.http_client.get(url, timeout=service.timeout_seconds, headers=headers)
                    if response.status_code == 200:
                        upstream_schemas[service.id] = response.json()
                except Exception:  # noqa: BLE001
                    continue
            schema["x-lv3-upstream-openapi"] = upstream_schemas

        await emit_request_event(request, identity=identity, status_code=200, started_at=started_at)
        return JSONResponse(schema)

    @app.api_route(
        "/v1/{service_path:path}",
        methods=["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"],
    )
    async def proxy_service(
        service_path: str,
        request: Request,
        identity: dict[str, Any] = Depends(require_identity),
    ) -> Response:
        started_at = time.perf_counter()
        runtime: GatewayRuntime = request.app.state.runtime
        matched = runtime.match_service(f"/v1/{service_path}")
        if matched is None:
            raise HTTPException(status_code=404, detail="unknown gateway route")
        service, upstream_path = matched
        if not has_required_role(identity, service.required_role):
            raise HTTPException(
                status_code=403,
                detail=f"missing required role '{service.required_role}' for {service.id}",
            )

        headers = {
            key: value
            for key, value in request.headers.items()
            if key.lower()
            not in {
                "authorization",
                "connection",
                "content-length",
                "host",
            }
        }
        headers["X-Gateway-Request-ID"] = request.state.request_id
        headers["X-Caller-Identity"] = identity["subject"]

        if service.forward_authorization:
            headers["Authorization"] = f"Bearer {identity['token']}"
        else:
            upstream_token = runtime.upstream_token(service)
            if upstream_token:
                headers["Authorization"] = f"Bearer {upstream_token}"

        url = urljoin(service.upstream + "/", upstream_path.lstrip("/"))
        body = await request.body()
        upstream_response = await runtime.http_client.request(
            request.method,
            url,
            params=request.query_params,
            content=body,
            headers=headers,
            timeout=service.timeout_seconds,
        )

        await emit_request_event(
            request,
            identity=identity,
            status_code=upstream_response.status_code,
            started_at=started_at,
        )
        excluded = {"content-encoding", "content-length", "transfer-encoding", "connection"}
        response_headers = {
            key: value for key, value in upstream_response.headers.items() if key.lower() not in excluded
        }
        return Response(
            content=upstream_response.content,
            status_code=upstream_response.status_code,
            headers=response_headers,
            media_type=upstream_response.headers.get("content-type"),
        )

    return app


app = create_app()
