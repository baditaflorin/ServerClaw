#!/usr/bin/env python3
"""Govern repository validation-gate bypass waivers."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from datetime import UTC
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
repo_root_str = str(REPO_ROOT)
if repo_root_str not in sys.path:
    sys.path.insert(0, repo_root_str)
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

try:
    from validation_toolkit import require_list, require_mapping, require_str
except ModuleNotFoundError as exc:
    if exc.name != "validation_toolkit":
        raise

    def require_mapping(value: Any, path: str) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise ValueError(f"{path} must be a mapping")
        return value

    def require_list(value: Any, path: str) -> list[Any]:
        if not isinstance(value, list):
            raise ValueError(f"{path} must be a list")
        return value

    def require_str(value: Any, path: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{path} must be a non-empty string")
        return value


from scripts.controller_automation_toolkit import emit_cli_error

DEFAULT_CATALOG_PATH = REPO_ROOT / "config" / "gate-bypass-waiver-catalog.json"
DEFAULT_RECEIPT_DIR = REPO_ROOT / "receipts" / "gate-bypasses"
CATALOG_SCHEMA_PATH = REPO_ROOT / "docs" / "schema" / "gate-bypass-waiver-catalog.schema.json"
RECEIPT_SCHEMA_PATH = REPO_ROOT / "docs" / "schema" / "gate-bypass-waiver-receipt.schema.json"
SUPPORTED_CATALOG_SCHEMA_VERSION = "1.0.0"
SUPPORTED_RECEIPT_SCHEMA_VERSION = "2.0.0"
IDENTIFIER_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
LIST_SPLIT_PATTERN = re.compile(r"[,\n;]+")


@dataclass(frozen=True)
class ValidatedWaiverReceipt:
    path: str
    created_at: datetime
    bypass: str
    source: str
    branch: str
    commit: str
    reason_code: str | None = None
    reason_summary: str | None = None
    detail: str | None = None
    impacted_lanes: tuple[str, ...] = ()
    substitute_evidence: tuple[str, ...] = ()
    owner: str | None = None
    expires_on: date | None = None
    remediation_ref: str | None = None
    schema_mode: str = "legacy"

    @property
    def is_legacy(self) -> bool:
        return self.schema_mode == "legacy"

    @property
    def is_compliant(self) -> bool:
        return self.schema_mode == "v2"

    def status_on(self, reference_date: date) -> str:
        if self.expires_on is None:
            return "legacy"
        return "expired" if self.expires_on < reference_date else "open"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def require_identifier(value: Any, path: str) -> str:
    value = require_str(value, path)
    if not IDENTIFIER_PATTERN.match(value):
        raise ValueError(f"{path} must use lowercase letters, numbers, hyphens, or underscores")
    return value


def require_int(value: Any, path: str, minimum: int = 1) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{path} must be an integer >= {minimum}")
    return value


def parse_datetime(raw: str, path: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(require_str(raw, path).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{path} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def parse_date(raw: str, path: str) -> date:
    try:
        return date.fromisoformat(require_str(raw, path))
    except ValueError as exc:
        raise ValueError(f"{path} must use YYYY-MM-DD format") from exc


def split_list_values(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        for item in LIST_SPLIT_PATTERN.split(value):
            item = item.strip()
            if item:
                result.append(item)
    return result


def require_string_list(value: Any, path: str) -> list[str]:
    items = require_list(value, path)
    result: list[str] = []
    for index, item in enumerate(items):
        result.append(require_str(item, f"{path}[{index}]"))
    if not result:
        raise ValueError(f"{path} must not be empty")
    return result


def require_identifier_list(value: Any, path: str) -> list[str]:
    items = require_list(value, path)
    result: list[str] = []
    for index, item in enumerate(items):
        result.append(require_identifier(item, f"{path}[{index}]"))
    if not result:
        raise ValueError(f"{path} must not be empty")
    return result


def repo_relative_label(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def load_catalog(path: Path | None = None) -> dict[str, Any]:
    path = path or DEFAULT_CATALOG_PATH
    return require_mapping(load_json(path), str(path))


def validate_catalog(catalog: dict[str, Any], *, path: Path | None = None) -> None:
    path = path or DEFAULT_CATALOG_PATH
    prefix = str(path)
    if catalog.get("$schema") != "docs/schema/gate-bypass-waiver-catalog.schema.json":
        raise ValueError(f"{prefix}.$schema must reference docs/schema/gate-bypass-waiver-catalog.schema.json")
    if catalog.get("schema_version") != SUPPORTED_CATALOG_SCHEMA_VERSION:
        raise ValueError(f"{prefix}.schema_version must be {SUPPORTED_CATALOG_SCHEMA_VERSION}")

    expiring_soon_days = require_int(catalog.get("expiring_soon_days"), f"{prefix}.expiring_soon_days")
    repeat_after_expiry = require_mapping(catalog.get("repeat_after_expiry"), f"{prefix}.repeat_after_expiry")
    warning_after = require_int(
        repeat_after_expiry.get("warning_after_occurrences"),
        f"{prefix}.repeat_after_expiry.warning_after_occurrences",
    )
    blocker_after = require_int(
        repeat_after_expiry.get("blocker_after_occurrences"),
        f"{prefix}.repeat_after_expiry.blocker_after_occurrences",
    )
    if blocker_after < warning_after:
        raise ValueError(f"{prefix}.repeat_after_expiry.blocker_after_occurrences must be >= warning_after_occurrences")
    if expiring_soon_days > 30:
        raise ValueError(f"{prefix}.expiring_soon_days must stay within a short-lived waiver window")

    reason_codes = require_mapping(catalog.get("reason_codes"), f"{prefix}.reason_codes")
    if not reason_codes:
        raise ValueError(f"{prefix}.reason_codes must not be empty")
    for reason_code, value in sorted(reason_codes.items()):
        item_path = f"{prefix}.reason_codes.{reason_code}"
        require_identifier(reason_code, item_path)
        item = require_mapping(value, item_path)
        require_str(item.get("summary"), f"{item_path}.summary")
        require_int(item.get("max_expiry_days"), f"{item_path}.max_expiry_days")
        require_identifier_list(item.get("allowed_bypasses"), f"{item_path}.allowed_bypasses")


def validate_jsonschema(instance: Any, schema_path: Path) -> None:
    try:
        import jsonschema  # type: ignore[import-untyped]
    except ModuleNotFoundError as exc:  # pragma: no cover
        raise RuntimeError("Missing dependency: jsonschema") from exc
    jsonschema.validate(instance=instance, schema=load_json(schema_path))


def max_expiry_days_for_reason(catalog: dict[str, Any], reason_code: str) -> int:
    reason = require_mapping(
        require_mapping(catalog.get("reason_codes"), "config/gate-bypass-waiver-catalog.json.reason_codes").get(
            reason_code
        ),
        f"config/gate-bypass-waiver-catalog.json.reason_codes.{reason_code}",
    )
    return require_int(
        reason.get("max_expiry_days"),
        f"config/gate-bypass-waiver-catalog.json.reason_codes.{reason_code}.max_expiry_days",
    )


def default_expiry_date(*, created_at: datetime, catalog: dict[str, Any], reason_code: str) -> date:
    return created_at.date() + timedelta(days=max_expiry_days_for_reason(catalog, reason_code))


def build_receipt_payload(
    *,
    created_at: datetime,
    bypass: str,
    source: str,
    branch: str,
    commit: str,
    reason_code: str,
    detail: str,
    impacted_lanes: list[str],
    substitute_evidence: list[str],
    owner: str,
    expires_on: date,
    remediation_ref: str,
    catalog: dict[str, Any],
) -> dict[str, Any]:
    reasons = require_mapping(catalog.get("reason_codes"), "config/gate-bypass-waiver-catalog.json.reason_codes")
    reason = require_mapping(
        reasons.get(reason_code), f"config/gate-bypass-waiver-catalog.json.reason_codes.{reason_code}"
    )
    return {
        "schema_version": SUPPORTED_RECEIPT_SCHEMA_VERSION,
        "created_at": created_at.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "bypass": bypass,
        "source": source,
        "branch": branch,
        "commit": commit,
        "waiver": {
            "reason_code": reason_code,
            "reason_summary": require_str(
                reason.get("summary"),
                f"config/gate-bypass-waiver-catalog.json.reason_codes.{reason_code}.summary",
            ),
            "detail": detail,
            "impacted_lanes": impacted_lanes,
            "substitute_evidence": substitute_evidence,
            "owner": owner,
            "expires_on": expires_on.isoformat(),
            "remediation_ref": remediation_ref,
        },
    }


def validate_receipt(
    payload: dict[str, Any],
    *,
    path: str,
    catalog: dict[str, Any],
    validate_schema: bool = False,
) -> ValidatedWaiverReceipt:
    created_at = parse_datetime(str(payload.get("created_at") or ""), f"{path}.created_at")
    bypass = require_identifier(payload.get("bypass"), f"{path}.bypass")
    source = require_str(payload.get("source"), f"{path}.source")
    branch = require_str(payload.get("branch"), f"{path}.branch")
    commit = require_str(payload.get("commit"), f"{path}.commit")

    if payload.get("schema_version") != SUPPORTED_RECEIPT_SCHEMA_VERSION:
        return ValidatedWaiverReceipt(
            path=path,
            created_at=created_at,
            bypass=bypass,
            source=source,
            branch=branch,
            commit=commit,
            schema_mode="legacy",
        )

    if validate_schema:
        validate_jsonschema(payload, RECEIPT_SCHEMA_PATH)
    waiver = require_mapping(payload.get("waiver"), f"{path}.waiver")
    reason_code = require_identifier(waiver.get("reason_code"), f"{path}.waiver.reason_code")
    reasons = require_mapping(catalog.get("reason_codes"), "config/gate-bypass-waiver-catalog.json.reason_codes")
    if reason_code not in reasons:
        raise ValueError(f"{path}.waiver.reason_code references unknown reason code '{reason_code}'")
    reason = require_mapping(reasons[reason_code], f"config/gate-bypass-waiver-catalog.json.reason_codes.{reason_code}")
    allowed_bypasses = require_identifier_list(reason.get("allowed_bypasses"), f"{path}.waiver.allowed_bypasses")
    if bypass not in allowed_bypasses:
        raise ValueError(f"{path}.bypass is not allowed for reason code '{reason_code}'")

    expires_on = parse_date(str(waiver.get("expires_on") or ""), f"{path}.waiver.expires_on")
    if expires_on < created_at.date():
        raise ValueError(f"{path}.waiver.expires_on must not be earlier than {path}.created_at")
    max_expiry_days = require_int(reason.get("max_expiry_days"), f"{path}.waiver.max_expiry_days")
    if (expires_on - created_at.date()).days > max_expiry_days:
        raise ValueError(
            f"{path}.waiver.expires_on exceeds the {max_expiry_days}-day policy window for '{reason_code}'"
        )

    return ValidatedWaiverReceipt(
        path=path,
        created_at=created_at,
        bypass=bypass,
        source=source,
        branch=branch,
        commit=commit,
        reason_code=reason_code,
        reason_summary=require_str(waiver.get("reason_summary"), f"{path}.waiver.reason_summary"),
        detail=require_str(waiver.get("detail"), f"{path}.waiver.detail"),
        impacted_lanes=tuple(require_identifier_list(waiver.get("impacted_lanes"), f"{path}.waiver.impacted_lanes")),
        substitute_evidence=tuple(
            require_string_list(waiver.get("substitute_evidence"), f"{path}.waiver.substitute_evidence")
        ),
        owner=require_str(waiver.get("owner"), f"{path}.waiver.owner"),
        expires_on=expires_on,
        remediation_ref=require_str(waiver.get("remediation_ref"), f"{path}.waiver.remediation_ref"),
        schema_mode="v2",
    )


def load_receipts(
    *,
    directory: Path | None = None,
    catalog: dict[str, Any],
    validate_schema: bool = False,
) -> tuple[list[ValidatedWaiverReceipt], list[dict[str, str]]]:
    directory = directory or DEFAULT_RECEIPT_DIR
    directory = directory if directory.is_absolute() else REPO_ROOT / directory
    receipts: list[ValidatedWaiverReceipt] = []
    invalid: list[dict[str, str]] = []
    if not directory.exists():
        return receipts, invalid

    for path in sorted(directory.glob("*.json")):
        try:
            payload = require_mapping(load_json(path), str(path))
            receipts.append(
                validate_receipt(
                    payload,
                    path=repo_relative_label(path),
                    catalog=catalog,
                    validate_schema=validate_schema,
                )
            )
        except (OSError, ValueError, json.JSONDecodeError, RuntimeError) as exc:
            invalid.append({"path": repo_relative_label(path), "error": str(exc)})
    return receipts, invalid


def summarize_receipts(
    *,
    directory: Path | None = None,
    catalog: dict[str, Any] | None = None,
    reference_date: date | None = None,
    validate_schema: bool = False,
) -> dict[str, Any]:
    directory = directory or DEFAULT_RECEIPT_DIR
    directory = directory if directory.is_absolute() else REPO_ROOT / directory
    catalog = catalog or load_catalog()
    validate_catalog(catalog)
    if validate_schema:
        validate_jsonschema(catalog, CATALOG_SCHEMA_PATH)
    reference_date = reference_date or datetime.now(UTC).date()
    receipts, invalid_receipts = load_receipts(directory=directory, catalog=catalog, validate_schema=validate_schema)
    latest_receipt = max(receipts, key=lambda item: item.created_at, default=None)
    compliant_receipts = [item for item in receipts if item.is_compliant]
    legacy_receipts = [item for item in receipts if item.is_legacy]
    open_waivers = [item for item in compliant_receipts if item.status_on(reference_date) == "open"]
    expired_waivers = [item for item in compliant_receipts if item.status_on(reference_date) == "expired"]
    expiring_soon_days = require_int(
        catalog.get("expiring_soon_days"), "config/gate-bypass-waiver-catalog.json.expiring_soon_days"
    )
    expiring_soon = [
        item
        for item in open_waivers
        if item.expires_on is not None and (item.expires_on - reference_date).days <= expiring_soon_days
    ]

    grouped: dict[str, list[ValidatedWaiverReceipt]] = defaultdict(list)
    for receipt in compliant_receipts:
        if receipt.reason_code is not None:
            grouped[receipt.reason_code].append(receipt)

    repeat_policy = require_mapping(
        catalog.get("repeat_after_expiry"),
        "config/gate-bypass-waiver-catalog.json.repeat_after_expiry",
    )
    warning_after = require_int(
        repeat_policy.get("warning_after_occurrences"),
        "config/gate-bypass-waiver-catalog.json.repeat_after_expiry.warning_after_occurrences",
    )
    blocker_after = require_int(
        repeat_policy.get("blocker_after_occurrences"),
        "config/gate-bypass-waiver-catalog.json.repeat_after_expiry.blocker_after_occurrences",
    )
    reason_summaries: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    release_blockers: list[dict[str, Any]] = []
    for reason_code, items in sorted(grouped.items()):
        ordered = sorted(items, key=lambda item: item.created_at)
        repeat_after_expiry = 0
        for index, current in enumerate(ordered):
            if any(
                previous.expires_on is not None and previous.expires_on < current.created_at.date()
                for previous in ordered[:index]
            ):
                repeat_after_expiry += 1

        status = "none"
        if repeat_after_expiry >= blocker_after:
            status = "release_blocker"
        elif repeat_after_expiry >= warning_after:
            status = "warning"

        latest = ordered[-1]
        reason_summary = {
            "reason_code": reason_code,
            "summary": latest.reason_summary,
            "receipt_count": len(ordered),
            "open_waivers": sum(1 for item in ordered if item.status_on(reference_date) == "open"),
            "expired_waivers": sum(1 for item in ordered if item.status_on(reference_date) == "expired"),
            "repeat_after_expiry_occurrences": repeat_after_expiry,
            "status": status,
            "latest_created_at": latest.created_at.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "latest_expires_on": latest.expires_on.isoformat() if latest.expires_on is not None else None,
        }
        reason_summaries.append(reason_summary)
        if status == "warning":
            warnings.append(reason_summary)
        elif status == "release_blocker":
            release_blockers.append(reason_summary)

    return {
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "catalog_path": repo_relative_label(DEFAULT_CATALOG_PATH),
        "receipt_dir": repo_relative_label(directory),
        "policy": {
            "expiring_soon_days": expiring_soon_days,
            "repeat_after_expiry": {
                "warning_after_occurrences": warning_after,
                "blocker_after_occurrences": blocker_after,
            },
        },
        "totals": {
            "all_receipts": len(receipts),
            "legacy_receipts": len(legacy_receipts),
            "compliant_receipts": len(compliant_receipts),
            "open_waivers": len(open_waivers),
            "expired_waivers": len(expired_waivers),
            "invalid_receipts": len(invalid_receipts),
        },
        "latest_receipt": None
        if latest_receipt is None
        else {
            "path": latest_receipt.path,
            "created_at": latest_receipt.created_at.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "bypass": latest_receipt.bypass,
            "schema_mode": latest_receipt.schema_mode,
            "reason_code": latest_receipt.reason_code,
            "expires_on": latest_receipt.expires_on.isoformat() if latest_receipt.expires_on is not None else None,
        },
        "open_waivers": [
            {
                "path": item.path,
                "created_at": item.created_at.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                "bypass": item.bypass,
                "reason_code": item.reason_code,
                "reason_summary": item.reason_summary,
                "owner": item.owner,
                "expires_on": item.expires_on.isoformat() if item.expires_on is not None else None,
                "remediation_ref": item.remediation_ref,
            }
            for item in sorted(open_waivers, key=lambda entry: (entry.expires_on or date.max, entry.created_at))
        ],
        "expiring_soon": [
            {
                "path": item.path,
                "reason_code": item.reason_code,
                "expires_on": item.expires_on.isoformat() if item.expires_on is not None else None,
            }
            for item in sorted(expiring_soon, key=lambda entry: (entry.expires_on or date.max, entry.created_at))
        ],
        "reason_codes": reason_summaries,
        "warnings": warnings,
        "release_blockers": release_blockers,
        "invalid_receipts": invalid_receipts,
    }


def render_summary(summary: dict[str, Any]) -> str:
    totals = summary["totals"]
    lines = [
        "Gate bypass waivers",
        f"- Receipts: {totals['all_receipts']} total, {totals['legacy_receipts']} legacy, {totals['compliant_receipts']} governed",
        f"- Open waivers: {totals['open_waivers']}",
        f"- Expired waivers: {totals['expired_waivers']}",
        f"- Aging repeated reasons: {len(summary['warnings'])} warning, {len(summary['release_blockers'])} release-blocking",
    ]
    if summary["open_waivers"]:
        lines.append("- Open waiver details:")
        for item in summary["open_waivers"]:
            lines.append(
                f"  {item['reason_code']} until {item['expires_on']} ({item['owner']}; {item['remediation_ref']})"
            )
    if summary["release_blockers"] or summary["warnings"]:
        lines.append("- Repeated reasons:")
        for item in summary["release_blockers"] + summary["warnings"]:
            lines.append(
                f"  {item['reason_code']} [{item['status']}] after {item['repeat_after_expiry_occurrences']} repeat(s) past expiry"
            )
    if summary["invalid_receipts"]:
        lines.append("- Invalid receipts:")
        for item in summary["invalid_receipts"]:
            lines.append(f"  {item['path']}: {item['error']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate and summarize governed validation-gate bypass waivers.")
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG_PATH)
    parser.add_argument("--receipt-dir", type=Path, default=DEFAULT_RECEIPT_DIR)
    parser.add_argument("--validate", action="store_true", help="Validate the waiver catalog and committed receipts.")
    parser.add_argument("--summary", action="store_true", help="Print the waiver summary.")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)

    if not args.validate and not args.summary:
        parser.print_help()
        return 0

    try:
        catalog = load_catalog(args.catalog)
        validate_catalog(catalog, path=args.catalog)
        if args.validate:
            validate_jsonschema(catalog, CATALOG_SCHEMA_PATH)
        summary = summarize_receipts(directory=args.receipt_dir, catalog=catalog, validate_schema=args.validate)
        if summary["invalid_receipts"]:
            raise ValueError("one or more gate-bypass receipts are invalid")
        if args.summary:
            if args.format == "json":
                print(json.dumps(summary, indent=2, sort_keys=True))
            else:
                print(render_summary(summary))
        if args.validate:
            # Fail the gate if any reason codes have reached release-blocker status.
            # This means a bypass has been re-used after its waiver expired enough times
            # that the policy considers it a systemic problem requiring remediation.
            release_blockers = summary.get("release_blockers", [])
            if release_blockers:
                blocker_codes = ", ".join(item["reason_code"] for item in release_blockers)
                raise ValueError(
                    f"gate-bypass waiver release-blockers detected for reason codes: {blocker_codes} — "
                    "repeated use of expired waivers requires remediation before the gate can pass"
                )
            print("Gate bypass waivers OK")
        return 0
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        return emit_cli_error("gate bypass waivers", exc)


if __name__ == "__main__":
    raise SystemExit(main())
