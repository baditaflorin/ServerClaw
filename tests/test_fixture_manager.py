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
    (repo_root / "tofu" / "modules" / "proxmox-vm-destroyable").mkdir(parents=True)

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
        json.dumps(
            {
                "templates": {
                    "lv3-debian-base": {"vmid": 9000, "name": "lv3-debian-base"},
                    "lv3-docker-host": {
                        "vmid": 9001,
                        "name": "lv3-docker-host",
                        "source_template": "lv3-debian-base",
                    },
                    "lv3-ops-base": {
                        "vmid": 9003,
                        "name": "lv3-ops-base",
                        "source_template": "lv3-debian-base",
                    },
                }
            }
        )
        + "\n"
    )
    (repo_root / "config" / "capacity-model.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "reservations": [
                    {
                        "id": "ephemeral-pool",
                        "kind": "ephemeral_pool",
                        "status": "reserved",
                        "vmid_range": {"start": 910, "end": 979},
                        "max_concurrent_vms": 5,
                        "reserved": {"ram_gb": 20, "vcpu": 8, "disk_gb": 100},
                        "notes": "fixture test pool",
                    }
                ],
            }
        )
        + "\n"
    )
    (repo_root / "config" / "ephemeral-capacity-pools.json").write_text(
        json.dumps(
            {
                "$schema": "docs/schema/ephemeral-capacity-pools.schema.json",
                "schema_version": "1.0.0",
                "defaults": {
                    "max_local_active_leases": 3,
                    "protected_capacity_class": "ephemeral-burst-local",
                    "spillover_domain": "hetzner-cloud-burst",
                    "warm_lifetime_minutes": 1440,
                },
                "pools": [
                    {
                        "id": "docker-host",
                        "fixture_id": "docker-host",
                        "warm_count": 1,
                        "refill_target": 1,
                        "max_concurrent_leases": 2,
                        "allowed_lease_purposes": ["fixture", "preview", "recovery-drill", "load-test"],
                        "allowed_placement_classes": ["fixture", "preview", "recovery"],
                        "ip_addresses": ["10.20.10.100/24", "10.20.10.101/24", "10.20.10.102/24"],
                        "placement_domain": "proxmox-local",
                        "spillover_domain": "hetzner-cloud-burst",
                        "protected_capacity_class": "ephemeral-burst-local",
                    }
                ],
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
                "proxmox_guest_searchdomain: example.com",
                "proxmox_host_admin_user: ops",
            ]
        )
        + "\n"
    )
    (repo_root / "inventory" / "host_vars" / "proxmox-host.yml").write_text(
        "management_ipv4: 203.0.113.1\nmanagement_tailscale_ipv4: 100.64.0.1\n"
    )
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
    monkeypatch.setattr(
        fixture_manager, "CONTROLLER_SECRETS_PATH", repo_root / "config" / "controller-local-secrets.json"
    )
    monkeypatch.setattr(fixture_manager, "TEMPLATE_MANIFEST_PATH", repo_root / "config" / "vm-template-manifest.json")
    monkeypatch.setattr(fixture_manager, "CAPACITY_MODEL_PATH", repo_root / "config" / "capacity-model.json")
    monkeypatch.setattr(
        fixture_manager,
        "EPHEMERAL_POOL_CATALOG_PATH",
        repo_root / "config" / "ephemeral-capacity-pools.json",
    )
    monkeypatch.setattr(fixture_manager, "GROUP_VARS_PATH", repo_root / "inventory" / "group_vars" / "all.yml")
    monkeypatch.setattr(fixture_manager, "HOST_VARS_PATH", repo_root / "inventory" / "host_vars" / "proxmox-host.yml")
    monkeypatch.setattr(
        fixture_manager.seed_data_snapshots, "seed_classes", lambda catalog=None: ["tiny", "standard", "recovery"]
    )
    return repo_root


