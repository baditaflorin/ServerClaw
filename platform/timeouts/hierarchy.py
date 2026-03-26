from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import os
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TIMEOUT_HIERARCHY_PATH = REPO_ROOT / "config" / "timeout-hierarchy.yaml"


@dataclass(frozen=True)
class TimeoutLayer:
    name: str
    timeout_s: int
    default_timeout_s: int
    inner_layers: tuple[str, ...]


class TimeoutHierarchyError(ValueError):
    pass


def _require_int(value: Any, path: str, *, minimum: int = 1) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TimeoutHierarchyError(f"{path} must be an integer")
    if value < minimum:
        raise TimeoutHierarchyError(f"{path} must be >= {minimum}")
    return value


def _require_string_list(value: Any, path: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise TimeoutHierarchyError(f"{path} must be a list")
    result: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise TimeoutHierarchyError(f"{path}[{index}] must be a non-empty string")
        result.append(item)
    return tuple(result)


def hierarchy_path(path: str | Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    env_path = os.environ.get("LV3_TIMEOUT_HIERARCHY_PATH", "").strip()
    if env_path:
        return Path(env_path)
    return DEFAULT_TIMEOUT_HIERARCHY_PATH


def load_hierarchy_payload(path: str | Path | None = None) -> dict[str, Any]:
    resolved = hierarchy_path(path)
    try:
        import yaml
    except ModuleNotFoundError as exc:  # pragma: no cover - runtime-only dependency
        raise RuntimeError("PyYAML is required to load the timeout hierarchy") from exc
    payload = yaml.safe_load(resolved.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TimeoutHierarchyError(f"{resolved} must define a mapping")
    return payload


def validate_timeout_hierarchy(payload: dict[str, Any], *, path: str = "config/timeout-hierarchy.yaml") -> dict[str, TimeoutLayer]:
    schema_version = payload.get("schema_version")
    if schema_version != "1.0.0":
        raise TimeoutHierarchyError(f"{path}.schema_version must be '1.0.0'")
    layers = payload.get("layers")
    if not isinstance(layers, dict) or not layers:
        raise TimeoutHierarchyError(f"{path}.layers must be a non-empty mapping")

    normalized: dict[str, TimeoutLayer] = {}
    for layer_name, raw in layers.items():
        layer_path = f"{path}.layers.{layer_name}"
        if not isinstance(layer_name, str) or not layer_name.strip():
            raise TimeoutHierarchyError(f"{layer_path} must use a non-empty string key")
        if not isinstance(raw, dict):
            raise TimeoutHierarchyError(f"{layer_path} must be a mapping")
        timeout_s = _require_int(raw.get("timeout_s"), f"{layer_path}.timeout_s")
        default_timeout_s = _require_int(raw.get("default_timeout_s"), f"{layer_path}.default_timeout_s")
        if default_timeout_s > timeout_s:
            raise TimeoutHierarchyError(
                f"{layer_path}.default_timeout_s must be <= {layer_path}.timeout_s"
            )
        normalized[layer_name] = TimeoutLayer(
            name=layer_name,
            timeout_s=timeout_s,
            default_timeout_s=default_timeout_s,
            inner_layers=_require_string_list(raw.get("inner_layers", []), f"{layer_path}.inner_layers"),
        )

    for layer in normalized.values():
        missing = [name for name in layer.inner_layers if name not in normalized]
        if missing:
            raise TimeoutHierarchyError(
                f"{path}.layers.{layer.name}.inner_layers references unknown layers: {', '.join(missing)}"
            )
        if layer.name in layer.inner_layers:
            raise TimeoutHierarchyError(f"{path}.layers.{layer.name}.inner_layers must not include itself")
        if layer.inner_layers:
            child_total = sum(normalized[name].timeout_s for name in layer.inner_layers)
            if layer.timeout_s <= child_total:
                raise TimeoutHierarchyError(
                    f"{path}.layers.{layer.name}.timeout_s must be greater than the sum of child timeout_s values "
                    f"({layer.timeout_s} <= {child_total})"
                )
    return normalized


@lru_cache(maxsize=None)
def load_timeout_hierarchy(path: str | Path | None = None) -> dict[str, TimeoutLayer]:
    payload = load_hierarchy_payload(path)
    return validate_timeout_hierarchy(payload, path=str(hierarchy_path(path)))


def timeout_layer(name: str, *, path: str | Path | None = None) -> TimeoutLayer:
    hierarchy = load_timeout_hierarchy(path)
    try:
        return hierarchy[name]
    except KeyError as exc:
        raise TimeoutHierarchyError(f"unknown timeout layer '{name}'") from exc


def timeout_limit(name: str, *, path: str | Path | None = None) -> int:
    return timeout_layer(name, path=path).timeout_s


def default_timeout(name: str, *, path: str | Path | None = None) -> int:
    return timeout_layer(name, path=path).default_timeout_s


def resolve_timeout_seconds(
    name: str,
    requested_seconds: int | float | None = None,
    *,
    path: str | Path | None = None,
) -> float:
    layer = timeout_layer(name, path=path)
    if requested_seconds is None:
        return float(layer.default_timeout_s)
    if isinstance(requested_seconds, bool) or not isinstance(requested_seconds, (int, float)):
        raise TimeoutHierarchyError(f"timeout request for layer '{name}' must be numeric")
    if requested_seconds <= 0:
        raise TimeoutHierarchyError(f"timeout request for layer '{name}' must be > 0")
    return float(min(requested_seconds, layer.timeout_s))
