#!/usr/bin/env python3
"""Generate the ADR 0271 backup coverage ledger from live Proxmox state."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from controller_automation_toolkit import emit_cli_error, load_json, load_yaml, repo_path
from drift_lib import build_host_ssh_command, isoformat, load_controller_context, run_command, utc_now


HOST_VARS_PATH = repo_path("inventory", "host_vars", "proxmox_florin.yml")
REDUNDANCY_CATALOG_PATH = repo_path("config", "service-redundancy-catalog.json")
DR_TARGETS_PATH = repo_path("config", "disaster-recovery-targets.json")
RESTORE_RECEIPTS_DIR = repo_path("receipts", "restore-verifications")
DEFAULT_RECEIPTS_DIR = repo_path("receipts", "backup-coverage")
DEFAULT_PBS_STORAGE_ID = "lv3-backup-pbs"
DEFAULT_PBS_SCHEDULE = "02:30"
DEFAULT_FRESHNESS_HOURS = 36
SOURCE_ID_PATTERN = re.compile(r"^(pbs_vm|proxmox_offsite_vm)_(\d+)$")


@dataclass(frozen=True)
class GovernedAsset:
    asset_id: str
    vmid: int
    source_id: str
    source_kind: str
    storage_id: str
    expected_schedule: str
    expected_max_age_hours: int
    dependent_services: list[str]


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(repo_path()))
    except ValueError:
        return str(path)


def parse_backup_source_id(source_id: str) -> tuple[str, int] | None:
    match = SOURCE_ID_PATTERN.match(source_id.strip())
    if match is None:
        return None
    source_prefix, vmid = match.groups()
    source_kind = "pbs" if source_prefix == "pbs_vm" else "offsite"
    return source_kind, int(vmid)


def parse_job_vmids(value: Any) -> set[int]:
    if value in (None, ""):
        return set()
    if isinstance(value, int):
        return {value}
    result: set[int] = set()
    for item in str(value).split(","):
        item = item.strip()
        if not item:
            continue
        result.add(int(item))
    return result


def parse_pvesm_rows(payload: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in payload.splitlines():
        if not line.strip() or line.startswith("Volid"):
            continue
        parts = re.split(r"\s+", line.strip())
        if len(parts) < 5:
            continue
        rows.append(
            {
                "volid": parts[0],
                "format": parts[1],
                "type": parts[2],
                "size": parts[3],
                "vmid": int(parts[4]),
            }
        )
    return rows


def extract_backup_timestamp(volid: str) -> datetime | None:
    match = re.search(r"/(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)$", volid)
    if match is None:
        return None
    return datetime.fromisoformat(match.group(1).replace("Z", "+00:00")).astimezone(UTC)


def parse_recorded_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def build_governed_assets(
    host_vars: dict[str, Any],
    redundancy_catalog: dict[str, Any],
    dr_targets: dict[str, Any],
) -> list[GovernedAsset]:
    guests = host_vars.get("proxmox_guests", [])
    guest_names_by_vmid = {
        int(guest["vmid"]): str(guest["name"])
        for guest in guests
        if isinstance(guest, dict) and "vmid" in guest and "name" in guest
    }
    offsite_backup = dr_targets.get("offsite_backup", {}) if isinstance(dr_targets, dict) else {}
    offsite_storage_id = str(offsite_backup.get("storage_id") or "lv3-backup-offsite")
    offsite_schedule = str(offsite_backup.get("schedule_utc") or "04:00")

    protected_services: dict[str, set[str]] = defaultdict(set)
    services = redundancy_catalog.get("services", {})
    if not isinstance(services, dict):
        raise ValueError(f"{REDUNDANCY_CATALOG_PATH} must define a services object")

    for service_id, service_payload in services.items():
        if not isinstance(service_payload, dict):
            continue
        for source_id in service_payload.get("backup_sources", []):
            parsed = parse_backup_source_id(str(source_id))
            if parsed is None:
                continue
            protected_services[str(source_id)].add(str(service_id))

    assets: list[GovernedAsset] = []
    for source_id, dependent_services in sorted(protected_services.items()):
        source_kind, vmid = parse_backup_source_id(source_id) or ("unknown", -1)
        guest_name = guest_names_by_vmid.get(vmid, f"vm-{vmid}")
        if source_kind == "pbs":
            assets.append(
                GovernedAsset(
                    asset_id=guest_name,
                    vmid=vmid,
                    source_id=source_id,
                    source_kind=source_kind,
                    storage_id=DEFAULT_PBS_STORAGE_ID,
                    expected_schedule=DEFAULT_PBS_SCHEDULE,
                    expected_max_age_hours=DEFAULT_FRESHNESS_HOURS,
                    dependent_services=sorted(dependent_services),
                )
            )
            continue

        assets.append(
            GovernedAsset(
                asset_id=guest_name,
                vmid=vmid,
                source_id=source_id,
                source_kind=source_kind,
                storage_id=offsite_storage_id,
                expected_schedule=offsite_schedule,
                expected_max_age_hours=DEFAULT_FRESHNESS_HOURS,
                dependent_services=sorted(dependent_services),
            )
        )

    return assets


def load_restore_evidence(restore_dir: Path = RESTORE_RECEIPTS_DIR) -> dict[int, dict[str, Any]]:
    evidence_by_vmid: dict[int, dict[str, Any]] = {}
    if not restore_dir.is_dir():
        return evidence_by_vmid

    for path in sorted(restore_dir.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        recorded_at = parse_recorded_datetime(
            str(payload.get("recorded_at") or payload.get("recorded_on") or "")
        )
        for result in payload.get("results", []):
            if not isinstance(result, dict):
                continue
            source_vmid = result.get("source_vmid")
            if isinstance(source_vmid, bool) or not isinstance(source_vmid, int):
                continue
            if str(result.get("overall") or "").strip().lower() not in {"pass", "passed", "ok"}:
                continue
            candidate_time = (
                parse_recorded_datetime(str(result.get("recorded_at") or ""))
                or parse_recorded_datetime(str(result.get("backup_date") or ""))
                or recorded_at
            )
            if candidate_time is None:
                continue
            current = evidence_by_vmid.get(source_vmid)
            if current is not None and parse_recorded_datetime(current.get("recorded_at")) >= candidate_time:
                continue
            evidence_by_vmid[source_vmid] = {
                "recorded_at": isoformat(candidate_time),
                "path": _display_path(path),
                "backup_volid": result.get("backup_volid"),
                "backup_date": result.get("backup_date"),
            }
    return evidence_by_vmid


def run_host_command(context: dict[str, Any], command: str) -> tuple[int, str, str]:
    outcome = run_command(build_host_ssh_command(context, command))
    return outcome.returncode, outcome.stdout, outcome.stderr


def load_backup_jobs(context: dict[str, Any]) -> list[dict[str, Any]]:
    returncode, stdout, stderr = run_host_command(
        context,
        "sudo pvesh get /cluster/backup --output-format json",
    )
    if returncode != 0:
        detail = stderr or stdout or "failed to query Proxmox backup jobs"
        raise RuntimeError(detail)
    payload = json.loads(stdout or "[]")
    if not isinstance(payload, list):
        raise ValueError("cluster backup jobs response must be a list")
    return payload


def load_storage_listing(context: dict[str, Any], storage_id: str) -> dict[str, Any]:
    returncode, stdout, stderr = run_host_command(context, f"sudo pvesm list {storage_id}")
    if returncode != 0:
        return {
            "storage_id": storage_id,
            "available": False,
            "error": (stderr or stdout or f"storage '{storage_id}' not available").strip(),
            "rows": [],
        }
    rows = parse_pvesm_rows(stdout)
    for row in rows:
        row["timestamp"] = extract_backup_timestamp(str(row["volid"]))
    return {
        "storage_id": storage_id,
        "available": True,
        "error": "",
        "rows": rows,
    }


def summarize_retention(job: dict[str, Any] | None, asset: GovernedAsset, dr_targets: dict[str, Any]) -> dict[str, Any]:
    if job is not None:
        prune = job.get("prune-backups") or {}
        return {
            "source": "cluster_backup_job",
            "job_id": job.get("id"),
            "policy": prune,
        }
    if asset.source_kind == "offsite":
        offsite = dr_targets.get("offsite_backup", {}) if isinstance(dr_targets, dict) else {}
        return {
            "source": "disaster_recovery_targets",
            "job_id": "backup-lv3-offsite",
            "policy": offsite.get("retention") or {},
        }
    return {
        "source": "missing",
        "job_id": None,
        "policy": {},
    }


def fallback_job_for_storage(jobs: list[dict[str, Any]], storage_id: str) -> dict[str, Any] | None:
    for job in jobs:
        if str(job.get("storage") or "") == storage_id:
            return job
    return None


def evaluate_asset(
    asset: GovernedAsset,
    jobs: list[dict[str, Any]],
    storage_listing: dict[str, Any],
    restore_evidence: dict[int, dict[str, Any]],
    dr_targets: dict[str, Any],
    now: datetime,
) -> dict[str, Any]:
    matching_jobs = [
        job
        for job in jobs
        if str(job.get("storage") or "") == asset.storage_id and asset.vmid in parse_job_vmids(job.get("vmid"))
    ]
    fallback_job = fallback_job_for_storage(jobs, asset.storage_id)
    rows = [row for row in storage_listing.get("rows", []) if int(row.get("vmid", -1)) == asset.vmid]
    latest_backup = max(
        (row for row in rows if isinstance(row.get("timestamp"), datetime)),
        key=lambda row: row["timestamp"],
        default=None,
    )

    coverage_state = "protected"
    state_reasons: list[str] = []

    if not storage_listing.get("available", False):
        coverage_state = "uncovered"
        state_reasons.append(str(storage_listing.get("error") or f"storage {asset.storage_id} is unavailable"))
    elif latest_backup is None:
        coverage_state = "uncovered"
        state_reasons.append(f"No backup evidence exists on {asset.storage_id} for VM {asset.vmid}.")
    else:
        backup_age = now - latest_backup["timestamp"]
        if backup_age > timedelta(hours=asset.expected_max_age_hours):
            coverage_state = "uncovered"
            state_reasons.append(
                f"Latest backup is {backup_age.total_seconds() / 3600:.1f}h old, which exceeds the {asset.expected_max_age_hours}h freshness window."
            )

    if coverage_state == "protected" and not matching_jobs:
        coverage_state = "degraded"
        state_reasons.append(
            f"Fresh backup evidence exists, but no governed Proxmox backup job currently covers VM {asset.vmid} on {asset.storage_id}."
        )

    if coverage_state == "protected" and latest_backup is not None:
        state_reasons.append(
            f"Fresh backup evidence is present on {asset.storage_id} for VM {asset.vmid}."
        )

    observed_job = matching_jobs[0] if matching_jobs else fallback_job
    restore_entry = restore_evidence.get(asset.vmid)
    last_successful_backup = None
    if latest_backup is not None:
        last_successful_backup = {
            "timestamp": isoformat(latest_backup["timestamp"]),
            "volid": latest_backup["volid"],
            "format": latest_backup["format"],
            "size": latest_backup["size"],
            "age_hours": round((now - latest_backup["timestamp"]).total_seconds() / 3600, 2),
        }

    return {
        "asset_id": asset.asset_id,
        "vmid": asset.vmid,
        "source_id": asset.source_id,
        "source_kind": asset.source_kind,
        "storage_id": asset.storage_id,
        "dependent_services": asset.dependent_services,
        "expected_schedule": asset.expected_schedule,
        "expected_max_age_hours": asset.expected_max_age_hours,
        "governed_job_ids": [str(job.get("id")) for job in matching_jobs if job.get("id")],
        "retention_policy": summarize_retention(observed_job, asset, dr_targets),
        "coverage_state": coverage_state,
        "state_reasons": state_reasons,
        "last_successful_backup": last_successful_backup,
        "last_verified_restore": restore_entry,
    }


def build_backup_coverage_report(
    *,
    now: datetime | None = None,
    host_vars_path: Path = HOST_VARS_PATH,
    redundancy_catalog_path: Path = REDUNDANCY_CATALOG_PATH,
    dr_targets_path: Path = DR_TARGETS_PATH,
    restore_dir: Path = RESTORE_RECEIPTS_DIR,
) -> dict[str, Any]:
    now = (now or utc_now()).astimezone(UTC)
    host_vars = load_yaml(host_vars_path)
    redundancy_catalog = load_json(redundancy_catalog_path)
    dr_targets = load_json(dr_targets_path)
    assets = build_governed_assets(host_vars, redundancy_catalog, dr_targets)
    context = load_controller_context()
    jobs = load_backup_jobs(context)
    storage_ids = sorted({asset.storage_id for asset in assets})
    storage_listings = {
        storage_id: load_storage_listing(context, storage_id)
        for storage_id in storage_ids
    }
    restore_evidence = load_restore_evidence(restore_dir)

    evaluated_assets = [
        evaluate_asset(
            asset,
            jobs=jobs,
            storage_listing=storage_listings[asset.storage_id],
            restore_evidence=restore_evidence,
            dr_targets=dr_targets,
            now=now,
        )
        for asset in assets
    ]

    counts = defaultdict(int)
    uncovered_assets: list[str] = []
    degraded_assets: list[str] = []
    for asset in evaluated_assets:
        counts[asset["coverage_state"]] += 1
        if asset["coverage_state"] == "uncovered":
            uncovered_assets.append(asset["asset_id"])
        elif asset["coverage_state"] == "degraded":
            degraded_assets.append(asset["asset_id"])

    summary = {
        "governed_assets": len(evaluated_assets),
        "protected": counts["protected"],
        "degraded": counts["degraded"],
        "uncovered": counts["uncovered"],
        "uncovered_assets": uncovered_assets,
        "degraded_assets": degraded_assets,
    }

    return {
        "schema_version": "1.0.0",
        "report_id": f"backup-coverage-{now.strftime('%Y%m%dT%H%M%SZ')}",
        "generated_at": isoformat(now),
        "recorded_on": now.date().isoformat(),
        "recorded_by": "codex",
        "summary": summary,
        "policy": {
            "adr": "0271",
            "freshness_window_hours": DEFAULT_FRESHNESS_HOURS,
            "governed_source_prefixes": ["pbs_vm_", "proxmox_offsite_vm_"],
            "offsite_strategy": dr_targets.get("offsite_backup", {}).get("strategy"),
        },
        "assets": evaluated_assets,
        "evidence": {
            "jobs_checked": [str(job.get("id")) for job in jobs if job.get("id")],
            "storage_listings": {
                storage_id: {
                    "available": listing["available"],
                    "error": listing["error"],
                    "row_count": len(listing["rows"]),
                }
                for storage_id, listing in storage_listings.items()
            },
        },
    }


def render_text(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "LV3 backup coverage ledger",
        f"Generated: {report['generated_at']}",
        "",
        (
            "Protected: {protected}  Degraded: {degraded}  Uncovered: {uncovered}  Governed assets: {governed_assets}"
        ).format(**summary),
    ]
    if summary["uncovered_assets"]:
        lines.append("Uncovered assets: " + ", ".join(summary["uncovered_assets"]))
    if summary["degraded_assets"]:
        lines.append("Degraded assets: " + ", ".join(summary["degraded_assets"]))

    lines.extend(
        [
            "",
            "ASSET                STATE       STORAGE              LAST BACKUP            LAST VERIFIED RESTORE",
        ]
    )
    for asset in report["assets"]:
        last_backup = asset["last_successful_backup"]
        last_restore = asset["last_verified_restore"]
        lines.append(
            f"{asset['asset_id']:<20} {asset['coverage_state']:<11} {asset['storage_id']:<20} "
            f"{(last_backup['timestamp'] if last_backup else 'missing'):<22} "
            f"{(last_restore['recorded_at'] if last_restore else 'not recorded')}"
        )
        for reason in asset["state_reasons"]:
            lines.append(f"  - {reason}")
        lines.append(f"  - dependent services: {', '.join(asset['dependent_services'])}")
    return "\n".join(lines)


def write_receipt(report: dict[str, Any], receipts_dir: Path) -> Path:
    receipts_dir.mkdir(parents=True, exist_ok=True)
    path = receipts_dir / f"{report['generated_at'].replace(':', '').replace('-', '')}.json"
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate the ADR 0271 backup coverage ledger.")
    parser.add_argument("--host-vars", type=Path, default=HOST_VARS_PATH)
    parser.add_argument("--redundancy-catalog", type=Path, default=REDUNDANCY_CATALOG_PATH)
    parser.add_argument("--dr-targets", type=Path, default=DR_TARGETS_PATH)
    parser.add_argument("--restore-dir", type=Path, default=RESTORE_RECEIPTS_DIR)
    parser.add_argument("--receipts-dir", type=Path, default=DEFAULT_RECEIPTS_DIR)
    parser.add_argument("--format", choices=["text", "json"], default="text")
    parser.add_argument("--write-receipt", action="store_true", help="Write one dated receipt under receipts/backup-coverage.")
    parser.add_argument("--print-report-json", action="store_true", help="Emit a final REPORT_JSON=<json> line for wrappers.")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero if any asset is degraded or uncovered.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        report = build_backup_coverage_report(
            host_vars_path=args.host_vars,
            redundancy_catalog_path=args.redundancy_catalog,
            dr_targets_path=args.dr_targets,
            restore_dir=args.restore_dir,
        )
        if args.write_receipt:
            receipt_path = write_receipt(report, args.receipts_dir)
            report["receipt_path"] = _display_path(receipt_path)
        if args.format == "json":
            print(json.dumps(report, indent=2))
        else:
            print(render_text(report))
        if args.print_report_json:
            print("REPORT_JSON=" + json.dumps(report, separators=(",", ":")))
        return 1 if args.strict and (report["summary"]["degraded"] or report["summary"]["uncovered"]) else 0
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        return emit_cli_error("Backup coverage ledger", exc)


if __name__ == "__main__":
    raise SystemExit(main())
