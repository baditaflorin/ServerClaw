from __future__ import annotations

import asyncio
import base64
import hmac
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
        platform_init = candidate / "platform" / "__init__.py"
        packaged_gateway = candidate / "api_gateway" / "main.py"
        source_gateway = candidate / "scripts" / "api_gateway" / "main.py"
        if platform_init.exists() and (packaged_gateway.exists() or source_gateway.exists()):
            return candidate
    raise RuntimeError(f"unable to resolve repo root for {resolved_path}")


REPO_ROOT = _resolve_repo_root()
import httpx
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from fastapi import Body, Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
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
from agent_tool_registry import call_tool, load_agent_tool_registry
from canonical_errors import ErrorRegistry
GRAPH_RUNTIME_IMPORT_ERROR: str | None = None

try:
    from platform.circuit import (
        CircuitOpenError,
        CircuitRegistry,
        MemoryCircuitStateBackend,
        should_count_httpx_exception,
        should_count_socket_exception,
    )
except Exception as exc:  # noqa: BLE001
    CircuitOpenError = RuntimeError  # type: ignore[assignment]
    CircuitRegistry = Any  # type: ignore[assignment]
    MemoryCircuitStateBackend = Any  # type: ignore[assignment]

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
from platform.degradation import DegradationStateStore
from platform.events import build_envelope
from platform.health import HealthCompositeClient, ServiceHealthNotFoundError
from platform.logging import clear_context, generate_trace_id, get_logger, set_context
from platform.retry import async_with_retry, policy_for_surface
from platform.runtime_assurance import (
    ServiceAttestationNotFoundError,
    collect_declared_live_attestations,
    collect_declared_live_service_attestation,
)
from platform.timeouts import TimeoutContext, resolve_timeout_seconds
from platform.use_cases.runbooks import RunbookRunStore, RunbookSurfaceError, RunbookUseCaseService, WindmillWorkflowRunner
from platform.world_state.client import SurfaceNotFoundError, WorldStateClient, WorldStateUnavailable
from platform.world_state.materializer import SQLITE_CURRENT_VIEW_NAME, SQLITE_SNAPSHOTS_TABLE_NAME
from platform.world_state.workers import collect_service_health

try:
    from search_fabric import SearchClient
except ImportError:  # pragma: no cover - packaged import path
    from scripts.search_fabric import SearchClient

try:
    from scripts.runtime_assurance import build_runtime_assurance_report
except ImportError:  # pragma: no cover - packaged import path
    from runtime_assurance import build_runtime_assurance_report


HTTP_LOGGER = get_logger("api_gateway", "http", name="lv3.api_gateway.http")
RUNTIME_LOGGER = get_logger("api_gateway", "runtime", name="lv3.api_gateway.runtime")
REQUEST_EVENT_TIMEOUT_SECONDS = 1.0


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


class RunbookExecuteRequest(BaseModel):
    runbook_id: str = Field(min_length=2)
    parameters: dict[str, Any] = Field(default_factory=dict)
    delivery_surface: str = Field(default="api_gateway")


class BillingEventInput(BaseModel):
    transaction_id: str = Field(min_length=1)
    external_subscription_id: str = Field(min_length=1)
    code: str = Field(min_length=1)
    timestamp: str | None = None
    properties: dict[str, Any] = Field(default_factory=dict)


class BillingEventRequest(BaseModel):
    event: BillingEventInput


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
    upstream_auth_header: str | None = None
    upstream_auth_scheme: str = "bearer"


@dataclass(frozen=True)
class BillingProducer:
    id: str
    name: str
    token: str
    allowed_metric_codes: frozenset[str]
    allowed_external_subscription_ids: frozenset[str]


@dataclass(frozen=True)
class GatewayConfig:
    repo_root: Path
    catalog_path: Path
    service_catalog_path: Path
    error_registry_path: Path
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
    windmill_base_url: str | None
    windmill_token: str | None
    runbook_runs_dir: Path
    openapi_include_upstreams: bool
    circuit_policy_path: Path
    degradation_state_path: Path
    nats_outbox_path: Path
    graph_dsn: str | None = None
    world_state_dsn: str | None = None
    clock_skew_seconds: int = 30
    keycloak_retry_after_seconds: int = 30
    dify_tools_api_key: str | None = None
    dify_tools_api_key_header: str = "X-LV3-Dify-Api-Key"
    billing_api_base_url: str | None = None
    billing_ingest_producers_path: Path = Path("/config/billing-ingest-producers.json")
    billing_rejection_subject: str = "billing.events.rejected"
    billing_org_api_key: str | None = None
    typesense_base_url: str | None = None
    typesense_api_key: str | None = None


class TypesenseStructuredSearchClient:
    _COLLECTION_PROFILES = {
        "platform-services": {
            "query_by": "name,description,tags,category,vm,exposure,subdomain,runbook,adr,health_probe_id",
            "facet_by": "category,exposure,vm,lifecycle_status,tags",
        }
    }

    def __init__(self, *, base_url: str, api_key: str, client: httpx.AsyncClient) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._client = client

    @staticmethod
    def _quoted_filter_value(value: str) -> str:
        return f"`{value.replace('`', '')}`"

    async def search(
        self,
        query: str,
        *,
        collection: str,
        limit: int,
        filters: dict[str, str],
    ) -> dict[str, Any]:
        profile = self._COLLECTION_PROFILES.get(collection)
        if profile is None:
            raise HTTPException(status_code=404, detail=f"unknown structured-search collection '{collection}'")
        filter_parts = [
            f"{field}:={self._quoted_filter_value(value)}"
            for field, value in sorted(filters.items())
            if value.strip()
        ]
        params = {
            "q": query,
            "query_by": profile["query_by"],
            "facet_by": profile["facet_by"],
            "per_page": str(limit),
        }
        if filter_parts:
            params["filter_by"] = " && ".join(filter_parts)
        try:
            response = await self._client.get(
                f"{self._base_url}/collections/{collection}/documents/search",
                params=params,
                headers={"X-TYPESENSE-API-KEY": self._api_key},
                timeout=resolve_timeout_seconds("http_request", 5),
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=503, detail="structured search dependency is unavailable") from exc
        payload = response.json()
        hits = payload.get("hits", [])
        results = []
        for hit in hits:
            if not isinstance(hit, dict):
                continue
            document = hit.get("document", {})
            if not isinstance(document, dict):
                continue
            result = dict(document)
            result["text_match"] = hit.get("text_match")
            result["highlights"] = hit.get("highlights", [])
            results.append(result)
        return {
            "backend": "typesense",
            "collection": collection,
            "query": query,
            "count": len(results),
            "found": int(payload.get("found", len(results))),
            "facet_counts": payload.get("facet_counts", []),
            "results": results,
        }


