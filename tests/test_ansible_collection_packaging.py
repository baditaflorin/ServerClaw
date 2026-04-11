import json
import os
import subprocess
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
COLLECTION_ROOT = REPO_ROOT / "collections" / "ansible_collections" / "lv3" / "platform"
PUBLISH_SCRIPT = REPO_ROOT / "config" / "windmill" / "scripts" / "collection-publish.py"


def test_collection_metadata_and_runtime_contract() -> None:
    galaxy = yaml.safe_load((COLLECTION_ROOT / "galaxy.yml").read_text())
    runtime = yaml.safe_load((COLLECTION_ROOT / "meta" / "runtime.yml").read_text())

    assert galaxy["namespace"] == "lv3"
    assert galaxy["name"] == "platform"
    assert galaxy["version"] == "1.0.0"
    assert runtime["requires_ansible"] == ">=2.16.0"


def test_repo_root_paths_are_collection_symlinks() -> None:
    roles_link = REPO_ROOT / "roles"
    filter_link = REPO_ROOT / "filter_plugins"
    callback_link = REPO_ROOT / "callback_plugins"

    assert roles_link.is_symlink()
    assert filter_link.is_symlink()
    assert callback_link.is_symlink()
    assert roles_link.resolve() == COLLECTION_ROOT / "roles"
    assert filter_link.resolve() == COLLECTION_ROOT / "plugins" / "filter"
    assert callback_link.resolve() == COLLECTION_ROOT / "plugins" / "callback"


def test_preflight_dependency_is_declared_by_multiple_roles() -> None:
    role_names = [
        "docker_runtime",
        "uptime_kuma_runtime",
        "postgres_vm",
        "proxmox_tailscale",
        "linux_access",
        "linux_guest_firewall",
    ]
    for role_name in role_names:
        meta = yaml.safe_load((COLLECTION_ROOT / "roles" / role_name / "meta" / "main.yml").read_text())
        assert meta["dependencies"][0]["role"] == "lv3.platform.preflight"


def test_makefile_exposes_collection_targets() -> None:
    makefile = (REPO_ROOT / "Makefile").read_text()
    assert "collection-sync" in makefile
    assert "collection-build" in makefile
    assert "collection-publish" in makefile
    assert "collection-install" in makefile


def test_collection_publish_script_supports_dry_run(tmp_path: Path) -> None:
    log_path = tmp_path / "ansible-galaxy.log"
    fake_ansible_galaxy = tmp_path / "ansible-galaxy"
    fake_ansible_galaxy.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'printf \'%s\\n\' "$*" >> "$ANSIBLE_GALAXY_LOG"\n'
        'if [[ "$2" == "build" ]]; then\n'
        '  out_dir="$5"\n'
        '  mkdir -p "$out_dir"\n'
        '  touch "$out_dir/lv3-platform-1.0.0.tar.gz"\n'
        "fi\n"
    )
    fake_ansible_galaxy.chmod(0o755)

    env = os.environ.copy()
    env.update(
        {
            "ANSIBLE_GALAXY_BIN": str(fake_ansible_galaxy),
            "ANSIBLE_GALAXY_LOG": str(log_path),
        }
    )
    completed = subprocess.run(
        ["python3", str(PUBLISH_SCRIPT), "--repo-root", str(REPO_ROOT), "--dry-run"],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["dry_run"] is True
    assert payload["server"] == "internal_galaxy"
    assert "collection build" in payload["build_command"]
    assert "collection publish" in payload["publish_command"]
    assert "collection build" in log_path.read_text()
