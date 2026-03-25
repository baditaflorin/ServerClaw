from __future__ import annotations

import json
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
EXECUTION_LANES_PATH = REPO_ROOT / "config" / "execution-lanes.yaml"
ALLOWED_ADMISSION_POLICIES = {"hard", "soft"}
ALLOWED_SERIALISATION = {"strict", "resource_lock"}


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _isoformat(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_isoformat(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _load_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _require_mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be a mapping")
    return value


def _require_list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{path} must be a list")
    return value


def _require_str(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path} must be a non-empty string")
    return value.strip()


def _require_int(value: Any, path: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{path} must be an integer")
    if value < minimum:
        raise ValueError(f"{path} must be >= {minimum}")
    return value


@dataclass(frozen=True)
class ResourceReservation:
    cpu_milli: int
    memory_mb: int
    disk_iops: int
    estimated_duration_seconds: int

    def usage(self) -> "ResourceUsage":
        return ResourceUsage(
            cpu_milli=self.cpu_milli,
            memory_mb=self.memory_mb,
            disk_iops=self.disk_iops,
        )

    def as_dict(self) -> dict[str, int]:
        return {
            "cpu_milli": self.cpu_milli,
            "memory_mb": self.memory_mb,
            "disk_iops": self.disk_iops,
            "estimated_duration_seconds": self.estimated_duration_seconds,
        }


@dataclass(frozen=True)
class ResourceUsage:
    cpu_milli: int = 0
    memory_mb: int = 0
    disk_iops: int = 0

    def add(self, reservation: ResourceReservation) -> "ResourceUsage":
        return ResourceUsage(
            cpu_milli=self.cpu_milli + reservation.cpu_milli,
            memory_mb=self.memory_mb + reservation.memory_mb,
            disk_iops=self.disk_iops + reservation.disk_iops,
        )

    def as_dict(self) -> dict[str, int]:
        return {
            "cpu_milli": self.cpu_milli,
            "memory_mb": self.memory_mb,
            "disk_iops": self.disk_iops,
        }


@dataclass(frozen=True)
class LaneBudget:
    total_cpu_milli: int
    total_memory_mb: int
    total_disk_iops: int

    def as_usage(self) -> ResourceUsage:
        return ResourceUsage(
            cpu_milli=self.total_cpu_milli,
            memory_mb=self.total_memory_mb,
            disk_iops=self.total_disk_iops,
        )

    def as_dict(self) -> dict[str, int]:
        return {
            "total_cpu_milli": self.total_cpu_milli,
            "total_memory_mb": self.total_memory_mb,
            "total_disk_iops": self.total_disk_iops,
        }


@dataclass(frozen=True)
class ExecutionLane:
    lane_id: str
    vm_id: int | None
    hostname: str
    max_concurrent_ops: int
    serialisation: str
    admission_policy: str
    budget: LaneBudget
    services: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "lane_id": self.lane_id,
            "vm_id": self.vm_id,
            "hostname": self.hostname,
            "max_concurrent_ops": self.max_concurrent_ops,
            "serialisation": self.serialisation,
            "admission_policy": self.admission_policy,
            "services": list(self.services),
            "vm_budget": self.budget.as_dict(),
        }


@dataclass(frozen=True)
class LaneReservationRecord:
    actor_intent_id: str
    workflow_id: str
    requested_by: str
    lane_id: str
    reservation: ResourceReservation
    reserved_at: str
    expires_at: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "actor_intent_id": self.actor_intent_id,
            "workflow_id": self.workflow_id,
            "requested_by": self.requested_by,
            "lane_id": self.lane_id,
            "reservation": self.reservation.as_dict(),
            "reserved_at": self.reserved_at,
            "expires_at": self.expires_at,
        }


@dataclass(frozen=True)
class LaneReservationDecision:
    allowed: bool
    lane: ExecutionLane
    reservation: ResourceReservation
    current_usage: ResourceUsage
    projected_usage: ResourceUsage
    active_reservations: int
    reasons: tuple[str, ...]
    soft_exceeded: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "lane": self.lane.as_dict(),
            "reservation": self.reservation.as_dict(),
            "current_usage": self.current_usage.as_dict(),
            "projected_usage": self.projected_usage.as_dict(),
            "active_reservations": self.active_reservations,
            "reasons": list(self.reasons),
            "soft_exceeded": self.soft_exceeded,
        }


