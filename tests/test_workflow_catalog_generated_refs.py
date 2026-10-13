from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import workflow_catalog


def test_implementation_ref_exists_accepts_manifested_generated_path_without_git(tmp_path: Path) -> None:
    bootstrap_catalog = {
        "manifests": {
            "generated": {
                "generated_artifacts": [
                    {
                        "id": "monitors",
                        "kind": "file",
                        "path": "config/uptime-kuma/monitors.json",
                        "materialize_command": "make generate-uptime-kuma-monitors",
                        "description": "Generated monitor catalog",
                    }
                ]
            }
        }
    }

    assert workflow_catalog.implementation_ref_exists(
        "config/uptime-kuma/monitors.json",
        repo_root=tmp_path,
        bootstrap_catalog=bootstrap_catalog,
    )


def test_implementation_ref_exists_rejects_unmanifested_missing_path_without_git(tmp_path: Path) -> None:
    bootstrap_catalog = {"manifests": {"generated": {"generated_artifacts": []}}}

    assert not workflow_catalog.implementation_ref_exists(
        "config/uptime-kuma/missing.json",
        repo_root=tmp_path,
        bootstrap_catalog=bootstrap_catalog,
    )
