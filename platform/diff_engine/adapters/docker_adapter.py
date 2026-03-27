from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from platform.world_state.client import SurfaceNotFoundError, WorldStateClient

from ..schema import ChangedObject, unknown_object


class DockerAdapter:
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
        desired = self._desired_images(intent, service)
        if not desired:
            return []
        current = self._current_containers(world_state)
        if current is None:
            return [
                unknown_object(
                    surface="docker_container",
                    object_id=item["container_name"],
                    notes="container inventory is unavailable in world state",
                )
                for item in desired
            ]

        current_by_name = {str(item.get("name")): item for item in current}
        changes: list[ChangedObject] = []
        for image in desired:
            container_name = str(image["container_name"])
            desired_state = {
                "name": container_name,
                "image": image["ref"],
                "runtime_host": image.get("runtime_host"),
            }
            current_state = current_by_name.get(container_name)
            if current_state is None:
                changes.append(
                    ChangedObject(
                        surface="docker_container",
                        object_id=container_name,
                        change_kind="create",
                        before=None,
                        after=desired_state,
                        confidence="exact",
                        reversible=True,
                        notes="container is declared in the image catalog but missing from container inventory",
                    )
                )
                continue
            current_image = str(current_state.get("image", ""))
            current_status = str(current_state.get("state", "")).strip().lower()
            if current_image != desired_state["image"]:
                changes.append(
                    ChangedObject(
                        surface="docker_container",
                        object_id=container_name,
                        change_kind="update",
                        before={"image": current_image, "state": current_status},
                        after=desired_state,
                        confidence="exact",
                        reversible=True,
                        notes="container image differs from the repo-pinned image reference",
                    )
                )
            elif current_status and current_status != "running":
                changes.append(
                    ChangedObject(
                        surface="docker_container",
                        object_id=container_name,
                        change_kind="restart",
                        before={"image": current_image, "state": current_status},
                        after=desired_state,
                        confidence="estimated",
                        reversible=True,
                        notes="container exists with the desired image but is not running",
                    )
                )
        return changes

    def _desired_images(self, intent: dict[str, Any], service: dict[str, Any] | None) -> list[dict[str, Any]]:
        catalog_path = self.repo_root / "config" / "image-catalog.json"
        if not catalog_path.exists():
            return []
        payload = json.loads(catalog_path.read_text())
        images = payload.get("images", {})
        if not isinstance(images, dict):
            return []

        service_ids = {str(intent.get("target_service_id", ""))}
        if isinstance(service, dict):
            service_ids.add(str(service.get("id", "")))
            from_service: list[dict[str, Any]] = []
            for image_id in service.get("image_catalog_ids", []):
                if image_id in images:
                    item = images[image_id]
                    if isinstance(item, dict):
                        from_service.append(item)
            if from_service:
                return from_service

        desired: list[dict[str, Any]] = []
        for item in images.values():
            if not isinstance(item, dict):
                continue
            if str(item.get("service_id", "")) in service_ids or intent["workflow_id"] in item.get("apply_targets", []):
                desired.append(item)
        return desired

    @staticmethod
    def _current_containers(world_state: WorldStateClient | None) -> list[dict[str, Any]] | None:
        if world_state is None:
            return None
        try:
            payload = world_state.get("container_inventory", allow_stale=True)
        except (SurfaceNotFoundError, RuntimeError):
            return None
        return payload if isinstance(payload, list) else None
