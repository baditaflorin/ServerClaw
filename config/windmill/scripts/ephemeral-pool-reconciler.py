import json
import os
import importlib.util
import sys
from pathlib import Path
from types import ModuleType


DEFAULT_REPO_PATH = "/srv/proxmox_florin_server"
PROXMOX_ENV_KEYS = ("TF_VAR_proxmox_endpoint", "TF_VAR_proxmox_api_token")
REPO_LOCAL_PROXMOX_API_TOKEN_PAYLOAD = Path(".local/proxmox-api/lv3-automation-primary.json")
REPO_LOCAL_BOOTSTRAP_PRIVATE_KEYS = (
    Path(".local/ssh/bootstrap.id_ed25519"),
    Path(".local/ssh/hetzner_llm_agents_ed25519"),
)


def _hydrate_proxmox_env_from_runtime_env(
    runtime_env_path: Path = Path("/run/lv3-secrets/windmill/runtime.env"),
) -> None:
    if all(os.environ.get(key) for key in PROXMOX_ENV_KEYS):
        return
    try:
        payload = runtime_env_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return
    for line in payload.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key not in PROXMOX_ENV_KEYS or os.environ.get(key):
            continue
        os.environ[key] = value


def _resolve_proxmox_api_credentials() -> tuple[str, str] | None:
    endpoint = os.environ.get("TF_VAR_proxmox_endpoint", "").strip()
    api_token = os.environ.get("TF_VAR_proxmox_api_token", "").strip()
    if endpoint and api_token:
        return endpoint, api_token
    return None


def _load_fixture_manager(repo_root: Path) -> ModuleType:
    scripts_dir = repo_root / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    fixture_manager_path = repo_root / "scripts" / "fixture_manager.py"
    spec = importlib.util.spec_from_file_location("lv3_fixture_manager", fixture_manager_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load fixture manager from {fixture_manager_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main(repo_path: str | None = DEFAULT_REPO_PATH):
    repo_root = Path(repo_path or DEFAULT_REPO_PATH)
    if not repo_root.exists():
        return {
            "status": "blocked",
            "reason": "repo checkout not mounted on the worker",
            "expected_repo_path": str(repo_root),
        }

    fixture_manager = _load_fixture_manager(repo_root)
    _hydrate_proxmox_env_from_runtime_env()
    proxmox_credentials = _resolve_proxmox_api_credentials()
    repo_local_proxmox_payload = repo_root / REPO_LOCAL_PROXMOX_API_TOKEN_PAYLOAD
    if proxmox_credentials is not None:
        fixture_manager.proxmox_api_credentials = lambda: proxmox_credentials
        fixture_manager.vmid_allocator.read_api_credentials = lambda **_: proxmox_credentials
    elif repo_local_proxmox_payload.exists():
        original_read_api_credentials = fixture_manager.vmid_allocator.read_api_credentials
        fixture_manager.vmid_allocator.read_api_credentials = (
            lambda **kwargs: original_read_api_credentials(token_file=repo_local_proxmox_payload, **kwargs)
        )
        fixture_manager.proxmox_api_credentials = lambda: fixture_manager.vmid_allocator.read_api_credentials()
    fixture_manager.REPO_ROOT = repo_root
    fixture_manager.FIXTURE_DEFINITIONS_DIR = repo_root / "tests" / "fixtures"
    fixture_manager.FIXTURE_RECEIPTS_DIR = repo_root / "receipts" / "fixtures"
    fixture_manager.FIXTURE_LOCAL_ROOT = repo_root / ".local" / "fixtures"
    fixture_manager.FIXTURE_REAPER_RUNS_DIR = fixture_manager.FIXTURE_LOCAL_ROOT / "reaper-runs"
    fixture_manager.FIXTURE_RUNTIME_DIR = fixture_manager.FIXTURE_LOCAL_ROOT / "runtime"
    fixture_manager.FIXTURE_ARCHIVE_DIR = fixture_manager.FIXTURE_LOCAL_ROOT / "archive"
    fixture_manager.FIXTURE_LOCKS_DIR = fixture_manager.FIXTURE_LOCAL_ROOT / "locks"
    fixture_manager.CONTROLLER_SECRETS_PATH = repo_root / "config" / "controller-local-secrets.json"
    fixture_manager.TEMPLATE_MANIFEST_PATH = repo_root / "config" / "vm-template-manifest.json"
    fixture_manager.GROUP_VARS_PATH = repo_root / "inventory" / "group_vars" / "all.yml"
    fixture_manager.HOST_VARS_PATH = repo_root / "inventory" / "host_vars" / "proxmox_florin.yml"
    fixture_manager.CAPACITY_MODEL_PATH = repo_root / "config" / "capacity-model.json"
    fixture_manager.EPHEMERAL_POOL_CATALOG_PATH = repo_root / "config" / "ephemeral-capacity-pools.json"
    for worker_bootstrap_private_key in (
        repo_root / candidate for candidate in REPO_LOCAL_BOOTSTRAP_PRIVATE_KEYS
    ):
        if worker_bootstrap_private_key.exists():
            fixture_manager.bootstrap_private_key = lambda: worker_bootstrap_private_key
            break
    return fixture_manager.reconcile_pools()


if __name__ == "__main__":
    print(json.dumps(main(), indent=2, sort_keys=True))
