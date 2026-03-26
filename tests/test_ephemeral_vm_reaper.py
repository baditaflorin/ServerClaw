import importlib.util
import os
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "config" / "windmill" / "scripts" / "ephemeral-vm-reaper.py"
SPEC = importlib.util.spec_from_file_location("ephemeral_vm_reaper", SCRIPT_PATH)
ephemeral_vm_reaper = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(ephemeral_vm_reaper)


def test_reaper_blocks_when_repo_checkout_is_missing(tmp_path: Path) -> None:
    payload = ephemeral_vm_reaper.main(repo_path=str(tmp_path / "missing"))
    assert payload["status"] == "blocked"


def test_reaper_treats_null_repo_path_as_default(monkeypatch) -> None:
    monkeypatch.setattr(ephemeral_vm_reaper, "DEFAULT_REPO_PATH", "/srv/proxmox_florin_server")
    monkeypatch.setattr(
        ephemeral_vm_reaper,
        "_load_fixture_manager",
        lambda repo_root: (_ for _ in ()).throw(AssertionError("fixture_manager should not load when repo is missing")),
    )

    payload = ephemeral_vm_reaper.main(repo_path=None)
    assert payload["status"] == "blocked"
    assert payload["expected_repo_path"] == "/srv/proxmox_florin_server"


def test_reaper_hydrates_proxmox_env_from_pid1(monkeypatch, tmp_path: Path) -> None:
    environ_path = tmp_path / "proc1.environ"
    environ_path.write_bytes(
        b"TF_VAR_proxmox_endpoint=https://proxmox.example.invalid:8006/api2/json\0"
        b"TF_VAR_proxmox_api_token=lv3-automation@pve!primary=secret-token\0"
    )

    monkeypatch.delenv("TF_VAR_proxmox_endpoint", raising=False)
    monkeypatch.delenv("TF_VAR_proxmox_api_token", raising=False)

    ephemeral_vm_reaper._hydrate_proxmox_env_from_pid1(environ_path)

    assert os.environ["TF_VAR_proxmox_endpoint"] == "https://proxmox.example.invalid:8006/api2/json"
    assert os.environ["TF_VAR_proxmox_api_token"] == "lv3-automation@pve!primary=secret-token"


def test_reaper_hydrates_proxmox_env_from_runtime_env(monkeypatch, tmp_path: Path) -> None:
    runtime_env_path = tmp_path / "runtime.env"
    runtime_env_path.write_text(
        "DATABASE_URL=postgres://example\n"
        "TF_VAR_proxmox_endpoint=https://proxmox.example.invalid:8006/api2/json\n"
        "TF_VAR_proxmox_api_token=lv3-automation@pve!primary=secret-token\n",
        encoding="utf-8",
    )

    monkeypatch.delenv("TF_VAR_proxmox_endpoint", raising=False)
    monkeypatch.delenv("TF_VAR_proxmox_api_token", raising=False)

    ephemeral_vm_reaper._hydrate_proxmox_env_from_runtime_env(runtime_env_path)

    assert os.environ["TF_VAR_proxmox_endpoint"] == "https://proxmox.example.invalid:8006/api2/json"
    assert os.environ["TF_VAR_proxmox_api_token"] == "lv3-automation@pve!primary=secret-token"


def test_reaper_resolves_proxmox_api_credentials_from_env(monkeypatch) -> None:
    monkeypatch.setenv("TF_VAR_proxmox_endpoint", "https://proxmox.example.invalid:8006/api2/json")
    monkeypatch.setenv("TF_VAR_proxmox_api_token", "lv3-automation@pve!primary=secret-token")

    assert ephemeral_vm_reaper._resolve_proxmox_api_credentials() == (
        "https://proxmox.example.invalid:8006/api2/json",
        "lv3-automation@pve!primary=secret-token",
    )


def test_reaper_reads_proxmox_api_credentials_from_runtime_env(tmp_path: Path) -> None:
    runtime_env_path = tmp_path / "runtime.env"
    runtime_env_path.write_text(
        "DATABASE_URL=postgres://example\n"
        "TF_VAR_proxmox_endpoint=https://proxmox.example.invalid:8006/api2/json\n"
        "TF_VAR_proxmox_api_token=lv3-automation@pve!primary=secret-token\n",
        encoding="utf-8",
    )

    assert ephemeral_vm_reaper._read_proxmox_credentials_from_runtime_env(runtime_env_path) == (
        "https://proxmox.example.invalid:8006/api2/json",
        "lv3-automation@pve!primary=secret-token",
    )


