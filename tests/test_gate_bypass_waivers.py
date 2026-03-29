from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "gate_bypass_waivers.py"


def load_module(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def test_summary_classifies_legacy_and_governed_receipts(tmp_path: Path) -> None:
    module = load_module("gate_bypass_waivers_summary")
    catalog = {
        "$schema": "docs/schema/gate-bypass-waiver-catalog.schema.json",
        "schema_version": "1.0.0",
        "expiring_soon_days": 2,
        "repeat_after_expiry": {
            "warning_after_occurrences": 1,
            "blocker_after_occurrences": 2,
        },
        "reason_codes": {
            "build_server_unreachable": {
                "summary": "builder unavailable",
                "max_expiry_days": 2,
                "allowed_bypasses": ["skip_remote_gate"],
            }
        },
    }
    receipt_dir = tmp_path / "receipts"
    write(
        receipt_dir / "legacy.json",
        {
            "created_at": "2026-03-29T08:00:00Z",
            "bypass": "skip_remote_gate",
            "source": "manual",
            "branch": "main",
            "commit": "abc1234",
        },
    )
    write(
        receipt_dir / "governed.json",
        {
            "schema_version": "2.0.0",
            "created_at": "2026-03-29T09:00:00Z",
            "bypass": "skip_remote_gate",
            "source": "manual",
            "branch": "main",
            "commit": "def5678",
            "waiver": {
                "reason_code": "build_server_unreachable",
                "reason_summary": "builder unavailable",
                "detail": "first governed receipt",
                "impacted_lanes": ["remote-pre-push-gate"],
                "substitute_evidence": ["make gate-status"],
                "owner": "ops",
                "expires_on": "2026-03-30",
                "remediation_ref": "ws-0267-live-apply",
            },
        },
    )

    summary = module.summarize_receipts(
        directory=receipt_dir,
        catalog=catalog,
        reference_date=module.date(2026, 3, 29),
    )

    assert summary["totals"]["legacy_receipts"] == 1
    assert summary["totals"]["compliant_receipts"] == 1
    assert summary["totals"]["open_waivers"] == 1
    assert summary["open_waivers"][0]["reason_code"] == "build_server_unreachable"


def test_summary_escalates_repeated_reasons_after_expiry(tmp_path: Path) -> None:
    module = load_module("gate_bypass_waivers_escalation")
    catalog = {
        "$schema": "docs/schema/gate-bypass-waiver-catalog.schema.json",
        "schema_version": "1.0.0",
        "expiring_soon_days": 2,
        "repeat_after_expiry": {
            "warning_after_occurrences": 1,
            "blocker_after_occurrences": 2,
        },
        "reason_codes": {
            "build_server_unreachable": {
                "summary": "builder unavailable",
                "max_expiry_days": 2,
                "allowed_bypasses": ["skip_remote_gate"],
            }
        },
    }
    receipt_dir = tmp_path / "receipts"
    for name, created_at, expires_on in (
        ("one.json", "2026-03-29T08:00:00Z", "2026-03-29"),
        ("two.json", "2026-04-02T08:00:00Z", "2026-04-02"),
        ("three.json", "2026-04-05T08:00:00Z", "2026-04-05"),
    ):
        write(
            receipt_dir / name,
            {
                "schema_version": "2.0.0",
                "created_at": created_at,
                "bypass": "skip_remote_gate",
                "source": "manual",
                "branch": "main",
                "commit": name.replace(".json", ""),
                "waiver": {
                    "reason_code": "build_server_unreachable",
                    "reason_summary": "builder unavailable",
                    "detail": name,
                    "impacted_lanes": ["remote-pre-push-gate"],
                    "substitute_evidence": ["make gate-status"],
                    "owner": "ops",
                    "expires_on": expires_on,
                    "remediation_ref": "ws-0267-live-apply",
                },
            },
        )

    summary = module.summarize_receipts(
        directory=receipt_dir,
        catalog=catalog,
        reference_date=module.date(2026, 4, 6),
    )

    assert summary["release_blockers"][0]["reason_code"] == "build_server_unreachable"
    assert summary["release_blockers"][0]["repeat_after_expiry_occurrences"] == 2