def load_execution_lanes(
    *,
    repo_root: Path | None = None,
    lanes_path: Path | None = None,
) -> dict[str, ExecutionLane]:
    root = repo_root or REPO_ROOT
    path = lanes_path or root / "config" / "execution-lanes.yaml"
    if not path.exists():
        return {}
    payload = _load_yaml(path)
    lanes_payload = _require_list(payload.get("lanes"), f"{path}.lanes")
    lanes: dict[str, ExecutionLane] = {}
    hostnames: set[str] = set()
    for index, raw_lane in enumerate(lanes_payload):
        lane = _require_mapping(raw_lane, f"{path}.lanes[{index}]")
        lane_id = _require_str(lane.get("lane_id"), f"{path}.lanes[{index}].lane_id")
        if lane_id in lanes:
            raise ValueError(f"duplicate execution lane '{lane_id}'")
        hostname = _require_str(lane.get("hostname"), f"{path}.lanes[{index}].hostname")
        if hostname in hostnames:
            raise ValueError(f"duplicate execution lane hostname '{hostname}'")
        hostnames.add(hostname)
        vm_id_raw = lane.get("vm_id")
        vm_id = None if vm_id_raw is None else _require_int(vm_id_raw, f"{path}.lanes[{index}].vm_id", minimum=1)
        max_concurrent_ops = _require_int(
            lane.get("max_concurrent_ops"),
            f"{path}.lanes[{index}].max_concurrent_ops",
            minimum=1,
        )
        serialisation = _require_str(lane.get("serialisation"), f"{path}.lanes[{index}].serialisation")
        if serialisation not in ALLOWED_SERIALISATION:
            raise ValueError(
                f"{path}.lanes[{index}].serialisation must be one of {sorted(ALLOWED_SERIALISATION)}"
            )
        admission_policy = _require_str(
            lane.get("admission_policy"),
            f"{path}.lanes[{index}].admission_policy",
        )
        if admission_policy not in ALLOWED_ADMISSION_POLICIES:
            raise ValueError(
                f"{path}.lanes[{index}].admission_policy must be one of {sorted(ALLOWED_ADMISSION_POLICIES)}"
            )
        budget = _require_mapping(lane.get("vm_budget"), f"{path}.lanes[{index}].vm_budget")
        services_payload = _require_list(lane.get("services", []), f"{path}.lanes[{index}].services")
        services = tuple(
            _require_str(item, f"{path}.lanes[{index}].services[{service_index}]")
            for service_index, item in enumerate(services_payload)
        )
        lanes[lane_id] = ExecutionLane(
            lane_id=lane_id,
            vm_id=vm_id,
            hostname=hostname,
            max_concurrent_ops=max_concurrent_ops,
            serialisation=serialisation,
            admission_policy=admission_policy,
            budget=LaneBudget(
                total_cpu_milli=_require_int(
                    budget.get("total_cpu_milli"),
                    f"{path}.lanes[{index}].vm_budget.total_cpu_milli",
                    minimum=1,
                ),
                total_memory_mb=_require_int(
                    budget.get("total_memory_mb"),
                    f"{path}.lanes[{index}].vm_budget.total_memory_mb",
                    minimum=1,
                ),
                total_disk_iops=_require_int(
                    budget.get("total_disk_iops"),
                    f"{path}.lanes[{index}].vm_budget.total_disk_iops",
                    minimum=1,
                ),
            ),
            services=services,
        )
    return lanes


def _service_vm_map(repo_root: Path) -> dict[str, str]:
    path = repo_root / "config" / "service-capability-catalog.json"
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    services = payload.get("services")
    if not isinstance(services, list):
        return {}
    mapping: dict[str, str] = {}
    for service in services:
        if not isinstance(service, dict):
            continue
        service_id = service.get("id")
        vm_name = service.get("vm")
        if isinstance(service_id, str) and service_id.strip() and isinstance(vm_name, str) and vm_name.strip():
            mapping[service_id.strip()] = vm_name.strip()
    return mapping


