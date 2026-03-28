from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from platform.catalogs import service_entries, workflow_entries
from platform.world_state.client import WorldStateClient

from .registry import DiffAdapterRegistry
from .schema import ChangedObject, SemanticDiff, unknown_object


def semantic_intent_id(payload: dict[str, Any]) -> str:
    digest = hashlib.sha1(
        json.dumps(payload.get("arguments", {}), sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:12]
    return f"{payload['workflow_id']}:{digest}"


def infer_surfaces(payload: dict[str, Any], workflow: dict[str, Any], service: dict[str, Any] | None) -> list[str]:
    refs = workflow.get("implementation_refs", [])
    implementation_refs = [str(item) for item in refs] if isinstance(refs, list) else []
    verification_commands = workflow.get("verification_commands", [])
    verification_text = " ".join(str(item) for item in verification_commands) if isinstance(verification_commands, list) else ""
    preferred = workflow.get("preferred_entrypoint", {})
    preferred_command = str(preferred.get("command", "")) if isinstance(preferred, dict) else ""
    combined = " ".join([preferred_command, verification_text, *implementation_refs]).lower()

    surfaces: list[str] = []
    if any(item.startswith("playbooks/") for item in implementation_refs) or "ansible-playbook" in combined:
        surfaces.append("ansible")
    if any(item.startswith("tofu/") for item in implementation_refs) or "tofu " in combined:
        surfaces.append("opentofu")
    if service and service.get("image_catalog_ids"):
        surfaces.append("docker")
    if service and (service.get("subdomain") or service.get("public_url")):
        surfaces.append("dns")
        surfaces.append("cert")
    elif "provision-subdomain" in combined or "database-dns" in combined:
        surfaces.append("dns")

    if not surfaces and str(payload.get("live_impact", "")).strip().lower() != "repo_only":
        surfaces.append("unknown")
    return list(dict.fromkeys(surfaces))


class DiffEngine:
    def __init__(self, *, repo_root: Path | None = None, registry: DiffAdapterRegistry | None = None) -> None:
        self.repo_root = repo_root or Path(__file__).resolve().parents[2]
        self.registry = registry or DiffAdapterRegistry(repo_root=self.repo_root)

    def compute(
        self,
        intent: Any,
        world_state: WorldStateClient | None = None,
    ) -> SemanticDiff:
        payload = intent.as_dict() if hasattr(intent, "as_dict") else dict(intent)
        workflow = workflow_entries(self.repo_root).get(payload["workflow_id"], {})
        services = service_entries(self.repo_root)
        service_id = payload.get("target_service_id")
        service = services.get(service_id) if isinstance(service_id, str) else None
        surfaces = infer_surfaces(payload, workflow if isinstance(workflow, dict) else {}, service)

        started = time.monotonic()
        changed_objects: list[ChangedObject] = []
        adapters_used: list[str] = []
        client = world_state or self._world_state_from_env()

        for surface in surfaces:
            if surface == "unknown":
                changed_objects.append(
                    unknown_object(
                        surface="workflow_surface",
                        object_id=str(payload["workflow_id"]),
                        notes="no diff adapter could be inferred for this workflow",
                    )
                )
                continue

            spec = self.registry.get_by_surface(surface)
            if spec is None or not spec.enabled:
                changed_objects.append(
                    unknown_object(
                        surface=surface,
                        object_id=str(payload["workflow_id"]),
                        notes=f"no enabled adapter registered for surface '{surface}'",
                    )
                )
                continue

            adapter = self.registry.build(spec.adapter_id)
            try:
                results = adapter.compute_diff(
                    payload,
                    world_state=client,
                    workflow=workflow if isinstance(workflow, dict) else {},
                    service=service,
                )
            except Exception as exc:  # noqa: BLE001
                results = [
                    unknown_object(
                        surface=surface,
                        object_id=str(payload["workflow_id"]),
                        notes=f"{spec.adapter_id} adapter failed: {exc}",
                    )
                ]
            if results:
                adapters_used.append(spec.adapter_id)
                changed_objects.extend(results)

        elapsed_ms = int((time.monotonic() - started) * 1000)
        normalized = tuple(changed_objects)
        return SemanticDiff(
            intent_id=str(payload.get("intent_id") or semantic_intent_id(payload)),
            computed_at=datetime.now(UTC).isoformat(),
            changed_objects=normalized,
            total_changes=len(normalized),
            irreversible_count=sum(1 for item in normalized if not item.reversible),
            unknown_count=sum(1 for item in normalized if item.confidence == "unknown"),
            adapters_used=tuple(dict.fromkeys(adapters_used)),
            elapsed_ms=elapsed_ms,
        )

    @staticmethod
    def _world_state_from_env() -> WorldStateClient | None:
        dsn = os.environ.get("LV3_WORLD_STATE_DSN", "").strip()
        if not dsn:
            return None
        return WorldStateClient(dsn=dsn)
