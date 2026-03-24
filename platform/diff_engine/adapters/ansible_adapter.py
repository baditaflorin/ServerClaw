from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable

from scripts.parse_ansible_drift import parse_ansible_output

from ..schema import ChangedObject, unknown_object


Runner = Callable[..., subprocess.CompletedProcess[str]]


class AnsibleAdapter:
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
        del world_state
        playbooks = self._playbooks(workflow)
        if not playbooks:
            return []
        if shutil.which("ansible-playbook") is None:
            return [
                unknown_object(
                    surface="ansible_task",
                    object_id=str(intent["workflow_id"]),
                    notes="ansible-playbook is not available on the execution host",
                )
            ]

        inventory = self.repo_root / "inventory" / "hosts.yml"
        limit = service.get("vm") if isinstance(service, dict) else intent.get("target_vm")
        changes: list[ChangedObject] = []
        env = os.environ.copy()
        env.setdefault("ANSIBLE_STDOUT_CALLBACK", "json")
        for playbook in playbooks:
            command = ["ansible-playbook", "-i", str(inventory), str(playbook), "--check", "--diff"]
            if isinstance(limit, str) and limit.strip():
                command.extend(["-l", limit])
            result = self.runner(
                command,
                cwd=self.repo_root,
                env=env,
                text=True,
                capture_output=True,
                check=False,
                timeout=self.spec.timeout_seconds,
            )
            payload = result.stdout if result.stdout.strip() else result.stderr
            parsed = parse_ansible_output(payload)
            if not parsed and result.returncode not in {0, 2, 4}:
                changes.append(
                    unknown_object(
                        surface="ansible_task",
                        object_id=playbook.name,
                        notes=result.stderr.strip() or result.stdout.strip() or "ansible check mode failed",
                    )
                )
                continue
            for record in parsed:
                host = str(record.get("host", "unknown"))
                task = str(record.get("task", "unknown task"))
                before_text = str(record.get("diff_before", "")).strip()
                after_text = str(record.get("diff_after", "")).strip()
                unreachable = str(record.get("type", "")).strip() == "unreachable"
                changes.append(
                    ChangedObject(
                        surface="ansible_task",
                        object_id=f"{host}:{task}",
                        change_kind="unknown" if unreachable else "update",
                        before={"diff": before_text} if before_text else None,
                        after={"diff": after_text} if after_text else None,
                        confidence="unknown" if unreachable else ("exact" if before_text or after_text else "estimated"),
                        reversible=not unreachable,
                        notes=str(record.get("detail", "")).strip() or None,
                    )
                )
        return changes

    def _playbooks(self, workflow: dict[str, Any]) -> list[Path]:
        refs = workflow.get("implementation_refs", [])
        if not isinstance(refs, list):
            return []
        return [
            self.repo_root / ref
            for ref in refs
            if isinstance(ref, str) and ref.startswith("playbooks/") and ref.endswith((".yml", ".yaml"))
        ]
