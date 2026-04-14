from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import upgrade_container_image as tool  # noqa: E402


def make_catalog() -> dict:
    digest = "sha256:" + "a" * 64
    return {
        "schema_version": "1.0.0",
        "images": {
            "dozzle_runtime": {
                "kind": "runtime",
                "service_id": "dozzle",
                "registry_ref": "docker.io/amir20/dozzle",
                "tag": "v8.13.7",
                "digest": digest,
                "ref": f"docker.io/amir20/dozzle:v8.13.7@{digest}",
                "platform": "linux/amd64",
                "pinned_on": "2026-03-25",
                "scan_status": "pass_no_critical",
                "scan_receipt": "receipts/image-scans/2026-03-25-dozzle-runtime.json",
                "consumers": ["docs/runbooks/dozzle.md"],
                "apply_targets": ["converge-dozzle"],
            }
        },
    }


def make_exception_catalog(*, legacy_exception: bool = False) -> dict:
    catalog = make_catalog()
    if legacy_exception:
        catalog["images"]["dozzle_runtime"]["scan_status"] = "exception_open"
        catalog["images"]["dozzle_runtime"]["exception"] = {
            "owner": "Platform operations",
            "reason": "The pinned digest still reports critical findings.",
            "approved_on": "2026-03-30",
            "review_by": "2026-04-13",
        }
    else:
        catalog["images"]["dozzle_runtime"]["scan_status"] = "exception_open"
        catalog["images"]["dozzle_runtime"]["exception"] = {
            "owner": "Platform operations",
            "justification": "The pinned digest still reports critical findings.",
            "compensating_controls": ["Digest pin prevents surprise drift."],
            "approved_on": "2026-03-30",
            "expires_on": "2026-04-13",
            "remediation_plan": "Refresh during the next image review window.",
        }
    return catalog


def test_update_catalog_refresh_scan_only_preserves_pin_fields(monkeypatch, tmp_path: Path) -> None:
    catalog = make_catalog()
    original = dict(catalog["images"]["dozzle_runtime"])

    monkeypatch.setattr(tool, "IMAGE_CATALOG_PATH", tmp_path / "config" / "image-catalog.json")
    receipt_path = tmp_path / "receipts" / "image-scans" / "2026-04-14-dozzle-runtime.json"
    receipt_path.parent.mkdir(parents=True, exist_ok=True)

    updated = tool.update_catalog(
        catalog,
        image_id="dozzle_runtime",
        tag="v9.0.0",
        digest="sha256:" + "b" * 64,
        scanned_on="2026-04-14",
        receipt_path=receipt_path,
        exception=None,
        preserve_pin=True,
    )

    entry = updated["images"]["dozzle_runtime"]
    assert entry["tag"] == original["tag"]
    assert entry["digest"] == original["digest"]
    assert entry["ref"] == original["ref"]
    assert entry["pinned_on"] == original["pinned_on"]
    assert entry["scan_receipt"] == "receipts/image-scans/2026-04-14-dozzle-runtime.json"
    assert entry["scan_status"] == "pass_no_critical"


def test_update_catalog_uses_shared_repo_root_for_shared_receipts(monkeypatch, tmp_path: Path) -> None:
    catalog = make_catalog()
    worktree_root = tmp_path / ".worktrees" / "ws-0370-live-apply"
    shared_root = tmp_path

    monkeypatch.setattr(tool, "IMAGE_CATALOG_PATH", worktree_root / "config" / "image-catalog.json")
    monkeypatch.setattr(tool, "shared_repo_root", lambda root: shared_root)

    receipt_path = shared_root / "receipts" / "image-scans" / "2026-04-14-dozzle-runtime.json"
    receipt_path.parent.mkdir(parents=True, exist_ok=True)

    updated = tool.update_catalog(
        catalog,
        image_id="dozzle_runtime",
        tag="v8.13.7",
        digest=catalog["images"]["dozzle_runtime"]["digest"],
        scanned_on="2026-04-14",
        receipt_path=receipt_path,
        exception=None,
        preserve_pin=True,
    )

    assert updated["images"]["dozzle_runtime"]["scan_receipt"] == "receipts/image-scans/2026-04-14-dozzle-runtime.json"


