from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import materialize_live_apply_worktree_artifacts as materializer


def test_materialize_gate_bypass_keep_writes_non_empty_file(tmp_path: Path) -> None:
    target = materializer.materialize_artifact("gate_bypass_keep", repo_root=tmp_path)

    assert target == tmp_path / "receipts" / "gate-bypasses" / ".gitkeep"
    assert target.read_text(encoding="utf-8").strip()
    assert materializer.artifact_ready("gate_bypass_keep", repo_root=tmp_path) is True


def test_materialize_drift_reports_dir_creates_directory(tmp_path: Path) -> None:
    target = materializer.materialize_artifact("drift_reports_dir", repo_root=tmp_path)

    assert target == tmp_path / "receipts" / "drift-reports"
    assert target.is_dir()
    assert materializer.artifact_ready("drift_reports_dir", repo_root=tmp_path) is True


def test_materialize_platform_vars_invokes_make_generate_platform_vars(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[list[str]] = []

    def fake_run_command(argv: list[str], *, repo_root: Path) -> None:
        captured.append(argv)
        (repo_root / "inventory" / "group_vars").mkdir(parents=True, exist_ok=True)
        (repo_root / "inventory" / "group_vars" / "platform.yml").write_text("platform: true\n", encoding="utf-8")

    monkeypatch.setattr(materializer, "run_command", fake_run_command)

    target = materializer.materialize_artifact("platform_vars", repo_root=tmp_path)

    assert captured == [["make", "generate-platform-vars"]]
    assert target.read_text(encoding="utf-8") == "platform: true\n"


def test_materialize_https_tls_targets_invokes_shared_generator(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[list[str]] = []

    def fake_run_command(argv: list[str], *, repo_root: Path) -> None:
        captured.append(argv)
        (repo_root / "config" / "prometheus" / "file_sd").mkdir(parents=True, exist_ok=True)
        (repo_root / "config" / "prometheus" / "rules").mkdir(parents=True, exist_ok=True)
        (repo_root / "config" / "prometheus" / "file_sd" / "https_tls_targets.yml").write_text(
            "targets:\n", encoding="utf-8"
        )
        (repo_root / "config" / "prometheus" / "rules" / "https_tls_alerts.yml").write_text(
            "groups:\n", encoding="utf-8"
        )

    monkeypatch.setattr(materializer, "run_command", fake_run_command)

    materializer.materialize_artifact("https_tls_targets", repo_root=tmp_path)
    materializer.materialize_artifact("https_tls_alerts", repo_root=tmp_path)

    assert captured == [["make", "generate-https-tls-assurance"], ["make", "generate-https-tls-assurance"]]


def test_materialize_uptime_kuma_monitors_invokes_generator(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[list[str]] = []

    def fake_run_command(argv: list[str], *, repo_root: Path) -> None:
        captured.append(argv)
        (repo_root / "config" / "uptime-kuma").mkdir(parents=True, exist_ok=True)
        (repo_root / "config" / "uptime-kuma" / "monitors.json").write_text("[]\n", encoding="utf-8")

    monkeypatch.setattr(materializer, "run_command", fake_run_command)

    materializer.materialize_artifact("uptime_kuma_monitors", repo_root=tmp_path)

    assert captured == [["make", "generate-uptime-kuma-monitors"]]


def test_materialize_image_scan_receipts_prefers_shared_root_for_worktrees(tmp_path: Path) -> None:
    shared_root = tmp_path / "repo"
    repo_root = shared_root / ".worktrees" / "ws-0380"
    source_dir = shared_root / "receipts" / "image-scans"
    source_dir.mkdir(parents=True, exist_ok=True)
    (source_dir / "2026-03-30-example.trivy.json").write_text('{"ok": true}\n', encoding="utf-8")

    target = materializer.materialize_artifact("image_scan_receipts", repo_root=repo_root)

    assert target == repo_root / "receipts" / "image-scans"
    assert (target / "2026-03-30-example.trivy.json").read_text(encoding="utf-8") == '{"ok": true}\n'


def test_live_apply_workflow_catalog_references_generated_artifact_manifest() -> None:
    workflow_catalog = json.loads((REPO_ROOT / "config" / "workflow-catalog.json").read_text(encoding="utf-8"))

    for workflow_id in ("live-apply-group", "live-apply-service", "live-apply-site", "live-apply-waves"):
        manifest_ids = workflow_catalog["workflows"][workflow_id]["preflight"]["bootstrap_manifest_ids"]
        assert manifest_ids == [
            "controller-local-base",
            "live-apply-generated-artifacts",
            "shared-edge-generated-portals",
        ]


def test_live_apply_generated_artifacts_manifest_declares_expected_entries() -> None:
    manifest_catalog = json.loads(
        (REPO_ROOT / "config" / "worktree-bootstrap-manifests.json").read_text(encoding="utf-8")
    )
    generated = manifest_catalog["manifests"]["live-apply-generated-artifacts"]["generated_artifacts"]
    generated_by_id = {entry["id"]: entry for entry in generated}

    assert generated_by_id["platform_vars"]["path"] == "inventory/group_vars/platform.yml"
    assert generated_by_id["gate_bypass_keep"]["path"] == "receipts/gate-bypasses/.gitkeep"
    assert generated_by_id["drift_reports_dir"]["path"] == "receipts/drift-reports"
    assert generated_by_id["https_tls_targets"]["path"] == "config/prometheus/file_sd/https_tls_targets.yml"
    assert generated_by_id["https_tls_alerts"]["path"] == "config/prometheus/rules/https_tls_alerts.yml"
    assert generated_by_id["uptime_kuma_monitors"]["path"] == "config/uptime-kuma/monitors.json"
