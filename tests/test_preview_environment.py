from __future__ import annotations

import json
from pathlib import Path

import preview_environment


def test_validate_profile_catalog_accepts_repo_catalog() -> None:
    payload = preview_environment.load_profile_catalog(preview_environment.PROFILE_CATALOG_PATH)
    preview_environment.validate_profile_catalog(payload)


def test_allocate_preview_ips_skips_active_reservations(tmp_path: Path, monkeypatch) -> None:
    catalog = {
        "network_pool": {
            "ip_range": ["10.20.10.130", "10.20.10.132"],
        }
    }
    active_dir = tmp_path / "active"
    active_dir.mkdir()
    (active_dir / "example.json").write_text(
        json.dumps(
            {
                "preview_id": "active-preview",
                "members": [{"ip_address": "10.20.10.130"}],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(preview_environment, "ACTIVE_STATE_DIR", active_dir)

    assert preview_environment.allocate_preview_ips(catalog, 2) == ["10.20.10.131", "10.20.10.132"]


def test_preview_slug_truncates_and_stabilizes() -> None:
    branch = "codex/" + ("very-long-branch-name-" * 6)
    slug = preview_environment.preview_slug(workstream="ws-0185-live-apply", branch=branch)

    assert slug.startswith("ws-0185-live-apply")
    assert len(slug) <= 48


def test_build_member_definition_copies_ansible_vars() -> None:
    definition = preview_environment.build_member_definition(
        preview_id="preview-123",
        slug="ws-0185-live-apply",
        profile_id="runtime-smoke",
        member={
            "id": "runtime",
            "template": "lv3-debian-base",
            "resources": {"cores": 2, "memory_mb": 4096, "disk_gb": 32},
            "roles_under_test": ["lv3.platform.docker_runtime"],
            "ansible_vars": {"docker_runtime_container_forward_compat_enabled": False},
        },
        ip_address="10.20.10.130",
        catalog={"network_pool": {"bridge": "vmbr20", "gateway": "10.20.10.1", "cidr": 24}},
        ttl_hours=1,
    )

    assert definition["ansible_vars"] == {"docker_runtime_container_forward_compat_enabled": False}


def test_finalize_preview_evidence_writes_live_apply_receipt(tmp_path: Path, monkeypatch) -> None:
    evidence_dir = tmp_path / "receipts" / "preview-environments"
    live_receipts_dir = tmp_path / "receipts" / "live-applies" / "preview"
    evidence_dir.mkdir(parents=True)
    live_receipts_dir.mkdir(parents=True)
    monkeypatch.setattr(preview_environment, "EVIDENCE_DIR", evidence_dir)
    monkeypatch.setattr(preview_environment, "LIVE_RECEIPTS_DIR", live_receipts_dir)
    monkeypatch.setattr(preview_environment, "current_commit", lambda: "c4db21b414c44e5bcd9d6c1fe5ae4fdd9e5cac99")
    monkeypatch.setattr(preview_environment, "repo_version", lambda: "0.177.12")
    monkeypatch.setattr(preview_environment, "DEFAULT_RECORDED_BY", "codex")

    state = {
        "preview_id": "2026-03-27-adr-0185-ws-0185-live-apply-preview-live-apply",
        "status": "destroyed",
        "preview_domain": "ws-0185-live-apply.preview.example.com",
        "branch": "codex/ws-0185-live-apply",
        "workstream": "ws-0185-live-apply",
        "profile_id": "runtime-smoke",
        "service_subset": ["docker_runtime"],
        "network_boundary": {"bridge": "vmbr20"},
        "members": [
            {
                "name": "preview-runtime",
                "member_id": "runtime",
                "vm_id": 930,
                "ip_address": "10.20.10.130",
            }
        ],
        "validation": {
            "smoke": {"ok": True, "results": [{"ok": True}]},
            "synthetic": {"ok": True, "results": [{"ok": True}, {"ok": True}]},
        },
        "destroyed_at": "2026-03-27T10:00:00Z",
    }

    evidence_path, live_receipt_path = preview_environment.finalize_preview_evidence(state)

    assert evidence_path.exists()
    assert live_receipt_path.exists()
    receipt = json.loads(live_receipt_path.read_text(encoding="utf-8"))
    assert receipt["environment"] == "preview"
    assert receipt["workflow_id"] == preview_environment.WORKFLOW_ID
    assert receipt["targets"][1]["vmid"] == 930
