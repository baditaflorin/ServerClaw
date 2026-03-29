"""Helpers for repo-managed Ansible job orchestration."""

from __future__ import annotations

import importlib


_EXPORTS = {
    "DependencyWaveExecutor": ".dependency_waves",
    "DependencyWaveManifest": ".dependency_waves",
    "PlaybookApplyCatalog": ".dependency_waves",
    "PlaybookApplyMetadata": ".dependency_waves",
    "execute_dependency_wave_manifest": ".dependency_waves",
    "load_dependency_wave_manifest": ".dependency_waves",
    "load_playbook_apply_catalog": ".dependency_waves",
}

__all__ = list(_EXPORTS)


def __getattr__(name: str):
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = importlib.import_module(module_name, __name__)
    value = getattr(module, name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