def _intent_service_id(intent: Any) -> str | None:
    for attr in ("target_service_id",):
        value = getattr(intent, attr, None)
        if isinstance(value, str) and value.strip():
            return value.strip()
    target = getattr(intent, "target", None)
    services = getattr(target, "services", None)
    if isinstance(services, list):
        for item in services:
            if isinstance(item, str) and item.strip():
                return item.strip()
    arguments = getattr(intent, "arguments", {}) or {}
    for key in ("service", "service_id", "target_service"):
        value = arguments.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _intent_target_vm(intent: Any) -> str | None:
    for attr in ("target_vm",):
        value = getattr(intent, attr, None)
        if isinstance(value, str) and value.strip():
            return value.strip()
    scope = getattr(intent, "scope", None)
    allowed_hosts = getattr(scope, "allowed_hosts", None)
    if isinstance(allowed_hosts, list):
        for item in allowed_hosts:
            if isinstance(item, str) and item.strip():
                return item.strip()
    target = getattr(intent, "target", None)
    hosts = getattr(target, "hosts", None)
    if isinstance(hosts, list):
        for item in hosts:
            if isinstance(item, str) and item.strip():
                return item.strip()
    arguments = getattr(intent, "arguments", {}) or {}
    for key in ("host", "vm", "vm_name", "target_vm"):
        value = arguments.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def resolve_execution_lane(
    intent: Any,
    *,
    workflow: dict[str, Any] | None = None,
    repo_root: Path | None = None,
    lanes: dict[str, ExecutionLane] | None = None,
) -> ExecutionLane | None:
    root = repo_root or REPO_ROOT
    loaded_lanes = lanes if lanes is not None else load_execution_lanes(repo_root=root)
    if not loaded_lanes:
        return None
    workflow = workflow or {}
    explicit_lane = workflow.get("target_lane")
    if isinstance(explicit_lane, str) and explicit_lane.strip():
        return loaded_lanes.get(explicit_lane.strip())

    service_id = _intent_service_id(intent)
    service_vms = _service_vm_map(root)
    target_vm = service_vms.get(service_id or "") or _intent_target_vm(intent)
    if target_vm:
        for lane in loaded_lanes.values():
            if lane.hostname == target_vm:
                return lane

    return loaded_lanes.get("lane:platform")


