from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import upgrade_container_image as upgrade  # noqa: E402


def test_update_catalog_uses_repo_relative_receipt_path(monkeypatch, tmp_path: Path) -> None:
    shared_root = tmp_path
    worktree_root = shared_root / ".worktrees" / "ws-0368"
    worktree_root.mkdir(parents=True)
    receipt_path = shared_root / "receipts" / "image-scans" / "2026-04-14-redpanda-runtime.json"
    receipt_path.parent.mkdir(parents=True)
    receipt_path.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(upgrade, "IMAGE_CATALOG_PATH", worktree_root / "config" / "image-catalog.json")
    monkeypatch.setattr(upgrade, "relpath", lambda path: str(path.relative_to(shared_root)))

    catalog = {
        "images": {
            "redpanda_runtime": {
                "registry_ref": "docker.redpanda.com/redpandadata/redpanda",
                "tag": "v25.3.11",
                "digest": "sha256:old",
                "ref": "docker.redpanda.com/redpandadata/redpanda:v25.3.11@sha256:old",
                "scan_status": "pass_no_critical",
            }
        }
    }

    updated = upgrade.update_catalog(
        catalog,
        image_id="redpanda_runtime",
        tag="v25.3.11",
        digest="sha256:new",
        scanned_on="2026-04-14",
        receipt_path=receipt_path,
        exception=None,
    )

    assert (
        updated["images"]["redpanda_runtime"]["scan_receipt"] == "receipts/image-scans/2026-04-14-redpanda-runtime.json"
    )