def test_reaper_prefers_repo_local_proxmox_payload_when_runtime_env_is_missing(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / "config").mkdir(parents=True)
    (tmp_path / "inventory" / "group_vars").mkdir(parents=True)
    (tmp_path / "inventory" / "host_vars").mkdir(parents=True)
    (tmp_path / "tests" / "fixtures").mkdir(parents=True)
    (tmp_path / "receipts" / "fixtures").mkdir(parents=True)
    payload_path = tmp_path / ".local" / "proxmox-api" / "lv3-automation-primary.json"
    payload_path.parent.mkdir(parents=True)
    payload_path.write_text('{"api_url":"https://repo-local.example.invalid","full_token_id":"id","value":"secret"}\n')
    seen: dict[str, Path | None] = {"token_file": None}

    class FixtureManagerStub:
        proxmox_api_credentials = staticmethod(lambda: FixtureManagerStub.vmid_allocator.read_api_credentials())

        class vmid_allocator:  # noqa: N801 - mirrors imported module attribute
            @staticmethod
            def read_api_credentials(*, endpoint=None, api_token=None, token_file=None):
                seen["token_file"] = token_file
                return ("https://repo-local.example.invalid", "id=secret")

        @staticmethod
        def reap_expired():
            endpoint, api_token = FixtureManagerStub.proxmox_api_credentials()
            return {"endpoint": endpoint, "api_token": api_token}

    monkeypatch.setattr(ephemeral_vm_reaper, "_load_fixture_manager", lambda repo_root: FixtureManagerStub)
    monkeypatch.setattr(ephemeral_vm_reaper, "_hydrate_proxmox_env_from_pid1", lambda: None)
    monkeypatch.setattr(ephemeral_vm_reaper, "_hydrate_proxmox_env_from_runtime_env", lambda: None)
    monkeypatch.setattr(ephemeral_vm_reaper, "_resolve_proxmox_api_credentials", lambda: None)

    payload = ephemeral_vm_reaper.main(repo_path=str(tmp_path))
    assert payload == {"endpoint": "https://repo-local.example.invalid", "api_token": "id=secret"}
    assert seen["token_file"] == payload_path


def test_reaper_uses_fixture_manager_for_existing_repo(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / "config").mkdir(parents=True)
    (tmp_path / "inventory" / "group_vars").mkdir(parents=True)
    (tmp_path / "inventory" / "host_vars").mkdir(parents=True)
    (tmp_path / "tests" / "fixtures").mkdir(parents=True)
    (tmp_path / "receipts" / "fixtures").mkdir(parents=True)

    class FixtureManagerStub:
        REPO_ROOT = None
        FIXTURE_DEFINITIONS_DIR = None
        FIXTURE_RECEIPTS_DIR = None
        FIXTURE_LOCAL_ROOT = None
        FIXTURE_RUNTIME_DIR = None
        FIXTURE_ARCHIVE_DIR = None
        FIXTURE_LOCKS_DIR = None
        CONTROLLER_SECRETS_PATH = None
        TEMPLATE_MANIFEST_PATH = None
        GROUP_VARS_PATH = None
        HOST_VARS_PATH = None
        CAPACITY_MODEL_PATH = None
        proxmox_api_credentials = None
        class vmid_allocator:  # noqa: N801 - mirrors imported module attribute
            read_api_credentials = None

        @staticmethod
        def reap_expired():
            return {"run_at": "2026-03-23T12:00:00Z", "expired_vmids": [], "skipped_vmids": []}

    monkeypatch.setattr(ephemeral_vm_reaper, "_load_fixture_manager", lambda repo_root: FixtureManagerStub)
    monkeypatch.setattr(ephemeral_vm_reaper, "_hydrate_proxmox_env_from_pid1", lambda: None)
    monkeypatch.setattr(ephemeral_vm_reaper, "_hydrate_proxmox_env_from_runtime_env", lambda: None)
    monkeypatch.setattr(
        ephemeral_vm_reaper,
        "_resolve_proxmox_api_credentials",
        lambda: ("https://proxmox.example.invalid:8006/api2/json", "lv3-automation@pve!primary=secret-token"),
    )

    payload = ephemeral_vm_reaper.main(repo_path=str(tmp_path))
    assert payload["run_at"] == "2026-03-23T12:00:00Z"
    assert FixtureManagerStub.proxmox_api_credentials() == (
        "https://proxmox.example.invalid:8006/api2/json",
        "lv3-automation@pve!primary=secret-token",
    )
    assert FixtureManagerStub.vmid_allocator.read_api_credentials() == (
        "https://proxmox.example.invalid:8006/api2/json",
        "lv3-automation@pve!primary=secret-token",
    )
