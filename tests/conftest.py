import importlib.util
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
PLATFORM_PACKAGE_DIR = REPO_ROOT / "platform"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

if PLATFORM_PACKAGE_DIR.exists():
    sys.modules.pop("platform", None)
    platform_init = PLATFORM_PACKAGE_DIR / "__init__.py"
    spec = importlib.util.spec_from_file_location(
        "platform",
        platform_init,
        submodule_search_locations=[str(PLATFORM_PACKAGE_DIR)],
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["platform"] = module
    spec.loader.exec_module(module)
