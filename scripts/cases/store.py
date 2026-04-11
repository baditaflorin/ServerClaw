"""ADR 0118 — Failure case store backed by a local JSON file.

Production deployments should migrate to the Postgres schema defined in
migrations/0018_cases_schema.sql.  The JSON store is used for local
development, tests, and Windmill workers that have the repo checkout
mounted but no live database connection.
"""

from __future__ import annotations

import copy
import json
import subprocess
import uuid
from datetime import datetime, timedelta
try:
    from datetime import UTC
except ImportError:  # Python < 3.11
    from datetime import timezone
    UTC = timezone.utc  # type: ignore[assignment]
from pathlib import Path
from typing import Any

from controller_automation_toolkit import load_json, load_yaml, repo_path, write_json
from mutation_audit import resolve_local_sink_path

from .retrieval import CaseRetriever


DEFAULT_CASES_PATH = repo_path(".local", "state", "cases", "failure_cases.json")
DEFAULT_CATEGORY_PATH = repo_path("config", "case-root-cause-categories.yaml")
DEFAULT_MUTATION_AUDIT_PATH = resolve_local_sink_path()
ALLOWED_CASE_STATUSES = {"open", "resolved", "archived"}


def utc_now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def isoformat(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def normalize_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.splitlines() if item.strip()]
    if not isinstance(value, list):
        raise ValueError("expected a list of strings")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError("list entries must be non-empty strings")
        result.append(item.strip())
    return result


