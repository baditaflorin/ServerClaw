from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_PATH = REPO_ROOT / "collections" / "ansible_collections" / "lv3" / "platform" / "plugins" / "callback" / "structured_log.py"


class DisplayRecorder:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def display(self, message: str) -> None:
        self.messages.append(message)


class FakeTask:
    def __init__(self, name: str, vars_: dict[str, object]) -> None:
        self._name = name
        self.vars = vars_

    def get_name(self) -> str:
        return self._name


class FakeHost:
    def __init__(self, name: str) -> None:
        self._name = name

    def get_name(self) -> str:
        return self._name


class FakeResult:
    def __init__(self, task: FakeTask, host: FakeHost, payload: dict[str, object]) -> None:
        self._task = task
        self._host = host
        self._result = payload


def load_plugin_module() -> types.ModuleType:
    ansible_module = types.ModuleType("ansible")
    ansible_plugins_module = types.ModuleType("ansible.plugins")
    ansible_callback_module = types.ModuleType("ansible.plugins.callback")

    class CallbackBase:  # pragma: no cover - import stub
        def __init__(self) -> None:
            self._display = DisplayRecorder()

    ansible_callback_module.CallbackBase = CallbackBase
    saved_modules = {
        name: sys.modules.get(name)
        for name in ("ansible", "ansible.plugins", "ansible.plugins.callback", "test_structured_log_callback_plugin")
    }

    try:
        sys.modules["ansible"] = ansible_module
        sys.modules["ansible.plugins"] = ansible_plugins_module
        sys.modules["ansible.plugins.callback"] = ansible_callback_module
        spec = importlib.util.spec_from_file_location("test_structured_log_callback_plugin", PLUGIN_PATH)
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        for name, original in saved_modules.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


def test_structured_log_callback_emits_required_fields() -> None:
    module = load_plugin_module()
    callback = module.CallbackModule()
    callback._display = DisplayRecorder()
    task = FakeTask(
        "Render API gateway config",
        {
            "platform_trace_id": "trace-123",
            "platform_intent_id": "intent-123",
            "playbook_execution_notification_service": "api_gateway",
            "playbook_execution_audit_target": "api_gateway",
            "playbook_name": "api-gateway",
        },
    )
    result = FakeResult(task, FakeHost("docker-runtime-lv3"), {"changed": True})

    callback.v2_runner_on_ok(result)

    payload = json.loads(callback._display.messages[0])
    assert payload["service_id"] == "api_gateway"
    assert payload["component"] == "ansible.task"
    assert payload["trace_id"] == "trace-123"
    assert payload["intent_id"] == "intent-123"
    assert payload["vm"] == "docker-runtime-lv3"
    assert payload["task_status"] == "ok"
    assert payload["changed"] is True
