#!/usr/bin/env python3
"""Summarize LV3 disaster-recovery readiness from repo-managed targets and evidence."""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any

from controller_automation_toolkit import REPO_ROOT, load_json, load_yaml, repo_path


DEFAULT_TARGETS_PATH = repo_path("config", "disaster-recovery-targets.json")
DEFAULT_STACK_PATH = repo_path("versions", "stack.yaml")
DEFAULT_TABLE_TOP_DIR = repo_path("receipts", "dr-table-top-reviews")
DEFAULT_RESTORE_DIR = repo_path("receipts", "restore-verifications")
DEFAULT_WITNESS_DIR = repo_path("receipts", "witness-replication")
DEFAULT_ADR_DIR = repo_path("docs", "adr")
UTC = dt.timezone.utc


def _parse_datetime(value: str) -> dt.datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = dt.datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _parse_date(value: str) -> dt.date:
    return dt.date.fromisoformat(value)


def _latest_json_receipt(directory: Path) -> tuple[Path, dict[str, Any]] | None:
    if not directory.is_dir():
        return None
    receipts = sorted(path for path in directory.glob("*.json") if path.is_file())
    if not receipts:
        return None
    latest = receipts[-1]
    return latest, json.loads(latest.read_text(encoding="utf-8"))


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def load_targets(path: Path = DEFAULT_TARGETS_PATH) -> dict[str, Any]:
    return load_json(path)


def load_stack(path: Path = DEFAULT_STACK_PATH) -> dict[str, Any]:
    return load_yaml(path)


def _load_restore_evidence(stack: dict[str, Any], restore_dir: Path) -> dict[str, Any]:
    latest_receipt = _latest_json_receipt(restore_dir)
    if latest_receipt is not None:
        path, payload = latest_receipt
        checked_at = str(payload.get("recorded_at") or payload.get("recorded_on") or "unknown")
        result = str(payload.get("overall") or payload.get("result") or "unknown")
        return {
            "source": "restore_verification_receipt",
            "status": "pass" if result in {"pass", "passed", "ok"} else result,
            "checked_at": checked_at,
            "path": _display_path(path),
        }

    observed_state = stack.get("observed_state", {}) if isinstance(stack, dict) else {}
    backups = observed_state.get("backups", stack.get("backups", {})) if isinstance(observed_state, dict) else {}
    control_plane = backups.get("control_plane_recovery", {}).get("latest_restore_drill", {}) if isinstance(backups, dict) else {}
    checked_at = control_plane.get("checked_at")
    result = control_plane.get("result")
    if isinstance(checked_at, dt.datetime):
        checked_at = checked_at.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    elif isinstance(checked_at, dt.date):
        checked_at = dt.datetime.combine(checked_at, dt.time.min, tzinfo=UTC).isoformat().replace("+00:00", "Z")
    if isinstance(checked_at, str) and isinstance(result, str):
        return {
            "source": "control_plane_restore_drill",
            "status": result,
            "checked_at": checked_at,
            "path": "versions/stack.yaml",
        }

    return {
        "source": "missing",
        "status": "missing",
        "checked_at": "not recorded",
        "path": "",
    }


def _load_table_top_review(table_top_dir: Path) -> dict[str, Any]:
    latest_receipt = _latest_json_receipt(table_top_dir)
    if latest_receipt is None:
        return {
            "status": "missing",
            "reviewed_on": "not recorded",
            "path": "",
            "result": "missing",
        }
    path, payload = latest_receipt
    reviewed_on = str(payload.get("reviewed_on") or "unknown")
    result = str(payload.get("result") or "unknown")
    return {
        "status": "complete",
        "reviewed_on": reviewed_on,
        "path": _display_path(path),
        "result": result,
    }


def _load_offsite_status(targets: dict[str, Any], stack: dict[str, Any]) -> dict[str, Any]:
    configured = False
    last_success = "not recorded"
    storage_id = ""

    observed_state = stack.get("observed_state", {}) if isinstance(stack, dict) else {}
    backups = observed_state.get("backups", stack.get("backups", {})) if isinstance(observed_state, dict) else {}
    if isinstance(backups, dict):
        offsite = backups.get("offsite_backup", {})
        if isinstance(offsite, dict):
            configured = bool(offsite.get("configured", False))
            last_success = str(offsite.get("last_success") or offsite.get("latest_run") or last_success)
            storage_id = str(offsite.get("storage_id") or "")

    configured_targets = targets.get("offsite_backup", {})
    if isinstance(configured_targets, dict) and not storage_id:
        storage_id = str(configured_targets.get("storage_id") or "")

    return {
        "configured": configured,
        "last_success": last_success,
        "storage_id": storage_id or "not declared",
        "strategy": str(configured_targets.get("strategy") or "unknown"),
    }


