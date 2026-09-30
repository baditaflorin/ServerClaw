from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCANNER = REPO_ROOT / "scripts" / "trivy_scan_running_images.sh"


def test_scanner_uses_running_containers_local_image_id(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    docker.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
case "$1" in
  ps)
    printf 'container-1\\n'
    ;;
  inspect)
    printf 'artifacts.example.invalid/team/app:v1|sha256:0123456789abcdef\\n'
    ;;
  image)
    [[ "$2" == inspect && "$3" == sha256:0123456789abcdef ]]
    ;;
  run)
    target="${@: -1}"
    [[ "$target" == sha256:0123456789abcdef ]]
    printf '{"ArtifactName":"local-image","Results":[]}\\n'
    ;;
  *)
    exit 90
    ;;
esac
""",
        encoding="utf-8",
    )
    docker.chmod(0o755)

    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{bin_dir}{os.pathsep}{env['PATH']}",
            "TRIVY_IMAGE": "trivy-test:local",
            "TRIVY_CACHE_DIR": str(tmp_path / "cache"),
        }
    )
    result = subprocess.run(
        ["bash", str(SCANNER)],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert len(payload) == 1
    assert payload[0]["image"] == "artifacts.example.invalid/team/app:v1"
    assert payload[0]["image_id"] == "sha256:0123456789abcdef"


def test_scanner_refuses_missing_local_image_without_registry_fallback(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    docker.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
case "$1" in
  ps) printf 'container-1\\n' ;;
  inspect) printf 'example.invalid/team/app:v1|sha256:0123456789abcdef\\n' ;;
  image) exit 1 ;;
  run) echo 'must not pull or scan' >&2; exit 91 ;;
  *) exit 90 ;;
esac
""",
        encoding="utf-8",
    )
    docker.chmod(0o755)

    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{bin_dir}{os.pathsep}{env['PATH']}",
            "TRIVY_IMAGE": "trivy-test:local",
            "TRIVY_CACHE_DIR": str(tmp_path / "cache"),
        }
    )
    result = subprocess.run(
        ["bash", str(SCANNER)],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode == 1
    assert "refusing an implicit registry pull" in result.stderr
    assert "must not pull or scan" not in result.stderr
