from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

import fixture_manager


@pytest.fixture()
def fixture_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    repo_root = tmp_path
    (repo_root / "config").mkdir()
    (repo_root / "inventory" / "group_vars").mkdir(parents=True)
    (repo_root / "inventory" / "host_vars").mkdir(parents=True)
    (repo_root / "tests" / "fixtures").mkdir(parents=True)
    (repo_root / "receipts" / "fixtures").mkdir(parents=True)
    (repo_root / ".local" / "keys").mkdir(parents=True)
    (repo_root / "tofu" / "modules" / "proxmox-fixture").mkdir(parents=True)

    (repo_root / "config" / "controller-local-secrets.json").write_text(
        json.dumps(
            {
                "secrets": {
                    "bootstrap_ssh_private_key": {"path": str(repo_root / ".local" / "keys" / "bootstrap")},
                    "proxmox_api_token_payload": {"path": str(repo_root / ".local" / "keys" / "token.json")},
                }
            }
        )
        + "\n"
    )
    (repo_root / ".local" / "keys" / "bootstrap").write_text("PRIVATE\n")
    (repo_root / ".local" / "keys" / "bootstrap.pub").write_text("ssh-ed25519 AAAATEST fixture\n")
    (repo_root / ".local" / "keys" / "token.json").write_text(
        json.dumps(
            {
                "api_url": "https://proxmox.example.invalid:8006/api2/json",
                "full_token_id": "lv3-automation@pve!primary",
                "value": "secret-token",
            }
        )
        + "\n"
    )
    (repo_root / "config" / "vm-template-manifest.json").write_text(
        json.dumps({"templates": {"lv3-docker-host": {"vmid": 9001, "name": "lv3-docker-host"}}}) + "\n"
    )
    (repo_root / "config" / "capacity-model.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "ephemeral_pool": {
                    "vmid_range": [910, 979],
                    "max_concurrent_vms": 5,
                    "reserved_ram_gb": 20,
                    "reserved_vcpu": 8,
                    "reserved_disk_gb": 100,
                    "notes": "fixture test pool",
                },
            }
        )
        + "\n"
    )
    (repo_root / "inventory" / "group_vars" / "all.yml").write_text(
        "\n".join(
            [
                "proxmox_storage_id: local",
                "proxmox_snippets_storage_id: local",
                "proxmox_guest_ci_user: ops",
                "proxmox_guest_nameserver: 1.1.1.1",
                "proxmox_guest_searchdomain: lv3.org",
                "proxmox_host_admin_user: ops",
            ]
        )
        + "\n"
    )
    (repo_root / "inventory" / "host_vars" / "proxmox_florin.yml").write_text("management_ipv4: 65.108.75.123\n")
    (repo_root / "tests" / "fixtures" / "docker-host-fixture.yml").write_text(
        json.dumps(
            {
                "fixture_id": "docker-host",
                "template": "lv3-docker-host",
                "vmid_range": [910, 979],
                "network": {"bridge": "vmbr20", "ip_cidr": "10.20.10.100/24", "gateway": "10.20.10.1"},
                "resources": {"cores": 2, "memory_mb": 2048, "disk_gb": 20},
                "lifetime_minutes": 30,
                "roles_under_test": ["lv3.platform.docker_runtime"],
                "verify": [{"command": "docker info >/dev/null", "timeout_seconds": 30}],
            }
        )
        + "\n"
    )

    monkeypatch.setattr(fixture_manager, "REPO_ROOT", repo_root)
    monkeypatch.setattr(fixture_manager, "FIXTURE_DEFINITIONS_DIR", repo_root / "tests" / "fixtures")
    monkeypatch.setattr(fixture_manager, "FIXTURE_RECEIPTS_DIR", repo_root / "receipts" / "fixtures")
    monkeypatch.setattr(fixture_manager, "FIXTURE_LOCAL_ROOT", repo_root / ".local" / "fixtures")
    monkeypatch.setattr(fixture_manager, "FIXTURE_REAPER_RUNS_DIR", repo_root / ".local" / "fixtures" / "reaper-runs")
    monkeypatch.setattr(fixture_manager, "FIXTURE_RUNTIME_DIR", repo_root / ".local" / "fixtures" / "runtime")
    monkeypatch.setattr(fixture_manager, "FIXTURE_ARCHIVE_DIR", repo_root / ".local" / "fixtures" / "archive")
    monkeypatch.setattr(fixture_manager, "FIXTURE_LOCKS_DIR", repo_root / ".local" / "fixtures" / "locks")
    monkeypatch.setattr(fixture_manager, "CONTROLLER_SECRETS_PATH", repo_root / "config" / "controller-local-secrets.json")
    monkeypatch.setattr(fixture_manager, "TEMPLATE_MANIFEST_PATH", repo_root / "config" / "vm-template-manifest.json")
    monkeypatch.setattr(fixture_manager, "CAPACITY_MODEL_PATH", repo_root / "config" / "capacity-model.json")
    monkeypatch.setattr(fixture_manager, "GROUP_VARS_PATH", repo_root / "inventory" / "group_vars" / "all.yml")
    monkeypatch.setattr(fixture_manager, "HOST_VARS_PATH", repo_root / "inventory" / "host_vars" / "proxmox_florin.yml")
    return repo_root