def _load_witness_status(witness_dir: Path) -> dict[str, Any]:
    latest_receipt = _latest_json_receipt(witness_dir)
    if latest_receipt is None:
        return {
            "configured": False,
            "status": "missing",
            "checked_at": "not recorded",
            "path": "",
            "detail": "no witness replication receipt recorded",
        }
    path, payload = latest_receipt
    targets = payload.get("targets", {}) if isinstance(payload, dict) else {}
    git_target = targets.get("git_remote", {}) if isinstance(targets, dict) else {}
    archive_target = targets.get("archive", {}) if isinstance(targets, dict) else {}
    healthy = git_target.get("status") == "pass" and archive_target.get("status") == "pass"
    checked_at = str(payload.get("recorded_at") or "unknown")
    return {
        "configured": healthy,
        "status": "pass" if healthy else "warn",
        "checked_at": checked_at,
        "path": _display_path(path),
        "detail": f"git={git_target.get('status', 'unknown')} archive={archive_target.get('status', 'unknown')}",
    }


def _collect_adr_metadata(adr_dir: Path) -> dict[str, dict[str, str]]:
    metadata: dict[str, dict[str, str]] = {}
    for path in sorted(adr_dir.glob("*.md")):
        adr_number = path.name.split("-", 1)[0]
        status = ""
        implementation_status = ""
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("- Status: "):
                status = line.removeprefix("- Status: ").strip()
            if line.startswith("- Implementation Status: "):
                implementation_status = line.removeprefix("- Implementation Status: ").strip()
            if status and implementation_status:
                break
        metadata[adr_number] = {
            "status": status or "unknown",
            "implementation_status": implementation_status or "unknown",
        }
    return metadata


def build_dr_report(
    *,
    targets_path: Path = DEFAULT_TARGETS_PATH,
    stack_path: Path = DEFAULT_STACK_PATH,
    table_top_dir: Path = DEFAULT_TABLE_TOP_DIR,
    restore_dir: Path = DEFAULT_RESTORE_DIR,
    witness_dir: Path = DEFAULT_WITNESS_DIR,
    adr_dir: Path = DEFAULT_ADR_DIR,
    today: dt.date | None = None,
) -> dict[str, Any]:
    targets = load_targets(targets_path)
    stack = load_stack(stack_path)
    today = today or dt.datetime.now(UTC).date()

    restore_evidence = _load_restore_evidence(stack, restore_dir)
    table_top_review = _load_table_top_review(table_top_dir)
    offsite_backup = _load_offsite_status(targets, stack)
    witness_status = _load_witness_status(witness_dir)
    review_policy = targets.get("review_policy", {})
    table_top_interval_days = int(review_policy.get("table_top_interval_days", 90))

    table_top_recent = False
    if table_top_review["status"] == "complete":
        try:
            reviewed_on = _parse_date(table_top_review["reviewed_on"])
            table_top_recent = (today - reviewed_on).days <= table_top_interval_days
        except ValueError:
            table_top_recent = False

    restore_recent = False
    if restore_evidence["status"] in {"pass", "passed"}:
        try:
            checked_at = _parse_datetime(restore_evidence["checked_at"])
            restore_recent = (dt.datetime.combine(today, dt.time.min, tzinfo=UTC) - checked_at).days <= 30
        except ValueError:
            restore_recent = False

    witness_recent = False
    if witness_status["status"] == "pass":
        try:
            checked_at = _parse_datetime(witness_status["checked_at"])
            witness_recent = (dt.datetime.combine(today, dt.time.min, tzinfo=UTC) - checked_at).days <= 30
        except ValueError:
            witness_recent = False

    checks = [
        {
            "id": "platform_target",
            "label": "Platform target",
            "status": "pass",
            "detail": (
                f"RTO < {targets['platform_target']['rto_minutes'] // 60}h, "
                f"RPO < {targets['platform_target']['rpo_hours']}h"
            ),
        },
        {
            "id": "restore_verification",
            "label": "Restore verification",
            "status": "pass" if restore_recent else "warn",
            "detail": f"{restore_evidence['status']} via {restore_evidence['source']} at {restore_evidence['checked_at']}",
        },
        {
            "id": "offsite_backup",
            "label": "Off-site backup",
            "status": "pass" if offsite_backup["configured"] else "warn",
            "detail": (
                f"{offsite_backup['strategy']} on {offsite_backup['storage_id']}; "
                f"last success {offsite_backup['last_success']}"
            ),
        },
        {
            "id": "off_host_witness",
            "label": "Off-host witness",
            "status": "pass" if witness_recent else "warn",
            "detail": f"{witness_status['detail']} at {witness_status['checked_at']}",
        },
        {
            "id": "table_top_review",
            "label": "Table-top review",
            "status": "pass" if table_top_recent else "warn",
            "detail": (
                f"{table_top_review['result']} on {table_top_review['reviewed_on']}"
                if table_top_review["status"] == "complete"
                else "no recorded receipt"
            ),
        },
    ]
    overall_status = "pass" if all(check["status"] == "pass" for check in checks) else "degraded"

    adrs = _collect_adr_metadata(adr_dir)
    implemented_count = sum(1 for payload in adrs.values() if payload["implementation_status"] == "Implemented")

    return {
        "targets": targets,
        "stack_path": _display_path(stack_path),
        "restore_evidence": restore_evidence,
        "table_top_review": table_top_review,
        "offsite_backup": offsite_backup,
        "witness_status": witness_status,
        "checks": checks,
        "overall_status": overall_status,
        "adr_summary": {
            "implemented": implemented_count,
            "total": len(adrs),
        },
        "adrs": adrs,
    }


