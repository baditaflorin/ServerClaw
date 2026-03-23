from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from ansible.plugins.callback import CallbackBase


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from mutation_audit import build_event, emit_event_best_effort  # noqa: E402


ACTION_SANITIZE_PATTERN = re.compile(r"[^a-z0-9]+")


class CallbackModule(CallbackBase):
    CALLBACK_VERSION = 2.0
    CALLBACK_TYPE = "notification"
    CALLBACK_NAME = "mutation_audit"
    CALLBACK_NEEDS_ENABLED = True

    def _slugify_action(self, task_name: str) -> str:
        base = ACTION_SANITIZE_PATTERN.sub(".", task_name.lower()).strip(".")
        return base or "task.mutation"

    def _task_has_mutation_tag(self, task) -> bool:
        return "mutation" in set(getattr(task, "tags", []) or [])

    def _emit_for_result(self, result, *, outcome: str) -> None:
        task = result._task
        if not self._task_has_mutation_tag(task):
            return

        task_vars = getattr(task, "vars", {}) or {}
        changed = bool(result._result.get("changed"))
        emit_on_success = bool(task_vars.get("mutation_audit_emit_on_success"))
        if outcome == "success" and not changed and not emit_on_success:
            return

        action = task_vars.get("mutation_audit_action") or self._slugify_action(task.get_name().strip())
        target = str(task_vars.get("mutation_audit_target") or result._host.get_name())
        actor_class = str(task_vars.get("mutation_audit_actor_class") or "automation")
        actor_id = str(task_vars.get("mutation_audit_actor_id") or os.environ.get("LV3_MUTATION_AUDIT_ACTOR_ID") or "ansible-playbook")
        correlation_id = str(
            task_vars.get("mutation_audit_correlation_id")
            or os.environ.get("LV3_MUTATION_AUDIT_CORRELATION_ID")
            or f"ansible:{getattr(task, '_uuid', 'unknown')}"
        )
        evidence_ref = str(task_vars.get("mutation_audit_evidence_ref") or "")
        surface = str(task_vars.get("mutation_audit_surface") or "ansible")

        try:
            event = build_event(
                actor_class=actor_class,
                actor_id=actor_id,
                surface=surface,
                action=action,
                target=target,
                outcome=outcome,
                correlation_id=correlation_id,
                evidence_ref=evidence_ref,
            )
        except ValueError as exc:
            self._display.warning(f"Mutation audit callback skipped invalid event for task '{task.get_name()}': {exc}")
            return

        emit_event_best_effort(
            event,
            context=f"ansible task '{task.get_name()}'",
            stderr=sys.stderr,
        )

    def v2_runner_on_ok(self, result) -> None:
        self._emit_for_result(result, outcome="success")

    def v2_runner_on_failed(self, result, ignore_errors=False) -> None:
        self._emit_for_result(result, outcome="failure")