class FileLaneReservationStore:
    def __init__(self, state_path: Path | None = None) -> None:
        self._state_path = state_path or (REPO_ROOT / ".local" / "scheduler" / "lane-reservations.json")
        self._lock_path = self._state_path.with_suffix(f"{self._state_path.suffix}.lock")

    @contextmanager
    def _locked_state(self) -> Any:
        import fcntl

        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_handle = self._lock_path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
            state = self._load_state()
            self._prune_expired(state)
            yield state
            self._write_state(state)
        finally:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
            lock_handle.close()

    def _load_state(self) -> dict[str, Any]:
        if not self._state_path.exists():
            return {"schema_version": "1.0.0", "reservations": []}
        payload = json.loads(self._state_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"{self._state_path} must contain an object")
        reservations = payload.get("reservations")
        if not isinstance(reservations, list):
            raise ValueError(f"{self._state_path}.reservations must be a list")
        return payload

    def _write_state(self, state: dict[str, Any]) -> None:
        self._state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    @staticmethod
    def _prune_expired(state: dict[str, Any], *, now: datetime | None = None) -> None:
        current_time = now or _utc_now()
        active: list[dict[str, Any]] = []
        for item in state.get("reservations", []):
            if not isinstance(item, dict):
                continue
            expires_at = item.get("expires_at")
            if not isinstance(expires_at, str):
                continue
            try:
                if _parse_isoformat(expires_at) <= current_time:
                    continue
            except ValueError:
                continue
            active.append(item)
        state["schema_version"] = "1.0.0"
        state["reservations"] = active

    @staticmethod
    def _records_for_lane(state: dict[str, Any], lane_id: str) -> list[LaneReservationRecord]:
        records: list[LaneReservationRecord] = []
        for item in state.get("reservations", []):
            if not isinstance(item, dict) or item.get("lane_id") != lane_id:
                continue
            reservation_payload = _require_mapping(item.get("reservation"), "lane reservation")
            records.append(
                LaneReservationRecord(
                    actor_intent_id=_require_str(item.get("actor_intent_id"), "lane reservation.actor_intent_id"),
                    workflow_id=_require_str(item.get("workflow_id"), "lane reservation.workflow_id"),
                    requested_by=_require_str(item.get("requested_by"), "lane reservation.requested_by"),
                    lane_id=_require_str(item.get("lane_id"), "lane reservation.lane_id"),
                    reservation=ResourceReservation(
                        cpu_milli=_require_int(reservation_payload.get("cpu_milli"), "lane reservation.cpu_milli", minimum=0),
                        memory_mb=_require_int(
                            reservation_payload.get("memory_mb"),
                            "lane reservation.memory_mb",
                            minimum=0,
                        ),
                        disk_iops=_require_int(
                            reservation_payload.get("disk_iops"),
                            "lane reservation.disk_iops",
                            minimum=0,
                        ),
                        estimated_duration_seconds=_require_int(
                            reservation_payload.get("estimated_duration_seconds"),
                            "lane reservation.estimated_duration_seconds",
                            minimum=1,
                        ),
                    ),
                    reserved_at=_require_str(item.get("reserved_at"), "lane reservation.reserved_at"),
                    expires_at=_require_str(item.get("expires_at"), "lane reservation.expires_at"),
                )
            )
        return records

    def reserve(
        self,
        *,
        lane: ExecutionLane,
        reservation: ResourceReservation,
        actor_intent_id: str,
        workflow_id: str,
        requested_by: str,
        ttl_seconds: int | None = None,
        now: datetime | None = None,
    ) -> LaneReservationDecision:
        current_time = now or _utc_now()
        ttl = ttl_seconds or max(1, reservation.estimated_duration_seconds * 2)
        with self._locked_state() as state:
            state["reservations"] = [
                item
                for item in state.get("reservations", [])
                if isinstance(item, dict) and item.get("actor_intent_id") != actor_intent_id
            ]
            active = self._records_for_lane(state, lane.lane_id)
            current_usage = ResourceUsage()
            for item in active:
                current_usage = current_usage.add(item.reservation)
            projected_usage = current_usage.add(reservation)
            reasons: list[str] = []
            if len(active) + 1 > lane.max_concurrent_ops:
                reasons.append("max_concurrent_ops")
            if projected_usage.cpu_milli > lane.budget.total_cpu_milli:
                reasons.append("cpu_milli")
            if projected_usage.memory_mb > lane.budget.total_memory_mb:
                reasons.append("memory_mb")
            if projected_usage.disk_iops > lane.budget.total_disk_iops:
                reasons.append("disk_iops")
            soft_exceeded = bool(reasons) and lane.admission_policy == "soft"
            allowed = not reasons or soft_exceeded
            if allowed:
                state.setdefault("reservations", []).append(
                    LaneReservationRecord(
                        actor_intent_id=actor_intent_id,
                        workflow_id=workflow_id,
                        requested_by=requested_by,
                        lane_id=lane.lane_id,
                        reservation=reservation,
                        reserved_at=_isoformat(current_time),
                        expires_at=_isoformat(current_time + timedelta(seconds=ttl)),
                    ).as_dict()
                )
            return LaneReservationDecision(
                allowed=allowed,
                lane=lane,
                reservation=reservation,
                current_usage=current_usage,
                projected_usage=projected_usage,
                active_reservations=len(active),
                reasons=tuple(reasons),
                soft_exceeded=soft_exceeded,
            )

    def renew(self, actor_intent_id: str, *, ttl_seconds: int, now: datetime | None = None) -> None:
        current_time = now or _utc_now()
        with self._locked_state() as state:
            for item in state.get("reservations", []):
                if isinstance(item, dict) and item.get("actor_intent_id") == actor_intent_id:
                    item["expires_at"] = _isoformat(current_time + timedelta(seconds=ttl_seconds))

    def release(self, actor_intent_id: str) -> None:
        with self._locked_state() as state:
            state["reservations"] = [
                item
                for item in state.get("reservations", [])
                if isinstance(item, dict) and item.get("actor_intent_id") != actor_intent_id
            ]

    def snapshot(self) -> dict[str, list[LaneReservationRecord]]:
        with self._locked_state() as state:
            lane_ids = sorted(
                {
                    item.get("lane_id")
                    for item in state.get("reservations", [])
                    if isinstance(item, dict) and isinstance(item.get("lane_id"), str)
                }
            )
            return {lane_id: self._records_for_lane(state, lane_id) for lane_id in lane_ids}
