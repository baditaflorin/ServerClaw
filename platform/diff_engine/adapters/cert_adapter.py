from __future__ import annotations

import json
from platform.datetime_compat import UTC, datetime
from pathlib import Path
from typing import Any

from platform.world_state.client import SurfaceNotFoundError, WorldStateClient

from ..schema import ChangedObject, unknown_object


def issuer_string(raw: Any) -> str:
    if isinstance(raw, str):
        return raw.lower()
    if isinstance(raw, list):
        fragments: list[str] = []
        for entry in raw:
            if isinstance(entry, tuple):
                fragments.extend(str(item) for item in entry)
            elif isinstance(entry, list):
                for pair in entry:
                    if isinstance(pair, tuple):
                        fragments.extend(str(item) for item in pair)
            else:
                fragments.append(str(entry))
        return " ".join(fragments).lower()
    return str(raw).lower()


class CertAdapter:
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
        desired = self._desired_certificates(intent, service)
        if not desired:
            return []
        current = self._current_certificates(world_state)
        if current is None:
            return [
                unknown_object(
                    surface="tls_cert",
                    object_id=item["endpoint"]["host"],
                    notes="TLS certificate world-state surface is unavailable",
                )
                for item in desired
            ]
        current_by_host = {str(item.get("fqdn")): item for item in current}
        changes: list[ChangedObject] = []
        for record in desired:
            endpoint = record.get("endpoint", {})
            host = str(endpoint.get("host", "unknown"))
            current_cert = current_by_host.get(host)
            expected_issuer = str(record.get("expected_issuer", "any")).strip().lower()
            if current_cert is None:
                changes.append(
                    ChangedObject(
                        surface="tls_cert",
                        object_id=host,
                        change_kind="renew",
                        before=None,
                        after={"expected_issuer": expected_issuer},
                        confidence="estimated",
                        reversible=True,
                        notes="certificate is declared in the catalog but absent from the world-state inventory",
                    )
                )
                continue
            current_issuer = issuer_string(current_cert.get("issuer"))
            current_status = str(current_cert.get("status", "unknown")).strip().lower()
            if current_status == "error" or (expected_issuer != "any" and expected_issuer not in current_issuer):
                changes.append(
                    ChangedObject(
                        surface="tls_cert",
                        object_id=host,
                        change_kind="renew",
                        before={"status": current_status, "issuer": current_cert.get("issuer")},
                        after={"expected_issuer": expected_issuer},
                        confidence="exact",
                        reversible=True,
                        notes="certificate issuer or probe status differs from the repository policy",
                    )
                )
                continue
            if self._expires_soon(record, current_cert):
                changes.append(
                    ChangedObject(
                        surface="tls_cert",
                        object_id=host,
                        change_kind="renew",
                        before={"not_after": current_cert.get("not_after")},
                        after={"expected_issuer": expected_issuer},
                        confidence="estimated",
                        reversible=True,
                        notes="certificate is within the configured warning window",
                    )
                )
        return changes

    def _desired_certificates(self, intent: dict[str, Any], service: dict[str, Any] | None) -> list[dict[str, Any]]:
        catalog_path = self.repo_root / "config" / "certificate-catalog.json"
        if not catalog_path.exists():
            return []
        payload = json.loads(catalog_path.read_text())
        certificates = payload.get("certificates", [])
        if not isinstance(certificates, list):
            return []
        service_id = str(intent.get("target_service_id", ""))
        service_host = str(service.get("subdomain", "")) if isinstance(service, dict) else ""
        desired: list[dict[str, Any]] = []
        for item in certificates:
            if not isinstance(item, dict):
                continue
            endpoint = item.get("endpoint", {})
            host = str(endpoint.get("host", "")) if isinstance(endpoint, dict) else ""
            if str(item.get("service_id", "")) == service_id or (service_host and host == service_host):
                desired.append(item)
        return desired

    @staticmethod
    def _current_certificates(world_state: WorldStateClient | None) -> list[dict[str, Any]] | None:
        if world_state is None:
            return None
        try:
            payload = world_state.get("tls_cert_expiry", allow_stale=True)
        except (SurfaceNotFoundError, RuntimeError):
            return None
        if isinstance(payload, dict):
            certificates = payload.get("certificates")
            if isinstance(certificates, list):
                return certificates
        return None

    @staticmethod
    def _expires_soon(desired: dict[str, Any], current: dict[str, Any]) -> bool:
        raw = current.get("not_after")
        if not isinstance(raw, str) or not raw.strip():
            return False
        policy = desired.get("policy", {})
        warn_days = int(policy.get("warn_days", 0)) if isinstance(policy, dict) else 0
        if warn_days <= 0:
            return False
        try:
            expiry = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return False
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=UTC)
        return (expiry - datetime.now(UTC)).days <= warn_days
