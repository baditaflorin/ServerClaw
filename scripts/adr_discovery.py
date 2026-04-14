#!/usr/bin/env python3
"""Shared ADR discovery and reservation helpers for ADR 0325."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import datetime as dt
from pathlib import Path
import re
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ADR_DIR = REPO_ROOT / "docs" / "adr"
INDEX_PATH = ADR_DIR / ".index.yaml"
INDEX_DIR = ADR_DIR / "index"
RANGE_DIR = INDEX_DIR / "by-range"
CONCERN_DIR = INDEX_DIR / "by-concern"
STATUS_DIR = INDEX_DIR / "by-status"
RESERVATIONS_PATH = INDEX_DIR / "reservations.yaml"

GENERATE_COMMAND = "python scripts/generate_adr_index.py --write"

CONCERN_RULES: list[tuple[str, list[str]]] = [
    ("bootstrap", ["bootstrap", "hetzner", "rescue", "installimage", "debian-packages"]),
    ("host-os", ["proxmox", "debian", "host-os", "target-os"]),
    ("vm-topology", ["vm", "topology", "guest", "provision", "cloud-init", "template"]),
    ("networking", ["network", "bridge", "nat", "ingress", "egress", "subdomain", "dns"]),
    (
        "security",
        ["security", "hardening", "firewall", "mtls", "credential", "secret", "token", "key", "certificate", "tls"],
    ),
    ("storage", ["storage", "backup", "pbs", "volume", "disk"]),
    (
        "monitoring",
        ["monitoring", "grafana", "prometheus", "alertmanager", "metrics", "observability", "loki", "tempo"],
    ),
    ("ci-cd", ["ci", "cd", "gitea", "github", "actions", "pipeline", "validation", "pre-push", "gate"]),
    ("automation", ["ansible", "playbook", "role", "windmill", "workflow", "automation", "scheduled"]),
    ("identity", ["keycloak", "sso", "oidc", "identity", "authentication", "authorization", "access"]),
    (
        "documentation",
        ["changelog", "runbook", "documentation", "portal", "search", "indexing", "reservation", "shard"],
    ),
    ("testing", ["testing", "test", "pytest", "molecule", "integration-test", "idempotency"]),
    ("release", ["release", "version", "changelog", "semantic"]),
    ("api", ["api", "gateway", "catalog", "openapi", "rest"]),
    ("agent-discovery", ["agent", "discovery", "index", "metadata", "handoff", "context", "reservation", "shard"]),
    ("agent-coordination", ["coordination", "concurrency", "lock", "handoff", "parallelism", "deadlock"]),
    ("resilience", ["retry", "circuit-breaker", "timeout", "fault", "watchdog", "degradation"]),
    ("platform", ["platform", "manifest", "scaffold", "capability"]),
]

STATUS_NORMALIZATION_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("Not Implemented", ("not implemented",)),
    ("Partial", ("partial", "partially implemented")),
    ("Implemented", ("live applied", "implemented", "live", "deployed")),
    ("Deprecated", ("deprecated", "superseded")),
    ("Accepted", ("accepted",)),
    ("Proposed", ("proposed",)),
]

IMPLEMENTATION_STATUS_ORDER = (
    "Implemented",
    "Partial",
    "Not Implemented",
    "Deprecated",
    "Accepted",
    "Proposed",
)
DECISION_STATUS_ORDER = (
    "Accepted",
    "Proposed",
    "Deprecated",
    "Implemented",
    "Partial",
    "Not Implemented",
)
ACTIVE_RESERVATION_STATUSES = {"active", "reserved"}
RESERVATION_STATUSES = ACTIVE_RESERVATION_STATUSES | {"released", "expired", "realized", "cancelled"}

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
_TITLE_RE = re.compile(r"^#\s+ADR\s+\d+[:\s]+(.+)$", re.MULTILINE)
_NUMBER_RE = re.compile(r"^(\d{4})")

_DISCOVERY_QUERIES = {
    "how do we bootstrap": ["0001", "0003", "0004", "0005"],
    "authentication and identity": ["0007", "0056", "0147"],
    "ci and testing": ["0031", "0083", "0111", "0143"],
    "automation and workflows": ["0044", "0090"],
    "disaster recovery": ["0029", "0051"],
    "monitoring and observability": ["0011", "0027", "0032"],
    "networking and ingress": ["0012", "0013", "0014", "0015"],
    "vm management": ["0010", "0016", "0018"],
    "agent access and coordination": ["0007", "0090", "0131", "0132"],
    "multi-agent handoff": ["0163", "0164", "0165", "0166", "0167", "0168"],
    "deployment and release": ["0081", "0143"],
    "local services": ["0023", "0024", "0027", "0043", "0044"],
    "security hardening": ["0006", "0007", "0024", "0047", "0102"],
    "data and state": ["0033", "0037", "0038", "0132"],
}

DEFAULT_RESERVATIONS_CONTENT = """# ============================================================================
# ADR Reservation Ledger — ADR 0325
# ============================================================================
# Coordination surface for reserving future ADR numbers or windows.
# Active reservations participate in overlap checks and ADR allocation.
# Update manually or through ADR-aware tooling, then regenerate the ADR index:
#   python scripts/generate_adr_index.py --write
# ============================================================================

