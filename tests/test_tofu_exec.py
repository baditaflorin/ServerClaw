from __future__ import annotations

import os
import shutil
import subprocess
import textwrap
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
TOFU_SCRIPT = REPO_ROOT / "scripts" / "tofu_exec.sh"


def write_executable(path: Path, content: str) -> None:
    path.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")
    path.chmod(0o755)


def test_native_validate_uses_host_tofu_and_local_plan_paths(tmp_path: Path) -> None:
    repo_root = tmp_path / "snapshot"
    scripts_dir = repo_root / "scripts"
    scripts_dir.mkdir(parents=True)
    shutil.copy2(TOFU_SCRIPT, scripts_dir / TOFU_SCRIPT.name)
    (repo_root / "tofu" / "environments" / "production").mkdir(parents=True)
    (repo_root / "tofu" / "environments" / "production" / "main.tf").write_text("terraform {}\n", encoding="utf-8")
    (repo_root / "keys").mkdir()

    mock_bin = tmp_path / "bin"
    mock_bin.mkdir()
    invocation_log = tmp_path / "tofu-invocations.log"
    write_executable(
        mock_bin / "rsync",
        """
        #!/usr/bin/env bash
        set -euo pipefail
        while [[ "$1" == -* ]]; do
          shift
        done
        source_path="${1%/}"
        destination_path="${2%/}"
        mkdir -p "$destination_path"
        cp -a "$source_path/." "$destination_path/"
        """,
    )
    write_executable(
        mock_bin / "tofu",
        """
        #!/usr/bin/env bash
        set -euo pipefail
        printf '%s\\n' "$*" >> "$TOFU_INVOCATION_LOG"
        """,
    )
    environment = {
        **os.environ,
        "PATH": f"{mock_bin}{os.pathsep}{os.environ['PATH']}",
        "LV3_NATIVE_EXECUTION": "1",
        "TOFU_INIT_BACKEND": "false",
        "TOFU_PLAN_DIR": str(repo_root / "plans"),
        "TOFU_INVOCATION_LOG": str(invocation_log),
    }

    completed = subprocess.run(
        ["bash", str(scripts_dir / TOFU_SCRIPT.name), "validate", "production"],
        cwd=repo_root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    invocations = invocation_log.read_text(encoding="utf-8").splitlines()
    local_workdir = repo_root / "plans" / "runtime" / "tofu" / "environments" / "production"
    assert invocations == [
        f"-chdir={local_workdir} init -backend=false -input=false",
        f"-chdir={local_workdir} validate -no-color",
    ]
    assert (repo_root / "plans" / "tofu.tfrc").is_file()