def test_fixture_up_writes_active_receipt(fixture_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        fixture_manager,
        "fetch_cluster_resources",
        lambda endpoint, api_token: [{"vmid": 9000}, {"vmid": 9001}],
    )
    monkeypatch.setattr(fixture_manager, "apply_fixture", lambda runtime_dir, endpoint, api_token: None)
    monkeypatch.setattr(fixture_manager, "wait_for_ssh", lambda receipt, timeout_seconds=300: None)
    monkeypatch.setattr(fixture_manager, "converge_roles", lambda receipt, skip_roles=False: None)
    monkeypatch.setattr(fixture_manager, "verify_fixture", lambda receipt, definition: {"ok": True, "checks": [{"ok": True}]})
    monkeypatch.setattr(fixture_manager, "capture_ssh_fingerprint", lambda receipt: "fingerprint")
    monkeypatch.setattr(fixture_manager, "emit_ephemeral_event", lambda *args, **kwargs: None)

    receipt = fixture_manager.fixture_up("docker-host", purpose="adr-0106-test", owner="codex")

    assert receipt["status"] == "active"
    assert receipt["vm_id"] == 910
    assert "expires_at" in receipt
    assert receipt["owner"] == "codex"
    assert receipt["purpose"] == "adr-0106-test"
    assert any(tag.startswith("ephemeral-codex-adr-0106-test-") for tag in receipt["ephemeral_tags"])
    saved_receipts = list((fixture_repo / "receipts" / "fixtures").glob("*.json"))
    assert len(saved_receipts) == 1
    payload = json.loads(saved_receipts[0].read_text())
    assert payload["ssh_fingerprint"] == "fingerprint"