def test_fixture_up_writes_active_receipt(fixture_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        fixture_manager,
        "fetch_cluster_resources",
        lambda endpoint, api_token: [{"vmid": 9000}, {"vmid": 9001}],
    )
    monkeypatch.setattr(fixture_manager, "apply_fixture", lambda runtime_dir, endpoint, api_token, **kwargs: None)
    monkeypatch.setattr(fixture_manager, "wait_for_ssh", lambda receipt, timeout_seconds=300: None)

    def fake_stage_seed_snapshot(receipt, seed_class=None, snapshot_id=None):
        receipt["seed_class"] = seed_class or "tiny"
        receipt["seed_snapshot_id"] = snapshot_id or "tiny-snapshot"
        receipt["seed_snapshot_remote_dir"] = "/var/lib/lv3-seed-data/tiny"
        return {
            "seed_class": receipt["seed_class"],
            "snapshot_id": receipt["seed_snapshot_id"],
            "remote_dir": receipt["seed_snapshot_remote_dir"],
        }

    monkeypatch.setattr(fixture_manager, "stage_seed_snapshot", fake_stage_seed_snapshot)
    monkeypatch.setattr(fixture_manager, "wait_for_cloud_init", lambda receipt: None)
    monkeypatch.setattr(fixture_manager, "prepare_guest_for_converge", lambda receipt: None)
    monkeypatch.setattr(fixture_manager, "converge_roles", lambda receipt, skip_roles=False: None)
    monkeypatch.setattr(
        fixture_manager, "verify_fixture", lambda receipt, definition: {"ok": True, "checks": [{"ok": True}]}
    )
    monkeypatch.setattr(fixture_manager, "capture_ssh_fingerprint", lambda receipt: "fingerprint")
    monkeypatch.setattr(fixture_manager, "emit_ephemeral_event", lambda *args, **kwargs: None)

    receipt = fixture_manager.fixture_up("docker-host", purpose="adr-0106-test", owner="codex")

    assert receipt["status"] == "active"
    assert receipt["vm_id"] == 910
    assert "expires_at" in receipt
    assert receipt["owner"] == "codex"
    assert receipt["purpose"] == "adr-0106-test"
    assert receipt["seed_snapshot_id"] == "tiny-snapshot"
    assert receipt["lease_purpose"] == "fixture"
    assert receipt["pool_id"] == "docker-host"
    assert any(tag.startswith("ephemeral-codex-adr-0106-test-") for tag in receipt["ephemeral_tags"])
    saved_receipts = list((fixture_repo / "receipts" / "fixtures").glob("*.json"))
    assert len(saved_receipts) == 1
    payload = json.loads(saved_receipts[0].read_text())
    assert payload["ssh_fingerprint"] == "fingerprint"
    assert payload["context"]["jump_host"] == "100.64.0.1"


def test_load_ephemeral_pool_accepts_reservation_shape(fixture_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (fixture_repo / "config" / "capacity-model.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "reservations": [
                    {
                        "id": "ephemeral-pool",
                        "kind": "ephemeral_pool",
                        "status": "reserved",
                        "vmid_range": {"start": 910, "end": 979},
                        "max_concurrent_vms": 5,
                        "reserved": {"ram_gb": 20, "vcpu": 8, "disk_gb": 100},
                    }
                ],
            }
        )
        + "\n"
    )
    monkeypatch.setattr(fixture_manager, "CAPACITY_MODEL_PATH", fixture_repo / "config" / "capacity-model.json")

    pool = fixture_manager.load_ephemeral_pool()

    assert pool["vmid_range"] == [910, 979]
    assert pool["reserved_ram_gb"] == 20
    assert pool["reserved_vcpu"] == 8


def test_load_ephemeral_pool_accepts_current_reservations_shape(fixture_repo: Path) -> None:
    pool = fixture_manager.load_ephemeral_pool()

    assert pool == {
        "vmid_range": [910, 979],
        "max_concurrent_vms": 5,
        "reserved_ram_gb": 20,
        "reserved_vcpu": 8,
        "reserved_disk_gb": 100,
        "capacity_class": "preview_burst",
        "notes": "fixture test pool",
    }


