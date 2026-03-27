from __future__ import annotations

import importlib
import importlib.util
import sys
import types
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_PATH = REPO_ROOT / "collections" / "ansible_collections" / "lv3" / "platform" / "plugins" / "callback" / "mutation_audit.py"


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
        repo_platform = importlib.import_module("platform")
        assert getattr(repo_platform, "__file__", "").endswith("platform/__init__.py")
    finally:
        for name, original in saved_modules.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original