def test_main_refresh_scan_only_reuses_current_pin(monkeypatch, tmp_path: Path, capsys) -> None:
    catalog = make_catalog()
    image_catalog_path = tmp_path / "config" / "image-catalog.json"
    image_catalog_path.parent.mkdir(parents=True, exist_ok=True)
    image_catalog_path.write_text(json.dumps(catalog), encoding="utf-8")

    receipts_dir = tmp_path / "receipts"
    image_scan_dir = receipts_dir / "image-scans"
    sbom_dir = receipts_dir / "sbom"
    cve_dir = receipts_dir / "cve"
    image_scan_dir.mkdir(parents=True, exist_ok=True)
    sbom_dir.mkdir(parents=True, exist_ok=True)
    cve_dir.mkdir(parents=True, exist_ok=True)

    written: list[tuple[Path, dict]] = []

    monkeypatch.setattr(tool, "IMAGE_CATALOG_PATH", image_catalog_path)
    monkeypatch.setattr(tool, "IMAGE_SCAN_RECEIPTS_DIR", image_scan_dir)
    monkeypatch.setattr(tool, "SBOM_RECEIPTS_DIR", sbom_dir)
    monkeypatch.setattr(tool, "CVE_RECEIPTS_DIR", cve_dir)
    monkeypatch.setattr(tool, "relpath", lambda path: str(path.relative_to(tmp_path)))
    monkeypatch.setattr(tool, "load_image_catalog", lambda: json.loads(image_catalog_path.read_text(encoding="utf-8")))
    monkeypatch.setattr(tool, "validate_image_catalog", lambda payload: payload)
    monkeypatch.setattr(
        tool,
        "load_scanner_config",
        lambda: {
            "grype": {"container_image": "grype:latest"},
            "syft": {"container_image": "syft:latest"},
        },
    )
    monkeypatch.setattr(tool, "now_utc", lambda: dt.datetime(2026, 4, 14, 12, 0, tzinfo=dt.timezone.utc))
    monkeypatch.setattr(
        tool,
        "scan_catalog_image",
        lambda **kwargs: (
            sbom_dir / "dozzle.spdx.json",
            cve_dir / "dozzle.cve.json",
            {
                "summary": {
                    "critical": 0,
                    "high": 0,
                    "blocking_findings_with_fix": 0,
                }
            },
        ),
    )

    def fake_write_json(path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        written.append((path, payload))

    monkeypatch.setattr(tool, "write_json", fake_write_json)

    def fail_resolve(*args, **kwargs):
        raise AssertionError("resolve_remote_digest should not be called during --refresh-scan-only")

    monkeypatch.setattr(tool, "resolve_remote_digest", fail_resolve)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "upgrade_container_image.py",
            "--image-id",
            "dozzle_runtime",
            "--write",
            "--refresh-scan-only",
        ],
    )

    assert tool.main() == 0

    updated_catalog = json.loads(image_catalog_path.read_text(encoding="utf-8"))
    entry = updated_catalog["images"]["dozzle_runtime"]
    assert entry["tag"] == catalog["images"]["dozzle_runtime"]["tag"]
    assert entry["digest"] == catalog["images"]["dozzle_runtime"]["digest"]
    assert entry["ref"] == catalog["images"]["dozzle_runtime"]["ref"]
    assert entry["pinned_on"] == catalog["images"]["dozzle_runtime"]["pinned_on"]
    assert entry["scan_receipt"] == "receipts/image-scans/2026-04-14-dozzle-runtime.json"

    stdout = capsys.readouterr().out
    result = json.loads(stdout)
    assert result["refresh_scan_only"] is True
    assert result["image_ref"] == catalog["images"]["dozzle_runtime"]["ref"]
    assert [path.name for path, _ in written] == [
        "2026-04-14-dozzle-runtime.json",
        "image-catalog.json",
    ]


def test_main_rejects_tag_with_refresh_scan_only(monkeypatch) -> None:
    captured: dict[str, str] = {}

    def fake_emit_cli_error(label: str, exc: Exception) -> int:
        captured["label"] = label
        captured["error"] = str(exc)
        return 1

    monkeypatch.setattr(tool, "emit_cli_error", fake_emit_cli_error)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "upgrade_container_image.py",
            "--image-id",
            "dozzle_runtime",
            "--tag",
            "latest",
            "--refresh-scan-only",
        ],
    )

    assert tool.main() == 1
    assert captured == {
        "label": "Upgrade container image",
        "error": "--tag cannot be combined with --refresh-scan-only",
    }