schema_version: 1
reservations: []
"""


@dataclass(frozen=True)
class AdrMeta:
    number: str
    title: str
    status: str
    implementation_status: str
    implemented_in_repo_version: str | None
    implemented_in_platform_version: str | None
    implemented_on: str | None
    date: str
    concern: str
    keywords: list[str]
    summary: str
    filename: str
    path: str

    def to_entry(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "adr": self.number,
            "title": self.title,
            "status": self.status,
            "implementation_status": self.implementation_status,
            "date": self.date,
            "concern": self.concern,
            "keywords": self.keywords,
            "summary": self.summary,
            "filename": self.filename,
            "path": self.path,
        }
        if self.implemented_in_repo_version:
            payload["implemented_in_repo_version"] = self.implemented_in_repo_version
        if self.implemented_in_platform_version:
            payload["implemented_in_platform_version"] = self.implemented_in_platform_version
        if self.implemented_on:
            payload["implemented_on"] = self.implemented_on
        return payload

    def to_compact_entry(self) -> dict[str, Any]:
        payload = {
            "adr": self.number,
            "title": self.title,
            "implementation_status": self.implementation_status,
            "concern": self.concern,
            "path": self.path,
        }
        if self.implemented_on:
            payload["implemented_on"] = self.implemented_on
        return payload


@dataclass(frozen=True)
class AdrReservation:
    reservation_id: str
    start: int
    end: int
    owner: str | None
    branch: str | None
    workstream: str | None
    reason: str
    reserved_on: str
    expires_on: str | None
    status: str

    @property
    def start_str(self) -> str:
        return f"{self.start:04d}"

    @property
    def end_str(self) -> str:
        return f"{self.end:04d}"

    @property
    def count(self) -> int:
        return self.end - self.start + 1

    def overlaps(self, start: int, end: int) -> bool:
        return not (end < self.start or start > self.end)

    def is_active(self) -> bool:
        return self.status.lower() in ACTIVE_RESERVATION_STATUSES

    def is_expired_candidate(self, today: dt.date) -> bool:
        if not self.is_active() or not self.expires_on or not _DATE_RE.match(self.expires_on):
            return False
        return self.expires_on < today.isoformat()

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.reservation_id,
            "start": self.start_str,
            "end": self.end_str,
            "reason": self.reason,
            "reserved_on": self.reserved_on,
            "status": self.status,
            "count": self.count,
        }
        if self.owner:
            payload["owner"] = self.owner
        if self.branch:
            payload["branch"] = self.branch
        if self.workstream:
            payload["workstream"] = self.workstream
        if self.expires_on:
            payload["expires_on"] = self.expires_on
        return payload


@dataclass(frozen=True)
class ReservationLedger:
    path: Path
    schema_version: int
    reservations: tuple[AdrReservation, ...]
    exists: bool = True

    def active(self) -> tuple[AdrReservation, ...]:
        return tuple(reservation for reservation in self.reservations if reservation.is_active())

    def expired_candidates(self, today: dt.date) -> tuple[AdrReservation, ...]:
        return tuple(reservation for reservation in self.active() if reservation.is_expired_candidate(today))


@dataclass(frozen=True)
class AllocationResult:
    start: int
    end: int
    existing_adrs: tuple[str, ...]
    reservations: tuple[AdrReservation, ...]

    @property
    def start_str(self) -> str:
        return f"{self.start:04d}"

    @property
    def end_str(self) -> str:
        return f"{self.end:04d}"

    @property
    def window_size(self) -> int:
        return self.end - self.start + 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "start": self.start_str,
            "end": self.end_str,
            "window_size": self.window_size,
            "existing_adr_conflicts": list(self.existing_adrs),
            "reservation_conflicts": [reservation.to_dict() for reservation in self.reservations],
        }


class IndentedSafeDumper(yaml.SafeDumper):
    def increase_indent(self, flow: bool = False, indentless: bool = False):  # type: ignore[override]
        return super().increase_indent(flow, False)


def repo_relative_path(path: Path, repo_root: Path = REPO_ROOT) -> str:
    return path.resolve().relative_to(repo_root.resolve()).as_posix()


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")


def _normalise_status(value: str, *, default: str) -> str:
    lower_value = value.lower()
    for normalized, variants in STATUS_NORMALIZATION_RULES:
        if any(variant in lower_value for variant in variants):
            return normalized
    return default


def _extract_value(text: str, key: str, default: str = "") -> str:
    escaped_key = re.escape(key)
    pattern = re.compile(rf"^[-*]\s+(?:\*\*)?{escaped_key}(?:\*\*)?:\s+(.+)$", re.IGNORECASE | re.MULTILINE)
    match = pattern.search(text)
    if match:
        return match.group(1).strip()
    header_pattern = re.compile(
        rf"^#{1, 2}\s+(?:\*\*)?{escaped_key}(?:\*\*)?:\s+(.+)$",
        re.IGNORECASE | re.MULTILINE,
    )
    match = header_pattern.search(text)
    if match:
        return match.group(1).strip()
    return default


def _clean_optional_value(value: str) -> str | None:
    stripped = value.strip()
    if not stripped or stripped.lower() in {"n/a", "na", "none"}:
        return None
    return stripped


def _extract_title(text: str) -> str:
    match = _TITLE_RE.search(text)
    if match:
        return match.group(1).strip()
    fallback = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    if fallback:
        return fallback.group(1).strip()
    return "Unknown"


def _extract_tags(text: str) -> list[str]:
    value = _extract_value(text, "Tags", "")
    if not value:
        return []
    tags: list[str] = []
    for item in value.split(","):
        tag = slugify(item)
        if tag and tag not in tags:
            tags.append(tag)
    return tags


def _extract_keywords(title: str, tags: list[str]) -> list[str]:
    words = re.findall(r"[a-z][a-z0-9\-]+", title.lower())
    stopwords = {"for", "and", "the", "with", "via", "of", "to", "in", "on", "a", "an"}
    keywords: list[str] = []
    for item in list(tags) + [word for word in words if word not in stopwords]:
        if item not in keywords:
            keywords.append(item)
    return keywords[:10]


def _infer_concern(title: str, keywords: list[str]) -> str:
    haystack = " ".join([title.lower(), *keywords])
    for concern, rules in CONCERN_RULES:
        if any(rule in haystack for rule in rules):
            return concern
    return "platform"


def _extract_summary(path: Path, title: str) -> str:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return title

    in_decision = False
    for line in lines[:120]:
        if re.match(r"^#{1,3}\s+Decision", line, re.IGNORECASE):
            in_decision = True
            continue
        if not in_decision:
            continue
        candidate = line.strip()
        if not candidate or candidate.startswith("#"):
            continue
        candidate = re.sub(r"[*_`]", "", candidate)
        candidate = re.sub(r"\[(.*?)\]\((.*?)\)", r"\1", candidate)
        return candidate[:160]
    return title


def _extract_date_value(text: str, key: str) -> str | None:
    value = _clean_optional_value(_extract_value(text, key, ""))
    if value is None:
        return None
    if not _DATE_RE.match(value):
        return None
    return value


def _extract_version_value(text: str, key: str) -> str | None:
    value = _clean_optional_value(_extract_value(text, key, ""))
    if value is None:
        return None
    if _VERSION_RE.match(value):
        return value
    return None


def parse_adr(path: Path, *, repo_root: Path | None = None) -> AdrMeta | None:
    match = _NUMBER_RE.match(path.name)
    if not match:
        return None
    number = match.group(1)
    repo_root = repo_root or path.parents[2]

    text = path.read_text(encoding="utf-8")
    header = "\n".join(text.splitlines()[:40])
    title = _extract_title(header)
    tags = _extract_tags(header)
    keywords = _extract_keywords(title, tags)
    status = _normalise_status(_extract_value(header, "Status", "Proposed"), default="Proposed")
    implementation_status = _normalise_status(
        _extract_value(header, "Implementation Status", status),
        default=status,
    )
    date = _extract_date_value(header, "Date") or "2026-03-21"
    implemented_in_repo_version = _extract_version_value(header, "Implemented In Repo Version")
    implemented_in_platform_version = _extract_version_value(header, "Implemented In Platform Version")
    implemented_on = _extract_date_value(header, "Implemented On")
    concern = _infer_concern(title, keywords)
    summary = _extract_summary(path, title)

    return AdrMeta(
        number=number,
        title=title,
        status=status,
        implementation_status=implementation_status,
        implemented_in_repo_version=implemented_in_repo_version,
        implemented_in_platform_version=implemented_in_platform_version,
        implemented_on=implemented_on,
        date=date,
        concern=concern,
        keywords=keywords,
        summary=summary,
        filename=path.name,
        path=repo_relative_path(path, repo_root),
    )


def load_adrs(adr_dir: Path = ADR_DIR, *, repo_root: Path | None = None) -> list[AdrMeta]:
    repo_root = repo_root or adr_dir.parents[1]
    adrs: list[AdrMeta] = []
    for path in sorted(adr_dir.glob("[0-9][0-9][0-9][0-9]-*.md")):
        adr = parse_adr(path, repo_root=repo_root)
        if adr is not None:
            adrs.append(adr)
    return adrs


def _coerce_adr_number(value: Any, field_name: str) -> int:
    if isinstance(value, int):
        number = value
    elif isinstance(value, str) and value.strip():
        number = int(value.strip())
    else:
        raise ValueError(f"reservation field '{field_name}' must be a non-empty ADR number")
    if number < 1 or number > 9999:
        raise ValueError(f"reservation field '{field_name}' must be between 0001 and 9999")
    return number


def load_reservation_ledger(path: Path = RESERVATIONS_PATH) -> ReservationLedger:
    if not path.exists():
        return ReservationLedger(path=path, schema_version=1, reservations=(), exists=False)

    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    raw_reservations = payload.get("reservations", [])
    if not isinstance(raw_reservations, list):
        raise ValueError(f"{path} must define reservations as a list")

    reservations: list[AdrReservation] = []
    for index, item in enumerate(raw_reservations):
        if not isinstance(item, dict):
            raise ValueError(f"{path}.reservations[{index}] must be a mapping")
        reservation_id = _clean_optional_value(str(item.get("id", "") or ""))
        if reservation_id is None:
            raise ValueError(f"{path}.reservations[{index}].id is required")
        start = _coerce_adr_number(item.get("start"), f"reservations[{index}].start")
        end = _coerce_adr_number(item.get("end", item.get("start")), f"reservations[{index}].end")
        if end < start:
            raise ValueError(f"{path}.reservations[{index}] end must be >= start")
        reason = _clean_optional_value(str(item.get("reason", "") or ""))
        if reason is None:
            raise ValueError(f"{path}.reservations[{index}].reason is required")
        reserved_on = _clean_optional_value(str(item.get("reserved_on", "") or ""))
        if reserved_on is None or not _DATE_RE.match(reserved_on):
            raise ValueError(f"{path}.reservations[{index}].reserved_on must be YYYY-MM-DD")
        expires_on_raw = _clean_optional_value(str(item.get("expires_on", "") or ""))
        if expires_on_raw is not None and not _DATE_RE.match(expires_on_raw):
            raise ValueError(f"{path}.reservations[{index}].expires_on must be YYYY-MM-DD when set")
        status = slugify(str(item.get("status", "active") or "active"))
        if status not in RESERVATION_STATUSES:
            raise ValueError(f"{path}.reservations[{index}].status must be one of {sorted(RESERVATION_STATUSES)}")
        reservations.append(
            AdrReservation(
                reservation_id=reservation_id,
                start=start,
                end=end,
                owner=_clean_optional_value(str(item.get("owner", "") or "")),
                branch=_clean_optional_value(str(item.get("branch", "") or "")),
                workstream=_clean_optional_value(str(item.get("workstream", "") or "")),
                reason=reason,
                reserved_on=reserved_on,
                expires_on=expires_on_raw,
                status=status,
            )
        )

    return ReservationLedger(
        path=path,
        schema_version=int(payload.get("schema_version", 1)),
        reservations=tuple(reservations),
        exists=True,
    )


def validate_reservation_ledger(
    ledger: ReservationLedger,
    adrs: list[AdrMeta],
    *,
    today: dt.date | None = None,
) -> list[str]:
    issues: list[str] = []
    seen_ids: set[str] = set()
    today = today or dt.date.today()
    committed_numbers = {int(adr.number): adr.number for adr in adrs}

    for reservation in ledger.reservations:
        if reservation.reservation_id in seen_ids:
            issues.append(f"duplicate reservation id '{reservation.reservation_id}' in {ledger.path}")
        seen_ids.add(reservation.reservation_id)
        if reservation.is_expired_candidate(today):
            issues.append(
                f"reservation '{reservation.reservation_id}' is still active even though expires_on={reservation.expires_on}"
            )
        for number in range(reservation.start, reservation.end + 1):
            if number in committed_numbers:
                issues.append(
                    f"reservation '{reservation.reservation_id}' overlaps committed ADR {committed_numbers[number]}"
                )
                break

    active = ledger.active()
    for index, left in enumerate(active):
        for right in active[index + 1 :]:
            if left.overlaps(right.start, right.end):
                issues.append(f"active reservations '{left.reservation_id}' and '{right.reservation_id}' overlap")

    return issues


def find_conflicts(
    start: int,
    end: int,
    adrs: list[AdrMeta],
    ledger: ReservationLedger,
) -> AllocationResult:
    existing = tuple(adr.number for adr in adrs if start <= int(adr.number) <= end)
    reservations = tuple(reservation for reservation in ledger.active() if reservation.overlaps(start, end))
    return AllocationResult(start=start, end=end, existing_adrs=existing, reservations=reservations)


def next_available_window(
    adrs: list[AdrMeta],
    ledger: ReservationLedger,
    *,
    window_size: int = 1,
    start: int | None = None,
) -> AllocationResult:
    if window_size < 1:
        raise ValueError("window_size must be >= 1")

    if start is not None:
        end = start + window_size - 1
        conflicts = find_conflicts(start, end, adrs, ledger)
        if conflicts.existing_adrs or conflicts.reservations:
            raise ValueError(f"requested ADR window {conflicts.start_str}-{conflicts.end_str} is already occupied")
        return conflicts

    high_water_mark = 0
    if adrs:
        high_water_mark = max(high_water_mark, max(int(adr.number) for adr in adrs))
    if ledger.active():
        high_water_mark = max(high_water_mark, max(reservation.end for reservation in ledger.active()))

    candidate = max(1, high_water_mark + 1)
    while candidate <= 9999:
        end = candidate + window_size - 1
        if end > 9999:
            break
        conflicts = find_conflicts(candidate, end, adrs, ledger)
        if not conflicts.existing_adrs and not conflicts.reservations:
            return conflicts
        candidate = end + 1

    raise ValueError("no ADR window available inside 0001-9999")


def range_label_for(number: str | int) -> str:
    value = int(number)
    start = (value // 100) * 100
    end = start + 99
    return f"{start:04d}-{end:04d}"


def status_slug(value: str) -> str:
    return slugify(value)


def _count_by_order(values: list[str], order: tuple[str, ...]) -> dict[str, int]:
    counts = Counter(values)
    ordered: dict[str, int] = {}
    for key in order:
        if counts.get(key):
            ordered[key] = counts[key]
    for key in sorted(counts):
        if key not in ordered:
            ordered[key] = counts[key]
    return ordered


def _render_yaml_document(payload: dict[str, Any], *, title: str, adr_ref: str = "ADR 0325") -> str:
    header = (
        "# ============================================================================\n"
        f"# {title} — {adr_ref}\n"
        "# ============================================================================\n"
        "# GENERATED FILE — do not edit by hand\n"
        f"# Regenerate: {GENERATE_COMMAND}\n"
        "# ============================================================================\n\n"
    )
    body = yaml.dump(
        payload,
        Dumper=IndentedSafeDumper,
        default_flow_style=False,
        sort_keys=False,
        allow_unicode=True,
        indent=2,
        width=120,
    )
    body = re.sub(r"^(\s*)-\s{2,}", r"\1- ", body, flags=re.MULTILINE)
    return header + body


def build_generated_index_documents(
    adrs: list[AdrMeta],
    ledger: ReservationLedger,
    *,
    repo_root: Path = REPO_ROOT,
    adr_dir: Path = ADR_DIR,
    generated_on: dt.date | None = None,
) -> dict[Path, str]:
    generated_on = generated_on or dt.date.today()
    range_groups: dict[str, list[AdrMeta]] = defaultdict(list)
    concern_groups: dict[str, list[AdrMeta]] = defaultdict(list)
    status_groups: dict[str, list[AdrMeta]] = defaultdict(list)

    for adr in adrs:
        range_groups[range_label_for(adr.number)].append(adr)
        concern_groups[adr.concern].append(adr)
        status_groups[adr.implementation_status].append(adr)

    next_window = next_available_window(adrs, ledger)
    active_reservations = ledger.active()
    expired_candidates = ledger.expired_candidates(generated_on)

    range_facets = [
        {
            "label": label,
            "path": repo_relative_path(adr_dir / "index" / "by-range" / f"{label}.yaml", repo_root),
            "count": len(entries),
            "first_adr": entries[0].number,
            "last_adr": entries[-1].number,
        }
        for label, entries in sorted(range_groups.items())
    ]
    concern_facets = [
        {
            "concern": concern,
            "path": repo_relative_path(adr_dir / "index" / "by-concern" / f"{slugify(concern)}.yaml", repo_root),
            "count": len(entries),
        }
        for concern, entries in sorted(concern_groups.items())
    ]
    status_facets = [
        {
            "implementation_status": status,
            "slug": status_slug(status),
            "path": repo_relative_path(adr_dir / "index" / "by-status" / f"{status_slug(status)}.yaml", repo_root),
            "count": len(entries),
        }
        for status, entries in sorted(
            status_groups.items(),
            key=lambda item: (
                IMPLEMENTATION_STATUS_ORDER.index(item[0])
                if item[0] in IMPLEMENTATION_STATUS_ORDER
                else len(IMPLEMENTATION_STATUS_ORDER),
                item[0],
            ),
        )
    ]

    root_manifest = {
        "schema_version": 2,
        "generated": generated_on.isoformat(),
        "purpose": "Compact ADR discovery manifest that points readers to shard-sized ADR metadata surfaces.",
        "total_adrs": len(adrs),
        "adr_number_range": {
            "first": adrs[0].number if adrs else None,
            "last": adrs[-1].number if adrs else None,
            "next_available": next_window.start_str,
        },
        "implementation_status_summary": _count_by_order(
            [adr.implementation_status for adr in adrs],
            IMPLEMENTATION_STATUS_ORDER,
        ),
        "decision_status_summary": _count_by_order(
            [adr.status for adr in adrs],
            DECISION_STATUS_ORDER,
        ),
        "facets": {
            "by_range": range_facets,
            "by_concern": concern_facets,
            "by_status": status_facets,
        },
        "reservation_ledger": {
            "path": repo_relative_path(ledger.path, repo_root),
            "total_reservations": len(ledger.reservations),
            "active_reservations": len(active_reservations),
            "expired_candidates": len(expired_candidates),
            "next_available_adr": next_window.start_str,
        },
        "latest_adrs": [adr.to_compact_entry() for adr in reversed(adrs[-10:])],
        "discovery_queries": _DISCOVERY_QUERIES,
        "agent_discovery_tips": [
            "Read latest_adrs for the newest decisions before opening older ADRs.",
            "Load one range shard for chronological browsing instead of the whole corpus.",
            "Use concern and status shards for focused discovery queries.",
            "Check docs/adr/index/reservations.yaml before allocating new ADR numbers.",
            "Use 'python scripts/adr_query_tool.py allocate --window-size N' for reservation-safe ADR numbering.",
        ],
    }

    documents: dict[Path, str] = {
        adr_dir / ".index.yaml": _render_yaml_document(root_manifest, title="ADR Discovery Root Manifest"),
    }

    for label, entries in sorted(range_groups.items()):
        payload = {
            "schema_version": 2,
            "generated": generated_on.isoformat(),
            "facet": "range",
            "label": label,
            "range": {"start": label[:4], "end": label[-4:]},
            "total_adrs": len(entries),
            "adrs": [entry.to_entry() for entry in entries],
        }
        documents[adr_dir / "index" / "by-range" / f"{label}.yaml"] = _render_yaml_document(
            payload,
            title=f"ADR Range Shard {label}",
        )

    for concern, entries in sorted(concern_groups.items()):
        payload = {
            "schema_version": 2,
            "generated": generated_on.isoformat(),
            "facet": "concern",
            "concern": concern,
            "total_adrs": len(entries),
            "adrs": [entry.to_entry() for entry in entries],
        }
        documents[adr_dir / "index" / "by-concern" / f"{slugify(concern)}.yaml"] = _render_yaml_document(
            payload,
            title=f"ADR Concern Shard {concern}",
        )

    for status, entries in sorted(
        status_groups.items(),
        key=lambda item: (
            IMPLEMENTATION_STATUS_ORDER.index(item[0])
            if item[0] in IMPLEMENTATION_STATUS_ORDER
            else len(IMPLEMENTATION_STATUS_ORDER),
            item[0],
        ),
    ):
        payload = {
            "schema_version": 2,
            "generated": generated_on.isoformat(),
            "facet": "status",
            "implementation_status": status,
            "slug": status_slug(status),
            "total_adrs": len(entries),
            "adrs": [entry.to_entry() for entry in entries],
        }
        documents[adr_dir / "index" / "by-status" / f"{status_slug(status)}.yaml"] = _render_yaml_document(
            payload,
            title=f"ADR Status Shard {status}",
        )

    return documents


def generated_shard_paths(adr_dir: Path = ADR_DIR) -> set[Path]:
    paths: set[Path] = set()
    for directory in (
        adr_dir / "index" / "by-range",
        adr_dir / "index" / "by-concern",
        adr_dir / "index" / "by-status",
    ):
        if not directory.exists():
            continue
        paths.update(path for path in directory.glob("*.yaml") if path.is_file())
    return paths


def check_generated_index_documents(expected_documents: dict[Path, str], *, adr_dir: Path = ADR_DIR) -> list[str]:
    issues: list[str] = []
    for path, expected_content in sorted(expected_documents.items()):
        if not path.exists():
            issues.append(f"missing generated ADR discovery file: {repo_relative_path(path, adr_dir.parents[1])}")
            continue
        actual_content = path.read_text(encoding="utf-8")
        if actual_content != expected_content:
            issues.append(f"stale generated ADR discovery file: {repo_relative_path(path, adr_dir.parents[1])}")

    expected_shards = {path for path in expected_documents if path != adr_dir / ".index.yaml"}
    extra_shards = generated_shard_paths(adr_dir) - expected_shards
    for path in sorted(extra_shards):
        issues.append(f"unexpected generated ADR shard: {repo_relative_path(path, adr_dir.parents[1])}")

    return issues


def write_generated_index_documents(expected_documents: dict[Path, str], *, adr_dir: Path = ADR_DIR) -> None:
    index_root = adr_dir / "index"
    index_root.mkdir(parents=True, exist_ok=True)
    (index_root / "by-range").mkdir(parents=True, exist_ok=True)
    (index_root / "by-concern").mkdir(parents=True, exist_ok=True)
    (index_root / "by-status").mkdir(parents=True, exist_ok=True)

    expected_shards = {path for path in expected_documents if path != adr_dir / ".index.yaml"}
    for path in generated_shard_paths(adr_dir) - expected_shards:
        path.unlink()

    for path, content in expected_documents.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def ensure_reservations_file(path: Path = RESERVATIONS_PATH) -> bool:
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(DEFAULT_RESERVATIONS_CONTENT, encoding="utf-8")
    return True


def load_root_index(path: Path = INDEX_PATH) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a mapping")
    return payload


def load_shard_entries(root_manifest: dict[str, Any], *, repo_root: Path = REPO_ROOT) -> list[dict[str, Any]]:
    if "adr_index" in root_manifest:
        entries = root_manifest.get("adr_index") or []
        return list(entries) if isinstance(entries, list) else []

    facets = root_manifest.get("facets") or {}
    range_facets = facets.get("by_range") or []
    entries: list[dict[str, Any]] = []
    for facet in range_facets:
        if not isinstance(facet, dict) or not isinstance(facet.get("path"), str):
            continue
        shard_path = repo_root / facet["path"]
        if not shard_path.exists():
            continue
        payload = yaml.safe_load(shard_path.read_text(encoding="utf-8")) or {}
        shard_entries = payload.get("adrs") or []
        if isinstance(shard_entries, list):
            entries.extend(entry for entry in shard_entries if isinstance(entry, dict))
    return entries
