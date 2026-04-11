from __future__ import annotations

import importlib
import importlib.util
import sys
import types
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_PATH = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "plugins"
    / "callback"
    / "mutation_audit.py"
)


def test_callback_loads_mutation_audit_helpers_from_repo_root() -> None:
    ansible_module = types.ModuleType("ansible")
    ansible_plugins_module = types.ModuleType("ansible.plugins")
    ansible_callback_module = types.ModuleType("ansible.plugins.callback")

    class CallbackBase:  # pragma: no cover - stub for import-time dependency
        pass

    ansible_callback_module.CallbackBase = CallbackBase
    saved_modules = {
        name: sys.modules.get(name)
        for name in (
            "ansible",
            "ansible.plugins",
            "ansible.plugins.callback",
            "test_mutation_audit_callback_plugin",
            "lv3_mutation_audit",
        )
    }

    try:
        sys.modules["ansible"] = ansible_module
        sys.modules["ansible.plugins"] = ansible_plugins_module
        sys.modules["ansible.plugins.callback"] = ansible_callback_module

        spec = importlib.util.spec_from_file_location("test_mutation_audit_callback_plugin", PLUGIN_PATH)
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)

        assert module.REPO_ROOT == REPO_ROOT
        assert str(REPO_ROOT / "scripts") in sys.path
        assert module.MUTATION_AUDIT_PATH == REPO_ROOT / "scripts" / "mutation_audit.py"
        assert module.build_event.__module__ == "lv3_mutation_audit"
        assert module.emit_event_best_effort.__module__ == "lv3_mutation_audit"
        assert module.publish_ntfy_failure_best_effort.__module__ == "lv3_mutation_audit"
    finally:
        for name, original in saved_modules.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


def test_callback_replaces_stdlib_platform_module_before_loading_repo_helpers() -> None:
    ansible_module = types.ModuleType("ansible")
    ansible_plugins_module = types.ModuleType("ansible.plugins")
    ansible_callback_module = types.ModuleType("ansible.plugins.callback")
    stdlib_platform_module = types.ModuleType("platform")
    stdlib_platform_module.system = lambda: "Darwin"

    class CallbackBase:  # pragma: no cover - stub for import-time dependency
        pass

    ansible_callback_module.CallbackBase = CallbackBase
    saved_modules = {
        name: sys.modules.get(name)
        for name in (
            "ansible",
            "ansible.plugins",
            "ansible.plugins.callback",
            "platform",
            "test_mutation_audit_callback_plugin_platform",
            "lv3_mutation_audit",
        )
    }

    try:
        sys.modules["ansible"] = ansible_module
        sys.modules["ansible.plugins"] = ansible_plugins_module
        sys.modules["ansible.plugins.callback"] = ansible_callback_module
        sys.modules["platform"] = stdlib_platform_module

        spec = importlib.util.spec_from_file_location(
            "test_mutation_audit_callback_plugin_platform",
            PLUGIN_PATH,
        )
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)

        assert module.build_event.__module__ == "lv3_mutation_audit"
        assert module.publish_ntfy_failure_best_effort.__module__ == "lv3_mutation_audit"
        repo_platform = importlib.import_module("platform")
        assert getattr(repo_platform, "__file__", "").endswith("platform/__init__.py")
    finally:
        for name, original in saved_modules.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


def test_callback_emits_ntfy_notification_for_mutation_failures() -> None:
    ansible_module = types.ModuleType("ansible")
    ansible_plugins_module = types.ModuleType("ansible.plugins")
    ansible_callback_module = types.ModuleType("ansible.plugins.callback")

    class CallbackBase:  # pragma: no cover - stub for import-time dependency
        def __init__(self) -> None:
            self._display = types.SimpleNamespace(warning=lambda _message: None)

    ansible_callback_module.CallbackBase = CallbackBase
    saved_modules = {
        name: sys.modules.get(name)
        for name in (
            "ansible",
            "ansible.plugins",
            "ansible.plugins.callback",
            "test_mutation_audit_callback_plugin_failure",
            "lv3_mutation_audit",
        )
    }

    try:
        sys.modules["ansible"] = ansible_module
        sys.modules["ansible.plugins"] = ansible_plugins_module
        sys.modules["ansible.plugins.callback"] = ansible_callback_module

        spec = importlib.util.spec_from_file_location(
            "test_mutation_audit_callback_plugin_failure",
            PLUGIN_PATH,
        )
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)

        emitted: list[dict[str, object]] = []
        published: list[dict[str, object]] = []

        module.build_event = lambda **kwargs: {
            "ts": "2026-04-01T00:00:00Z",
            "actor": {"class": "automation", "id": "ansible-playbook"},
            "surface": "ansible",
            "action": kwargs["action"],
            "target": kwargs["target"],
            "outcome": kwargs["outcome"],
            "correlation_id": kwargs["correlation_id"],
            "evidence_ref": kwargs["evidence_ref"],
        }
        module.emit_event_best_effort = lambda event, **kwargs: emitted.append({"event": event, **kwargs}) or True
        module.publish_ntfy_failure_best_effort = lambda event, **kwargs: (
            published.append({"event": event, **kwargs}) or True
        )

        callback = module.CallbackModule()
        callback._display = types.SimpleNamespace(warning=lambda _message: None)
        task = types.SimpleNamespace(
            tags=["mutation"],
            vars={},
            _uuid="task-uuid-1",
            get_name=lambda: "Render ntfy config",
        )
        host = types.SimpleNamespace(get_name=lambda: "docker-runtime")
        result = types.SimpleNamespace(_task=task, _result={"changed": True}, _host=host)

        callback.v2_runner_on_failed(result)

        assert len(emitted) == 1
        assert emitted[0]["event"]["outcome"] == "failure"
        assert len(published) == 1
        assert published[0]["event"]["outcome"] == "failure"
        assert "failure notification" in str(published[0]["context"])
    finally:
        for name, original in saved_modules.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original
