from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_validator():
    module_path = REPO_ROOT / "scripts" / "validate_dependency_direction.py"
    scripts_dir = REPO_ROOT / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    spec = importlib.util.spec_from_file_location("validate_dependency_direction", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_current_repo_passes_dependency_direction_validation() -> None:
    validator = load_validator()

    assert validator.validate_dependency_direction(REPO_ROOT) == []


def test_detects_direct_import_of_script_module(tmp_path: Path) -> None:
    validator = load_validator()
    write(tmp_path / "scripts" / "controller_automation_toolkit.py", "load_json = object()\n")
    write(
        tmp_path / "platform" / "bad.py",
        "from controller_automation_toolkit import load_json\n",
    )

    violations = validator.validate_dependency_direction(tmp_path)

    assert len(violations) == 1
    assert violations[0].code == "outward-import"
    assert "controller_automation_toolkit" in violations[0].detail


def test_detects_dynamic_script_loader(tmp_path: Path) -> None:
    validator = load_validator()
    write(tmp_path / "scripts" / "drift_lib.py", "publish_nats_events = object()\n")
    write(
        tmp_path / "platform" / "bad.py",
        "\n".join(
            [
                "from pathlib import Path",
                "import importlib.util",
                "",
                'drift_lib_path = Path(__file__).resolve().parents[1] / "scripts" / "drift_lib.py"',
                'spec = importlib.util.spec_from_file_location("bad_drift_lib", drift_lib_path)',
            ]
        )
        + "\n",
    )

    violations = validator.validate_dependency_direction(tmp_path)

    assert len(violations) == 1
    assert violations[0].code == "dynamic-script-load"


def test_allows_generic_package_loader_without_scripts_reference(tmp_path: Path) -> None:
    validator = load_validator()
    write(tmp_path / "scripts" / "controller_automation_toolkit.py", "load_json = object()\n")
    write(
        tmp_path / "platform" / "good.py",
        "\n".join(
            [
                "from pathlib import Path",
                "import importlib.util",
                "",
                'init_path = Path(__file__).resolve().parent / "pkg" / "__init__.py"',
                'spec = importlib.util.spec_from_file_location("pkg", init_path)',
            ]
        )
        + "\n",
    )

    assert validator.validate_dependency_direction(tmp_path) == []
