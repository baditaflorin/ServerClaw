from __future__ import annotations

import importlib.util
import sys
import sysconfig
from pathlib import Path


def _load_stdlib_platform():
    stdlib_path = Path(sysconfig.get_path("stdlib")) / "platform.py"
    spec = importlib.util.spec_from_file_location("_lv3_stdlib_platform", stdlib_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load stdlib platform module from {stdlib_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault(spec.name, module)
    spec.loader.exec_module(module)
    return module


_STDLIB_PLATFORM = _load_stdlib_platform()
_SUBMODULE_ROOT = Path(__file__).with_name("platform")

# Re-export the stdlib platform module so existing imports keep working while
# this repository adds platform.* subpackages for ADR 0112+ workstreams.
for _name in dir(_STDLIB_PLATFORM):
    if _name in {"__builtins__", "__cached__", "__loader__", "__name__", "__package__", "__spec__"}:
        continue
    globals()[_name] = getattr(_STDLIB_PLATFORM, _name)

__all__ = list(getattr(_STDLIB_PLATFORM, "__all__", []))
__doc__ = getattr(_STDLIB_PLATFORM, "__doc__", None)
__path__ = [str(_SUBMODULE_ROOT)]
