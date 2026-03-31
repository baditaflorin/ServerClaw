from __future__ import annotations

import json
from pathlib import Path

from disaster_recovery_runbook import build_runbook_plan, render_text
from generate_dr_report import build_dr_report, render_dr_report, render_release_status


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_build_dr_report_falls_back_to_control_plane_restore_drill(tmp_path: Path) -> None:
    targets = tmp_path / "config" / "disaster-recovery-targets.json"
    stack = tmp_path / "versions" / "stack.yaml"
    adr_dir = tmp_path / "docs" / "adr"
    table_top_dir = tmp_path / "receipts" / "dr-table-top-reviews"
    restore_dir = tmp_path / "receipts" / "restore-verifications"
    backup_coverage_dir = tmp_path / "receipts" / "backup-coverage"

    write(
        targets,
        json.dumps(
            {
                "schema_version": "1.0.0",
                "platform_target": {"rto_minutes": 240, "rpo_hours": 24},
                "review_policy": {"table_top_interval_days": 90, "live_drill_interval_days": 365},
                "offsite_backup": {"strategy": "vm160", "storage_id": "lv3-backup-offsite"},
                "scenarios": [
                    {"id": "host", "name": "Host loss", "rto_minutes": 240, "rpo_hours": 24, "notes": "restore vm160"}
                ],
            }
        ),
    )
    write(
        stack,
        """
repo_version: 0.96.0
platform_version: 0.40.0
backups:
  control_plane_recovery:
    latest_restore_drill:
      checked_at: 2026-03-23T08:00:00Z
      result: pass
""".strip()
        + "\n",
    )
    write(adr_dir / "0093-interactive-ops-portal.md", "- Status: Proposed\n- Implementation Status: Not Implemented\n")
    write(adr_dir / "0094-developer-portal.md", "- Status: Proposed\n- Implementation Status: Implemented\n")
    write(adr_dir / "0109-public-status-page.md", "- Status: Proposed\n- Implementation Status: Not Implemented\n")
    write(
        table_top_dir / "2026-03-23-review.json",
        json.dumps({"reviewed_on": "2026-03-23", "result": "completed_with_gaps"}) + "\n",
    )
    write(
        backup_coverage_dir / "20260329T010203Z.json",
        json.dumps(
            {
                "generated_at": "2026-03-29T01:02:03Z",
                "summary": {
                    "governed_assets": 2,
                    "protected": 1,
                    "degraded": 0,
                    "uncovered": 1,
                    "degraded_assets": [],
                    "uncovered_assets": ["backup-lv3"],
                },
            }
        )
        + "\n",
    )
    restore_dir.mkdir(parents=True)

    report = build_dr_report(
        targets_path=targets,
        stack_path=stack,
        table_top_dir=table_top_dir,
        restore_dir=restore_dir,
        backup_coverage_dir=backup_coverage_dir,
        adr_dir=adr_dir,
    )

    assert report["restore_evidence"]["source"] == "control_plane_restore_drill"
    assert report["backup_coverage"]["summary"]["uncovered_assets"] == ["backup-lv3"]
    assert report["offsite_backup"]["configured"] is False
    assert report["overall_status"] == "degraded"
    assert "Host loss" in render_dr_report(report)
    assert "backup-lv3" in render_dr_report(report)
    assert "Docs site (ADR 0094): complete" in render_release_status(report)


def test_runbook_plan_restores_backup_vm_first(tmp_path: Path) -> None:
    repo_root = tmp_path
    write(
        repo_root / "config" / "disaster-recovery-targets.json",
        json.dumps(
            {
                "schema_version": "1.0.0",
                "platform_target": {"rto_minutes": 240, "rpo_hours": 24},
                "review_policy": {"table_top_interval_days": 90, "live_drill_interval_days": 365},
                "offsite_backup": {"strategy": "vm160", "storage_id": "lv3-backup-offsite"},
                "scenarios": [],
            }
        ),
    )

    plan = build_runbook_plan(repo_root=repo_root)
    tier_1 = next(tier for tier in plan["tiers"] if tier["id"] == "tier_1")
    assert "lv3-backup-offsite" in tier_1["steps"][0]["command"]
    assert "qmrestore" in tier_1["steps"][1]["command"]
    assert "Restore backup-lv3 from off-site storage" in render_text(plan)