def normalize_signals(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return {str(key): entry for key, entry in value.items()}
    if isinstance(value, list):
        result: dict[str, Any] = {}
        for item in value:
            if not isinstance(item, dict):
                raise ValueError("correlated_signals list entries must be objects")
            key = item.get("key")
            if not isinstance(key, str) or not key.strip():
                raise ValueError("correlated_signals entries require a non-empty key")
            result[key.strip()] = item.get("value")
        return result
    raise ValueError("correlated_signals must be an object or list of key/value objects")


def normalize_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("expected a string")
    cleaned = value.strip()
    return cleaned or None


class CaseStore:
    """CRUD and search interface for ADR 0118 failure cases."""

    def __init__(
        self,
        *,
        path: Path = DEFAULT_CASES_PATH,
        categories_path: Path = DEFAULT_CATEGORY_PATH,
        mutation_audit_path: Path | None = DEFAULT_MUTATION_AUDIT_PATH,
    ) -> None:
        self.path = path
        self.categories_path = categories_path
        self.mutation_audit_path = mutation_audit_path
        self.retriever = CaseRetriever()

    # ------------------------------------------------------------------
    # Categories
    # ------------------------------------------------------------------

    def categories(self) -> list[str]:
        """Load the controlled vocabulary from config/case-root-cause-categories.yaml."""
        payload = load_yaml(self.categories_path)
        if not isinstance(payload, list):
            raise ValueError(f"{self.categories_path} must define a list")
        categories: list[str] = []
        for index, item in enumerate(payload):
            if not isinstance(item, str) or not item.strip():
                raise ValueError(f"{self.categories_path}[{index}] must be a non-empty string")
            categories.append(item.strip())
        return categories

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def _load_payload(self) -> dict[str, Any]:
        payload = load_json(self.path, default={"schema_version": "1.0.0", "cases": []})
        if not isinstance(payload, dict):
            raise ValueError(f"{self.path} must contain a JSON object")
        cases = payload.get("cases")
        if not isinstance(cases, list):
            raise ValueError(f"{self.path}.cases must be a list")
        payload.setdefault("schema_version", "1.0.0")
        return payload

    def _save_payload(self, payload: dict[str, Any]) -> None:
        write_json(self.path, payload, indent=2, sort_keys=False)

    def _next_numeric_id(self, payload: dict[str, Any]) -> int:
        numeric_ids = [int(item.get("id", 0)) for item in payload["cases"] if str(item.get("id", "")).isdigit()]
        return (max(numeric_ids) if numeric_ids else 0) + 1

    def _lookup(self, payload: dict[str, Any], case_id: str) -> tuple[int, dict[str, Any]]:
        for index, case in enumerate(payload["cases"]):
            if str(case.get("case_id")) == case_id or str(case.get("id")) == case_id:
                return index, case
        raise KeyError(f"case '{case_id}' not found")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def list_cases(
        self,
        *,
        status: str | None = None,
        affected_service: str | None = None,
        root_cause_category: str | None = None,
    ) -> list[dict[str, Any]]:
        payload = self._load_payload()
        filtered: list[dict[str, Any]] = []
        for case in payload["cases"]:
            if status and case.get("status") != status:
                continue
            if affected_service and case.get("affected_service") != affected_service:
                continue
            if root_cause_category and case.get("root_cause_category") != root_cause_category:
                continue
            filtered.append(copy.deepcopy(case))
        filtered.sort(
            key=lambda item: (
                item.get("updated_at", ""),
                item.get("created_at", ""),
            ),
            reverse=True,
        )
        return filtered

    def get(self, case_id: str) -> dict[str, Any]:
        _index, case = self._lookup(self._load_payload(), case_id)
        return copy.deepcopy(case)

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        title = normalize_optional_text(payload.get("title"))
        affected_service = normalize_optional_text(payload.get("affected_service"))
        if not title:
            raise ValueError("title is required")
        if not affected_service:
            raise ValueError("affected_service is required")

        data = self._load_payload()
        now = isoformat(utc_now())
        status = normalize_optional_text(payload.get("status")) or "open"
        if status not in ALLOWED_CASE_STATUSES:
            raise ValueError(f"status must be one of {sorted(ALLOWED_CASE_STATUSES)}")

        case: dict[str, Any] = {
            "id": self._next_numeric_id(data),
            "case_id": str(uuid.uuid4()),
            "incident_id": normalize_optional_text(payload.get("incident_id")),
            "created_at": now,
            "updated_at": now,
            "status": status,
            "title": title,
            "affected_service": affected_service,
            "symptoms": normalize_list(payload.get("symptoms")),
            "correlated_signals": normalize_signals(payload.get("correlated_signals")),
            "root_cause": normalize_optional_text(payload.get("root_cause")),
            "root_cause_category": normalize_optional_text(payload.get("root_cause_category")),
            "remediation_steps": normalize_list(payload.get("remediation_steps")),
            "verification_command": normalize_optional_text(payload.get("verification_command")),
            "incident_duration_minutes": payload.get("incident_duration_minutes"),
            "first_observed_at": normalize_optional_text(payload.get("first_observed_at")),
            "resolved_at": normalize_optional_text(payload.get("resolved_at")),
            "triage_report_id": normalize_optional_text(payload.get("triage_report_id")),
            "ledger_event_ids": normalize_list(payload.get("ledger_event_ids")),
            "annotations": normalize_list(payload.get("annotations")),
        }
        if case["root_cause_category"] and case["root_cause_category"] not in self.categories():
            raise ValueError("root_cause_category must be declared in config/case-root-cause-categories.yaml")
        if case["status"] == "resolved":
            self._validate_resolution(case)
            case["resolved_at"] = case["resolved_at"] or now

        data["cases"].append(case)
        self._save_payload(data)
        return copy.deepcopy(case)

    def update(self, case_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        data = self._load_payload()
        index, case = self._lookup(data, case_id)

        if normalize_optional_text(patch.get("status")) == "resolved":
            return self.close(case_id, patch)

        updated = copy.deepcopy(case)
        for field in (
            "title",
            "incident_id",
            "affected_service",
            "root_cause",
            "root_cause_category",
            "verification_command",
            "first_observed_at",
            "resolved_at",
            "triage_report_id",
        ):
            if field in patch:
                updated[field] = normalize_optional_text(patch.get(field))
        if "symptoms" in patch:
            updated["symptoms"] = normalize_list(patch.get("symptoms"))
        if "correlated_signals" in patch:
            updated["correlated_signals"] = normalize_signals(patch.get("correlated_signals"))
        if "remediation_steps" in patch:
            updated["remediation_steps"] = normalize_list(patch.get("remediation_steps"))
        if "ledger_event_ids" in patch:
            updated["ledger_event_ids"] = normalize_list(patch.get("ledger_event_ids"))
        if "annotations" in patch:
            updated["annotations"] = normalize_list(patch.get("annotations"))
        if "incident_duration_minutes" in patch:
            updated["incident_duration_minutes"] = patch.get("incident_duration_minutes")

        status = normalize_optional_text(patch.get("status"))
        if status:
            if status not in ALLOWED_CASE_STATUSES:
                raise ValueError(f"status must be one of {sorted(ALLOWED_CASE_STATUSES)}")
            updated["status"] = status
        if updated.get("root_cause_category") and updated["root_cause_category"] not in self.categories():
            raise ValueError("root_cause_category must be declared in config/case-root-cause-categories.yaml")
        updated["updated_at"] = isoformat(utc_now())
        data["cases"][index] = updated
        self._save_payload(data)
        return copy.deepcopy(updated)

    def _validate_resolution(self, resolution: dict[str, Any]) -> None:
        root_cause = normalize_optional_text(resolution.get("root_cause"))
        if not root_cause:
            raise ValueError("root_cause is required when resolving a case")
        category = normalize_optional_text(resolution.get("root_cause_category"))
        if not category:
            raise ValueError("root_cause_category is required when resolving a case")
        if category not in self.categories():
            raise ValueError("root_cause_category must be declared in config/case-root-cause-categories.yaml")
        remediation_steps = normalize_list(resolution.get("remediation_steps"))
        if not remediation_steps:
            raise ValueError("at least one remediation_step is required when resolving a case")

    def close(self, case_id: str, resolution: dict[str, Any]) -> dict[str, Any]:
        """Resolve a case, enforcing that all required resolution fields are present."""
        data = self._load_payload()
        index, case = self._lookup(data, case_id)
        updated = copy.deepcopy(case)
        updated["root_cause"] = normalize_optional_text(resolution.get("root_cause"))
        updated["root_cause_category"] = normalize_optional_text(resolution.get("root_cause_category"))
        updated["remediation_steps"] = normalize_list(resolution.get("remediation_steps"))
        updated["verification_command"] = normalize_optional_text(
            resolution.get("verification_command")
        ) or updated.get("verification_command")
        if "ledger_event_ids" in resolution:
            updated["ledger_event_ids"] = normalize_list(resolution.get("ledger_event_ids"))
        if "annotations" in resolution:
            updated["annotations"] = normalize_list(resolution.get("annotations"))
        self._validate_resolution(updated)
        now = isoformat(utc_now())
        updated["status"] = "resolved"
        updated["resolved_at"] = normalize_optional_text(resolution.get("resolved_at")) or now
        updated["updated_at"] = now

        first_observed = parse_timestamp(updated.get("first_observed_at"))
        resolved_at = parse_timestamp(updated.get("resolved_at"))
        if first_observed and resolved_at:
            updated["incident_duration_minutes"] = max(
                int((resolved_at - first_observed).total_seconds() // 60),
                0,
            )

        data["cases"][index] = updated
        self._save_payload(data)
        return copy.deepcopy(updated)

    def search(
        self,
        query: str,
        *,
        affected_service: str | None = None,
        current_signals: dict[str, Any] | None = None,
        category_hints: list[str] | None = None,
        status: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        cases = self.list_cases(status=status, affected_service=affected_service)
        return self.retriever.search(
            cases=cases,
            query=query,
            affected_service=affected_service,
            current_signals=current_signals,
            category_hints=category_hints,
            limit=limit,
        )

    def get_similar(
        self,
        *,
        affected_service: str,
        symptoms: list[str] | None = None,
        log_lines: list[str] | None = None,
        current_signals: dict[str, Any] | None = None,
        category_hints: list[str] | None = None,
        limit: int = 3,
    ) -> list[dict[str, Any]]:
        """Return top *limit* resolved/archived cases most similar to a new incident."""
        candidates = [
            case
            for case in self.list_cases(affected_service=affected_service)
            if case.get("status") in {"resolved", "archived"}
        ]
        query_parts = [
            affected_service,
            *(symptoms or []),
            *(log_lines or []),
        ]
        return self.retriever.find_similar(
            cases=candidates,
            query=" ".join(part for part in query_parts if part),
            affected_service=affected_service,
            current_signals=current_signals,
            category_hints=category_hints,
            limit=limit,
        )

    def replay(self, case_id: str) -> dict[str, Any]:
        """Reconstruct the mutation timeline for a case from the local audit sink."""
        case = self.get(case_id)
        keys = {
            case.get("case_id"),
            case.get("incident_id"),
            case.get("triage_report_id"),
            *case.get("ledger_event_ids", []),
        }
        keys = {item for item in keys if item}
        timeline: list[dict[str, Any]] = []
        if self.mutation_audit_path and self.mutation_audit_path.exists():
            for line in self.mutation_audit_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                event = json.loads(line)
                if event.get("correlation_id") in keys:
                    timeline.append(event)
        timeline.sort(key=lambda item: item.get("ts", ""))
        return {
            "case": case,
            "timeline": timeline,
            "timeline_count": len(timeline),
        }

    def audit_quality(
        self,
        *,
        now: datetime | None = None,
        archive_after_days: int = 90,
        verify_commands: bool = False,
        command_runner: Any | None = None,
    ) -> dict[str, Any]:
        """Audit all cases for quality issues and archive stale open cases."""
        now = now or utc_now()
        payload = self._load_payload()
        report: dict[str, Any] = {
            "generated_at": isoformat(now),
            "flagged_missing_root_cause": [],
            "verification_results": [],
            "archived_cases": [],
        }
        stale_threshold = now - timedelta(days=archive_after_days)
        changed = False

        for case in payload["cases"]:
            # Flag resolved cases without root_cause.
            if case.get("status") == "resolved" and not normalize_optional_text(case.get("root_cause")):
                report["flagged_missing_root_cause"].append(
                    {
                        "case_id": case["case_id"],
                        "title": case["title"],
                        "affected_service": case["affected_service"],
                    }
                )

            # Archive open cases older than archive_after_days.
            created_at = parse_timestamp(case.get("created_at"))
            if case.get("status") == "open" and created_at and created_at <= stale_threshold:
                case["status"] = "archived"
                case["updated_at"] = isoformat(now)
                annotations = case.setdefault("annotations", [])
                annotations.append(f"Archived automatically after {archive_after_days} days without closure.")
                report["archived_cases"].append({"case_id": case["case_id"], "title": case["title"]})
                changed = True

            # Optionally re-execute verification_command.
            if case.get("verification_command"):
                if not verify_commands:
                    report["verification_results"].append(
                        {
                            "case_id": case["case_id"],
                            "status": "skipped",
                            "reason": "verification_command execution disabled for this run",
                        }
                    )
                    continue
                runner = command_runner or self._run_verification_command
                report["verification_results"].append(runner(case))

        if changed:
            self._save_payload(payload)

        report["summary"] = {
            "cases_reviewed": len(payload["cases"]),
            "missing_root_cause_count": len(report["flagged_missing_root_cause"]),
            "verification_count": len(report["verification_results"]),
            "archived_count": len(report["archived_cases"]),
        }
        return report

    @staticmethod
    def _run_verification_command(case: dict[str, Any]) -> dict[str, Any]:
        command = str(case.get("verification_command", "")).strip()
        if not command:
            return {
                "case_id": case["case_id"],
                "status": "skipped",
                "reason": "no verification command",
            }
        completed = subprocess.run(
            command,
            cwd=repo_path(),
            shell=True,
            text=True,
            capture_output=True,
            check=False,
        )
        return {
            "case_id": case["case_id"],
            "status": "pass" if completed.returncode == 0 else "fail",
            "exit_code": completed.returncode,
            "stdout": completed.stdout.strip(),
            "stderr": completed.stderr.strip(),
        }