def test_fixture_down_archives_and_removes_receipt(fixture_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runtime_dir = fixture_repo / ".local" / "fixtures" / "runtime" / "docker-host-20260323T100000Z"
    runtime_dir.mkdir(parents=True)
    receipt = {
        "receipt_id": "docker-host-20260323T100000Z",
        "fixture_id": "docker-host",
        "status": "active",
        "created_at": "2026-03-23T10:00:00Z",
        "updated_at": "2026-03-23T10:00:00Z",
        "lifetime_minutes": 30,
        "extend_minutes": 0,
        "owner": "codex",
        "purpose": "adr-0106-test",
        "policy": "adr-development",
        "expires_epoch": 1774261800,
        "expires_at": "2026-03-23T10:30:00Z",
        "ephemeral_tags": ["ephemeral-codex-adr-0106-test-1774261800"],
        "runtime_dir": ".local/fixtures/runtime/docker-host-20260323T100000Z",
        "vm_id": 910,
        "ip_address": "10.20.10.100",
        "definition": {"ssh_user": "ops"},
        "context": {"ci_user": "ops"},
    }
    (fixture_repo / "receipts" / "fixtures" / "docker-host-20260323T100000Z.json").write_text(json.dumps(receipt) + "\n")
    monkeypatch.setattr(fixture_manager, "destroy_fixture", lambda runtime_dir, endpoint, api_token: None)
    monkeypatch.setattr(fixture_manager, "emit_ephemeral_event", lambda *args, **kwargs: None)

    payload = fixture_manager.fixture_down("docker-host")

    assert payload["destroyed"] == [{"receipt_id": "docker-host-20260323T100000Z", "vm_id": 910}]
    assert not (fixture_repo / "receipts" / "fixtures" / "docker-host-20260323T100000Z.json").exists()
    assert (fixture_repo / ".local" / "fixtures" / "archive" / "docker-host-20260323T100000Z.json").exists()


def test_render_fixture_table_handles_empty_rows() -> None:
    assert fixture_manager.render_fixture_table([]) == "No active fixtures"


def test_reap_expired_only_destroys_expired_receipts(fixture_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    expired = {
        "receipt_id": "docker-host-20260323T080000Z",
        "fixture_id": "docker-host",
        "status": "active",
        "created_at": "2026-03-23T08:00:00Z",
        "updated_at": "2026-03-23T08:00:00Z",
        "lifetime_minutes": 30,
        "extend_minutes": 0,
        "owner": "codex",
        "purpose": "expired",
        "policy": "adr-development",
        "expires_epoch": 1774254600,
        "expires_at": "2026-03-23T08:30:00Z",
        "ephemeral_tags": ["ephemeral-codex-expired-1774254600"],
        "runtime_dir": ".local/fixtures/runtime/docker-host-20260323T080000Z",
        "vm_id": 910,
        "ip_address": "10.20.10.100",
        "definition": {},
        "context": {},
    }
    active = {
        "receipt_id": "docker-host-20990323T120000Z",
        "fixture_id": "docker-host",
        "status": "active",
        "created_at": "2099-03-23T12:00:00Z",
        "updated_at": "2099-03-23T12:00:00Z",
        "lifetime_minutes": 30,
        "extend_minutes": 0,
        "owner": "codex",
        "purpose": "active",
        "policy": "adr-development",
        "expires_epoch": 4088510400,
        "expires_at": "2099-03-23T12:30:00Z",
        "ephemeral_tags": ["ephemeral-codex-active-4088510400"],
        "runtime_dir": ".local/fixtures/runtime/docker-host-20990323T120000Z",
        "vm_id": 911,
        "ip_address": "10.20.10.101",
        "definition": {},
        "context": {},
    }
    (fixture_repo / "receipts" / "fixtures" / f"{expired['receipt_id']}.json").write_text(json.dumps(expired) + "\n")
    (fixture_repo / "receipts" / "fixtures" / f"{active['receipt_id']}.json").write_text(json.dumps(active) + "\n")

    destroyed_ids: list[str] = []

    def fake_fixture_down(fixture_name: str | None = None, *, receipt_id: str | None = None) -> dict[str, object]:
        destroyed_ids.append(receipt_id or fixture_name or "")
        return {"destroyed": []}

    monkeypatch.setattr(fixture_manager, "fixture_down", fake_fixture_down)
    monkeypatch.setattr(
        fixture_manager,
        "fetch_cluster_resources",
        lambda endpoint, api_token: [
            {"vmid": 910, "tags": "ephemeral-owner-codex;ephemeral-purpose-expired;ephemeral-expires-1", "status": "running"},
            {"vmid": 911, "tags": "ephemeral-owner-codex;ephemeral-purpose-active;ephemeral-expires-4088510400", "status": "running"},
        ],
    )
    payload = fixture_manager.reap_expired()

    assert destroyed_ids == [expired["receipt_id"]]
    assert payload["skipped_vmids"] == [911]
    reaper_runs = sorted((fixture_repo / ".local" / "fixtures" / "reaper-runs").glob("reaper-run-*.json"))
    assert len(reaper_runs) == 1
    assert json.loads(reaper_runs[0].read_text())["skipped_vmids"] == [911]


def test_build_runtime_main_targets_fixture_module(fixture_repo: Path) -> None:
    receipt = fixture_manager.build_receipt(
        fixture_manager.load_fixture_definition(fixture_repo / "tests" / "fixtures" / "docker-host-fixture.yml"),
        fixture_repo / "tests" / "fixtures" / "docker-host-fixture.yml",
        910,
        fixture_manager.utc_now(),
        owner="codex",
        purpose="runtime-test",
        policy="adr-development",
        lifetime_minutes=30,
    )
    rendered = fixture_manager.build_runtime_main(receipt)
    assert "proxmox-fixture" in rendered
    assert '"prevent_destroy"' not in rendered


def test_fixture_list_reads_cluster_ephemeral_metadata(
    fixture_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        fixture_manager,
        "fetch_cluster_resources",
        lambda endpoint, api_token: [
            {
                "vmid": 910,
                "name": "fixture-910",
                "status": "running",
                "type": "qemu",
                "tags": "ephemeral-owner-codex;ephemeral-purpose-adr-0106-test;ephemeral-expires-4088510400",
            }
        ],
    )
    rows = fixture_manager.fixture_list(refresh_health=False)

    assert rows[0]["owner"] == "codex"
    assert rows[0]["purpose"] == "adr-0106-test"
    assert rows[0]["vm_id"] == 910


def test_reaper_retags_untagged_cluster_vms(fixture_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    applied: list[list[str]] = []
    monkeypatch.setattr(
        fixture_manager,
        "fetch_cluster_resources",
        lambda endpoint, api_token: [{"vmid": 912, "node": "proxmox_florin", "status": "running", "type": "qemu", "tags": ""}],
    )
    monkeypatch.setattr(fixture_manager, "apply_cluster_vm_tags", lambda endpoint, api_token, resource, tags: applied.append(tags))

    payload = fixture_manager.reap_expired()

    assert payload["warned_vmids"] == [912]
    assert payload["retagged_vmids"] == [912]
    assert any(tag.startswith("ephemeral-expires-") for tag in applied[0])
