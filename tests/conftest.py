import importlib.util
import sys
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

SCRIPTS_DIR = REPO_ROOT / "scripts"
PLATFORM_PACKAGE_DIR = REPO_ROOT / "platform"
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


# ---------------------------------------------------------------------------
# Identity fixtures (ADR 0385) — single source for all test assertions
# ---------------------------------------------------------------------------

def _load_identity() -> dict:
    """Load identity.yml and return plain scalar variables."""
    identity_path = REPO_ROOT / "inventory" / "group_vars" / "all" / "identity.yml"
    if not identity_path.exists():
        return {}
    with identity_path.open() as f:
        data = yaml.safe_load(f) or {}
    return {k: v for k, v in data.items() if isinstance(v, str) and "{{" not in v}


_IDENTITY_CACHE = None


def _get_identity() -> dict:
    global _IDENTITY_CACHE
    if _IDENTITY_CACHE is None:
        _IDENTITY_CACHE = _load_identity()
    return _IDENTITY_CACHE


@pytest.fixture
def platform_domain() -> str:
    """The platform domain from identity.yml (e.g. 'lv3.org')."""
    return _get_identity().get("platform_domain", "localhost")


@pytest.fixture
def platform_operator_email() -> str:
    """The operator email from identity.yml."""
    return _get_identity().get("platform_operator_email", "operator@localhost")


@pytest.fixture
def identity_vars() -> dict:
    """All plain scalar identity variables from identity.yml."""
    return dict(_get_identity())