def test_tofu_endpoint_rewrites_loopback_for_docker_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        fixture_manager.shutil, "which", lambda command: None if command == "tofu" else "/usr/bin/docker"
    )

    assert (
        fixture_manager.tofu_endpoint("https://127.0.0.1:18006/api2/json")
        == "https://host.docker.internal:18006/api2/json"
    )


def test_default_fixture_context_prefers_private_jump_host_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LV3_PROXMOX_HOST_ADDR", "100.64.0.1")

    context = fixture_manager.default_fixture_context()

    assert context["jump_host"] == "100.64.0.1"


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
    (fixture_repo / "receipts" / "fixtures" / "docker-host-20260323T100000Z.json").write_text(
        json.dumps(receipt) + "\n"
    )
    monkeypatch.setattr(fixture_manager, "destroy_fixture", lambda runtime_dir, endpoint, api_token, **kwargs: None)
    monkeypatch.setattr(fixture_manager, "emit_ephemeral_event", lambda *args, **kwargs: None)

    payload = fixture_manager.fixture_down("docker-host")

    assert payload["destroyed"] == [{"receipt_id": "docker-host-20260323T100000Z", "vm_id": 910}]
    assert not (fixture_repo / "receipts" / "fixtures" / "docker-host-20260323T100000Z.json").exists()
    assert (fixture_repo / ".local" / "fixtures" / "archive" / "docker-host-20260323T100000Z.json").exists()


def test_render_fixture_table_handles_empty_rows() -> None:
    assert fixture_manager.render_fixture_table([]) == "No active fixtures"


def test_load_ephemeral_pool_accepts_reservation_backed_preview_burst(
    fixture_repo: Path,
) -> None:
    (fixture_repo / "config" / "capacity-model.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "reservations": [
                    {
                        "id": "ephemeral-pool",
                        "kind": "ephemeral_pool",
                        "status": "reserved",
                        "capacity_class": "preview_burst",
                        "vmid_range": {"start": 910, "end": 979},
                        "max_concurrent_vms": 5,
                        "reserved": {"ram_gb": 20, "vcpu": 8, "disk_gb": 100},
                        "notes": "fixture test pool",
                    }
                ],
            }
        )
        + "\n"
    )

    pool = fixture_manager.load_ephemeral_pool()

    assert pool["capacity_class"] == "preview_burst"
    assert pool["vmid_range"] == [910, 979]
    assert pool["reserved_ram_gb"] == 20


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
            {
                "vmid": 910,
                "tags": "ephemeral-owner-codex;ephemeral-purpose-expired;ephemeral-expires-1",
                "status": "running",
            },
            {
                "vmid": 911,
                "tags": "ephemeral-owner-codex;ephemeral-purpose-active;ephemeral-expires-4088510400",
                "status": "running",
            },
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
    assert "agent_enabled = false" in rendered
    assert 'agent_timeout = "10s"' in rendered
    assert 'value = "10.20.10.100"' in rendered


def test_stage_seed_snapshot_updates_receipt(monkeypatch: pytest.MonkeyPatch) -> None:
    receipt = {
        "receipt_id": "ops-base-20260327T120000Z",
        "seed_class": "tiny",
        "context": {"jump_user": "ops", "jump_host": "203.0.113.1", "ci_user": "ops"},
        "definition": {"ssh_user": "ops"},
        "ip_address": "10.20.10.120",
    }
    monkeypatch.setattr(fixture_manager, "ssh_base_argv", lambda receipt, timeout_seconds=5: ["ssh", "fixture"])
    monkeypatch.setattr(fixture_manager.seed_data_snapshots, "guest_stage_root", lambda: "/var/lib/lv3-seed-data")
    monkeypatch.setattr(
        fixture_manager.seed_data_snapshots,
        "stage_snapshot_to_remote_dir",
        lambda seed_class, ssh_base, remote_dir, snapshot_name=None: {
            "seed_class": seed_class,
            "snapshot_id": snapshot_name or "tiny-abc123",
            "remote_dir": remote_dir,
        },
    )

    staged = fixture_manager.stage_seed_snapshot(receipt)

    assert staged["snapshot_id"] == "tiny-abc123"
    assert receipt["seed_snapshot_remote_dir"] == "/var/lib/lv3-seed-data/ops-base-20260327T120000Z"


