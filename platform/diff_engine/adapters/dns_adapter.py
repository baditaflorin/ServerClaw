from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from platform.world_state.client import SurfaceNotFoundError, WorldStateClient

from ..schema import ChangedObject, unknown_object


class DNSAdapter:
    def __init__(self, *, repo_root: Path, spec: Any) -> None:
        self.repo_root = repo_root
        self.spec = spec

    def compute_diff(
        self,
        intent: dict[str, Any],
        *,
        world_state: WorldStateClient | None,
        workflow: dict[str, Any],
        service: dict[str, Any] | None,
    ) -> list[ChangedObject]:
        del workflow
        desired = self._desired_records(intent, service)
        if not desired:
            return []
        current = self._current_records(world_state)
        if current is None:
            return [
                unknown_object(surface="dns_record", object_id=item["fqdn"], notes="DNS world-state surface is unavailable")
                for item in desired
            ]
        current_by_name = {str(item.get("fqdn")): item for item in current}
        changes: list[ChangedObject] = []
        for record in desired:
            fqdn = str(record["fqdn"])
            current_record = current_by_name.get(fqdn)
            after = {key: record.get(key) for key in ("target", "target_port", "status", "exposure")}
            if current_record is None:
                changes.append(
                    ChangedObject(
                        surface="dns_record",
                        object_id=fqdn,
                        change_kind="create",
                        before=None,
                        after=after,
                        confidence="exact",
                        reversible=True,
                        notes="record is declared in the subdomain catalog but missing from world state",
                    )
                )
                continue
            before = {key: current_record.get(key) for key in ("target", "target_port", "status", "exposure")}
            if before != after:
                changes.append(
                    ChangedObject(
                        surface="dns_record",
                        object_id=fqdn,
                        change_kind="update",
                        before=before,
                        after=after,
                        confidence="exact",
                        reversible=True,
                        notes="world-state DNS record differs from the repository catalog",
                    )
                )
        return changes

    def _desired_records(self, intent: dict[str, Any], service: dict[str, Any] | None) -> list[dict[str, Any]]:
        catalog_path = self.repo_root / "config" / "subdomain-catalog.json"
        if not catalog_path.exists():
            return []
        payload = json.loads(catalog_path.read_text())
        records = payload.get("subdomains", [])
        if not isinstance(records, list):
            return []

        desired: list[dict[str, Any]] = []
        service_id = str(intent.get("target_service_id", ""))
        service_fqdn = None
        if isinstance(service, dict):
            service_fqdn = service.get("subdomain")
            if not service_fqdn and isinstance(service.get("public_url"), str):
                service_fqdn = urlparse(service["public_url"]).hostname
        for item in records:
            if not isinstance(item, dict):
                continue
            if str(item.get("service_id", "")) == service_id or str(item.get("fqdn", "")) == str(service_fqdn or ""):
                desired.append(item)
        return desired

    @staticmethod
    def _current_records(world_state: WorldStateClient | None) -> list[dict[str, Any]] | None:
        if world_state is None:
            return None
        try:
            payload = world_state.get("dns_records", allow_stale=True)
        except (SurfaceNotFoundError, RuntimeError):
            return None
        return payload if isinstance(payload, list) else None