class KeycloakJWTVerifier:
    def __init__(
        self,
        *,
        jwks_url: str,
        issuer: str | None,
        expected_audience: str | None,
        clock_skew_seconds: int,
        client: httpx.AsyncClient,
        degradation_store: DegradationStateStore | None,
        degradation_mode: dict[str, Any] | None,
        retry_after_seconds: int,
        circuit_breaker: Any | None = None,
    ) -> None:
        self._jwks_url = jwks_url
        self._issuer = issuer
        self._expected_audience = expected_audience
        self._clock_skew_seconds = clock_skew_seconds
        self._client = client
        self._degradation_store = degradation_store
        self._degradation_mode = degradation_mode
        self._retry_after_seconds = retry_after_seconds
        self._circuit_breaker = circuit_breaker
        self._jwks_cache: dict[str, Any] | None = None
        self._jwks_cache_expiry = 0.0
        self._lock = asyncio.Lock()
        self._retry_policy = policy_for_surface("internal_api")
        self._refresh_window_seconds = 30

    def _activate_degradation(self, error: str, *, stale_until: float | None = None) -> None:
        if self._degradation_store is None:
            return
        metadata: dict[str, Any] = {}
        if stale_until is not None:
            metadata["cache_valid_until_epoch"] = int(stale_until)
        self._degradation_store.activate(
            "api_gateway",
            self._degradation_mode,
            source="keycloak_jwks",
            last_error=error,
            metadata=metadata,
        )

    def _clear_degradation(self) -> None:
        if self._degradation_store is None:
            return
        dependency = str((self._degradation_mode or {}).get("dependency") or "keycloak")
        self._degradation_store.clear("api_gateway", dependency)

    def _dependency_unavailable(self, retry_after: int) -> HTTPException:
        return HTTPException(
            status_code=503,
            detail={
                "code": "GATE_CIRCUIT_OPEN",
                "error_code": "GATE_CIRCUIT_OPEN",
                "circuit": "keycloak",
                "dependency": "keycloak",
                "message": "Keycloak is unavailable and the JWKS cache has expired.",
                "retry_after": retry_after,
                "retry_after_s": retry_after,
            },
            headers={"Retry-After": str(retry_after)},
        )

    async def _fetch_jwks(self) -> dict[str, Any]:
        async def fetch() -> dict[str, Any]:
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

        if self._circuit_breaker is not None:
            return await self._circuit_breaker.call(fetch)
        return await fetch()

    async def _refresh_jwks(self, *, allow_stale: bool) -> dict[str, Any]:
        now = time.time()
        try:
            self._jwks_cache = await self._fetch_jwks()
        except CircuitOpenError as exc:
            cached_valid = self._jwks_cache is not None and now < self._jwks_cache_expiry
            if allow_stale and cached_valid:
                self._activate_degradation(str(exc), stale_until=self._jwks_cache_expiry)
                return self._jwks_cache
            self._activate_degradation(str(exc))
            raise self._dependency_unavailable(exc.retry_after) from exc
        except Exception as exc:  # noqa: BLE001
            cached_valid = self._jwks_cache is not None and now < self._jwks_cache_expiry
            if allow_stale and cached_valid:
                self._activate_degradation(str(exc), stale_until=self._jwks_cache_expiry)
                return self._jwks_cache
            self._activate_degradation(str(exc))
            raise self._dependency_unavailable(self._retry_after_seconds) from exc
        self._jwks_cache_expiry = now + 300
        self._clear_degradation()
        return self._jwks_cache

    async def _load_jwks(self) -> dict[str, Any]:
        now = time.time()
        if self._jwks_cache is not None and now < self._jwks_cache_expiry:
            if now >= self._jwks_cache_expiry - self._refresh_window_seconds:
                async with self._lock:
                    return await self._refresh_jwks(allow_stale=True)
            return self._jwks_cache

        async with self._lock:
            now = time.time()
            if self._jwks_cache is not None and now < self._jwks_cache_expiry:
                if now >= self._jwks_cache_expiry - self._refresh_window_seconds:
                    return await self._refresh_jwks(allow_stale=True)
                return self._jwks_cache
            return await self._refresh_jwks(allow_stale=False)

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
    def __init__(
        self,
        nats_url: str | None,
        *,
        username: str | None = None,
        password: str | None = None,
        outbox_path: Path,
        degradation_store: DegradationStateStore | None,
        degradation_mode: dict[str, Any] | None,
        circuit_breaker: Any | None = None,
    ) -> None:
        self._parsed = urlparse(nats_url) if nats_url else None
        self._username = (username or "").strip() or None
        self._password = (password or "").strip() or None
        self._retry_policy = policy_for_surface("nats_publish")
        self._outbox_path = outbox_path
        self._degradation_store = degradation_store
        self._degradation_mode = degradation_mode
        self._circuit_breaker = circuit_breaker

    async def emit(self, subject: str, payload: dict[str, Any]) -> None:
        if self._parsed is None:
            return
        host = self._parsed.hostname or "127.0.0.1"
        port = self._parsed.port or 4222
        envelope = build_envelope(subject, payload, actor_id="service/api-gateway")
        encoded = json.dumps(envelope, separators=(",", ":")).encode()

        try:
            await self._flush_outbox(host, port)
            await self._publish_live(host, port, subject, encoded)
        except Exception as exc:  # noqa: BLE001
            self._append_outbox(subject, encoded)
            self._activate_degradation(str(exc))
            return
        self._clear_degradation()

    def _activate_degradation(self, error: str) -> None:
        if self._degradation_store is None:
            return
        self._degradation_store.activate(
            "api_gateway",
            self._degradation_mode,
            source="nats_publish",
            last_error=error,
            metadata={"outbox_path": str(self._outbox_path)},
        )

    def _clear_degradation(self) -> None:
        if self._degradation_store is None:
            return
        dependency = str((self._degradation_mode or {}).get("dependency") or "nats")
        self._degradation_store.clear("api_gateway", dependency)

    def _append_outbox(self, subject: str, payload: bytes) -> None:
        self._outbox_path.parent.mkdir(parents=True, exist_ok=True)
        entry = {"subject": subject, "payload": payload.decode("utf-8")}
        with self._outbox_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, separators=(",", ":")) + "\n")

    async def _flush_outbox(self, host: str, port: int) -> None:
        if not self._outbox_path.exists():
            return
        lines = self._outbox_path.read_text(encoding="utf-8").splitlines()
        remaining: list[str] = []
        for index, line in enumerate(lines):
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                subject = str(entry["subject"])
                payload = str(entry["payload"]).encode("utf-8")
            except (KeyError, TypeError, ValueError):
                continue
            try:
                await self._publish_live(host, port, subject, payload)
            except Exception:  # noqa: BLE001
                remaining = lines[index:]
                break
        if remaining:
            self._outbox_path.write_text("\n".join(remaining) + "\n", encoding="utf-8")
            raise ConnectionError("unable to flush buffered NATS events")
        self._outbox_path.unlink(missing_ok=True)

    async def _publish_live(self, host: str, port: int, subject: str, payload: bytes) -> None:
        async def publish() -> None:
            await async_with_retry(
                lambda: asyncio.to_thread(
                    self._publish,
                    host,
                    port,
                    subject,
                    payload,
                    username=self._username,
                    password=self._password,
                ),
                policy=self._retry_policy,
                error_context=f"gateway nats publish {subject}",
            )

        if self._circuit_breaker is not None:
            await self._circuit_breaker.call(publish)
            return
        await publish()

    @staticmethod
    def _publish(
        host: str,
        port: int,
        subject: str,
        payload: bytes,
        *,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        connect_payload: dict[str, Any] = {"verbose": False}
        if username:
            connect_payload["user"] = username
        if password:
            connect_payload["pass"] = password
        with socket.create_connection(
            (host, port),
            timeout=resolve_timeout_seconds("liveness_probe", 3),
        ) as sock:
            connect_frame = json.dumps(connect_payload, separators=(",", ":")).encode()
            sock.sendall(b"CONNECT " + connect_frame + b"\r\n")
            sock.sendall(f"PUB {subject} {len(payload)}\r\n".encode() + payload + b"\r\n")


class GatewayRuntime:
    def __init__(self, config: GatewayConfig) -> None:
        self.config = config
        self.error_registry = ErrorRegistry.load(config.error_registry_path)
        self.catalog_payload, normalized_catalog = load_api_gateway_catalog(
            config.catalog_path,
            service_catalog_path=config.service_catalog_path,
        )
        self._service_catalog = json_file(config.service_catalog_path, {"services": []})
        self.services = [GatewayService(**service) for service in normalized_catalog]
        self.service_by_prefix = sorted(self.services, key=lambda service: len(service.gateway_prefix), reverse=True)
        self.billing_producers = self._load_billing_producers(config.billing_ingest_producers_path)
        self.http_client = httpx.AsyncClient(follow_redirects=False)
        self.search_client = SearchClient(config.repo_root)
        self.structured_search_client = (
            TypesenseStructuredSearchClient(
                base_url=config.typesense_base_url,
                api_key=config.typesense_api_key,
                client=self.http_client,
            )
            if config.typesense_base_url and config.typesense_api_key
            else None
        )
        self.degradation_store = DegradationStateStore(config.degradation_state_path)
        self.circuit_registry = CircuitRegistry(
            config.repo_root,
            policies_path=config.circuit_policy_path,
            backend=MemoryCircuitStateBackend(),
        )
        self.verifier = KeycloakJWTVerifier(
            jwks_url=config.jwks_url,
            issuer=config.issuer,
            expected_audience=config.expected_audience,
            clock_skew_seconds=config.clock_skew_seconds,
            client=self.http_client,
            degradation_store=self.degradation_store,
            degradation_mode=self.degradation_mode("api_gateway", "keycloak"),
            retry_after_seconds=config.keycloak_retry_after_seconds,
            circuit_breaker=self.circuit_registry.async_breaker(
                "keycloak",
                exception_classifier=should_count_httpx_exception,
            )
            if self.circuit_registry.has_policy("keycloak")
            else None,
        )
        self.event_emitter = NatsEventEmitter(
            config.nats_url,
            username=config.nats_username,
            password=config.nats_password,
            outbox_path=config.nats_outbox_path,
            degradation_store=self.degradation_store,
            degradation_mode=self.degradation_mode("api_gateway", "nats"),
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
        self._runbook_service: RunbookUseCaseService | None = None

    @staticmethod
    def _load_billing_producers(path: Path) -> list[BillingProducer]:
        payload = json_file(path, {"producers": []})
        raw_producers = payload.get("producers", [])
        if not isinstance(raw_producers, list):
            return []
        producers: list[BillingProducer] = []
        for item in raw_producers:
            if not isinstance(item, dict):
                continue
            producer_id = str(item.get("id") or "").strip()
            token = str(item.get("token") or "").strip()
            if not producer_id or not token:
                continue
            producers.append(
                BillingProducer(
                    id=producer_id,
                    name=str(item.get("name") or producer_id).strip() or producer_id,
                    token=token,
                    allowed_metric_codes=frozenset(
                        str(code).strip()
                        for code in item.get("allowed_metric_codes", [])
                        if isinstance(code, str) and code.strip()
                    ),
                    allowed_external_subscription_ids=frozenset(
                        str(external_id).strip()
                        for external_id in item.get("allowed_external_subscription_ids", [])
                        if isinstance(external_id, str) and external_id.strip()
                    ),
                )
            )
        return producers

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
        return self._service_catalog

    def degradation_mode(self, service_id: str, dependency: str) -> dict[str, Any] | None:
        services = self._service_catalog.get("services", [])
        for service in services:
            if not isinstance(service, dict) or service.get("id") != service_id:
                continue
            for mode in service.get("degradation_modes", []):
                if isinstance(mode, dict) and mode.get("dependency") == dependency:
                    return mode
        return None

    def active_degradations(self) -> dict[str, list[dict[str, Any]]]:
        return self.degradation_store.all_active()

    def workflow_catalog(self) -> dict[str, Any]:
        return json_file(self.config.workflow_catalog_path, {"workflows": {}})

    def runbook_service(self) -> RunbookUseCaseService:
        if self._runbook_service is None:
            if not self.config.windmill_base_url or not self.config.windmill_token:
                raise RuntimeError("runbook execution requires LV3_GATEWAY_WINDMILL_BASE_URL and LV3_GATEWAY_WINDMILL_TOKEN")
            self._runbook_service = RunbookUseCaseService(
                repo_root=self.config.repo_root,
                workflow_runner=WindmillWorkflowRunner(
                    base_url=self.config.windmill_base_url,
                    token=self.config.windmill_token,
                    repo_root=self.config.repo_root,
                ),
                store=RunbookRunStore(self.config.runbook_runs_dir),
            )
        return self._runbook_service

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

    def billing_service(self) -> GatewayService | None:
        return next((service for service in self.services if service.id == "lago"), None)

    def billing_enabled(self) -> bool:
        return bool((self.config.billing_api_base_url or "").strip()) and bool((self.config.billing_org_api_key or "").strip())

    def find_billing_producer(self, token: str) -> BillingProducer | None:
        for producer in self.billing_producers:
            if hmac.compare_digest(token, producer.token):
                return producer
        return None

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
        active_degradations = self.active_degradations()

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
            item["active_degradations"] = active_degradations.get(service_id, [])
            if item["active_degradations"] and item.get("composite_status") == "healthy":
                item["status"] = "degraded"
                item["composite_status"] = "degraded"
                item["safe_to_act"] = False
            services.append(item)

        statuses = {item["composite_status"] for item in services}
        overall = "healthy"
        if any(status == "critical" for status in statuses):
            overall = "degraded"
        elif any(status == "degraded" for status in statuses):
            overall = "degraded"
        elif statuses and statuses <= {"unknown"}:
            overall = "unknown"
        if any(item["active_degradations"] for item in services):
            overall = "degraded"

        return {
            "status": overall,
            "service_count": len(services),
            "safe_service_count": sum(1 for item in services if item.get("safe_to_act") is True),
            "unsafe_service_count": sum(1 for item in services if item.get("safe_to_act") is False),
            "degraded_service_count": sum(1 for item in services if item["active_degradations"]),
            "services": services,
            "source": "health_composite",
        }

    def collect_platform_service_health(self, service_id: str) -> dict[str, Any]:
        payload = self.collect_platform_health()
        for service in payload["services"]:
            if service["service_id"] == service_id:
                return service
        raise ServiceHealthNotFoundError(service_id)

    def collect_platform_attestation(self, environment: str = "production") -> dict[str, Any]:
        return collect_declared_live_attestations(
            repo_root=self.config.repo_root,
            environment=environment,
            world_state_dsn=self.config.world_state_dsn,
        )

    def collect_platform_service_attestation(self, service_id: str, environment: str = "production") -> dict[str, Any]:
        return collect_declared_live_service_attestation(
            service_id,
            repo_root=self.config.repo_root,
            environment=environment,
            world_state_dsn=self.config.world_state_dsn,
        )

    def collect_runtime_assurance(self) -> dict[str, Any]:
        return build_runtime_assurance_report(
            repo_root=self.config.repo_root,
            service_catalog=self.primary_service_catalog(),
            publication_registry=json_file(
                self.config.repo_root / "config" / "subdomain-exposure-registry.json",
                {"publications": []},
            ),
            health_payload=self.collect_platform_health(),
        )


def build_config() -> GatewayConfig:
    repo_root = Path(os.environ.get("LV3_GATEWAY_REPO_ROOT", REPO_ROOT))
    return GatewayConfig(
        repo_root=repo_root,
        catalog_path=Path(os.environ.get("LV3_GATEWAY_CATALOG_PATH", repo_root / "config" / "api-gateway-catalog.json")),
        service_catalog_path=Path(
            os.environ.get("LV3_GATEWAY_SERVICE_CATALOG_PATH", repo_root / "config" / "service-capability-catalog.json")
        ),
        error_registry_path=Path(
            os.environ.get("LV3_GATEWAY_ERROR_REGISTRY_PATH", repo_root / "config" / "error-codes.yaml")
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
        windmill_base_url=os.environ.get("LV3_GATEWAY_WINDMILL_BASE_URL") or None,
        windmill_token=os.environ.get("LV3_GATEWAY_WINDMILL_TOKEN") or None,
        runbook_runs_dir=Path(os.environ.get("LV3_GATEWAY_RUNBOOK_RUNS_DIR", "/data/runbooks/runs")),
        degradation_state_path=Path(
            os.environ.get("LV3_GATEWAY_DEGRADATION_STATE_PATH", "/data/degradation-state.json")
        ),
        nats_outbox_path=Path(
            os.environ.get("LV3_GATEWAY_NATS_OUTBOX_PATH", "/data/nats-outbox.jsonl")
        ),
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
        keycloak_retry_after_seconds=int(os.environ.get("LV3_GATEWAY_KEYCLOAK_RETRY_AFTER_SECONDS", "30")),
        dify_tools_api_key=os.environ.get("LV3_DIFY_TOOLS_API_KEY") or None,
        dify_tools_api_key_header=os.environ.get("LV3_DIFY_TOOLS_API_KEY_HEADER", "X-LV3-Dify-Api-Key"),
        billing_api_base_url=os.environ.get("LV3_GATEWAY_BILLING_API_BASE_URL") or None,
        billing_ingest_producers_path=Path(
            os.environ.get("LV3_GATEWAY_BILLING_INGEST_PRODUCERS_PATH", "/config/billing-ingest-producers.json")
        ),
        billing_rejection_subject=os.environ.get("LV3_GATEWAY_BILLING_REJECTION_SUBJECT", "billing.events.rejected"),
        billing_org_api_key=os.environ.get("LV3_GATEWAY_BILLING_ORG_API_KEY") or None,
        typesense_base_url=os.environ.get("LV3_GATEWAY_TYPESENSE_BASE_URL") or None,
        typesense_api_key=os.environ.get("LV3_GATEWAY_TYPESENSE_API_KEY") or None,
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


def require_dify_tools_identity(request: Request) -> dict[str, Any]:
    runtime: GatewayRuntime = request.app.state.runtime
    expected_api_key = (runtime.config.dify_tools_api_key or "").strip()
    if not expected_api_key:
        raise HTTPException(status_code=503, detail="dify tools api key is not configured")

    header_name = runtime.config.dify_tools_api_key_header
    provided_api_key = request.headers.get(header_name, "").strip()
    if not provided_api_key:
        raise HTTPException(status_code=401, detail="missing dify tools api key")
    if not hmac.compare_digest(provided_api_key, expected_api_key):
        raise HTTPException(status_code=401, detail="invalid dify tools api key")

    identity = {
        "claims": {"sub": "service/dify"},
        "roles": {"service-automation"},
        "subject": "service/dify",
    }
    set_context(actor_id=identity["subject"])
    request.state.identity = identity
    return identity


async def require_billing_producer_identity(request: Request) -> dict[str, Any]:
    runtime: GatewayRuntime = request.app.state.runtime
    header = request.headers.get("Authorization", "").strip()
    if not header.startswith("Bearer "):
        await emit_billing_rejection(
            runtime,
            request,
            reason_code="missing_producer_token",
            reason="Billing producer token is required.",
            payload={},
        )
        raise HTTPException(status_code=401, detail="missing billing producer token")

    token = header.split(" ", 1)[1].strip()
    producer = runtime.find_billing_producer(token)
    if producer is None:
        await emit_billing_rejection(
            runtime,
            request,
            reason_code="invalid_producer_token",
            reason="Billing producer token is invalid.",
            payload={},
        )
        raise HTTPException(status_code=401, detail="invalid billing producer token")

    identity = {
        "claims": {"sub": f"billing-producer:{producer.id}"},
        "roles": {"billing-producer"},
        "subject": f"billing-producer:{producer.id}",
        "producer": producer,
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
        await asyncio.wait_for(
            runtime.event_emitter.emit("platform.api.request", payload),
            timeout=REQUEST_EVENT_TIMEOUT_SECONDS,
        )
    except Exception:  # noqa: BLE001
        return


def request_trace_id(request: Request) -> str:
    return getattr(request.state, "trace_id", "") or getattr(request.state, "request_id", "") or generate_trace_id()


def dump_model(model: BaseModel) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump(exclude_none=True)
    return model.dict(exclude_none=True)


def registry_error_response(
    runtime: GatewayRuntime,
    request: Request,
    code: str,
    *,
    message: str | None = None,
    context: dict[str, Any] | None = None,
    retry_after: int | None = None,
) -> JSONResponse:
    error = runtime.error_registry.create(
        code,
        trace_id=request_trace_id(request),
        message=message,
        context=context or {},
        retry_after_s=retry_after,
    )
    response = JSONResponse(status_code=error.http_status, content=error.to_response())
    if error.retry_after_s is not None:
        response.headers["Retry-After"] = str(error.retry_after_s)
    return response


async def emit_billing_rejection(
    runtime: GatewayRuntime,
    request: Request,
    *,
    reason_code: str,
    reason: str,
    payload: dict[str, Any],
    producer: BillingProducer | None = None,
    context: dict[str, Any] | None = None,
) -> None:
    envelope = {
        "request_id": getattr(request.state, "request_id", ""),
        "trace_id": request_trace_id(request),
        "path": request.url.path,
        "producer_id": producer.id if producer else None,
        "reason_code": reason_code,
        "reason": reason,
        "context": context or {},
        "payload": payload,
    }
    try:
        await asyncio.wait_for(
            runtime.event_emitter.emit(runtime.config.billing_rejection_subject, envelope),
            timeout=REQUEST_EVENT_TIMEOUT_SECONDS,
        )
    except Exception:  # noqa: BLE001
        return


def validation_error_context(exc: RequestValidationError) -> dict[str, Any]:
    errors = exc.errors()
    if not errors:
        return {}
    first = errors[0]
    return {
        "field_path": ".".join(str(item) for item in first.get("loc", [])) or "request",
        "error_type": str(first.get("type") or "validation_error"),
        "validation_message": str(first.get("msg") or "request validation failed"),
    }


def canonical_error_from_http_exception(request: Request, exc: HTTPException) -> tuple[str, str | None, dict[str, Any], int | None]:
    raw_detail = exc.detail
    detail = raw_detail if isinstance(raw_detail, str) else str(raw_detail)
    detail_lower = detail.lower()
    context: dict[str, Any] = {}
    retry_after: int | None = None
    if exc.headers and exc.headers.get("Retry-After"):
        try:
            retry_after = int(exc.headers["Retry-After"])
        except ValueError:
            retry_after = None

    if exc.status_code == 401:
        if "billing producer token" in detail_lower:
            if "missing" in detail_lower:
                return (
                    "AUTH_TOKEN_MISSING",
                    "Billing producer token is required for this endpoint.",
                    {"header": "Authorization"},
                    retry_after,
                )
            return (
                "AUTH_TOKEN_INVALID",
                "Billing producer token could not be validated.",
                {"header": "Authorization", "reason": "token_validation"},
                retry_after,
            )
        if "dify tools api key" in detail_lower:
            header = "X-LV3-Dify-Api-Key"
            if "missing" in detail_lower:
                return (
                    "AUTH_TOKEN_MISSING",
                    "Dify tools API key is required for this endpoint.",
                    {"header": header},
                    retry_after,
                )
            return (
                "AUTH_TOKEN_INVALID",
                "Dify tools API key could not be validated.",
                {"header": header, "reason": "token_validation"},
                retry_after,
            )
        if "missing bearer token" in detail_lower:
            return (
                "AUTH_TOKEN_MISSING",
                "Bearer token is required for this endpoint.",
                {"header": "Authorization"},
                retry_after,
            )
        if "expired bearer token" in detail_lower:
            return (
                "AUTH_TOKEN_EXPIRED",
                "Bearer token has expired.",
                {"reason": "expired"},
                retry_after,
            )
        return (
            "AUTH_TOKEN_INVALID",
            "Bearer token could not be validated.",
            {"reason": "token_validation"},
            retry_after,
        )

    if exc.status_code == 403:
        required_role = ""
        if "missing required role '" in detail:
            required_role = detail.split("missing required role '", 1)[1].split("'", 1)[0]
        identity = getattr(request.state, "identity", None) or {}
        service_id = request.path_params.get("service_id") or request.path_params.get("service_path")
        return (
            "AUTH_INSUFFICIENT_ROLE",
            "Caller identity is authenticated but lacks the required role.",
            {
                "required_role": required_role,
                "subject": identity.get("subject", "anonymous"),
                "service_id": str(service_id or ""),
            },
            retry_after,
        )

    if exc.status_code == 404:
        path = request.url.path
        if "unknown workflow" in detail_lower:
            return (
                "INPUT_UNKNOWN_WORKFLOW",
                f"Unknown workflow: {request.path_params.get('workflow_id', '')}",
                {"workflow_id": str(request.path_params.get("workflow_id", ""))},
                retry_after,
            )
        if "unknown command" in detail_lower:
            return (
                "INPUT_UNKNOWN_COMMAND",
                f"Unknown command: {request.path_params.get('command_id', '')}",
                {"command_id": str(request.path_params.get("command_id", ""))},
                retry_after,
            )
        if "unknown gateway route" in detail_lower:
            return (
                "INPUT_UNKNOWN_GATEWAY_ROUTE",
                "Requested gateway route is not registered.",
                {"path": path},
                retry_after,
            )
        service_id = request.path_params.get("service_id")
        if service_id:
            return (
                "INPUT_UNKNOWN_SERVICE",
                detail,
                {"service_id": str(service_id)},
                retry_after,
            )
        return (
            "INPUT_UNKNOWN_GATEWAY_ROUTE",
            "Requested gateway route is not registered.",
            {"path": path},
            retry_after,
        )

    if exc.status_code == 503:
        dependency = "platform-runtime"
        context_detail: Any = detail
        message = detail or "Required runtime dependency is unavailable."
        if isinstance(raw_detail, dict):
            dependency = str(raw_detail.get("dependency") or dependency)
            context_detail = raw_detail
            raw_message = raw_detail.get("message")
            if isinstance(raw_message, str) and raw_message.strip():
                message = raw_message
        return (
            "INFRA_RUNTIME_UNAVAILABLE",
            message,
            {"dependency": dependency, "detail": context_detail},
            retry_after,
        )

    if exc.status_code >= 500:
        return (
            "INTERNAL_UNEXPECTED_ERROR",
            detail or "Unexpected internal platform error.",
            {"detail": detail or "internal_error"},
            retry_after,
        )

    return (
        "INTERNAL_UNEXPECTED_ERROR",
        detail or "Unexpected internal platform error.",
        {"detail": detail or "internal_error"},
        retry_after,
    )


def require_graph_runtime(runtime: GatewayRuntime) -> DependencyGraphClient:
    if runtime.graph_client is None:
        detail = "dependency graph runtime is not configured"
        if GRAPH_RUNTIME_IMPORT_ERROR:
            detail = f"dependency graph runtime unavailable: {GRAPH_RUNTIME_IMPORT_ERROR}"
        raise HTTPException(status_code=503, detail=detail)
    return runtime.graph_client


def require_runbook_service(runtime: GatewayRuntime) -> RunbookUseCaseService:
    try:
        return runtime.runbook_service()
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "dependency": "runbook_runtime",
                "message": str(exc),
            },
        ) from exc


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
        request.state.request_started_at = started_at
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

    @app.exception_handler(HTTPException)
    async def handle_http_exception(request: Request, exc: HTTPException) -> JSONResponse:
        runtime: GatewayRuntime = request.app.state.runtime
        code, message, context, retry_after = canonical_error_from_http_exception(request, exc)
        error = runtime.error_registry.create(
            code,
            trace_id=request_trace_id(request),
            message=message,
            context=context,
            retry_after_s=retry_after,
        )
        response = JSONResponse(status_code=error.http_status, content=error.to_response())
        if error.retry_after_s is not None:
            response.headers["Retry-After"] = str(error.retry_after_s)
        return response

    @app.exception_handler(RequestValidationError)
    async def handle_request_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        runtime: GatewayRuntime = request.app.state.runtime
        error = runtime.error_registry.create(
            "INPUT_SCHEMA_INVALID",
            trace_id=request_trace_id(request),
            message="Request payload or parameters failed validation.",
            context=validation_error_context(exc),
        )
        return JSONResponse(status_code=error.http_status, content=error.to_response())

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        runtime: GatewayRuntime = request.app.state.runtime
        error = runtime.error_registry.create(
            "INTERNAL_UNEXPECTED_ERROR",
            trace_id=request_trace_id(request),
            message="Unexpected internal platform error.",
            context={"detail": type(exc).__name__},
        )
        return JSONResponse(status_code=error.http_status, content=error.to_response())

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

    @app.get("/v1/platform/runtime-assurance")
    async def platform_runtime_assurance(
        request: Request,
        identity: dict[str, Any] = Depends(require_identity),
    ) -> dict[str, Any]:
        started_at = time.perf_counter()
        if not has_required_role(identity, "platform-read"):
            raise HTTPException(status_code=403, detail="missing required role 'platform-read'")
        runtime: GatewayRuntime = request.app.state.runtime
        payload = await asyncio.to_thread(runtime.collect_runtime_assurance)
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
        active_degradations = runtime.active_degradations()
        services = []
        for service in catalog.get("services", []):
            if not isinstance(service, dict):
                continue
            item = dict(service)
            gateway = gateway_services.get(item.get("id"))
            if gateway:
                item["gateway_prefix"] = gateway.gateway_prefix
            item["active_degradations"] = active_degradations.get(str(item.get("id")), [])
            services.append(item)
        await emit_request_event(request, identity=identity, status_code=200, started_at=started_at)
        return {"count": len(services), "services": services}

    @app.get("/v1/platform/attestation")
    async def platform_attestation(
        request: Request,
        environment: str = Query(default="production"),
        identity: dict[str, Any] = Depends(require_identity),
    ) -> dict[str, Any]:
        started_at = time.perf_counter()
        if not has_required_role(identity, "platform-read"):
            raise HTTPException(status_code=403, detail="missing required role 'platform-read'")
        runtime: GatewayRuntime = request.app.state.runtime
        payload = await asyncio.to_thread(runtime.collect_platform_attestation, environment)
        await emit_request_event(request, identity=identity, status_code=200, started_at=started_at)
        return payload

    @app.get("/v1/platform/attestation/{service_id}")
    async def platform_service_attestation(
        service_id: str,
        request: Request,
        environment: str = Query(default="production"),
        identity: dict[str, Any] = Depends(require_identity),
    ) -> dict[str, Any]:
        started_at = time.perf_counter()
        if not has_required_role(identity, "platform-read"):
            raise HTTPException(status_code=403, detail="missing required role 'platform-read'")
        runtime: GatewayRuntime = request.app.state.runtime
        try:
            payload = await asyncio.to_thread(runtime.collect_platform_service_attestation, service_id, environment)
        except ServiceAttestationNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        await emit_request_event(request, identity=identity, status_code=200, started_at=started_at)
        return payload

    @app.get("/v1/platform/degradations")
    async def platform_degradations(
        request: Request,
        identity: dict[str, Any] = Depends(require_identity),
    ) -> dict[str, Any]:
        started_at = time.perf_counter()
        if not has_required_role(identity, "platform-read"):
            raise HTTPException(status_code=403, detail="missing required role 'platform-read'")
        runtime: GatewayRuntime = request.app.state.runtime
        payload = await asyncio.to_thread(runtime.active_degradations)
        await emit_request_event(request, identity=identity, status_code=200, started_at=started_at)
        return {
            "degradation_count": sum(len(entries) for entries in payload.values()),
            "services": payload,
        }

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

    @app.get("/v1/search/structured")
    @app.get("/v1/platform/search/structured")
    async def platform_structured_search(
        request: Request,
        q: str = Query(min_length=2),
        collection: str = Query(default="platform-services"),
        limit: int = Query(default=10, ge=1, le=25),
        category: str | None = Query(default=None),
        exposure: str | None = Query(default=None),
        vm: str | None = Query(default=None),
        lifecycle_status: str | None = Query(default=None),
        identity: dict[str, Any] = Depends(require_identity),
    ) -> dict[str, Any]:
        started_at = time.perf_counter()
        if not has_required_role(identity, "platform-read"):
            raise HTTPException(status_code=403, detail="missing required role 'platform-read'")
        runtime: GatewayRuntime = request.app.state.runtime
        if runtime.structured_search_client is None:
            raise HTTPException(status_code=503, detail="structured search is unavailable")
        payload = await runtime.structured_search_client.search(
            q,
            collection=collection,
            limit=limit,
            filters={
                "category": category or "",
                "exposure": exposure or "",
                "vm": vm or "",
                "lifecycle_status": lifecycle_status or "",
            },
        )
        await emit_request_event(request, identity=identity, status_code=200, started_at=started_at)
        return payload

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

    @app.get("/v1/platform/runbooks")
    async def platform_runbooks(
        request: Request,
        delivery_surface: str = Query(default="api_gateway"),
        identity: dict[str, Any] = Depends(require_identity),
    ) -> dict[str, Any]:
        started_at = time.perf_counter()
        if not has_required_role(identity, "platform-read"):
            raise HTTPException(status_code=403, detail="missing required role 'platform-read'")
        runtime: GatewayRuntime = request.app.state.runtime
        service = require_runbook_service(runtime)
        runbooks = await asyncio.to_thread(service.list_runbooks, surface=delivery_surface)
        await emit_request_event(request, identity=identity, status_code=200, started_at=started_at)
        return {
            "request_id": request.state.request_id,
            "delivery_surface": delivery_surface,
            "runbooks": runbooks,
        }

    @app.post("/v1/platform/runbooks/execute")
    async def platform_runbook_execute(
        body: RunbookExecuteRequest,
        request: Request,
        identity: dict[str, Any] = Depends(require_identity),
    ) -> dict[str, Any]:
        started_at = time.perf_counter()
        if not has_required_role(identity, "platform-operator"):
            raise HTTPException(status_code=403, detail="missing required role 'platform-operator'")
        runtime: GatewayRuntime = request.app.state.runtime
        service = require_runbook_service(runtime)
        try:
            record = await asyncio.to_thread(
                service.execute,
                body.runbook_id,
                body.parameters,
                actor_id=identity["subject"],
                surface=body.delivery_surface,
            )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=f"unknown runbook: {body.runbook_id}") from exc
        except RunbookSurfaceError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        await emit_request_event(request, identity=identity, status_code=200, started_at=started_at)
        return {
            "request_id": request.state.request_id,
            "run_id": record["run_id"],
            "runbook_id": record["runbook_id"],
            "status": record["status"],
            "delivery_surface": body.delivery_surface,
            "message": f"Runbook {record['runbook_id']} finished with status {record['status']}.",
        }

    @app.get("/v1/platform/runbooks/{run_id}")
    async def platform_runbook_status(
        run_id: str,
        request: Request,
        identity: dict[str, Any] = Depends(require_identity),
    ) -> dict[str, Any]:
        started_at = time.perf_counter()
        if not has_required_role(identity, "platform-read"):
            raise HTTPException(status_code=403, detail="missing required role 'platform-read'")
        runtime: GatewayRuntime = request.app.state.runtime
        service = require_runbook_service(runtime)
        try:
            record = await asyncio.to_thread(service.status, run_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=f"runbook run not found: {run_id}") from exc
        await emit_request_event(request, identity=identity, status_code=200, started_at=started_at)
        return record

    @app.post("/v1/platform/runbooks/{run_id}/approve")
    async def platform_runbook_approve(
        run_id: str,
        request: Request,
        identity: dict[str, Any] = Depends(require_identity),
    ) -> dict[str, Any]:
        started_at = time.perf_counter()
        if not has_required_role(identity, "platform-operator"):
            raise HTTPException(status_code=403, detail="missing required role 'platform-operator'")
        runtime: GatewayRuntime = request.app.state.runtime
        service = require_runbook_service(runtime)
        try:
            record = await asyncio.to_thread(service.resume, run_id, actor_id=identity["subject"])
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=f"runbook run not found: {run_id}") from exc
        await emit_request_event(request, identity=identity, status_code=200, started_at=started_at)
        return {
            "request_id": request.state.request_id,
            "run_id": record["run_id"],
            "runbook_id": record["runbook_id"],
            "status": record["status"],
            "message": f"Runbook {record['runbook_id']} finished with status {record['status']}.",
        }

    @app.post("/v1/dify-tools/{tool_name}")
    async def dify_tools_call(
        tool_name: str,
        request: Request,
        body: dict[str, Any] = Body(default_factory=dict),
    ) -> Any:
        started_at = time.perf_counter()
        identity = require_dify_tools_identity(request)
        try:
            registry, _workflow_catalog = await asyncio.to_thread(load_agent_tool_registry)
        except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=503, detail=f"agent tool registry unavailable: {exc}") from exc

        try:
            result, _audit_event = await asyncio.to_thread(
                call_tool,
                registry,
                tool_name,
                body,
                actor_class="service_identity",
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        if result.get("isError"):
            payload = result.get("structuredContent") or {"error": "tool handler failed"}
            await emit_request_event(request, identity=identity, status_code=502, started_at=started_at)
            return JSONResponse(status_code=502, content=payload)

        await emit_request_event(request, identity=identity, status_code=200, started_at=started_at)
        return result.get("structuredContent", {})

    @app.get("/v1/billing/health")
    async def billing_health(request: Request) -> Response:
        started_at = time.perf_counter()
        runtime: GatewayRuntime = request.app.state.runtime
        if not (runtime.config.billing_api_base_url or "").strip():
            return registry_error_response(
                runtime,
                request,
                "INFRA_CONFIGURATION_ERROR",
                message="Billing health routing is not configured.",
                context={"dependency": "lago", "detail": "missing billing api base url"},
            )

        url = urljoin(runtime.config.billing_api_base_url.rstrip("/") + "/", "health")

        async def fetch() -> httpx.Response:
            response = await async_with_retry(
                lambda: runtime.http_client.get(
                    url,
                    timeout=runtime.api_call_context(15).timeout_for(
                        "http_request",
                        15,
                        reserve_seconds=1.0,
                    ),
                ),
                policy=runtime.internal_api_retry_policy,
                error_context="gateway billing health",
            )
            response.raise_for_status()
            return response

        try:
            circuit = runtime.service_circuit("lago")
            if circuit is not None:
                upstream_response = await circuit.call(fetch)
            else:
                upstream_response = await fetch()
        except CircuitOpenError as exc:
            await emit_request_event(request, identity=None, status_code=503, started_at=started_at)
            return registry_error_response(
                runtime,
                request,
                "INFRA_RUNTIME_UNAVAILABLE",
                message="Lago is temporarily unavailable.",
                context={"dependency": "lago", "detail": "circuit_open"},
                retry_after=exc.retry_after,
            )
        except httpx.HTTPError as exc:
            await emit_request_event(request, identity=None, status_code=503, started_at=started_at)
            return registry_error_response(
                runtime,
                request,
                "INFRA_DEPENDENCY_DOWN",
                message="Billing health probe could not reach Lago.",
                context={"dependency": "lago", "detail": str(exc)},
            )

        await emit_request_event(
            request,
            identity=None,
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

    @app.post("/v1/billing/events")
    async def billing_events(
        body: BillingEventRequest,
        request: Request,
        identity: dict[str, Any] = Depends(require_billing_producer_identity),
    ) -> Response:
        started_at = time.perf_counter()
        runtime: GatewayRuntime = request.app.state.runtime
        producer: BillingProducer = identity["producer"]
        payload = dump_model(body)
        event = payload["event"]

        if not runtime.billing_enabled():
            await emit_request_event(request, identity=identity, status_code=500, started_at=started_at)
            return registry_error_response(
                runtime,
                request,
                "INFRA_CONFIGURATION_ERROR",
                message="Billing event routing is not configured.",
                context={"dependency": "lago", "detail": "missing billing api base url or org api key"},
            )

        try:
            uuid.UUID(event["transaction_id"])
        except ValueError:
            await emit_billing_rejection(
                runtime,
                request,
                reason_code="invalid_transaction_id",
                reason="Billing event transaction_id must be a valid UUID.",
                payload=payload,
                producer=producer,
                context={"field_path": "event.transaction_id"},
            )
            await emit_request_event(request, identity=identity, status_code=422, started_at=started_at)
            return registry_error_response(
                runtime,
                request,
                "INPUT_SCHEMA_INVALID",
                message="Billing event transaction_id must be a valid UUID.",
                context={
                    "field_path": "event.transaction_id",
                    "error_type": "uuid",
                    "validation_message": "transaction_id must be a valid UUID.",
                },
            )

        if producer.allowed_metric_codes and event["code"] not in producer.allowed_metric_codes:
            await emit_billing_rejection(
                runtime,
                request,
                reason_code="metric_not_allowed",
                reason="Billing producer is not allowed to emit this metric code.",
                payload=payload,
                producer=producer,
                context={"field_path": "event.code", "metric_code": event["code"]},
            )
            await emit_request_event(request, identity=identity, status_code=422, started_at=started_at)
            return registry_error_response(
                runtime,
                request,
                "INPUT_SCHEMA_INVALID",
                message="Billing producer is not allowed to emit this metric code.",
                context={
                    "field_path": "event.code",
                    "error_type": "producer_scope",
                    "validation_message": f"producer {producer.id} is not allowed to emit metric code {event['code']}",
                },
            )

        if (
            producer.allowed_external_subscription_ids
            and event["external_subscription_id"] not in producer.allowed_external_subscription_ids
        ):
            await emit_billing_rejection(
                runtime,
                request,
                reason_code="subscription_not_allowed",
                reason="Billing producer is not allowed to emit this external subscription id.",
                payload=payload,
                producer=producer,
                context={
                    "field_path": "event.external_subscription_id",
                    "external_subscription_id": event["external_subscription_id"],
                },
            )
            await emit_request_event(request, identity=identity, status_code=422, started_at=started_at)
            return registry_error_response(
                runtime,
                request,
                "INPUT_SCHEMA_INVALID",
                message="Billing producer is not allowed to emit this external subscription id.",
                context={
                    "field_path": "event.external_subscription_id",
                    "error_type": "producer_scope",
                    "validation_message": (
                        f"producer {producer.id} is not allowed to emit external subscription id "
                        f"{event['external_subscription_id']}"
                    ),
                },
            )

        url = urljoin(runtime.config.billing_api_base_url.rstrip("/") + "/", "api/v1/events")
        headers = {
            "Authorization": f"Bearer {runtime.config.billing_org_api_key}",
            "X-Gateway-Request-ID": request.state.request_id,
            "X-Trace-Id": request.state.trace_id,
            "X-Caller-Identity": identity["subject"],
        }

        async def forward() -> httpx.Response:
            return await runtime.http_client.post(
                url,
                json=payload,
                headers=headers,
                timeout=runtime.api_call_context(20).timeout_for(
                    "http_request",
                    20,
                    reserve_seconds=1.0,
                ),
            )

        try:
            circuit = runtime.service_circuit("lago")
            if circuit is not None:
                upstream_response = await circuit.call(forward)
            else:
                upstream_response = await forward()
        except CircuitOpenError as exc:
            await emit_billing_rejection(
                runtime,
                request,
                reason_code="upstream_circuit_open",
                reason="Lago is temporarily unavailable.",
                payload=payload,
                producer=producer,
            )
            await emit_request_event(request, identity=identity, status_code=503, started_at=started_at)
            return registry_error_response(
                runtime,
                request,
                "INFRA_RUNTIME_UNAVAILABLE",
                message="Lago is temporarily unavailable.",
                context={"dependency": "lago", "detail": "circuit_open"},
                retry_after=exc.retry_after,
            )
        except httpx.HTTPError as exc:
            await emit_billing_rejection(
                runtime,
                request,
                reason_code="upstream_transport_error",
                reason="Billing event forwarding to Lago failed.",
                payload=payload,
                producer=producer,
                context={"detail": str(exc)},
            )
            await emit_request_event(request, identity=identity, status_code=503, started_at=started_at)
            return registry_error_response(
                runtime,
                request,
                "INFRA_DEPENDENCY_DOWN",
                message="Billing event forwarding to Lago failed.",
                context={"dependency": "lago", "detail": str(exc)},
            )

        if upstream_response.status_code >= 400:
            await emit_billing_rejection(
                runtime,
                request,
                reason_code="upstream_rejected",
                reason="Lago rejected the billing event.",
                payload=payload,
                producer=producer,
                context={"status_code": upstream_response.status_code},
            )
            await emit_request_event(
                request,
                identity=identity,
                status_code=upstream_response.status_code,
                started_at=started_at,
            )
            return registry_error_response(
                runtime,
                request,
                "INFRA_DEPENDENCY_DOWN",
                message="Lago rejected the billing event.",
                context={
                    "dependency": "lago",
                    "detail": {
                        "status_code": upstream_response.status_code,
                        "body": upstream_response.text[:500],
                    },
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
        schema["x-lv3-error-codes"] = runtime.error_registry.openapi_fragment()

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
                auth_header = service.upstream_auth_header or "Authorization"
                auth_scheme = service.upstream_auth_scheme or "bearer"
                if auth_scheme.lower() == "raw":
                    headers[auth_header] = upstream_token
                else:
                    scheme = "Bearer" if auth_scheme.lower() == "bearer" else auth_scheme
                    headers[auth_header] = f"{scheme} {upstream_token}"

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
            error = runtime.error_registry.create(
                "INFRA_RUNTIME_UNAVAILABLE",
                trace_id=request_trace_id(request),
                message=f"{service.name} is temporarily unavailable.",
                context={"dependency": service.id, "detail": "circuit_open"},
                retry_after_s=exc.retry_after,
            )
            response = JSONResponse(status_code=error.http_status, content=error.to_response())
            response.headers["Retry-After"] = str(exc.retry_after)
            return response
        except httpx.HTTPError as exc:
            await emit_request_event(
                request,
                identity=identity,
                status_code=502,
                started_at=started_at,
            )
            error = runtime.error_registry.create(
                "INFRA_DEPENDENCY_DOWN",
                trace_id=request_trace_id(request),
                message=f"Upstream request to {service.id} failed.",
                context={"dependency": service.id, "detail": str(exc)},
            )
            return JSONResponse(status_code=error.http_status, content=error.to_response())

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