def test_tofu_module_source_path_uses_workspace_mount_when_host_tofu_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(fixture_manager.shutil, "which", lambda name: None if name == "tofu" else "/usr/bin/docker")

    assert fixture_manager.tofu_module_source_path() == "./modules/proxmox-fixture"


def test_tofu_command_passes_proxmox_tf_vars_into_docker_container(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fixture_manager.shutil, "which", lambda name: None if name == "tofu" else "/usr/bin/docker")

    command = fixture_manager.tofu_command(
        Path("/tmp/runtime"),
        "apply",
        env={
            "TF_VAR_proxmox_endpoint": "https://100.64.0.1:8006/api2/json",
            "TF_VAR_proxmox_api_token": "token",
        },
    )

    assert "-e" in command
    assert "TF_VAR_proxmox_endpoint=https://100.64.0.1:8006/api2/json" in command
    assert "TF_VAR_proxmox_api_token=token" in command


def test_fixture_list_reads_cluster_ephemeral_metadata(fixture_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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


def test_converge_roles_writes_ansible_vars_into_runtime_playbook(
    fixture_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime_dir = fixture_repo / ".local" / "fixtures" / "runtime" / "docker-host-20260323T100000Z"
    runtime_dir.mkdir(parents=True)
    receipt = {
        "runtime_dir": ".local/fixtures/runtime/docker-host-20260323T100000Z",
        "ip_address": "10.20.10.100",
        "context": {"ci_user": "ops", "jump_user": "ops", "jump_host": "100.64.0.1"},
        "definition": {
            "roles_under_test": ["lv3.platform.docker_runtime"],
            "ansible_vars": {"docker_runtime_container_forward_compat_enabled": False},
        },
    }

    monkeypatch.setattr(
        fixture_manager,
        "run_command",
        lambda argv, cwd=None: fixture_manager.CommandResult(list(argv), 0, "", ""),
    )

    fixture_manager.converge_roles(receipt)

    playbook = json.loads((runtime_dir / "converge.json").read_text())
    assert playbook[0]["vars"] == {"docker_runtime_container_forward_compat_enabled": False}


def test_reaper_retags_untagged_cluster_vms(fixture_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    applied: list[list[str]] = []
    monkeypatch.setattr(
        fixture_manager,
        "fetch_cluster_resources",
        lambda endpoint, api_token: [
            {"vmid": 912, "node": "proxmox-host", "status": "running", "type": "qemu", "tags": ""}
        ],
    )
    monkeypatch.setattr(
        fixture_manager, "apply_cluster_vm_tags", lambda endpoint, api_token, resource, tags: applied.append(tags)
    )

    payload = fixture_manager.reap_expired()

    assert payload["warned_vmids"] == [912]
    assert payload["retagged_vmids"] == [912]
    assert any(tag.startswith("ephemeral-expires-") for tag in applied[0])


def test_bootstrap_public_key_falls_back_to_ssh_keygen_when_pub_file_is_missing(
    fixture_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    public_key = fixture_repo / ".local" / "keys" / "bootstrap.pub"
    public_key.unlink()
    monkeypatch.setattr(
        fixture_manager,
        "run_command",
        lambda argv, **kwargs: fixture_manager.subprocess.CompletedProcess(
            argv,
            0,
            stdout="ssh-ed25519 AAAADERIVED fixture\n",
            stderr="",
        ),
    )

    assert fixture_manager.bootstrap_public_key() == "ssh-ed25519 AAAADERIVED fixture"


def test_proxmox_api_credentials_prefers_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TF_VAR_proxmox_endpoint", "https://100.64.0.1:8006/api2/json")
    monkeypatch.setenv("TF_VAR_proxmox_api_token", "token-value")
    monkeypatch.setattr(fixture_manager.vmid_allocator, "read_api_credentials", lambda **kwargs: ("ignored", "ignored"))

    assert fixture_manager.proxmox_api_credentials() == ("https://100.64.0.1:8006/api2/json", "token-value")


def test_insecure_proxmox_ssl_context_only_for_private_ip_endpoint() -> None:
    assert fixture_manager.insecure_proxmox_ssl_context("https://100.64.0.1:8006/api2/json") is not None
    assert fixture_manager.insecure_proxmox_ssl_context("https://proxmox.example.com:8006/api2/json") is None


def test_select_pool_ip_skips_existing_nonfinal_receipts(fixture_repo: Path) -> None:
    defaults, pools = fixture_manager.load_ephemeral_pool_catalog()
    assert defaults.max_local_active_leases == 3
    pool = pools["docker-host"]
    receipt = {
        "receipt_id": "docker-host-existing",
        "fixture_id": "docker-host",
        "status": "active",
        "created_at": "2026-03-23T10:00:00Z",
        "updated_at": "2026-03-23T10:00:00Z",
        "definition": {"network": {"ip_cidr": "10.20.10.100/24"}},
        "vm_id": 910,
        "pool_id": "docker-host",
    }
    (fixture_repo / "receipts" / "fixtures" / "docker-host-existing.json").write_text(json.dumps(receipt) + "\n")

    assert fixture_manager.select_pool_ip_address(pool) == "10.20.10.101/24"


def test_resolve_template_vmid_falls_back_to_available_source_template(fixture_repo: Path) -> None:
    cluster_resources = [
        {"vmid": 9000, "template": 1},
    ]

    assert fixture_manager.resolve_template_vmid("lv3-ops-base", cluster_resources) == 9000


def test_default_fixture_context_prefers_management_tailscale_jump_host(fixture_repo: Path) -> None:
    assert fixture_manager.default_fixture_context()["jump_host"] == "100.64.0.1"


def test_reconcile_pools_creates_prewarmed_receipts(fixture_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        fixture_manager, "proxmox_api_credentials", lambda: ("https://proxmox.example.invalid:8006/api2/json", "token")
    )
    monkeypatch.setattr(
        fixture_manager,
        "provision_prewarmed_fixture",
        lambda fixture_name, **kwargs: {
            "receipt_id": f"{fixture_name}-warm",
            "vm_id": 910,
            "ip_address": kwargs["definition"]["network"]["ip_cidr"].split("/")[0],
        },
    )

    payload = fixture_manager.reconcile_pools("docker-host")

    assert payload["created"] == [
        {
            "pool_id": "docker-host",
            "receipt_id": "docker-host-warm",
            "vm_id": 910,
            "ip_address": "10.20.10.100",
        }
    ]
    assert payload["status"][0]["pool_id"] == "docker-host"


def test_fixture_up_prefers_prewarmed_member(fixture_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    receipt = {
        "receipt_id": "docker-host-warm",
        "fixture_id": "docker-host",
        "status": "prewarmed",
        "created_at": "2026-03-23T10:00:00Z",
        "updated_at": "2026-03-23T10:00:00Z",
        "lifetime_minutes": 1440,
        "extend_minutes": 0,
        "owner": "pool-manager",
        "purpose": "pool-warm-docker-host",
        "lease_purpose": "fixture",
        "policy": "extended-fixture",
        "expires_epoch": 4088510400,
        "expires_at": "2099-03-23T12:30:00Z",
        "ephemeral_tags": ["ephemeral-owner-pool-manager"],
        "runtime_dir": ".local/fixtures/runtime/docker-host-warm",
        "vm_id": 910,
        "ip_address": "10.20.10.100",
        "mac_address": "BC:24:11:00:03:8E",
        "pool_id": "docker-host",
        "pool_state": "prewarmed",
        "definition": fixture_manager.load_fixture_definition(
            fixture_repo / "tests" / "fixtures" / "docker-host-fixture.yml"
        ),
        "context": fixture_manager.default_fixture_context(),
        "verification": {"ok": True, "checks": [{"ok": True}]},
    }
    (fixture_repo / "receipts" / "fixtures" / "docker-host-warm.json").write_text(json.dumps(receipt) + "\n")
    monkeypatch.setattr(
        fixture_manager, "proxmox_api_credentials", lambda: ("https://proxmox.example.invalid:8006/api2/json", "token")
    )
    monkeypatch.setattr(
        fixture_manager,
        "fetch_cluster_resources",
        lambda endpoint, api_token: [
            {"vmid": 910, "node": "proxmox-host", "status": "stopped", "type": "qemu", "tags": ""}
        ],
    )
    monkeypatch.setattr(fixture_manager, "start_cluster_vm", lambda endpoint, api_token, resource: None)
    monkeypatch.setattr(fixture_manager, "wait_for_ssh", lambda receipt, timeout_seconds=300: None)
    monkeypatch.setattr(
        fixture_manager, "verify_fixture", lambda receipt, definition: {"ok": True, "checks": [{"ok": True}]}
    )
    monkeypatch.setattr(fixture_manager, "capture_ssh_fingerprint", lambda receipt: "fingerprint")
    monkeypatch.setattr(fixture_manager, "apply_cluster_vm_tags", lambda endpoint, api_token, resource, tags: None)
    monkeypatch.setattr(fixture_manager, "emit_ephemeral_event", lambda *args, **kwargs: None)

    payload = fixture_manager.fixture_up("docker-host", purpose="preview-smoke", owner="codex", lease_purpose="preview")

    assert payload["vm_id"] == 910
    assert payload["allocation_mode"] == "warm-handoff"
    assert payload["owner"] == "codex"
    assert payload["lease_purpose"] == "preview"
    assert payload["status"] == "active"


def test_fixture_up_reports_spillover_when_pool_limit_is_reached(
    fixture_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for vmid, ip_cidr in ((910, "10.20.10.100/24"), (911, "10.20.10.101/24")):
        receipt = {
            "receipt_id": f"docker-host-{vmid}",
            "fixture_id": "docker-host",
            "status": "active",
            "created_at": "2026-03-23T10:00:00Z",
            "updated_at": "2026-03-23T10:00:00Z",
            "lifetime_minutes": 60,
            "extend_minutes": 0,
            "owner": "codex",
            "purpose": "busy",
            "lease_purpose": "fixture",
            "policy": "adr-development",
            "expires_epoch": 4088510400,
            "expires_at": "2099-03-23T12:30:00Z",
            "ephemeral_tags": [],
            "runtime_dir": f".local/fixtures/runtime/docker-host-{vmid}",
            "vm_id": vmid,
            "ip_address": ip_cidr.split("/")[0],
            "pool_id": "docker-host",
            "definition": {"network": {"ip_cidr": ip_cidr}},
            "context": {},
        }
        (fixture_repo / "receipts" / "fixtures" / f"docker-host-{vmid}.json").write_text(json.dumps(receipt) + "\n")

    monkeypatch.setattr(
        fixture_manager, "proxmox_api_credentials", lambda: ("https://proxmox.example.invalid:8006/api2/json", "token")
    )

    with pytest.raises(fixture_manager.SpilloverRequiredError) as excinfo:
        fixture_manager.fixture_up("docker-host", purpose="over-limit", owner="codex")

    assert excinfo.value.pool_id == "docker-host"
    assert excinfo.value.spillover_domain == "hetzner-cloud-burst"