def render_dr_report(report: dict[str, Any]) -> str:
    platform_target = report["targets"]["platform_target"]
    lines = [
        "LV3 disaster recovery readiness",
        f"Platform target: RTO < {platform_target['rto_minutes'] // 60}h, RPO < {platform_target['rpo_hours']}h",
        "",
        "SCENARIO                              RTO       RPO       NOTES",
    ]
    for scenario in report["targets"]["scenarios"]:
        rto = f"{scenario['rto_minutes']}m" if "rto_minutes" in scenario else "n/a"
        rpo = (
            f"{scenario['rpo_hours']}h"
            if "rpo_hours" in scenario
            else f"{scenario['rpo_minutes']}m"
            if "rpo_minutes" in scenario
            else str(scenario.get("rpo", "n/a"))
        )
        lines.append(f"{scenario['name']:<36} {rto:<8} {rpo:<9} {scenario['notes']}")

    lines.extend(["", "CHECK                              STATUS   DETAIL"])
    for check in report["checks"]:
        lines.append(f"{check['label']:<34} {check['status']:<7} {check['detail']}")
    lines.append("")
    lines.append(f"Overall readiness: {report['overall_status']}")
    return "\n".join(lines)


def render_release_status(report: dict[str, Any]) -> str:
    adrs = report["adrs"]

    def adr_ready(adr_number: str) -> str:
        payload = adrs.get(adr_number, {})
        implementation_status = payload.get("implementation_status", "unknown")
        return "complete" if implementation_status == "Implemented" else "pending"

    lines = [
        "Platform 1.0.0 readiness:",
        f"  ADR implementation coverage: {report['adr_summary']['implemented']}/{report['adr_summary']['total']} implemented",
        (
            "  Backup restore evidence: "
            f"{report['restore_evidence']['status']} ({report['restore_evidence']['source']} at {report['restore_evidence']['checked_at']})"
        ),
        f"  Ops portal (ADR 0093): {adr_ready('0093')}",
        f"  Status page (ADR 0109): {adr_ready('0109')}",
        f"  Docs site (ADR 0094): {adr_ready('0094')}",
    ]
    table_top = report["table_top_review"]
    if table_top["status"] == "complete":
        lines.append(f"  DR table-top review: complete ({table_top['reviewed_on']}, {table_top['result']})")
    else:
        lines.append("  DR table-top review: pending")
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Show LV3 disaster-recovery readiness.")
    parser.add_argument("--targets", type=Path, default=DEFAULT_TARGETS_PATH)
    parser.add_argument("--stack", type=Path, default=DEFAULT_STACK_PATH)
    parser.add_argument("--table-top-dir", type=Path, default=DEFAULT_TABLE_TOP_DIR)
    parser.add_argument("--restore-dir", type=Path, default=DEFAULT_RESTORE_DIR)
    parser.add_argument("--witness-dir", type=Path, default=DEFAULT_WITNESS_DIR)
    parser.add_argument("--adr-dir", type=Path, default=DEFAULT_ADR_DIR)
    parser.add_argument("--format", choices=["text", "json", "release"], default="text")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero when readiness is degraded.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_dr_report(
        targets_path=args.targets,
        stack_path=args.stack,
        table_top_dir=args.table_top_dir,
        restore_dir=args.restore_dir,
        witness_dir=args.witness_dir,
        adr_dir=args.adr_dir,
    )
    if args.format == "json":
        print(json.dumps(report, indent=2))
    elif args.format == "release":
        print(render_release_status(report))
    else:
        print(render_dr_report(report))
    return 1 if args.strict and report["overall_status"] != "pass" else 0


if __name__ == "__main__":
    raise SystemExit(main())
