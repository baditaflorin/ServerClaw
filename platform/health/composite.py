from __future__ import annotations

import json
import os
from dataclasses import dataclass
from platform.datetime_compat import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from platform.degradation import default_state_path
from platform.health.semantics import canonical_runtime_state, runtime_state_score
from platform.ledger import LedgerReader
from platform.maintenance import list_active_windows_best_effort
from platform.slo import build_slo_status_entries
from platform.world_state._db import (
    ConnectionFactory,
    connection_kind,
    create_connection_factory,
    decode_json,
    managed_connection,
    parse_timestamp,
    placeholder,
    rows_to_dicts,
    utc_now,
)
from platform.world_state.client import (
    StaleDataError,
    SurfaceNotFoundError,
    WorldStateClient,
    WorldStateUnavailable,
)
from platform.world_state.materializer import SQLITE_CURRENT_VIEW_NAME, SQLITE_SNAPSHOTS_TABLE_NAME


DEFAULT_TTL_SECONDS = 120
DEFAULT_SIGNAL_WEIGHTS = {
    "health_probe": 0.40,
    "slo_budget": 0.20,
    "drift_free": 0.15,
    "open_incidents": 0.15,
    "pending_mutations": 0.10,
}
ACTIVE_INCIDENT_STATUSES = {"firing", "open", "active", "triggered"}
TERMINAL_LEDGER_EVENTS = {"execution.completed", "execution.failed", "execution.aborted", "intent.rejected"}
ACTIVE_LEDGER_EVENTS = {"intent.compiled", "intent.approved", "execution.started"}
HEALTH_TABLE_NAME = "health.composite"
SQLITE_HEALTH_TABLE_NAME = "health_composite"


def repo_root_default() -> Path:
    return Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Signal:
    name: str
    value: Any
    score: float
    weight: float
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "score": round(float(self.score), 3),
            "weight": round(float(self.weight), 3),
            "reason": self.reason,
        }


@dataclass(frozen=True)
class ServiceHealthEntry:
    service_id: str
    composite_status: str
    composite_score: float
    safe_to_act: bool
    computed_at: datetime
    ttl_seconds: int
    signals: list[Signal]

    def is_stale(self, *, now: datetime | None = None) -> bool:
        observed_now = now or utc_now()
        return observed_now > (self.computed_at + timedelta(seconds=self.ttl_seconds))

    def primary_reason(self) -> str:
        sorted_signals = sorted(self.signals, key=lambda item: (item.score, -item.weight, item.name))
        return sorted_signals[0].reason if sorted_signals else "no signals recorded"

    def as_dict(self, *, now: datetime | None = None) -> dict[str, Any]:
        observed_now = now or utc_now()
        age_seconds = max(0, int((observed_now - self.computed_at).total_seconds()))
        return {
            "service_id": self.service_id,
            "status": self.composite_status,
            "composite_status": self.composite_status,
            "composite_score": round(float(self.composite_score), 3),
            "safe_to_act": self.safe_to_act,
            "computed_at": self.computed_at.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "ttl_seconds": self.ttl_seconds,
            "stale": self.is_stale(now=observed_now),
            "age_seconds": age_seconds,
            "reason": self.primary_reason(),
            "signals": [signal.as_dict() for signal in self.signals],
        }


class HealthCompositeError(RuntimeError):
    pass


class ServiceHealthNotFoundError(HealthCompositeError):
    def __init__(self, service_id: str):
        super().__init__(f"Health composite entry for service '{service_id}' was not found")
        self.service_id = service_id


class HealthEntryStaleError(HealthCompositeError):
    def __init__(self, service_id: str, computed_at: datetime, ttl_seconds: int):
        super().__init__(
            f"Health composite entry for service '{service_id}' is stale "
            f"(computed_at={computed_at.isoformat()}, ttl_seconds={ttl_seconds})"
        )
        self.service_id = service_id
        self.computed_at = computed_at
        self.ttl_seconds = ttl_seconds


