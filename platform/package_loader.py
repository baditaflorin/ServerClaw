from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


def load_repo_package(module_name: str, package_dir: Path) -> ModuleType:
    init_path = package_dir / "__init__.py"
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(
        module_name,
        init_path,
        submodule_search_locations=[str(package_dir)],
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load package {module_name} from {package_dir}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module
