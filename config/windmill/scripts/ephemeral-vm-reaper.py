import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

import fixture_manager


def main(repo_path: str = "/srv/proxmox_florin_server"):
    repo_root = Path(repo_path)
    if not repo_root.exists():
        return {
            "status": "blocked",
            "reason": "repo checkout not mounted on the worker",
            "expected_repo_path": str(repo_root),
        }

    fixture_manager.REPO_ROOT = repo_root
    fixture_manager.FIXTURE_DEFINITIONS_DIR = repo_root / "tests" / "fixtures"
    fixture_manager.FIXTURE_RECEIPTS_DIR = repo_root / "receipts" / "fixtures"
    fixture_manager.FIXTURE_LOCAL_ROOT = repo_root / ".local" / "fixtures"
    fixture_manager.FIXTURE_RUNTIME_DIR = fixture_manager.FIXTURE_LOCAL_ROOT / "runtime"
    fixture_manager.FIXTURE_ARCHIVE_DIR = fixture_manager.FIXTURE_LOCAL_ROOT / "archive"
    fixture_manager.FIXTURE_LOCKS_DIR = fixture_manager.FIXTURE_LOCAL_ROOT / "locks"
    fixture_manager.CONTROLLER_SECRETS_PATH = repo_root / "config" / "controller-local-secrets.json"
    fixture_manager.TEMPLATE_MANIFEST_PATH = repo_root / "config" / "vm-template-manifest.json"
    fixture_manager.GROUP_VARS_PATH = repo_root / "inventory" / "group_vars" / "all.yml"
    fixture_manager.HOST_VARS_PATH = repo_root / "inventory" / "host_vars" / "proxmox_florin.yml"
    fixture_manager.CAPACITY_MODEL_PATH = repo_root / "config" / "capacity-model.json"

    return fixture_manager.reap_expired()


if __name__ == "__main__":
    print(json.dumps(main(), indent=2, sort_keys=True))
