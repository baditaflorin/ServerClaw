from __future__ import annotations

import importlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class AdapterSpec:
    adapter_id: str
    class_path: str
    surface: str
    enabled: bool = True
    timeout_seconds: int = 90


class DiffAdapterRegistry:
    def __init__(self, *, repo_root: Path, config_path: Path | None = None) -> None:
        self.repo_root = repo_root
        self.config_path = config_path or repo_root / "config" / "diff-adapters.yaml"
        self._specs: dict[str, AdapterSpec] | None = None

    def load_specs(self) -> dict[str, AdapterSpec]:
        if self._specs is not None:
            return self._specs
        if not self.config_path.exists():
            self._specs = {}
            return self._specs

        payload = yaml.safe_load(self.config_path.read_text()) or {}
        configured = payload.get("adapters", {})
        specs: dict[str, AdapterSpec] = {}
        if isinstance(configured, dict):
            for adapter_id, values in configured.items():
                if not isinstance(values, dict):
                    continue
                class_path = str(values.get("class", "")).strip()
                surface = str(values.get("surface", adapter_id)).strip()
                if not class_path or not surface:
                    continue
                specs[adapter_id] = AdapterSpec(
                    adapter_id=adapter_id,
                    class_path=class_path,
                    surface=surface,
                    enabled=bool(values.get("enabled", True)),
                    timeout_seconds=int(values.get("timeout_seconds", 90)),
                )
        self._specs = specs
        return specs

    def get_by_surface(self, surface: str) -> AdapterSpec | None:
        for spec in self.load_specs().values():
            if spec.surface == surface:
                return spec
        return None

    def build(self, adapter_id: str) -> Any:
        spec = self.load_specs()[adapter_id]
        module_name, _, class_name = spec.class_path.rpartition(".")
        if not module_name or not class_name:
            raise ValueError(f"invalid diff adapter class path: {spec.class_path}")
        module = importlib.import_module(module_name)
        adapter_cls = getattr(module, class_name)
        return adapter_cls(repo_root=self.repo_root, spec=spec)
