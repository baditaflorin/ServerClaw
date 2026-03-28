from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from correction_loops import (
    load_correction_loop_catalog,
    resolve_workflow_correction_loop,
    validate_correction_loop_catalog,
)
from workflow_catalog import load_workflow_catalog


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_repo_correction_loop_catalog_validates_against_workflow_catalog() -> None:
    catalog = load_correction_loop_catalog()
    workflow_catalog = load_workflow_catalog()

    validate_correction_loop_catalog(catalog, workflow_catalog)


def test_platform_observation_loop_uses_runtime_self_correction_contract() -> None:
    catalog = load_correction_loop_catalog()

    loop = resolve_workflow_correction_loop(catalog, "platform-observation-loop")

    assert loop is not None
    assert loop["id"] == "runtime_self_correction_watchers"
    assert loop["retry_budget_cycles"] == 3


def test_correction_loops_bootstraps_scripts_directory_for_external_imports() -> None:
    script_path = REPO_ROOT / "scripts" / "correction_loops.py"
    command = [
        sys.executable,
        "-c",
        (
            "import importlib.util, sys; "
            f"spec = importlib.util.spec_from_file_location('correction_loops_bootstrap', {str(script_path)!r}); "
            "module = importlib.util.module_from_spec(spec); "
            "sys.modules[spec.name] = module; "
            "spec.loader.exec_module(module); "
            "print(module.SUPPORTED_SCHEMA_VERSION)"
        ),
    ]
    env = dict(__import__("os").environ)
    env.pop("PYTHONPATH", None)

    result = subprocess.run(
        command,
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert result.stdout.strip() == "1.0.0"
