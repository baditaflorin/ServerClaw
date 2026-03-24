from __future__ import annotations

import importlib
import importlib.util
import sysconfig
from pathlib import Path


_STDLIB_PLATFORM_PATH = Path(sysconfig.get_path("stdlib")) / "platform.py"
_STDLIB_SPEC = importlib.util.spec_from_file_location("_stdlib_platform", _STDLIB_PLATFORM_PATH)
if _STDLIB_SPEC is None or _STDLIB_SPEC.loader is None:  # pragma: no cover - defensive import guard
    raise RuntimeError(f"Unable to load stdlib platform module from {_STDLIB_PLATFORM_PATH}")

_stdlib_platform = importlib.util.module_from_spec(_STDLIB_SPEC)
_STDLIB_SPEC.loader.exec_module(_stdlib_platform)

for _name in dir(_stdlib_platform):
    if _name.startswith("__") and _name not in {"__all__", "__doc__"}:
        continue
    globals()[_name] = getattr(_stdlib_platform, _name)

_REPO_SUBMODULES = {"diff_engine", "goal_compiler", "health", "ledger", "world_state"}


def __getattr__(name: str):  # pragma: no cover - exercised indirectly through imports
    if name in _REPO_SUBMODULES:
        module = importlib.import_module(f"{__name__}.{name}")
        globals()[name] = module
        return module
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = list(getattr(_stdlib_platform, "__all__", []))
__all__.extend(sorted(_REPO_SUBMODULES))
__doc__ = getattr(_stdlib_platform, "__doc__", __doc__)
