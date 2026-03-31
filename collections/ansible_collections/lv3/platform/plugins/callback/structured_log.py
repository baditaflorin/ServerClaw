from __future__ import annotations

import json
import os
from datetime import datetime, timezone

try:
    from datetime import UTC
except ImportError:  # pragma: no cover - Python <3.11 compatibility
except ImportError:  # pragma: no cover - Python < 3.11 fallback for ansible-lint/idempotency lanes
    UTC = timezone.utc

from ansible.plugins.callback import CallbackBase


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class CallbackModule(CallbackBase):
    CALLBACK_VERSION = 2.0
    CALLBACK_TYPE = "notification"
    CALLBACK_NAME = "structured_log"
    CALLBACK_NEEDS_ENABLED = True

    def _service_id(self, task_vars: dict[str, object]) -> str:
        for field in ("playbook_execution_notification_service", "playbook_execution_audit_target"):
            value = task_vars.get(field)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return os.environ.get("LV3_LOG_SERVICE_ID", "ansible")

    def _trace_id(self, task_vars: dict[str, object]) -> str:
        for field in ("platform_trace_id", "playbook_execution_correlation_id"):
            value = task_vars.get(field)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return os.environ.get("PLATFORM_TRACE_ID", "background")

    def _intent_id(self, task_vars: dict[str, object]) -> str | None:
        value = task_vars.get("platform_intent_id")
        if isinstance(value, str) and value.strip():
            return value.strip()
        value = os.environ.get("PLATFORM_INTENT_ID", "").strip()
        return value or None

    def _base_payload(self, task_vars: dict[str, object], *, level: str, task_name: str, vm: str) -> dict[str, object]:
        payload: dict[str, object] = {
            "ts": _utc_now_iso(),
            "level": level,
            "service_id": self._service_id(task_vars),
            "component": "ansible.task",
            "trace_id": self._trace_id(task_vars),
            "msg": task_name,
            "vm": vm,
            "workflow_id": str(task_vars.get("playbook_name") or "ansible-playbook"),
            "target": str(task_vars.get("playbook_execution_audit_target") or vm),
        }
        intent_id = self._intent_id(task_vars)
        if intent_id:
            payload["intent_id"] = intent_id
        return payload

    def _emit(self, payload: dict[str, object]) -> None:
        rendered = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        self._display.display(rendered)

    def v2_playbook_on_task_start(self, task, is_conditional) -> None:
        task_vars = getattr(task, "vars", {}) or {}
        payload = self._base_payload(task_vars, level="INFO", task_name=f"Task start: {task.get_name()}", vm="controller")
        payload["task_status"] = "start"
        self._emit(payload)

    def v2_runner_on_ok(self, result) -> None:
        task_vars = getattr(result._task, "vars", {}) or {}
        payload = self._base_payload(
            task_vars,
            level="INFO",
            task_name=f"Task OK: {result._task.get_name()}",
            vm=result._host.get_name(),
        )
        payload["task_status"] = "ok"
        payload["changed"] = bool(result._result.get("changed"))
        self._emit(payload)

    def v2_runner_on_failed(self, result, ignore_errors=False) -> None:
        task_vars = getattr(result._task, "vars", {}) or {}
        payload = self._base_payload(
            task_vars,
            level="ERROR",
            task_name=f"Task failed: {result._task.get_name()}",
            vm=result._host.get_name(),
        )
        payload["task_status"] = "failed"
        payload["error_code"] = "ANSIBLE_TASK_FAILED"
        payload["ignored"] = bool(ignore_errors)
        payload["target"] = str(task_vars.get("playbook_execution_audit_target") or result._host.get_name())
        if isinstance(result._result.get("msg"), str) and result._result["msg"].strip():
            payload["error_detail"] = result._result["msg"].strip()
        self._emit(payload)

    def v2_runner_on_skipped(self, result) -> None:
        task_vars = getattr(result._task, "vars", {}) or {}
        payload = self._base_payload(
            task_vars,
            level="INFO",
            task_name=f"Task skipped: {result._task.get_name()}",
            vm=result._host.get_name(),
        )
        payload["task_status"] = "skipped"
        self._emit(payload)
