from __future__ import annotations

import asyncio
import base64
import hashlib
import importlib.util
import json
import os
import socket
import sys
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

def _resolve_repo_root(script_path: Path | None = None) -> Path:
    resolved_path = (script_path or Path(__file__)).resolve()
    for candidate in resolved_path.parents:
        if (candidate / "platform" / "__init__.py").exists():
            return candidate
    raise RuntimeError(f"unable to resolve repo root for {resolved_path}")


REPO_ROOT = _resolve_repo_root()
import httpx
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

REPO_PLATFORM_ROOT = REPO_ROOT / "platform"
REPO_SCRIPTS_ROOT = REPO_ROOT / "scripts"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_SCRIPTS_ROOT))
if "platform" in sys.modules and not hasattr(sys.modules["platform"], "__path__"):
    del sys.modules["platform"]


def _load_repo_platform_package() -> None:
    current = sys.modules.get("platform")
    current_file = getattr(current, "__file__", "") or ""
    if current_file.startswith(str(REPO_PLATFORM_ROOT)):
        return
    spec = importlib.util.spec_from_file_location(
        "platform",
        REPO_PLATFORM_ROOT / "__init__.py",
        submodule_search_locations=[str(REPO_PLATFORM_ROOT)],
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load repo platform package from {REPO_PLATFORM_ROOT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["platform"] = module
    spec.loader.exec_module(module)


_load_repo_platform_package()

from api_gateway_catalog import load_api_gateway_catalog
GRAPH_RUNTIME_IMPORT_ERROR: str | None = None

try:
    from platform.circuit import CircuitOpenError, CircuitRegistry, should_count_httpx_exception, should_count_socket_exception
except Exception as exc:  # noqa: BLE001
    CircuitOpenError = RuntimeError  # type: ignore[assignment]
    CircuitRegistry = Any  # type: ignore[assignment]

    def should_count_httpx_exception(exc: BaseException) -> bool:
        return isinstance(exc, Exception)

    def should_count_socket_exception(exc: BaseException) -> bool:
        return isinstance(exc, Exception)

    GRAPH_RUNTIME_IMPORT_ERROR = str(exc) if GRAPH_RUNTIME_IMPORT_ERROR is None else GRAPH_RUNTIME_IMPORT_ERROR

try:
    from platform.graph import DependencyGraphClient, NodeNotFoundError
except Exception as exc:  # noqa: BLE001
    DependencyGraphClient = Any  # type: ignore[assignment]

    class NodeNotFoundError(RuntimeError):
        pass

    GRAPH_RUNTIME_IMPORT_ERROR = str(exc)
from platform.agent import AgentCoordinationStore
from platform.events import build_envelope
from platform.health import HealthCompositeClient, ServiceHealthNotFoundError
from platform.logging import clear_context, generate_trace_id, get_logger, set_context
from platform.retry import async_with_retry, policy_for_surface
from platform.timeouts import TimeoutContext, resolve_timeout_seconds
from platform.world_state.client import SurfaceNotFoundError, WorldStateClient, WorldStateUnavailable
from platform.world_state.materializer import SQLITE_CURRENT_VIEW_NAME, SQLITE_SNAPSHOTS_TABLE_NAME
from platform.world_state.workers import collect_service_health

try:
    from search_fabric import SearchClient
except ImportError:  # pragma: no cover - packaged import path
    from scripts.search_fabric import SearchClient


HTTP_LOGGER = get_logger("api_gateway", "http", name="lv3.api_gateway.http")
RUNTIME_LOGGER = get_logger("api_gateway", "runtime", name="lv3.api_gateway.runtime")


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


RETRY_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


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
    nats_username: str | None
    nats_password: str | None
    deploy_webhook_url: str | None
    secret_rotation_webhook_url: str | None
    openapi_include_upstreams: bool
    circuit_policy_path: Path
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
        circuit_breaker: Any | None = None,
    ) -> None:
        self._jwks_url = jwks_url
        self._issuer = issuer
        self._expected_audience = expected_audience
        self._clock_skew_seconds = clock_skew_seconds
        self._client = client
        self._circuit_breaker = circuit_breaker
        self._jwks_cache: dict[str, Any] | None = None
        self._jwks_cache_expiry = 0.0
        self._lock = asyncio.Lock()
        self._retry_policy = policy_for_surface("internal_api")

    async def _load_jwks(self) -> dict[str, Any]:
        now = time.time()
        if self._jwks_cache is not None and now < self._jwks_cache_expiry:
            return self._jwks_cache

        async with self._lock:
            now = time.time()
            if self._jwks_cache is not None and now < self._jwks_cache_expiry:
                return self._jwks_cache

            async def fetch_jwks() -> dict[str, Any]:
                response = await async_with_retry(
                    lambda: self._client.get(
                        self._jwks_url,
                        timeout=resolve_timeout_seconds("http_request"),
                    ),
                    policy=self._retry_policy,
                    error_context="keycloak jwks fetch",
                )
                response.raise_for_status()
                return response.json()

            try:
                if self._circuit_breaker is not None:
                    self._jwks_cache = await self._circuit_breaker.call(fetch_jwks)
                else:
                    self._jwks_cache = await fetch_jwks()
            except CircuitOpenError as exc:
                if self._jwks_cache is not None and now < self._jwks_cache_expiry:
                    return self._jwks_cache
                raise HTTPException(
                    status_code=503,
                    detail={
                        "code": "GATE_CIRCUIT_OPEN",
                        "circuit": "keycloak",
                        "message": "Keycloak JWKS is temporarily unavailable.",
                        "retry_after": exc.retry_after,
                    },
                    headers={"Retry-After": str(exc.retry_after)},
                ) from exc
            except Exception as exc:  # noqa: BLE001
                raise HTTPException(
                    status_code=503,
                    detail={
                        "code": "GATE_DEPENDENCY_UNAVAILABLE",
                        "circuit": "keycloak",
                        "message": f"Keycloak JWKS fetch failed: {exc}",
                    },
                ) from exc
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
    def __init__(self, nats_url: str | None, *, circuit_breaker: Any | None = None) -> None:
        self._parsed = urlparse(nats_url) if nats_url else None
        self._retry_policy = policy_for_surface("nats_publish")
        self._circuit_breaker = circuit_breaker

    async def emit(self, subject: str, payload: dict[str, Any]) -> None:
        if self._parsed is None:
            return
        host = self._parsed.hostname or "127.0.0.1"
        port = self._parsed.port or 4222
        envelope = build_envelope(subject, payload, actor_id="service/api-gateway")
        encoded = json.dumps(envelope, separators=(",", ":")).encode()
        async def publish() -> None:
            await async_with_retry(
                lambda: asyncio.to_thread(self._publish, host, port, subject, encoded),
                policy=self._retry_policy,
                error_context=f"gateway nats publish {subject}",
            )

        try:
            if self._circuit_breaker is not None:
                await self._circuit_breaker.call(publish)
            else:
                await publish()
        except CircuitOpenError:
            return

    @staticmethod
    def _publish(host: str, port: int, subject: str, payload: bytes) -> None:
        with socket.create_connection(
            (host, port),
            timeout=resolve_timeout_seconds("liveness_probe", 3),
        ) as sock:
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
        self.circuit_registry = CircuitRegistry(
            config.repo_root,
            policies_path=config.circuit_policy_path,
            nats_url=config.nats_url,
        )
        self.verifier = KeycloakJWTVerifier(
            jwks_url=config.jwks_url,
            issuer=config.issuer,
            expected_audience=config.expected_audience,
            clock_skew_seconds=config.clock_skew_seconds,
            client=self.http_client,
            circuit_breaker=self.circuit_registry.async_breaker(
                "keycloak",
                exception_classifier=should_count_httpx_exception,
            )
            if self.circuit_registry.has_policy("keycloak")
            else None,
        )
        self.event_emitter = NatsEventEmitter(
            config.nats_url,
            circuit_breaker=self.circuit_registry.async_breaker(
                "nats",
                exception_classifier=should_count_socket_exception,
            )
            if self.circuit_registry.has_policy("nats")
            else None,
        )
        self.internal_api_retry_policy = policy_for_surface("internal_api")
        coordination_credentials = {}
        if config.nats_username and config.nats_password:
            coordination_credentials = {"user": config.nats_username, "password": config.nats_password}
        self.coordination_store = AgentCoordinationStore(
            repo_root=config.repo_root,
            nats_url=config.nats_url,
            nats_credentials=coordination_credentials,
        )
        self.graph_client = None
        if config.graph_dsn and GRAPH_RUNTIME_IMPORT_ERROR is None:
            self.graph_client = DependencyGraphClient(
                dsn=config.graph_dsn,
                world_state_dsn=config.world_state_dsn or config.graph_dsn,
            )
        self.health_client = HealthCompositeClient(
            repo_root=config.repo_root,
            dsn=config.world_state_dsn or config.graph_dsn,
            world_state_dsn=config.world_state_dsn,
            ledger_dsn=config.world_state_dsn or config.graph_dsn,
        )

    def service_circuit(self, service_id: str) -> Any | None:
        if not self.circuit_registry.has_policy(service_id):
            return None
        return self.circuit_registry.async_breaker(
            service_id,
            exception_classifier=should_count_httpx_exception,
        )
    @staticmethod
    def api_call_context(requested_seconds: int | float | None = None) -> TimeoutContext:
        return TimeoutContext.for_layer("api_call_chain", requested_seconds)

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

    def coordination_snapshot(self) -> dict[str, Any]:
        return self.coordination_store.snapshot()

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
            async def fetch() -> httpx.Response:
                response = await async_with_retry(
                    lambda: self.http_client.get(
                        url,
                        timeout=self.api_call_context(service.timeout_seconds).timeout_for(
                            "http_request",
                            service.timeout_seconds,
                            reserve_seconds=1.0,
                        ),
                        headers=headers,
                    ),
                    policy=self.internal_api_retry_policy,
                    error_context=f"gateway health probe {service.id}",
                )
                response.raise_for_status()
                return response

            circuit = self.service_circuit(service.id)
            if circuit is not None:
                response = await circuit.call(fetch)
            else:
                response = await fetch()
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
        except CircuitOpenError as exc:
            return {
                "service_id": service.id,
                "gateway_prefix": service.gateway_prefix,
                "upstream": service.upstream,
                "status": "circuit_open",
                "error": f"circuit open for {exc.retry_after}s",
                "retry_after": exc.retry_after,
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
        catalog = self.primary_service_catalog()
        services_by_id = {
            entry.service_id: entry.as_dict()
            for entry in self.health_client.get_all(allow_stale=True)
        }

        services: list[dict[str, Any]] = []
        for service in catalog.get("services", []):
            if not isinstance(service, dict) or service.get("lifecycle_status") != "active":
                continue
            service_id = str(service.get("id"))
            health = services_by_id.get(service_id) or {
                "service_id": service_id,
                "status": "unknown",
                "composite_status": "unknown",
                "composite_score": 0.0,
                "safe_to_act": False,
                "signals": [],
                "reason": "health composite entry unavailable",
                "stale": True,
            }
            item = dict(health)
            item.update(
                {
                    "service_id": service_id,
                    "name": service.get("name", service_id),
                    "vm": service.get("vm"),
                    "vmid": service.get("vmid"),
                    "public_url": service.get("public_url"),
                    "internal_url": service.get("internal_url"),
                    "uptime_monitor_name": service.get("uptime_monitor_name"),
                }
            )
            services.append(item)

        statuses = {item["composite_status"] for item in services}
        overall = "healthy"
        if any(status == "critical" for status in statuses):
            overall = "degraded"
        elif any(status == "degraded" for status in statuses):
            overall = "degraded"
        elif statuses and statuses <= {"unknown"}:
            overall = "unknown"

        return {
            "status": overall,
            "service_count": len(services),
            "safe_service_count": sum(1 for item in services if item.get("safe_to_act") is True),
            "unsafe_service_count": sum(1 for item in services if item.get("safe_to_act") is False),
            "services": services,
            "source": "health_composite",
        }

    def collect_platform_service_health(self, service_id: str) -> dict[str, Any]:
        payload = self.collect_platform_health()
        for service in payload["services"]:
            if service["service_id"] == service_id:
                return service
        raise ServiceHealthNotFoundError(service_id)


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
        nats_username=os.environ.get("LV3_NATS_USERNAME") or None,
        nats_password=os.environ.get("LV3_NATS_PASSWORD") or None,
        deploy_webhook_url=os.environ.get("LV3_GATEWAY_DEPLOY_WEBHOOK_URL") or None,
        secret_rotation_webhook_url=os.environ.get("LV3_GATEWAY_SECRET_ROTATION_WEBHOOK_URL") or None,
        graph_dsn=os.environ.get("LV3_GATEWAY_GRAPH_DSN")
        or os.environ.get("LV3_GRAPH_DSN")
        or os.environ.get("WORLD_STATE_DSN")
        or None,
        circuit_policy_path=Path(
            os.environ.get("LV3_GATEWAY_CIRCUIT_POLICY_PATH", repo_root / "config" / "circuit-policies.yaml")
        ),
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
        set_context(actor_id=identity["subject"])
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
    set_context(actor_id=identity["subject"])
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
        "trace_id": getattr(request.state, "trace_id", ""),
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
        detail = "dependency graph runtime is not configured"
        if GRAPH_RUNTIME_IMPORT_ERROR:
            detail = f"dependency graph runtime unavailable: {GRAPH_RUNTIME_IMPORT_ERROR}"
        raise HTTPException(status_code=503, detail=detail)
    return runtime.graph_client


def create_app(config: GatewayConfig | None = None) -> FastAPI:
    gateway_config = config or build_config()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        runtime = GatewayRuntime(gateway_config)
        app.state.runtime = runtime
        RUNTIME_LOGGER.info(
            "Gateway runtime initialized",
            extra={
                "trace_id": "startup",
                "workflow_id": "converge-api-gateway",
                "target": "service:api_gateway",
            },
        )
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
        request.state.trace_id = request.headers.get("X-Trace-Id") or generate_trace_id()
        set_context(trace_id=request.state.trace_id, request_id=request.state.request_id)
        started_at = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            HTTP_LOGGER.exception(
                "Unhandled request failure",
                extra={
                    "path": request.url.path,
                    "method": request.method,
                    "status_code": 500,
                    "duration_ms": round((time.perf_counter() - started_at) * 1000, 3),
                    "target": request.url.path,
                },
            )
            clear_context()
            raise

        response.headers["X-Gateway-Request-ID"] = request.state.request_id
        response.headers["X-Trace-Id"] = request.state.trace_id
        identity = getattr(request.state, "identity", None)
        HTTP_LOGGER.info(
            "Request completed",
            extra={
                "path": request.url.path,
                "method": request.method,
                "status_code": response.status_code,
                "duration_ms": round((time.perf_counter() - started_at) * 1000, 3),
                "actor_id": identity["subject"] if identity else "anonymous",
                "target": request.url.path,
            },
        )
        clear_context()
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
        try:
            payload = await asyncio.to_thread(runtime.collect_platform_service_health, service_id)
        except ServiceHealthNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        await emit_request_event(request, identity=identity, status_code=200, started_at=started_at)
        return payload

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

    @app.get("/v1/platform/agents")
    async def platform_agents(
        request: Request,
        identity: dict[str, Any] = Depends(require_identity),
    ) -> dict[str, Any]:
        started_at = time.perf_counter()
        if not has_required_role(identity, "platform-read"):
            raise HTTPException(status_code=403, detail="missing required role 'platform-read'")
        runtime: GatewayRuntime = request.app.state.runtime
        payload = await asyncio.to_thread(runtime.coordination_snapshot)
        await emit_request_event(request, identity=identity, status_code=200, started_at=started_at)
        return payload

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
                "trace_id": request.state.trace_id,
                "parameters": body.parameters,
            }
            timeout_ctx = runtime.api_call_context()
            webhook_response = await runtime.http_client.post(
                runtime.config.deploy_webhook_url,
                json=webhook_payload,
                timeout=timeout_ctx.timeout_for("http_request", reserve_seconds=1.0),
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
                "trace_id": request.state.trace_id,
                "parameters": body.parameters,
            }
            timeout_ctx = runtime.api_call_context()
            webhook_response = await runtime.http_client.post(
                runtime.config.secret_rotation_webhook_url,
                json=webhook_payload,
                timeout=timeout_ctx.timeout_for("http_request", reserve_seconds=1.0),
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
                    async def fetch() -> httpx.Response:
                        response = await async_with_retry(
                            lambda: runtime.http_client.get(
                                url,
                                timeout=runtime.api_call_context(service.timeout_seconds).timeout_for(
                                    "http_request",
                                    service.timeout_seconds,
                                    reserve_seconds=1.0,
                                ),
                                headers=headers,
                            ),
                            policy=runtime.internal_api_retry_policy,
                            error_context=f"gateway openapi fetch {service.id}",
                        )
                        response.raise_for_status()
                        return response

                    circuit = runtime.service_circuit(service.id)
                    if circuit is not None:
                        response = await circuit.call(fetch)
                    else:
                        response = await fetch()
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
                "x-trace-id",
                "x-gateway-request-id",
                "x-caller-identity",
            }
        }
        headers["X-Gateway-Request-ID"] = request.state.request_id
        headers["X-Trace-Id"] = request.state.trace_id
        headers["X-Caller-Identity"] = identity["subject"]

        if service.forward_authorization:
            headers["Authorization"] = f"Bearer {identity['token']}"
        else:
            upstream_token = runtime.upstream_token(service)
            if upstream_token:
                headers["Authorization"] = f"Bearer {upstream_token}"

        url = urljoin(service.upstream + "/", upstream_path.lstrip("/"))
        body = await request.body()
        async def forward_request() -> httpx.Response:
            return await runtime.http_client.request(
                request.method,
                url,
                params=request.query_params,
                content=body,
                headers=headers,
                timeout=runtime.api_call_context(service.timeout_seconds).timeout_for(
                    "http_request",
                    service.timeout_seconds,
                    reserve_seconds=1.0,
                ),
            )

        async def execute_request() -> httpx.Response:
            if request.method in RETRY_SAFE_METHODS:
                return await async_with_retry(
                    forward_request,
                    policy=runtime.internal_api_retry_policy,
                    error_context=f"gateway proxy {service.id} {request.method} {upstream_path}",
                )
            return await forward_request()

        try:
            circuit = runtime.service_circuit(service.id)
            if circuit is not None:
                upstream_response = await circuit.call(execute_request)
            else:
                upstream_response = await execute_request()
        except CircuitOpenError as exc:
            await emit_request_event(
                request,
                identity=identity,
                status_code=503,
                started_at=started_at,
            )
            return JSONResponse(
                status_code=503,
                headers={"Retry-After": str(exc.retry_after)},
                content={
                    "code": "GATE_CIRCUIT_OPEN",
                    "circuit": service.id,
                    "message": f"{service.name} is temporarily unavailable.",
                    "retry_after": exc.retry_after,
                },
            )
        except httpx.HTTPError as exc:
            await emit_request_event(
                request,
                identity=identity,
                status_code=502,
                started_at=started_at,
            )
            return JSONResponse(
                status_code=502,
                content={
                    "code": "GATE_DEPENDENCY_UNAVAILABLE",
                    "service": service.id,
                    "message": str(exc),
                },
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
