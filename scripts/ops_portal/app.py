from __future__ import annotations

import asyncio
import json
import os
import uuid
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

try:
    from publication_contract import registry_entries
except ImportError:  # pragma: no cover - repo checkout import path
    from scripts.publication_contract import registry_entries

try:
    from search_fabric.collectors import available_collections
except ImportError:  # pragma: no cover - repo checkout import path
    from scripts.search_fabric.collectors import available_collections

try:
    from .runtime_assurance import build_runtime_assurance_models
except ImportError:  # pragma: no cover - direct module or repo checkout import path
    try:
        from runtime_assurance import build_runtime_assurance_models
    except ImportError:  # pragma: no cover - repo checkout import path
        from scripts.ops_portal.runtime_assurance import build_runtime_assurance_models


def utc_now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def isoformat(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def humanize_timestamp(value: str | None) -> str:
    parsed = parse_timestamp(value)
    if parsed is None:
        return "Not recorded"
    return parsed.strftime("%Y-%m-%d %H:%M UTC")


def load_json_file(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_text(value: str) -> str:
    return " ".join("".join(ch.lower() if ch.isalnum() else " " for ch in value).split())


@dataclass(frozen=True)
class PortalSettings:
    gateway_url: str
    session_secret: str
    static_api_token: str | None
    service_catalog_path: Path
    publication_registry_path: Path
    workflow_catalog_path: Path
    changelog_path: Path
    live_applies_dir: Path
    drift_receipts_dir: Path
    maintenance_windows_path: Path | None
    docs_base_url: str
    grafana_logs_url: str

    @classmethod
    def from_env(cls) -> PortalSettings:
        data_root = Path(os.getenv("OPS_PORTAL_DATA_ROOT", "/srv/ops-portal/data"))
        maintenance_file = os.getenv("OPS_PORTAL_MAINTENANCE_WINDOWS_FILE", "").strip()
        return cls(
            gateway_url=os.getenv("GATEWAY_URL", "http://api-gateway:8080").rstrip("/"),
            session_secret=os.getenv("OPS_PORTAL_SESSION_SECRET", "development-secret-change-me"),
            static_api_token=os.getenv("OPS_PORTAL_STATIC_API_TOKEN") or None,
            service_catalog_path=Path(
                os.getenv("OPS_PORTAL_SERVICE_CATALOG", data_root / "config" / "service-capability-catalog.json")
            ),
            publication_registry_path=Path(
                os.getenv(
                    "OPS_PORTAL_PUBLICATION_REGISTRY",
                    data_root / "config" / "subdomain-exposure-registry.json",
                )
            ),
            workflow_catalog_path=Path(
                os.getenv("OPS_PORTAL_WORKFLOW_CATALOG", data_root / "config" / "workflow-catalog.json")
            ),
            changelog_path=Path(os.getenv("OPS_PORTAL_CHANGELOG_FILE", data_root / "changelog.md")),
            live_applies_dir=Path(
                os.getenv("OPS_PORTAL_LIVE_APPLIES_DIR", data_root / "receipts" / "live-applies")
            ),
            drift_receipts_dir=Path(
                os.getenv("OPS_PORTAL_DRIFT_RECEIPTS_DIR", data_root / "receipts" / "drift-reports")
            ),
            maintenance_windows_path=Path(maintenance_file) if maintenance_file else None,
            docs_base_url=os.getenv("OPS_PORTAL_DOCS_BASE_URL", "https://docs.lv3.org").rstrip("/"),
            grafana_logs_url=os.getenv(
                "OPS_PORTAL_GRAFANA_LOGS_URL",
                "https://grafana.lv3.org/explore?left=%7B%22queries%22:%5B%5D%7D",
            ),
        )


class EventBroker:
    def __init__(self, limit: int = 200) -> None:
        self._events: deque[dict[str, Any]] = deque(maxlen=limit)
        self._condition = asyncio.Condition()

    async def publish(self, message: str, *, event_type: str = "log", metadata: dict[str, Any] | None = None) -> None:
        event = {
            "id": str(uuid.uuid4()),
            "type": event_type,
            "message": message,
            "metadata": metadata or {},
            "ts": isoformat(utc_now()),
        }
        async with self._condition:
            self._events.append(event)
            self._condition.notify_all()

    async def stream(self):
        last_seen = 0
        while True:
            async with self._condition:
                if last_seen >= len(self._events):
                    try:
                        await asyncio.wait_for(self._condition.wait(), timeout=15)
                    except TimeoutError:
                        yield {"event": "heartbeat", "data": {"ts": isoformat(utc_now())}}
                        continue
                snapshot = list(self._events)
            for event in snapshot[last_seen:]:
                yield {"event": event["type"], "data": event}
            last_seen = len(snapshot)


class GatewayClient:
    def __init__(self, settings: PortalSettings, client: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(base_url=self.settings.gateway_url, timeout=20)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        token: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        headers = {"Accept": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        response = await self._client.request(method, path, json=payload, headers=headers)
        response.raise_for_status()
        if not response.content:
            return {}
        return response.json()

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def fetch_platform_health(self, token: str | None = None) -> dict[str, Any]:
        return await self._request("GET", "/v1/platform/health", token=token)

    async def fetch_agent_coordination(self, token: str | None = None) -> dict[str, Any]:
        return await self._request("GET", "/v1/platform/agents", token=token)

    async def fetch_service_health(self, service_id: str, token: str | None = None) -> dict[str, Any]:
        return await self._request("GET", f"/v1/platform/health/{service_id}", token=token)

    async def trigger_deploy(
        self,
        service_id: str,
        *,
        token: str | None = None,
        restart_only: bool = False,
        source: str = "portal",
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/v1/platform/deploy",
            token=token,
            payload={"service": service_id, "restart_only": restart_only, "source": source},
        )

    async def rotate_secret(self, service_id: str, *, token: str | None = None) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/v1/platform/secrets/rotate",
            token=token,
            payload={"service": service_id, "source": "portal"},
        )

    async def launch_runbook(
        self,
        runbook_id: str,
        *,
        token: str | None = None,
        parameters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/v1/platform/runbooks/execute",
            token=token,
            payload={
                "runbook_id": runbook_id,
                "parameters": parameters or {},
                "delivery_surface": "ops_portal",
            },
        )

    async def search(
        self,
        query: str,
        *,
        collection: str | None = None,
        token: str | None = None,
        limit: int = 8,
    ) -> dict[str, Any]:
        params = {"q": query, "limit": str(limit)}
        if collection:
            params["collection"] = collection
        return await self._request("GET", f"/v1/search?{httpx.QueryParams(params)}", token=token)

    async def fetch_runbooks(self, *, token: str | None = None, delivery_surface: str = "ops_portal") -> dict[str, Any]:
        params = httpx.QueryParams({"delivery_surface": delivery_surface})
        return await self._request("GET", f"/v1/platform/runbooks?{params}", token=token)


@dataclass
class PortalRepository:
    settings: PortalSettings

    def load_service_catalog(self) -> list[dict[str, Any]]:
        payload = load_json_file(self.settings.service_catalog_path, {"services": []})
        return payload.get("services", [])

    def load_publication_registry(self) -> list[dict[str, Any]]:
        payload = load_json_file(self.settings.publication_registry_path, {"publications": []})
        return registry_entries(payload)

    def load_capability_contract_catalog(self) -> list[dict[str, Any]]:
        contract_path = self.settings.service_catalog_path.parent / "capability-contract-catalog.json"
        payload = load_json_file(contract_path, {"capabilities": []})
        capabilities = payload.get("capabilities", [])
        return capabilities if isinstance(capabilities, list) else []

    def load_workflow_catalog(self) -> list[dict[str, Any]]:
        payload = load_json_file(self.settings.workflow_catalog_path, {"workflows": {}})
        workflows = []
        for workflow_id, workflow in payload.get("workflows", {}).items():
            if workflow.get("lifecycle_status") != "active":
                continue
            if workflow.get("live_impact") == "repo_only":
                continue
            workflows.append(
                {
                    "id": workflow_id,
                    "description": workflow.get("description", workflow_id),
                    "owner_runbook": workflow.get("owner_runbook"),
                    "entrypoint": workflow.get("preferred_entrypoint", {}),
                    "live_impact": workflow.get("live_impact", "unknown"),
                }
            )
        return sorted(workflows, key=lambda item: item["id"])

    def load_maintenance_windows(self) -> list[dict[str, Any]]:
        if self.settings.maintenance_windows_path is None:
            return []
        payload = load_json_file(self.settings.maintenance_windows_path, {})
        if isinstance(payload, dict):
            values = payload.values()
        else:
            values = payload
        windows = [item for item in values if isinstance(item, dict)]
        return sorted(windows, key=lambda item: item.get("opened_at", ""), reverse=True)

    def latest_drift_report(self) -> dict[str, Any]:
        reports = sorted(self.settings.drift_receipts_dir.glob("*.json"), reverse=True)
        for report in reports:
            try:
                payload = json.loads(report.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                continue
            payload["_path"] = str(report)
            return payload
        return {}

    def _service_keywords(self, services: list[dict[str, Any]]) -> dict[str, set[str]]:
        service_keywords: dict[str, set[str]] = {}
        for service in services:
            keywords = {
                normalize_text(service["id"]),
                normalize_text(service["name"]),
            }
            for field in ("public_url", "internal_url", "subdomain", "vm"):
                if isinstance(service.get(field), str):
                    keywords.add(normalize_text(service[field]))
            environments = service.get("environments")
            if isinstance(environments, dict):
                for binding in environments.values():
                    if not isinstance(binding, dict):
                        continue
                    for field in ("url", "subdomain"):
                        if isinstance(binding.get(field), str):
                            keywords.add(normalize_text(binding[field]))
            service_keywords[service["id"]] = {keyword for keyword in keywords if keyword}
        return service_keywords

    def load_live_apply_receipts(self, services: list[dict[str, Any]]) -> list[dict[str, Any]]:
        service_keywords = self._service_keywords(services)
        receipts: list[dict[str, Any]] = []
        for receipt_path in sorted(self.settings.live_applies_dir.rglob("*.json"), reverse=True):
            try:
                receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                continue
            text = normalize_text(json.dumps(receipt, sort_keys=True))
            matched = []
            for service_id, keywords in service_keywords.items():
                if any(keyword and keyword in text for keyword in keywords):
                    matched.append(service_id)
            receipt["_path"] = str(receipt_path)
            receipt["_normalized_text"] = text
            receipt["_matched_services"] = sorted(set(matched))
            receipt["_environment"] = (
                str(receipt.get("environment", "")).strip().lower()
                or ("staging" if "staging" in receipt_path.parts else "production")
            )
            receipts.append(receipt)
        return receipts

    def recent_deployments(
        self,
        services: list[dict[str, Any]],
        *,
        receipts: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        live_apply_receipts = receipts if receipts is not None else self.load_live_apply_receipts(services)

        receipts_out: list[dict[str, Any]] = []
        for receipt in live_apply_receipts:
            receipts_out.append(
                {
                    "id": receipt.get("receipt_id", Path(str(receipt.get("_path", "receipt"))).stem),
                    "summary": receipt.get("summary", Path(str(receipt.get("_path", "receipt"))).stem),
                    "workflow_id": receipt.get("workflow_id", ""),
                    "recorded_on": receipt.get("recorded_on") or receipt.get("applied_on"),
                    "recorded_by": receipt.get("recorded_by", "unknown"),
                    "services": list(receipt.get("_matched_services", [])),
                    "path": str(receipt.get("_path", "")),
                }
            )
        return receipts_out

    def changelog_notes(self) -> list[str]:
        if not self.settings.changelog_path.exists():
            return []
        notes: list[str] = []
        in_unreleased = False
        for line in self.settings.changelog_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped == "## Unreleased":
                in_unreleased = True
                continue
            if in_unreleased and stripped.startswith("## "):
                break
            if in_unreleased and stripped.startswith("- "):
                notes.append(stripped[2:])
        return notes


def normalize_health(payload: dict[str, Any], services: list[dict[str, Any]]) -> dict[str, dict[str, str]]:
    health_map = {
        service["id"]: {
            "status": "unknown",
            "detail": "No live health data",
        }
        for service in services
    }
    if not payload:
        return health_map

    raw_services = payload.get("services") if isinstance(payload, dict) else None
    if isinstance(raw_services, list):
        for item in raw_services:
            service_id = item.get("service_id") or item.get("service") or item.get("id")
            if service_id in health_map:
                health_map[service_id] = {
                    "status": str(item.get("status", "unknown")),
                    "detail": str(item.get("detail") or item.get("message") or "No detail"),
                }
    elif isinstance(raw_services, dict):
        for service_id, item in raw_services.items():
            if service_id not in health_map:
                continue
            if isinstance(item, str):
                health_map[service_id] = {"status": item, "detail": item}
                continue
            health_map[service_id] = {
                "status": str(item.get("status", "unknown")),
                "detail": str(item.get("detail") or item.get("message") or "No detail"),
            }
    elif isinstance(payload, dict):
        service_id = payload.get("service_id") or payload.get("service") or payload.get("id")
        if service_id in health_map:
            health_map[service_id] = {
                "status": str(payload.get("status", "unknown")),
                "detail": str(payload.get("detail") or payload.get("message") or "No detail"),
            }
    return health_map


def build_capability_contract_models(
    capability_contracts: list[dict[str, Any]],
    services: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    service_index = {service.get("id"): service for service in services if isinstance(service.get("id"), str)}
    models: list[dict[str, Any]] = []
    selected = 0
    export_ready = 0

    for capability in sorted(capability_contracts, key=lambda item: str(item.get("id", ""))):
        migration = capability.get("migration_expectations", {})
        selection = capability.get("current_selection", {})
        if not isinstance(migration, dict):
            migration = {}
        if not isinstance(selection, dict):
            selection = {}
        export_formats = migration.get("export_formats", [])
        if not isinstance(export_formats, list):
            export_formats = []
        service = service_index.get(selection.get("service_id"), {})
        if selection:
            selected += 1
        if export_formats:
            export_ready += 1
        models.append(
            {
                "id": capability.get("id", "unknown"),
                "name": capability.get("name", capability.get("id", "Unknown capability")),
                "summary": capability.get("summary", ""),
                "selected_product": selection.get("product_name"),
                "service_name": service.get("name"),
                "service_url": service.get("public_url") or service.get("internal_url"),
                "selection_adr": selection.get("selection_adr"),
                "runbook": selection.get("runbook"),
                "review_cadence": capability.get("review_cadence", "unspecified"),
                "export_format_count": len(export_formats),
                "fallback_behaviour": migration.get("fallback_behaviour", "No fallback recorded."),
            }
        )

    return models, {
        "total": len(models),
        "selected": selected,
        "contract_only": len(models) - selected,
        "export_ready": export_ready,
    }


def status_tone(status: str) -> str:
    value = status.lower()
    if value in {"healthy", "ok", "up", "success", "active", "pass"}:
        return "ok"
    if value in {"warning", "warn", "degraded", "pending", "blocked", "escalated", "maintenance"}:
        return "warn"
    if value in {"critical", "down", "error", "failed"}:
        return "danger"
    return "neutral"


def build_service_models(
    services: list[dict[str, Any]],
    publications: list[dict[str, Any]],
    health: dict[str, dict[str, str]],
    drift_report: dict[str, Any],
    maintenance_windows: list[dict[str, Any]],
    deployments: list[dict[str, Any]],
    settings: PortalSettings,
) -> list[dict[str, Any]]:
    latest_deploy_by_service: dict[str, dict[str, Any]] = {}
    for deployment in deployments:
        for service_id in deployment["services"]:
            latest_deploy_by_service.setdefault(service_id, deployment)

    drift_by_service: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in drift_report.get("records", []):
        service_id = item.get("service")
        if service_id:
            drift_by_service[str(service_id)].append(item)

    windows_by_service: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for window in maintenance_windows:
        service_id = str(window.get("service_id", ""))
        if service_id:
            windows_by_service[service_id].append(window)

    publications_by_service: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for publication in publications:
        service_id = publication.get("service_id")
        if not isinstance(service_id, str) or not service_id:
            continue
        publications_by_service[service_id].append(publication)

    models = []
    for service in sorted(services, key=lambda item: (item.get("category", ""), item["name"])):
        service_id = service["id"]
        deployment = latest_deploy_by_service.get(service_id)
        publication_models = sorted(
            publications_by_service.get(service_id, []),
            key=lambda item: item.get("fqdn", ""),
        )
        models.append(
            {
                "id": service_id,
                "name": service["name"],
                "description": service.get("description", ""),
                "category": service.get("category", "misc"),
                "adr": service.get("adr"),
                "runbook": service.get("runbook"),
                "dashboard_url": service.get("dashboard_url"),
                "public_url": service.get("public_url"),
                "internal_url": service.get("internal_url"),
                "lifecycle_status": service.get("lifecycle_status", "unknown"),
                "status": health.get(service_id, {}).get("status", "unknown"),
                "status_detail": health.get(service_id, {}).get("detail", "No detail"),
                "status_tone": status_tone(health.get(service_id, {}).get("status", "unknown")),
                "drift_items": drift_by_service.get(service_id, []),
                "maintenance_windows": windows_by_service.get(service_id, []) + windows_by_service.get("all", []),
                "last_deployment": deployment,
                "logs_url": build_logs_url(settings.grafana_logs_url, service_id),
                "publications": [
                    {
                        "fqdn": publication["fqdn"],
                        "delivery_model": publication.get("publication", {}).get("delivery_model", "unknown"),
                        "access_model": publication.get("publication", {}).get("access_model", "unknown"),
                        "audience": publication.get("publication", {}).get("audience", "unknown"),
                        "status": publication.get("status", "unknown"),
                    }
                    for publication in publication_models
                ],
            }
        )
    return models


def build_logs_url(base_url: str, service_id: str) -> str:
    if "{service}" in base_url:
        return base_url.format(service=service_id)
    return f"{base_url}&service={service_id}"


def deployment_console_seed() -> list[dict[str, Any]]:
    return [
        {
            "id": "seed",
            "type": "info",
            "message": "Deployment console connected. New portal actions will appear here.",
            "ts": isoformat(utc_now()),
        }
    ]


async def ensure_session(request: Request) -> dict[str, str]:
    session = request.session
    if "operator_id" not in session:
        session["operator_id"] = request.headers.get("x-auth-request-user", "operator")
        session["operator_email"] = request.headers.get("x-auth-request-email", "")
    if "api_token" not in session:
        forwarded_token = request.headers.get("x-forwarded-access-token") or request.headers.get("authorization", "")
        if forwarded_token.startswith("Bearer "):
            forwarded_token = forwarded_token.removeprefix("Bearer ").strip()
        if forwarded_token:
            session["api_token"] = forwarded_token
    return {
        "operator_id": session.get("operator_id", "operator"),
        "operator_email": session.get("operator_email", ""),
        "api_token": session.get("api_token", ""),
    }


def read_api_token(session: dict[str, str], settings: PortalSettings) -> str | None:
    return session.get("api_token") or settings.static_api_token


@lru_cache(maxsize=1)
def template_root() -> Path:
    return Path(__file__).resolve().parent


def build_runbook_models(runbooks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    featured_ids = {"validation-gate-status"}
    featured = [item for item in runbooks if item["id"] in featured_ids]
    remainder = [item for item in runbooks if item["id"] not in featured_ids]
    combined = featured + remainder
    return combined[:6]


def normalize_agent_coordination(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {"summary": {"count": 0, "active": 0, "blocked": 0, "escalated": 0, "completing": 0}, "entries": []}
    summary = payload.get("summary")
    if not isinstance(summary, dict):
        summary = {}
    entries = payload.get("entries")
    if not isinstance(entries, list):
        entries = []

    normalized_entries: list[dict[str, Any]] = []
    for item in entries:
        if not isinstance(item, dict):
            continue
        held_locks = item.get("held_locks")
        held_lanes = item.get("held_lanes")
        normalized_entries.append(
            {
                "agent_id": str(item.get("agent_id", "unknown")),
                "session_label": str(item.get("session_label", "session")),
                "current_phase": str(item.get("current_phase", "unknown")),
                "current_target": item.get("current_target"),
                "current_workflow_id": item.get("current_workflow_id"),
                "status": str(item.get("status", "unknown")),
                "blocked_reason": item.get("blocked_reason"),
                "progress_pct": item.get("progress_pct"),
                "held_locks": held_locks if isinstance(held_locks, list) else [],
                "held_lanes": held_lanes if isinstance(held_lanes, list) else [],
                "last_heartbeat": item.get("last_heartbeat"),
                "started_at": item.get("started_at"),
            }
        )

    return {
        "summary": {
            "count": int(summary.get("count", len(normalized_entries))),
            "active": int(summary.get("active", 0)),
            "blocked": int(summary.get("blocked", 0)),
            "escalated": int(summary.get("escalated", 0)),
            "completing": int(summary.get("completing", 0)),
            "generated_at": summary.get("generated_at"),
        },
        "entries": normalized_entries,
    }


async def build_dashboard_context(request: Request) -> dict[str, Any]:
    session = await ensure_session(request)
    repository: PortalRepository = request.app.state.repository
    gateway: Any = request.app.state.gateway_client

    services = repository.load_service_catalog()
    publications = repository.load_publication_registry()

    capability_contracts = repository.load_capability_contract_catalog()
    maintenance_windows = repository.load_maintenance_windows()
    live_apply_receipts = repository.load_live_apply_receipts(services)
    deployments = repository.recent_deployments(services, receipts=live_apply_receipts)
    drift_report = repository.latest_drift_report()
    changelog_notes = repository.changelog_notes()

    try:
        health_payload = await gateway.fetch_platform_health(
            token=read_api_token(session, request.app.state.settings),
        )
    except Exception as exc:  # noqa: BLE001
        health_payload = {"warning": str(exc)}
    try:
        runbook_payload = await gateway.fetch_runbooks(
            token=read_api_token(session, request.app.state.settings),
            delivery_surface="ops_portal",
        )
    except Exception as exc:  # noqa: BLE001
        runbook_payload = {"warning": str(exc), "runbooks": []}
    try:
        coordination_payload = await gateway.fetch_agent_coordination(
            token=read_api_token(session, request.app.state.settings),
        )
    except Exception as exc:  # noqa: BLE001
        coordination_payload = {"warning": str(exc)}

    health = normalize_health(health_payload, services)
    coordination = normalize_agent_coordination(coordination_payload)
    raw_runbooks = runbook_payload.get("runbooks") if isinstance(runbook_payload, dict) else []
    runbooks = raw_runbooks if isinstance(raw_runbooks, list) else []
    capability_models, capability_summary = build_capability_contract_models(capability_contracts, services)
    service_models = build_service_models(
        services,
        publications,
        health,
        drift_report,
        maintenance_windows,
        deployments,
        request.app.state.settings,
    )
    assurance_rows, assurance_summary = build_runtime_assurance_models(
        services,
        publications,
        health_payload if isinstance(health_payload, dict) else {},
        live_apply_receipts,
    )
    active_maintenance = [window for window in maintenance_windows if window.get("service_id")]
    drift_summary = drift_report.get("summary", {})

    return {
        "request": request,
        "operator": session,
        "services": service_models,
        "runtime_assurance_rows": assurance_rows,
        "runtime_assurance_summary": assurance_summary,
        "capability_contracts": capability_models,
        "capability_contract_summary": capability_summary,
        "maintenance_windows": active_maintenance,
        "maintenance_count": len(active_maintenance),
        "runbooks": build_runbook_models(runbooks),
        "deployments": deployments[:10],
        "changelog_notes": changelog_notes,
        "drift_report": drift_report,
        "drift_summary": drift_summary,
        "health_warning": health_payload.get("warning") if isinstance(health_payload, dict) else None,
        "coordination_warning": coordination_payload.get("warning") if isinstance(coordination_payload, dict) else None,
        "runbook_warning": runbook_payload.get("warning") if isinstance(runbook_payload, dict) else None,
        "coordination": coordination,
        "deployment_events": deployment_console_seed(),
        "generated_at": isoformat(utc_now()),
        "docs_base_url": request.app.state.settings.docs_base_url,
        "search_collections": available_collections(),
        "search_results": [],
        "search_query": "",
        "search_collection": "",
    }


def sse_encode(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def create_app(
    settings: PortalSettings | None = None,
    *,
    gateway_client: Any | None = None,
) -> FastAPI:
    settings = settings or PortalSettings.from_env()
    portal_gateway_client = gateway_client or GatewayClient(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        try:
            yield
        finally:
            if isinstance(portal_gateway_client, GatewayClient):
                await portal_gateway_client.close()

    app = FastAPI(title="LV3 Interactive Ops Portal", lifespan=lifespan)
    app.add_middleware(SessionMiddleware, secret_key=settings.session_secret, session_cookie="lv3_ops_portal")
    app.mount("/static", StaticFiles(directory=str(template_root() / "static")), name="static")
    templates = Jinja2Templates(directory=str(template_root() / "templates"))
    templates.env.filters["status_tone"] = status_tone
    templates.env.filters["humanize_timestamp"] = humanize_timestamp
    app.state.templates = templates
    app.state.settings = settings
    app.state.repository = PortalRepository(settings)
    app.state.gateway_client = portal_gateway_client
    app.state.event_broker = EventBroker()

    @app.get("/health")
    async def health() -> JSONResponse:
        return JSONResponse({"status": "ok"})

    @app.get("/", response_class=HTMLResponse)
    async def dashboard(request: Request) -> HTMLResponse:
        context = await build_dashboard_context(request)
        return templates.TemplateResponse(request=request, name="index.html", context=context)

    @app.get("/partials/overview", response_class=HTMLResponse)
    async def overview_partial(request: Request) -> HTMLResponse:
        context = await build_dashboard_context(request)
        return templates.TemplateResponse(request=request, name="partials/overview.html", context=context)

    @app.get("/partials/drift", response_class=HTMLResponse)
    async def drift_partial(request: Request) -> HTMLResponse:
        context = await build_dashboard_context(request)
        return templates.TemplateResponse(request=request, name="partials/drift.html", context=context)

    @app.get("/partials/agents", response_class=HTMLResponse)
    async def agents_partial(request: Request) -> HTMLResponse:
        context = await build_dashboard_context(request)
        return templates.TemplateResponse(request=request, name="partials/agents.html", context=context)

    @app.get("/partials/runbooks", response_class=HTMLResponse)
    async def runbooks_partial(request: Request) -> HTMLResponse:
        context = await build_dashboard_context(request)
        return templates.TemplateResponse(request=request, name="partials/runbooks.html", context=context)

    @app.get("/partials/changelog", response_class=HTMLResponse)
    async def changelog_partial(request: Request) -> HTMLResponse:
        context = await build_dashboard_context(request)
        return templates.TemplateResponse(request=request, name="partials/changelog.html", context=context)

    @app.get("/partials/search", response_class=HTMLResponse)
    async def search_partial(request: Request) -> HTMLResponse:
        context = await build_dashboard_context(request)
        return templates.TemplateResponse(request=request, name="partials/search.html", context=context)

    @app.get("/events/deployments")
    async def deployment_events() -> StreamingResponse:
        broker: EventBroker = app.state.event_broker

        async def event_stream():
            async for event in broker.stream():
                yield sse_encode(event["event"], event["data"])

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    @app.post("/actions/services/{service_id}/health-check", response_class=HTMLResponse)
    async def health_check_action(request: Request, service_id: str) -> HTMLResponse:
        session = await ensure_session(request)
        gateway = request.app.state.gateway_client
        try:
            result = await gateway.fetch_service_health(
                service_id,
                token=read_api_token(session, request.app.state.settings),
            )
            status = result.get("status", "unknown")
            detail = result.get("detail") or result.get("message") or "Health check completed."
            tone = status_tone(status)
        except Exception as exc:  # noqa: BLE001
            status = "error"
            detail = str(exc)
            tone = "danger"

        context = {
            "request": request,
            "result": {
                "title": f"Health check: {service_id}",
                "status": status,
                "detail": detail,
                "tone": tone,
                "timestamp": isoformat(utc_now()),
            },
        }
        return templates.TemplateResponse(request=request, name="partials/action_result.html", context=context)

    @app.post("/actions/services/{service_id}/deploy", response_class=HTMLResponse)
    async def deploy_action(request: Request, service_id: str, restart_only: bool = Form(default=False)) -> HTMLResponse:
        session = await ensure_session(request)
        gateway = request.app.state.gateway_client
        broker: EventBroker = request.app.state.event_broker
        try:
            result = await gateway.trigger_deploy(
                service_id,
                token=read_api_token(session, request.app.state.settings),
                restart_only=restart_only,
            )
            job_id = result.get("job_id", "queued")
            summary = result.get("message") or ("Restart queued." if restart_only else "Deployment queued.")
            await broker.publish(
                f"{service_id}: {summary}",
                event_type="deploy",
                metadata={"service": service_id, "job_id": job_id, "restart_only": restart_only},
            )
            tone = "ok"
            status = "queued"
        except Exception as exc:  # noqa: BLE001
            job_id = ""
            summary = str(exc)
            tone = "danger"
            status = "failed"
            await broker.publish(f"{service_id}: deployment failed - {summary}", event_type="deploy")

        context = {
            "request": request,
            "result": {
                "title": f"{'Restart' if restart_only else 'Deploy'}: {service_id}",
                "status": status,
                "detail": summary,
                "tone": tone,
                "timestamp": isoformat(utc_now()),
                "job_id": job_id,
            },
        }
        return templates.TemplateResponse(request=request, name="partials/action_result.html", context=context)

    @app.post("/actions/services/{service_id}/rotate-secret", response_class=HTMLResponse)
    async def rotate_secret_action(request: Request, service_id: str) -> HTMLResponse:
        session = await ensure_session(request)
        gateway = request.app.state.gateway_client
        broker: EventBroker = request.app.state.event_broker
        try:
            result = await gateway.rotate_secret(
                service_id,
                token=read_api_token(session, request.app.state.settings),
            )
            summary = result.get("message") or "Secret rotation queued."
            tone = "ok"
            status = "queued"
            await broker.publish(f"{service_id}: {summary}", event_type="secret", metadata={"service": service_id})
        except Exception as exc:  # noqa: BLE001
            summary = str(exc)
            tone = "danger"
            status = "failed"
        context = {
            "request": request,
            "result": {
                "title": f"Rotate secret: {service_id}",
                "status": status,
                "detail": summary,
                "tone": tone,
                "timestamp": isoformat(utc_now()),
            },
        }
        return templates.TemplateResponse(request=request, name="partials/action_result.html", context=context)

    @app.post("/actions/runbooks/{runbook_id}", response_class=HTMLResponse)
    async def launch_runbook_action(
        request: Request,
        runbook_id: str,
        parameters: str = Form(default="{}"),
    ) -> HTMLResponse:
        session = await ensure_session(request)
        gateway = request.app.state.gateway_client
        broker: EventBroker = request.app.state.event_broker
        try:
            parsed_parameters = json.loads(parameters) if parameters.strip() else {}
            if not isinstance(parsed_parameters, dict):
                raise ValueError("Runbook parameters must be a JSON object.")
            result = await gateway.launch_runbook(
                runbook_id,
                token=read_api_token(session, request.app.state.settings),
                parameters=parsed_parameters,
            )
            status = str(result.get("status") or "completed")
            detail = result.get("message") or f"Runbook {runbook_id} finished with status {status}."
            tone = "ok" if status == "completed" else "danger" if status == "failed" else "warn"
            await broker.publish(
                f"{runbook_id}: {detail}",
                event_type="runbook",
                metadata={"runbook_id": runbook_id, "status": status},
            )
        except Exception as exc:  # noqa: BLE001
            detail = str(exc)
            tone = "danger"
            status = "failed"

        context = {
            "request": request,
            "result": {
                "title": f"Runbook: {runbook_id}",
                "status": status,
                "detail": detail,
                "tone": tone,
                "timestamp": isoformat(utc_now()),
            },
        }
        return templates.TemplateResponse(request=request, name="partials/action_result.html", context=context)

    @app.post("/actions/search", response_class=HTMLResponse)
    async def search_action(
        request: Request,
        query: str = Form(default=""),
        collection: str = Form(default=""),
    ) -> HTMLResponse:
        session = await ensure_session(request)
        gateway = request.app.state.gateway_client
        context = await build_dashboard_context(request)
        context["search_query"] = query
        context["search_collection"] = collection
        if not query.strip():
            context["search_error"] = "Enter a query to search the platform corpus."
            return templates.TemplateResponse(request=request, name="partials/search.html", context=context)
        try:
            payload = await gateway.search(
                query,
                collection=collection or None,
                token=read_api_token(session, request.app.state.settings),
            )
            context["search_results"] = payload.get("results", [])
            context["search_expanded_query"] = payload.get("expanded_query", query)
        except Exception as exc:  # noqa: BLE001
            context["search_error"] = str(exc)
        return templates.TemplateResponse(request=request, name="partials/search.html", context=context)

    return app


app = create_app()