def health_dsn_from_env() -> str | None:
    for key in ("LV3_HEALTH_DSN", "WORLD_STATE_DSN", "LV3_GRAPH_DSN", "LV3_LEDGER_DSN"):
        value = os.environ.get(key, "").strip()
        if value:
            return value
    return None


def world_state_client_for_repo(repo_root: Path, *, dsn: str | None = None) -> WorldStateClient:
    kwargs: dict[str, Any] = {"repo_root": repo_root, "dsn": dsn}
    if (dsn or "").startswith("sqlite:///"):
        kwargs["current_view_name"] = SQLITE_CURRENT_VIEW_NAME
        kwargs["snapshots_table_name"] = SQLITE_SNAPSHOTS_TABLE_NAME
    return WorldStateClient(**kwargs)


def load_service_catalog(repo_root: Path) -> list[dict[str, Any]]:
    path = repo_root / "config" / "service-capability-catalog.json"
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    services = payload.get("services", [])
    return [item for item in services if isinstance(item, dict)]


def latest_drift_report(repo_root: Path) -> dict[str, Any]:
    receipt_dir = repo_root / "receipts" / "drift-reports"
    if not receipt_dir.exists():
        return {}
    paths = sorted(receipt_dir.glob("*.json"))
    if not paths:
        return {}
    try:
        return json.loads(paths[-1].read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def load_triage_reports(repo_root: Path) -> list[dict[str, Any]]:
    report_dir = repo_root / ".local" / "triage" / "reports"
    if not report_dir.exists():
        return []
    reports: list[dict[str, Any]] = []
    for path in sorted(report_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            reports.append(payload)
    return reports


def load_maintenance_windows(
    repo_root: Path,
    *,
    world_state: WorldStateClient,
) -> list[dict[str, Any]]:
    try:
        payload = world_state.get("maintenance_windows", allow_stale=True)
    except (SurfaceNotFoundError, WorldStateUnavailable, StaleDataError, OSError, RuntimeError):
        payload = None
    if isinstance(payload, dict):
        active_windows = payload.get("active_windows")
        if isinstance(active_windows, list):
            return [item for item in active_windows if isinstance(item, dict)]
    try:
        windows = list_active_windows_best_effort(repo_root=repo_root)
    except (ModuleNotFoundError, OSError, RuntimeError, ValueError, json.JSONDecodeError):
        return []
    return [window for window in windows.values() if isinstance(window, dict)]


def load_service_health_snapshot(world_state: WorldStateClient) -> dict[str, Any]:
    try:
        return world_state.get("service_health", allow_stale=True)
    except (SurfaceNotFoundError, WorldStateUnavailable, StaleDataError, OSError, RuntimeError):
        return {"services": []}


def load_slo_entries(
    repo_root: Path,
    *,
    allow_live_queries: bool,
    query_fn: Callable[[str], float | None] | None = None,
) -> list[dict[str, Any]]:
    catalog_path = repo_root / "config" / "slo-catalog.json"
    if not catalog_path.exists():
        return []
    prometheus_url = None if allow_live_queries else ""
    try:
        return build_slo_status_entries(
            repo_root=repo_root,
            prometheus_url=prometheus_url,
            query_fn=query_fn,
        )
    except (ModuleNotFoundError, OSError, RuntimeError, ValueError, json.JSONDecodeError):
        return []


def _load_ledger_events_from_file(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            events.append(payload)
    return events


def load_ledger_events(
    repo_root: Path,
    *,
    ledger_dsn: str | None = None,
) -> list[dict[str, Any]]:
    resolved_dsn = (ledger_dsn or os.environ.get("LV3_LEDGER_DSN", "")).strip()
    if resolved_dsn:
        try:
            reader = LedgerReader(dsn=resolved_dsn)
            return reader.events_in_time_range(
                from_ts="1970-01-01T00:00:00Z",
                to_ts=utc_now().isoformat(),
                limit=5000,
            )
        except Exception:
            pass
    return _load_ledger_events_from_file(repo_root / ".local" / "state" / "ledger" / "ledger.events.jsonl")


def load_degradation_state(repo_root: Path) -> dict[str, list[dict[str, Any]]]:
    configured = os.environ.get("LV3_DEGRADATION_STATE_PATH", "").strip()
    path = Path(configured) if configured else default_state_path(repo_root)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    services = payload.get("services", []) if isinstance(payload, dict) else {}
    if not isinstance(services, dict):
        return {}
    result: dict[str, list[dict[str, Any]]] = {}
    for service_id, entries in services.items():
        if not isinstance(service_id, str) or not isinstance(entries, dict):
            continue
        normalized = [entry for entry in entries.values() if isinstance(entry, dict)]
        if normalized:
            result[service_id] = normalized
    return result


def _score_probe_status(status: str) -> tuple[float, str]:
    return runtime_state_score(status)


def _service_health_map(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    services = payload.get("services", []) if isinstance(payload, dict) else []
    return {
        str(item.get("service_id") or item.get("id")): item
        for item in services
        if isinstance(item, dict) and (item.get("service_id") or item.get("id"))
    }


def _maintenance_active(service_id: str, windows: list[dict[str, Any]]) -> bool:
    for window in windows:
        target = str(window.get("service_id") or "").strip()
        if target in {"all", service_id}:
            return True
    return False


def _health_probe_signal(service_id: str, health_map: dict[str, dict[str, Any]]) -> Signal:
    item = health_map.get(service_id, {})
    status = canonical_runtime_state(item)
    score, reason = _score_probe_status(status)
    detail = (
        f"{reason}; HTTP {item['http_status']}" if isinstance(item.get("http_status"), int) else reason
    )
    return Signal(
        name="health_probe",
        value=status,
        score=score,
        weight=DEFAULT_SIGNAL_WEIGHTS["health_probe"],
        reason=detail,
    )


def _slo_budget_signal(service_id: str, slo_entries: list[dict[str, Any]]) -> Signal:
    service_entries = [entry for entry in slo_entries if str(entry.get("service_id")) == service_id]
    budgets = [
        float(entry["metrics"]["budget_remaining"])
        for entry in service_entries
        if isinstance(entry.get("metrics"), dict) and isinstance(entry["metrics"].get("budget_remaining"), (int, float))
    ]
    if not service_entries:
        return Signal(
            name="slo_budget",
            value=None,
            score=1.0,
            weight=DEFAULT_SIGNAL_WEIGHTS["slo_budget"],
            reason="no SLOs defined; neutral contribution",
        )
    if not budgets:
        return Signal(
            name="slo_budget",
            value=None,
            score=1.0,
            weight=DEFAULT_SIGNAL_WEIGHTS["slo_budget"],
            reason="SLOs exist but live budget data is unavailable; neutral contribution",
        )
    remaining = max(0.0, min(budgets))
    return Signal(
        name="slo_budget",
        value=remaining,
        score=remaining,
        weight=DEFAULT_SIGNAL_WEIGHTS["slo_budget"],
        reason=f"{remaining:.0%} error budget remaining",
    )


def _matching_drift_records(service_id: str, drift_report: dict[str, Any]) -> list[dict[str, Any]]:
    records = drift_report.get("records", []) if isinstance(drift_report, dict) else []
    matches: list[dict[str, Any]] = []
    for item in records:
        if not isinstance(item, dict):
            continue
        candidates = {
            str(item.get("service_id", "")).strip(),
            str(item.get("service", "")).strip(),
            str(item.get("resource", "")).strip(),
        }
        if service_id in candidates:
            matches.append(item)
    return matches


def _drift_signal(service_id: str, drift_report: dict[str, Any]) -> Signal:
    records = _matching_drift_records(service_id, drift_report)
    critical = [item for item in records if str(item.get("severity")).lower() == "critical"]
    warnings = [item for item in records if str(item.get("severity")).lower() in {"warn", "warning"}]
    if critical:
        return Signal(
            name="drift_free",
            value="critical",
            score=0.0,
            weight=DEFAULT_SIGNAL_WEIGHTS["drift_free"],
            reason=f"{len(critical)} critical drift finding(s) present",
        )
    if warnings or records:
        return Signal(
            name="drift_free",
            value="warning",
            score=0.5,
            weight=DEFAULT_SIGNAL_WEIGHTS["drift_free"],
            reason=f"{len(records)} drift finding(s) present",
        )
    return Signal(
        name="drift_free",
        value="clean",
        score=1.0,
        weight=DEFAULT_SIGNAL_WEIGHTS["drift_free"],
        reason="no drift detected",
    )


def _incident_signal(service_id: str, triage_reports: list[dict[str, Any]]) -> Signal:
    active = []
    for report in triage_reports:
        if str(report.get("affected_service")) != service_id:
            continue
        status = str(report.get("status", "open")).strip().lower()
        if status in ACTIVE_INCIDENT_STATUSES or not status:
            active.append(report)
    critical = [
        report
        for report in active
        if str(report.get("severity", "")).strip().lower() == "critical"
    ]
    if critical or len(active) >= 2:
        return Signal(
            name="open_incidents",
            value=len(active),
            score=0.0,
            weight=DEFAULT_SIGNAL_WEIGHTS["open_incidents"],
            reason=f"{len(active)} open incidents require operator attention",
        )
    if active:
        incident_id = str(active[0].get("incident_id", "incident"))
        return Signal(
            name="open_incidents",
            value=1,
            score=0.5,
            weight=DEFAULT_SIGNAL_WEIGHTS["open_incidents"],
            reason=f"open incident {incident_id}",
        )
    return Signal(
        name="open_incidents",
        value=0,
        score=1.0,
        weight=DEFAULT_SIGNAL_WEIGHTS["open_incidents"],
        reason="no open incidents",
    )


def _service_matches_event(service_id: str, event: dict[str, Any]) -> bool:
    if str(event.get("target_kind")) == "service" and str(event.get("target_id")) == service_id:
        return True
    payload = event.get("after_state")
    if isinstance(payload, dict):
        target = payload.get("target")
        if isinstance(target, dict):
            services = target.get("services")
            if isinstance(services, list) and service_id in {str(item) for item in services}:
                return True
    return False


def _pending_mutation_signal(service_id: str, ledger_events: list[dict[str, Any]]) -> Signal:
    active_by_intent: dict[str, dict[str, Any]] = {}
    for event in ledger_events:
        if not isinstance(event, dict) or not _service_matches_event(service_id, event):
            continue
        intent_id = str(event.get("actor_intent_id") or event.get("event_id") or "")
        if not intent_id:
            continue
        event_type = str(event.get("event_type", "")).strip()
        if event_type in TERMINAL_LEDGER_EVENTS:
            active_by_intent.pop(intent_id, None)
            continue
        if event_type in ACTIVE_LEDGER_EVENTS:
            active_by_intent[intent_id] = event
    active = list(active_by_intent.values())
    if len(active) >= 2:
        return Signal(
            name="pending_mutations",
            value=len(active),
            score=0.3,
            weight=DEFAULT_SIGNAL_WEIGHTS["pending_mutations"],
            reason=f"{len(active)} concurrent mutation intents are active",
        )
    if active:
        event_type = str(active[0].get("event_type"))
        state_label = "executing" if event_type == "execution.started" else "pending approval"
        return Signal(
            name="pending_mutations",
            value=1,
            score=0.8,
            weight=DEFAULT_SIGNAL_WEIGHTS["pending_mutations"],
            reason=f"1 mutation intent is {state_label}",
        )
    return Signal(
        name="pending_mutations",
        value=0,
        score=1.0,
        weight=DEFAULT_SIGNAL_WEIGHTS["pending_mutations"],
        reason="no pending mutations",
    )


def _degraded_mode_signal(service_id: str, degradation_state: dict[str, list[dict[str, Any]]]) -> Signal:
    active = degradation_state.get(service_id, [])
    if not active:
        return Signal(
            name="degraded_mode",
            value=[],
            score=1.0,
            weight=0.0,
            reason="no active degraded modes",
        )
    dependencies = ", ".join(sorted(str(item.get("dependency", "")).strip() for item in active if item.get("dependency")))
    return Signal(
        name="degraded_mode",
        value=active,
        score=0.5,
        weight=0.0,
        reason=f"active degraded mode for {dependencies or 'unknown dependency'}",
    )


def _status_for_score(score: float) -> str:
    if score < 0.4:
        return "critical"
    if score < 0.85:
        return "degraded"
    return "healthy"


def compute_health_entries(
    services: list[dict[str, Any]],
    *,
    service_health_snapshot: dict[str, Any],
    slo_entries: list[dict[str, Any]],
    drift_report: dict[str, Any],
    triage_reports: list[dict[str, Any]],
    maintenance_windows: list[dict[str, Any]],
    ledger_events: list[dict[str, Any]],
    degradation_state: dict[str, list[dict[str, Any]]] | None = None,
    computed_at: datetime | None = None,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> list[ServiceHealthEntry]:
    observed_at = computed_at or utc_now()
    health_map = _service_health_map(service_health_snapshot)
    active_degradations = degradation_state or {}
    entries: list[ServiceHealthEntry] = []
    for service in services:
        if str(service.get("lifecycle_status", "active")) != "active":
            continue
        service_id = str(service.get("id", "")).strip()
        if not service_id:
            continue

        signals = [
            _health_probe_signal(service_id, health_map),
            _slo_budget_signal(service_id, slo_entries),
            _drift_signal(service_id, drift_report),
            _incident_signal(service_id, triage_reports),
            _pending_mutation_signal(service_id, ledger_events),
            _degraded_mode_signal(service_id, active_degradations),
        ]

        maintenance_active = _maintenance_active(service_id, maintenance_windows)
        if maintenance_active:
            score = 0.9
            status = "maintenance"
            safe_to_act = True
        elif signals[0].score == 0.0 and signals[3].value >= 1:
            score = 0.0
            status = "critical"
            safe_to_act = False
        elif signals[1].score == 0.0:
            score = 0.0
            status = "critical"
            safe_to_act = False
        else:
            score = sum(signal.score * signal.weight for signal in signals)
            score = max(0.0, min(1.0, score))
            status = _status_for_score(score)
            if signals[0].value == "startup":
                status = "degraded"
                safe_to_act = False
            else:
                safe_to_act = score >= 0.7 and not any(signal.score == 0.0 for signal in signals)
            if any(signal.score == 0.0 for signal in signals) and status == "healthy":
                status = "degraded"
            if active_degradations.get(service_id):
                status = "degraded"
                safe_to_act = False

        entries.append(
            ServiceHealthEntry(
                service_id=service_id,
                composite_status=status,
                composite_score=round(score, 3),
                safe_to_act=safe_to_act,
                computed_at=observed_at,
                ttl_seconds=ttl_seconds,
                signals=signals,
            )
        )
    entries.sort(key=lambda item: item.service_id)
    return entries


class HealthCompositeClient:
    def __init__(
        self,
        repo_root: Path | str | None = None,
        *,
        dsn: str | None = None,
        world_state_dsn: str | None = None,
        ledger_dsn: str | None = None,
        connection_factory: ConnectionFactory | None = None,
    ) -> None:
        self.repo_root = Path(repo_root) if repo_root is not None else repo_root_default()
        self._dsn = dsn or health_dsn_from_env()
        self._world_state_dsn = world_state_dsn or self._dsn
        self._ledger_dsn = ledger_dsn or self._dsn
        self._connection_factory = connection_factory

    def _resolved_connection_factory(self) -> ConnectionFactory:
        if self._connection_factory is not None:
            return self._connection_factory
        if not self._dsn:
            raise HealthCompositeError("health composite storage is not configured")
        return create_connection_factory(self._dsn)

    def _world_state_client(self) -> WorldStateClient:
        return world_state_client_for_repo(self.repo_root, dsn=self._world_state_dsn)

    def _compute_entries(
        self,
        *,
        computed_at: datetime | None = None,
        allow_live_slo_queries: bool,
        slo_query_fn: Callable[[str], float | None] | None = None,
    ) -> list[ServiceHealthEntry]:
        repo_root = self.repo_root
        world_state = self._world_state_client()
        return compute_health_entries(
            load_service_catalog(repo_root),
            service_health_snapshot=load_service_health_snapshot(world_state),
            slo_entries=load_slo_entries(repo_root, allow_live_queries=allow_live_slo_queries, query_fn=slo_query_fn),
            drift_report=latest_drift_report(repo_root),
            triage_reports=load_triage_reports(repo_root),
            maintenance_windows=load_maintenance_windows(repo_root, world_state=world_state),
            ledger_events=load_ledger_events(repo_root, ledger_dsn=self._ledger_dsn),
            degradation_state=load_degradation_state(repo_root),
            computed_at=computed_at,
        )

    def _table_name(self, connection: Any) -> str:
        return SQLITE_HEALTH_TABLE_NAME if connection_kind(connection) == "sqlite" else HEALTH_TABLE_NAME

    def _ensure_sqlite_schema(self, connection: Any) -> None:
        if connection_kind(connection) != "sqlite":
            return
        cursor = connection.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS health_composite (
                service_id TEXT PRIMARY KEY,
                composite_status TEXT NOT NULL,
                composite_score REAL NOT NULL,
                safe_to_act INTEGER NOT NULL,
                signals TEXT NOT NULL,
                computed_at TEXT NOT NULL,
                ttl_seconds INTEGER NOT NULL DEFAULT 120
            )
            """
        )
        connection.commit()

    def _row_to_entry(self, row: dict[str, Any]) -> ServiceHealthEntry:
        payload = decode_json(row["signals"])
        signals = [
            Signal(
                name=str(item.get("name")),
                value=item.get("value"),
                score=float(item.get("score", 0.0)),
                weight=float(item.get("weight", 0.0)),
                reason=str(item.get("reason", "")),
            )
            for item in payload
            if isinstance(item, dict)
        ]
        return ServiceHealthEntry(
            service_id=str(row["service_id"]),
            composite_status=str(row["composite_status"]),
            composite_score=float(row["composite_score"]),
            safe_to_act=bool(row["safe_to_act"]),
            computed_at=parse_timestamp(row["computed_at"]),
            ttl_seconds=int(row["ttl_seconds"]),
            signals=signals,
        )

    def _fetch_all_rows(self) -> list[dict[str, Any]]:
        factory = self._resolved_connection_factory()
        with managed_connection(factory) as connection:
            self._ensure_sqlite_schema(connection)
            cursor = connection.cursor()
            cursor.execute(
                f"""
                SELECT
                    service_id,
                    composite_status,
                    composite_score,
                    safe_to_act,
                    signals,
                    computed_at,
                    ttl_seconds
                FROM {self._table_name(connection)}
                ORDER BY service_id
                """
            )
            return rows_to_dicts(cursor)

    def get_all(self, *, allow_stale: bool = False) -> list[ServiceHealthEntry]:
        if self._dsn:
            try:
                entries = [self._row_to_entry(row) for row in self._fetch_all_rows()]
            except Exception:
                entries = []
            if entries:
                if not allow_stale:
                    stale = next((entry for entry in entries if entry.is_stale()), None)
                    if stale is not None:
                        raise HealthEntryStaleError(stale.service_id, stale.computed_at, stale.ttl_seconds)
                return entries
        return self._compute_entries(allow_live_slo_queries=False)

    def get(self, service_id: str, *, allow_stale: bool = False) -> ServiceHealthEntry:
        for entry in self.get_all(allow_stale=allow_stale):
            if entry.service_id == service_id:
                return entry
        raise ServiceHealthNotFoundError(service_id)

    def refresh(
        self,
        *,
        computed_at: datetime | None = None,
        allow_live_slo_queries: bool = True,
        slo_query_fn: Callable[[str], float | None] | None = None,
        event_publisher: Callable[[str, dict[str, Any]], Any] | None = None,
    ) -> dict[str, Any]:
        if not self._dsn:
            raise HealthCompositeError("health composite refresh requires a configured DSN")
        observed_at = computed_at or utc_now()
        entries = self._compute_entries(
            computed_at=observed_at,
            allow_live_slo_queries=allow_live_slo_queries,
            slo_query_fn=slo_query_fn,
        )
        factory = self._resolved_connection_factory()
        previous: dict[str, ServiceHealthEntry] = {}
        events: list[dict[str, Any]] = []
        with managed_connection(factory) as connection:
            self._ensure_sqlite_schema(connection)
            table_name = self._table_name(connection)
            parameter = placeholder(connection)
            cursor = connection.cursor()
            cursor.execute(
                f"""
                SELECT
                    service_id,
                    composite_status,
                    composite_score,
                    safe_to_act,
                    signals,
                    computed_at,
                    ttl_seconds
                FROM {table_name}
                """
            )
            previous = {entry.service_id: entry for entry in (self._row_to_entry(row) for row in rows_to_dicts(cursor))}

            if connection_kind(connection) == "sqlite":
                upsert_sql = f"""
                    INSERT INTO {table_name} (
                        service_id,
                        composite_status,
                        composite_score,
                        safe_to_act,
                        signals,
                        computed_at,
                        ttl_seconds
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(service_id) DO UPDATE SET
                        composite_status=excluded.composite_status,
                        composite_score=excluded.composite_score,
                        safe_to_act=excluded.safe_to_act,
                        signals=excluded.signals,
                        computed_at=excluded.computed_at,
                        ttl_seconds=excluded.ttl_seconds
                """
            else:
                upsert_sql = f"""
                    INSERT INTO {table_name} (
                        service_id,
                        composite_status,
                        composite_score,
                        safe_to_act,
                        signals,
                        computed_at,
                        ttl_seconds
                    ) VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s)
                    ON CONFLICT (service_id) DO UPDATE SET
                        composite_status = EXCLUDED.composite_status,
                        composite_score = EXCLUDED.composite_score,
                        safe_to_act = EXCLUDED.safe_to_act,
                        signals = EXCLUDED.signals,
                        computed_at = EXCLUDED.computed_at,
                        ttl_seconds = EXCLUDED.ttl_seconds
                """

            for entry in entries:
                cursor.execute(
                    upsert_sql,
                    (
                        entry.service_id,
                        entry.composite_status,
                        entry.composite_score,
                        entry.safe_to_act,
                        json.dumps([signal.as_dict() for signal in entry.signals]),
                        entry.computed_at.isoformat(),
                        entry.ttl_seconds,
                    ),
                )
            connection.commit()

        if event_publisher is not None:
            for entry in entries:
                previous_entry = previous.get(entry.service_id)
                if previous_entry is None or previous_entry.composite_status == entry.composite_status:
                    continue
                payload = {
                    "service_id": entry.service_id,
                    "previous_status": previous_entry.composite_status,
                    "status": entry.composite_status,
                    "composite_score": entry.composite_score,
                    "safe_to_act": entry.safe_to_act,
                    "computed_at": entry.computed_at.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                }
                if entry.composite_status in {"degraded", "critical"}:
                    event_publisher("platform.health.degraded", payload)
                    events.append({"subject": "platform.health.degraded", **payload})
                elif previous_entry.composite_status in {"degraded", "critical"}:
                    event_publisher("platform.health.recovered", payload)
                    events.append({"subject": "platform.health.recovered", **payload})

        return {
            "status": "ok",
            "service_count": len(entries),
            "computed_at": observed_at.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "entries": [entry.as_dict(now=observed_at) for entry in entries],
            "events": events,
        }
