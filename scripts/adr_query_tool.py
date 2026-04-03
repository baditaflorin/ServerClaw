#!/usr/bin/env python3
"""ADR query tool for the proxmox_florin_server repo.

USE THIS TOOL when you need to find, read, or query Architecture Decision Records.
Do not manually grep through docs/adr/ — use this tool instead.

ADRs live in docs/adr/ as markdown files named NNNN-slug.md (for example
0153-distributed-resource-lock-registry.md).

ADR 0325 adds shard-based ADR discovery metadata under docs/adr/index/ plus a
reservation ledger at docs/adr/index/reservations.yaml. This tool reads the
compact root manifest and the facet shards for fast list and allocation flows,
while show/search operations still read the canonical markdown files directly.

COMMANDS
--------
list            List ADRs, optionally filtered by status, implementation status, concern, or range.
show            Display one ADR by number or slug.
search          Full-text search across ADR content.
affecting       Find ADRs that mention a specific resource or identifier.
status-summary  Count ADRs by decision and implementation status.
reservations    Show ADR number reservations from the ledger.
allocate        Allocate or validate the next free ADR number/window.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml

from adr_discovery import (
    ADR_DIR,
    INDEX_PATH,
    REPO_ROOT,
    find_conflicts,
    load_adrs,
    load_reservation_ledger,
    load_root_index,
    next_available_window,
    status_slug,
    validate_reservation_ledger,
)


INDEX_FILE = INDEX_PATH
RESERVATIONS_FILE = ADR_DIR / "index" / "reservations.yaml"

_RE_STATUS = re.compile(r"^-\s+Status:\s+(.+)$", re.IGNORECASE)
_RE_IMPL_STATUS = re.compile(r"^-\s+Implementation Status:\s+(.+)$", re.IGNORECASE)
_RE_DATE = re.compile(r"^-\s+Date:\s+(.+)$", re.IGNORECASE)
_RE_IMPL_ON = re.compile(r"^-\s+Implemented On:\s+(.+)$", re.IGNORECASE)
_RE_TITLE = re.compile(r"^#\s+ADR\s+\d+[:\s]+(.+)$")


def _adr_files() -> list[Path]:
    return sorted(fp for fp in ADR_DIR.glob("*.md") if fp.name[:1].isdigit())


def _parse_number(fp: Path) -> int:
    try:
        return int(fp.name[:4])
    except ValueError:
        return 0


def _parse_slug(fp: Path) -> str:
    stem = fp.stem
    if "-" in stem:
        return stem[stem.index("-") + 1 :]
    return stem


def _read_text(fp: Path) -> str:
    try:
        return fp.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _parse_meta(fp: Path) -> dict:
    text = _read_text(fp)
    lines = text.splitlines()[:25]

    title = ""
    status = ""
    implementation_status = ""
    date = ""

    for line in lines:
        if not title:
            match = _RE_TITLE.match(line.strip())
            if match:
                title = match.group(1).strip()
        if not status:
            match = _RE_STATUS.match(line.strip())
            if match:
                status = match.group(1).strip()
        if not implementation_status:
            match = _RE_IMPL_STATUS.match(line.strip())
            if match:
                implementation_status = match.group(1).strip()
        if not date:
            match = _RE_DATE.match(line.strip())
            if match:
                date = match.group(1).strip()
            else:
                match = _RE_IMPL_ON.match(line.strip())
                if match:
                    date = match.group(1).strip()

    return {
        "number": _parse_number(fp),
        "slug": _parse_slug(fp),
        "title": title or fp.stem,
        "status": status,
        "implementation_status": implementation_status,
        "date": date,
    }


def _snippet(text: str, query: str, max_len: int = 200) -> str:
    lower = text.lower()
    idx = lower.find(query.lower())
    if idx == -1:
        return text[:max_len]
    start = max(0, idx - 60)
    end = min(len(text), idx + len(query) + 140)
    fragment = text[start:end]
    if start > 0:
        fragment = "..." + fragment
    if end < len(text):
        fragment = fragment + "..."
    return fragment


def _find_adr_file(number_or_slug: str) -> Path | None:
    try:
        number = int(number_or_slug)
        prefix = f"{number:04d}-"
        for fp in ADR_DIR.glob(f"{prefix}*.md"):
            return fp
    except ValueError:
        pass

    slug_lower = number_or_slug.lower()
    for fp in _adr_files():
        if _parse_slug(fp).lower() == slug_lower:
            return fp
    for fp in _adr_files():
        if slug_lower in _parse_slug(fp).lower():
            return fp
    return None


def _load_yaml(path: Path) -> dict:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a mapping")
    return payload


def _facet_path_lookup(root_manifest: dict, facet_name: str, key: str, value: str) -> Path | None:
    facets = root_manifest.get("facets") or {}
    records = facets.get(facet_name) or []
    for record in records:
        if not isinstance(record, dict):
            continue
        if str(record.get(key, "")).lower() != value.lower():
            continue
        path = record.get("path")
        if isinstance(path, str) and path:
            return REPO_ROOT / path
    return None


def _load_index_entries(
    *,
    decision_status: str | None = None,
    implementation_status: str | None = None,
    concern: str | None = None,
    range_label: str | None = None,
) -> list[dict]:
    root_manifest = load_root_index(INDEX_FILE)
    if not root_manifest:
        return []

    if "adr_index" in root_manifest:
        entries = root_manifest.get("adr_index") or []
    else:
        shard_paths: list[Path] = []
        if concern:
            path = _facet_path_lookup(root_manifest, "by_concern", "concern", concern)
            if path:
                shard_paths.append(path)
        elif implementation_status:
            path = _facet_path_lookup(root_manifest, "by_status", "slug", status_slug(implementation_status))
            if path:
                shard_paths.append(path)
        elif range_label:
            normalized = range_label.strip()
            path = _facet_path_lookup(root_manifest, "by_range", "label", normalized)
            if path:
                shard_paths.append(path)
        else:
            shard_paths.extend(
                REPO_ROOT / record["path"]
                for record in (root_manifest.get("facets") or {}).get("by_range", [])
                if isinstance(record, dict) and isinstance(record.get("path"), str)
            )

        entries = []
        for shard_path in shard_paths:
            if not shard_path.exists():
                continue
            entries.extend(_load_yaml(shard_path).get("adrs") or [])

    if not isinstance(entries, list):
        entries = []

    results = [entry for entry in entries if isinstance(entry, dict)]
    if decision_status:
        results = [
            entry
            for entry in results
            if str(entry.get("status", "")).lower() == decision_status.lower()
        ]
    if implementation_status:
        results = [
            entry
            for entry in results
            if str(entry.get("implementation_status", "")).lower() == implementation_status.lower()
        ]
    if concern:
        results = [
            entry
            for entry in results
            if str(entry.get("concern", "")).lower() == concern.lower()
        ]
    if range_label:
        results = [
            entry
            for entry in results
            if range_label[:4] <= str(entry.get("adr", "")) <= range_label[-4:]
        ]
    results.sort(key=lambda entry: int(str(entry.get("adr", "0"))))
    return results


def command_list(args) -> int:
    entries = _load_index_entries(
        decision_status=args.status,
        implementation_status=args.implementation_status,
        concern=args.concern,
        range_label=args.range,
    )
    if args.limit:
        entries = entries[: args.limit]
    if not entries:
        print(json.dumps([]))
        return 2
    print(json.dumps(entries, indent=2))
    return 0


def command_show(args) -> int:
    target = args.number_or_slug
    fp = _find_adr_file(target)
    if fp is None:
        print(json.dumps({"error": f"ADR not found: {target}", "type": "FileNotFoundError"}), file=sys.stderr)
        return 1

    meta = _parse_meta(fp)
    meta["content_markdown"] = _read_text(fp)
    print(json.dumps(meta, indent=2))
    return 0


def command_search(args) -> int:
    query = args.query
    query_lower = query.lower()
    scored = []

    for fp in _adr_files():
        content = _read_text(fp)
        count = content.lower().count(query_lower)
        if count == 0:
            continue
        meta = _parse_meta(fp)
        scored.append(
            {
                "number": meta["number"],
                "title": meta["title"],
                "snippet": _snippet(content, query),
                "relevance": count,
            }
        )

    scored.sort(key=lambda result: result["relevance"], reverse=True)
    scored = scored[: args.limit]
    if not scored:
        print(json.dumps([]))
        return 2

    print(json.dumps(scored, indent=2))
    return 0


def command_affecting(args) -> int:
    resource = args.resource
    resource_lower = resource.lower()
    matches = []

    for fp in _adr_files():
        content = _read_text(fp)
        count = content.lower().count(resource_lower)
        if count == 0:
            continue
        meta = _parse_meta(fp)
        matches.append(
            {
                "number": meta["number"],
                "title": meta["title"],
                "snippet": _snippet(content, resource),
                "relevance": count,
            }
        )

    matches.sort(key=lambda result: result["relevance"], reverse=True)
    matches = matches[: args.limit]
    if not matches:
        print(json.dumps([]))
        return 2

    print(json.dumps(matches, indent=2))
    return 0


def command_status_summary(args) -> int:  # noqa: ARG001
    root_manifest = load_root_index(INDEX_FILE)
    if root_manifest:
        result = {
            "total": root_manifest.get("total_adrs", 0),
            "by_status": root_manifest.get("decision_status_summary", {}),
            "by_implementation_status": root_manifest.get("implementation_status_summary", {}),
        }
        print(json.dumps(result, indent=2))
        return 0

    by_status: dict[str, int] = {}
    by_implementation_status: dict[str, int] = {}
    total = 0
    for fp in _adr_files():
        meta = _parse_meta(fp)
        status = meta["status"] or "Unknown"
        implementation_status = meta["implementation_status"] or "Unknown"
        by_status[status] = by_status.get(status, 0) + 1
        by_implementation_status[implementation_status] = by_implementation_status.get(implementation_status, 0) + 1
        total += 1
    print(
        json.dumps(
            {
                "total": total,
                "by_status": dict(sorted(by_status.items())),
                "by_implementation_status": dict(sorted(by_implementation_status.items())),
            },
            indent=2,
        )
    )
    return 0


def command_reservations(args) -> int:
    adrs = load_adrs(ADR_DIR)
    ledger = load_reservation_ledger(RESERVATIONS_FILE)
    issues = validate_reservation_ledger(ledger, adrs)
    if issues:
        print(json.dumps({"error": issues, "type": "ReservationValidationError"}), file=sys.stderr)
        return 1

    reservations = ledger.reservations if args.include_inactive else ledger.active()
    print(
        json.dumps(
            {
                "path": RESERVATIONS_FILE.relative_to(REPO_ROOT).as_posix(),
                "count": len(reservations),
                "reservations": [reservation.to_dict() for reservation in reservations],
            },
            indent=2,
        )
    )
    return 0


def command_allocate(args) -> int:
    adrs = load_adrs(ADR_DIR)
    ledger = load_reservation_ledger(RESERVATIONS_FILE)
    issues = validate_reservation_ledger(ledger, adrs)
    if issues:
        print(json.dumps({"error": issues, "type": "ReservationValidationError"}), file=sys.stderr)
        return 1

    if args.end is not None and args.start is None:
        print(json.dumps({"error": "--end requires --start", "type": "ValueError"}), file=sys.stderr)
        return 1

    try:
        if args.start is not None and args.end is not None:
            window_size = args.end - args.start + 1
            if window_size < 1:
                raise ValueError("--end must be >= --start")
        else:
            window_size = args.window_size

        if args.start is None:
            allocation = next_available_window(adrs, ledger, window_size=window_size)
        else:
            conflicts = find_conflicts(args.start, args.start + window_size - 1, adrs, ledger)
            if conflicts.existing_adrs or conflicts.reservations:
                payload = conflicts.to_dict()
                payload["error"] = "requested ADR window is already occupied"
                payload["type"] = "ReservationConflictError"
                print(json.dumps(payload, indent=2), file=sys.stderr)
                return 1
            allocation = conflicts
    except ValueError as exc:
        print(json.dumps({"error": str(exc), "type": "ValueError"}), file=sys.stderr)
        return 1

    print(
        json.dumps(
            {
                "start": allocation.start_str,
                "end": allocation.end_str,
                "window_size": allocation.window_size,
                "highest_committed_adr": max((adr.number for adr in adrs), default=None),
                "active_reservation_count": len(ledger.active()),
                "reservations_path": RESERVATIONS_FILE.relative_to(REPO_ROOT).as_posix(),
            },
            indent=2,
        )
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Query the ADR library in the proxmox_florin_server repo.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="List ADRs, optionally filtered by discovery facets.")
    list_parser.add_argument("--status", help="Filter by decision status, for example accepted or proposed.")
    list_parser.add_argument("--implementation-status", help="Filter by implementation status, for example Implemented.")
    list_parser.add_argument("--concern", help="Filter by concern shard, for example documentation.")
    list_parser.add_argument("--range", help="Filter by a range shard label, for example 0300-0399.")
    list_parser.add_argument("--limit", type=int, help="Maximum number of results to return.")
    list_parser.set_defaults(func=command_list)

    show_parser = subparsers.add_parser("show", help="Display one ADR by number or slug.")
    show_parser.add_argument("number_or_slug", help="ADR number (for example 153) or slug.")
    show_parser.set_defaults(func=command_show)

    search_parser = subparsers.add_parser("search", help="Full-text search across ADR markdown.")
    search_parser.add_argument("query", help="Case-insensitive substring to search for.")
    search_parser.add_argument("--limit", type=int, default=10, help="Maximum number of results.")
    search_parser.set_defaults(func=command_search)

    affecting_parser = subparsers.add_parser("affecting", help="Find ADRs mentioning a specific resource.")
    affecting_parser.add_argument("resource", help="Resource identifier to search for.")
    affecting_parser.add_argument("--limit", type=int, default=20, help="Maximum number of results.")
    affecting_parser.set_defaults(func=command_affecting)

    status_parser = subparsers.add_parser("status-summary", help="Count ADRs by decision and implementation status.")
    status_parser.set_defaults(func=command_status_summary)

    reservations_parser = subparsers.add_parser("reservations", help="Show ADR reservation windows.")
    reservations_parser.add_argument(
        "--include-inactive",
        action="store_true",
        help="Include released, expired, and realized reservations.",
    )
    reservations_parser.set_defaults(func=command_reservations)

    allocate_parser = subparsers.add_parser("allocate", help="Allocate or validate an ADR number/window.")
    allocate_parser.add_argument(
        "--window-size",
        type=int,
        default=1,
        help="Requested ADR window size when auto-allocating (default: 1).",
    )
    allocate_parser.add_argument("--start", type=int, help="Validate a specific start ADR number.")
    allocate_parser.add_argument("--end", type=int, help="Validate a specific end ADR number.")
    allocate_parser.set_defaults(func=command_allocate)

    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        return args.func(args)
    except SystemExit:
        raise
    except Exception as exc:
        print(json.dumps({"error": str(exc), "type": type(exc).__name__}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
