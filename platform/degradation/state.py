from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def utcnow() -> datetime:
    return datetime.now(UTC)


def isoformat(value: datetime | None = None) -> str:
    current = value or utcnow()
    return current.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def default_state_path(repo_root: Path | str) -> Path:
    return Path(repo_root) / ".local" / "state" / "degradation" / "degradation-state.json"


class DegradationStateStore:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    def _load_payload(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"schema_version": "1.0.0", "services": {}}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"schema_version": "1.0.0", "services": {}}
        if not isinstance(payload, dict):
            return {"schema_version": "1.0.0", "services": {}}
        services = payload.get("services")
        if not isinstance(services, dict):
            payload["services"] = {}
        payload.setdefault("schema_version", "1.0.0")
        return payload

    def _write_payload(self, payload: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_suffix(f"{self.path.suffix}.tmp")
        tmp_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        tmp_path.replace(self.path)

    def active_for_service(self, service_id: str) -> list[dict[str, Any]]:
        payload = self._load_payload()
        services = payload.get("services", {})
        if not isinstance(services, dict):
            return []
        entries = services.get(service_id, {})
        if not isinstance(entries, dict):
            return []
        result = [entry for entry in entries.values() if isinstance(entry, dict)]
        result.sort(key=lambda item: str(item.get("dependency", "")))
        return result

    def all_active(self) -> dict[str, list[dict[str, Any]]]:
        payload = self._load_payload()
        services = payload.get("services", {})
        if not isinstance(services, dict):
            return {}
        result: dict[str, list[dict[str, Any]]] = {}
        for service_id, entries in services.items():
            if not isinstance(service_id, str) or not isinstance(entries, dict):
                continue
            normalized = [entry for entry in entries.values() if isinstance(entry, dict)]
            if not normalized:
                continue
            normalized.sort(key=lambda item: str(item.get("dependency", "")))
            result[service_id] = normalized
        return result

    def activate(
        self,
        service_id: str,
        mode: dict[str, Any] | None,
        *,
        source: str,
        last_error: str | None = None,
        metadata: dict[str, Any] | None = None,
        observed_at: datetime | None = None,
    ) -> dict[str, Any]:
        declaration = dict(mode or {})
        dependency = str(declaration.get("dependency") or source).strip()
        entry = {
            "service_id": service_id,
            "dependency": dependency,
            "dependency_type": str(declaration.get("dependency_type") or "soft"),
            "degraded_behaviour": str(declaration.get("degraded_behaviour") or "").strip(),
            "degraded_for_seconds_max": declaration.get("degraded_for_seconds_max", -1),
            "recovery_signal": str(declaration.get("recovery_signal") or "").strip(),
            "tested_by": str(declaration.get("tested_by") or "").strip(),
            "source": source,
            "observed_at": isoformat(observed_at),
            "last_error": last_error or "",
            "metadata": metadata or {},
        }
        payload = self._load_payload()
        services = payload.setdefault("services", {})
        service_entries = services.setdefault(service_id, {})
        service_entries[dependency] = entry
        self._write_payload(payload)
        return entry

    def clear(self, service_id: str, dependency: str) -> bool:
        payload = self._load_payload()
        services = payload.get("services", {})
        if not isinstance(services, dict):
            return False
        service_entries = services.get(service_id)
        if not isinstance(service_entries, dict) or dependency not in service_entries:
            return False
        del service_entries[dependency]
        if not service_entries:
            services.pop(service_id, None)
        self._write_payload(payload)
        return True