def test_main_refresh_scan_only_preserves_existing_legacy_exception(monkeypatch, tmp_path: Path, capsys) -> None:
    catalog = make_exception_catalog(legacy_exception=True)
    image_catalog_path = tmp_path / "config" / "image-catalog.json"
    image_catalog_path.parent.mkdir(parents=True, exist_ok=True)
    image_catalog_path.write_text(json.dumps(catalog), encoding="utf-8")

    receipts_dir = tmp_path / "receipts"
    image_scan_dir = receipts_dir / "image-scans"
    sbom_dir = receipts_dir / "sbom"
    cve_dir = receipts_dir / "cve"
    image_scan_dir.mkdir(parents=True, exist_ok=True)
    sbom_dir.mkdir(parents=True, exist_ok=True)
    cve_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(tool, "IMAGE_CATALOG_PATH", image_catalog_path)
    monkeypatch.setattr(tool, "IMAGE_SCAN_RECEIPTS_DIR", image_scan_dir)
    monkeypatch.setattr(tool, "SBOM_RECEIPTS_DIR", sbom_dir)
    monkeypatch.setattr(tool, "CVE_RECEIPTS_DIR", cve_dir)
    monkeypatch.setattr(tool, "shared_repo_root", lambda root: tmp_path)
    monkeypatch.setattr(tool, "relpath", lambda path: str(path.relative_to(tmp_path)))
    monkeypatch.setattr(tool, "load_image_catalog", lambda: json.loads(image_catalog_path.read_text(encoding="utf-8")))
    monkeypatch.setattr(tool, "validate_image_catalog", lambda payload: payload)
    monkeypatch.setattr(
        tool,
        "load_scanner_config",
        lambda: {
            "grype": {"container_image": "grype:latest"},
            "syft": {"container_image": "syft:latest"},
        },
    )
    monkeypatch.setattr(tool, "now_utc", lambda: dt.datetime(2026, 4, 14, 12, 0, tzinfo=dt.timezone.utc))
    monkeypatch.setattr(
        tool,
        "scan_catalog_image",
        lambda **kwargs: (
            sbom_dir / "dozzle.spdx.json",
            cve_dir / "dozzle.cve.json",
            {
                "summary": {
                    "critical": 1,
                    "high": 2,
                    "blocking_findings_with_fix": 0,
                }
            },
        ),
    )
    monkeypatch.setattr(
        tool, "write_json", lambda path, payload: path.write_text(json.dumps(payload), encoding="utf-8")
    )
    monkeypatch.setattr(tool, "resolve_remote_digest", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError()))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "upgrade_container_image.py",
            "--image-id",
            "dozzle_runtime",
            "--write",
            "--refresh-scan-only",
        ],
    )

    assert tool.main() == 0

    updated_catalog = json.loads(image_catalog_path.read_text(encoding="utf-8"))
    exception = updated_catalog["images"]["dozzle_runtime"]["exception"]
    assert exception == catalog["images"]["dozzle_runtime"]["exception"]
    assert json.loads(capsys.readouterr().out)["exception"] == exception


def test_main_refresh_scan_only_can_renew_existing_exception_window(monkeypatch, tmp_path: Path, capsys) -> None:
    catalog = make_exception_catalog()
    image_catalog_path = tmp_path / "config" / "image-catalog.json"
    image_catalog_path.parent.mkdir(parents=True, exist_ok=True)
    image_catalog_path.write_text(json.dumps(catalog), encoding="utf-8")

    receipts_dir = tmp_path / "receipts"
    image_scan_dir = receipts_dir / "image-scans"
    sbom_dir = receipts_dir / "sbom"
    cve_dir = receipts_dir / "cve"
    image_scan_dir.mkdir(parents=True, exist_ok=True)
    sbom_dir.mkdir(parents=True, exist_ok=True)
    cve_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(tool, "IMAGE_CATALOG_PATH", image_catalog_path)
    monkeypatch.setattr(tool, "IMAGE_SCAN_RECEIPTS_DIR", image_scan_dir)
    monkeypatch.setattr(tool, "SBOM_RECEIPTS_DIR", sbom_dir)
    monkeypatch.setattr(tool, "CVE_RECEIPTS_DIR", cve_dir)
    monkeypatch.setattr(tool, "shared_repo_root", lambda root: tmp_path)
    monkeypatch.setattr(tool, "relpath", lambda path: str(path.relative_to(tmp_path)))
    monkeypatch.setattr(tool, "load_image_catalog", lambda: json.loads(image_catalog_path.read_text(encoding="utf-8")))
    monkeypatch.setattr(tool, "validate_image_catalog", lambda payload: payload)
    monkeypatch.setattr(
        tool,
        "load_scanner_config",
        lambda: {
            "grype": {"container_image": "grype:latest"},
            "syft": {"container_image": "syft:latest"},
        },
    )
    monkeypatch.setattr(tool, "now_utc", lambda: dt.datetime(2026, 4, 14, 12, 0, tzinfo=dt.timezone.utc))
    monkeypatch.setattr(
        tool,
        "scan_catalog_image",
        lambda **kwargs: (
            sbom_dir / "dozzle.spdx.json",
            cve_dir / "dozzle.cve.json",
            {
                "summary": {
                    "critical": 1,
                    "high": 2,
                    "blocking_findings_with_fix": 0,
                }
            },
        ),
    )
    monkeypatch.setattr(
        tool, "write_json", lambda path, payload: path.write_text(json.dumps(payload), encoding="utf-8")
    )
    monkeypatch.setattr(tool, "resolve_remote_digest", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError()))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "upgrade_container_image.py",
            "--image-id",
            "dozzle_runtime",
            "--write",
            "--refresh-scan-only",
            "--renew-existing-exception",
        ],
    )

    assert tool.main() == 0

    updated_catalog = json.loads(image_catalog_path.read_text(encoding="utf-8"))
    exception = updated_catalog["images"]["dozzle_runtime"]["exception"]
    assert exception["approved_on"] == "2026-04-14"
    assert exception["expires_on"] == "2026-04-28"
    assert json.loads(capsys.readouterr().out)["exception"] == exception
