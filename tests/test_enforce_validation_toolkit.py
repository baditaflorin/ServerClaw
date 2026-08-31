from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLKIT_SCRIPT = REPO_ROOT / "scripts" / "enforce_validation_toolkit.sh"


def make_snapshot(tmp_path: Path) -> Path:
    snapshot = tmp_path / "snapshot"
    scripts_dir = snapshot / "scripts"
    scripts_dir.mkdir(parents=True)
    shutil.copy2(TOOLKIT_SCRIPT, scripts_dir / TOOLKIT_SCRIPT.name)
    return snapshot


def test_all_files_uses_content_fallback_without_git_metadata(tmp_path: Path) -> None:
    snapshot = make_snapshot(tmp_path)
    (snapshot / "scripts" / "valid.py").write_text("def local_helper() -> None:\n    return None\n", encoding="utf-8")

    completed = subprocess.run(
        ["bash", str(snapshot / "scripts" / TOOLKIT_SCRIPT.name), "--all-files"],
        cwd=snapshot,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr


def test_all_files_rejects_redefined_validator_without_git_metadata(tmp_path: Path) -> None:
    snapshot = make_snapshot(tmp_path)
    (snapshot / "scripts" / "invalid.py").write_text("def require_str() -> None:\n    return None\n", encoding="utf-8")

    completed = subprocess.run(
        ["bash", str(snapshot / "scripts" / TOOLKIT_SCRIPT.name), "--all-files"],
        cwd=snapshot,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 1
    assert "invalid.py: redefines shared validator 'require_str'" in completed.stdout
