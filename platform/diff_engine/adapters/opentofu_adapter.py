from __future__ import annotations

import json
import os
import subprocess
import uuid
from pathlib import Path
from typing import Any, Callable

from platform.run_namespace import ensure_run_namespace, resolve_run_namespace

from ..schema import ChangedObject, unknown_object


Runner = Callable[..., subprocess.CompletedProcess[str]]


def map_actions(actions: list[str]) -> tuple[str, bool]:
    normalized = [str(item) for item in actions]
    if normalized == ["create"]:
        return "create", True
    if normalized == ["delete"]:
        return "delete", False
    if normalized == ["create", "delete"] or normalized == ["delete", "create"]:
        return "replace", False
    return "update", True


class OpenTofuAdapter:
    def __init__(self, *, repo_root: Path, spec: Any, runner: Runner | None = None) -> None:
        self.repo_root = repo_root
        self.spec = spec
        self.runner = runner or subprocess.run

    def compute_diff(
        self,
        intent: dict[str, Any],
        *,
        world_state: Any,
        workflow: dict[str, Any],
        service: dict[str, Any] | None,
    ) -> list[ChangedObject]:
        del world_state, workflow, service
        environment = str(intent.get("arguments", {}).get("env", "production"))
        run_namespace = ensure_run_namespace(
            resolve_run_namespace(
                repo_root=self.repo_root,
                run_id=f"tofu-diff-{uuid.uuid4().hex}",
            )
        )
        env = os.environ.copy()
        env.setdefault("LV3_RUN_ID", run_namespace.run_id)
        env.setdefault("LV3_RUN_SLUG", run_namespace.run_slug)
        env.setdefault("LV3_RUN_NAMESPACE_ROOT", run_namespace.root)
        env.setdefault("LV3_RUN_TOFU_DIR", run_namespace.tofu_dir)
        result = self.runner(
            ["./scripts/tofu_exec.sh", "plan", environment],
            cwd=self.repo_root,
            env=env,
            text=True,
            capture_output=True,
            check=False,
            timeout=self.spec.timeout_seconds,
        )
        plan_path = Path(run_namespace.tofu_dir) / f"{environment}.plan.json"
        if not plan_path.exists():
            return [
                unknown_object(
                    surface="tofu_resource",
                    object_id=f"tofu/{environment}",
                    notes=result.stderr.strip() or result.stdout.strip() or "OpenTofu plan output was not produced",
                )
            ]
        payload = json.loads(plan_path.read_text())
        changes: list[ChangedObject] = []
        for resource in payload.get("resource_changes", []):
            if not isinstance(resource, dict):
                continue
            change = resource.get("change", {})
            actions = change.get("actions", [])
            if not isinstance(actions, list) or actions == ["no-op"]:
                continue
            change_kind, reversible = map_actions(actions)
            changes.append(
                ChangedObject(
                    surface="tofu_resource",
                    object_id=str(resource.get("address", "unknown")),
                    change_kind=change_kind,
                    before=change.get("before") if isinstance(change.get("before"), dict) else None,
                    after=change.get("after") if isinstance(change.get("after"), dict) else None,
                    confidence="exact",
                    reversible=reversible,
                    notes=f"planned actions: {', '.join(actions)}",
                )
            )
        if changes or result.returncode in {0, 2}:
            return changes
        return [
            unknown_object(
                surface="tofu_resource",
                object_id=f"tofu/{environment}",
                notes=result.stderr.strip() or result.stdout.strip() or "OpenTofu plan failed",
            )
        ]
