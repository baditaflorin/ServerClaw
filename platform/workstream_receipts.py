"""ADR 0357: Idempotent Workstream Apply Receipts.

Provides a simple state machine for tracking workstream apply status.
Receipts are written to receipts/live-applies/ as YAML files, keyed by
workstream ID.

State machine:
    (none) → pending → in_progress → completed
                                    → failed
                                    → partial

Guard usage (prevent duplicate applies):
    receipt = WorkstreamApplyReceipts(repo_root)
    state = receipt.current_state("ws-0347")
    if state == ApplyState.COMPLETED:
        print("Already applied — skipping")
        return
    if state == ApplyState.IN_PROGRESS:
        raise RuntimeError("Another agent is already applying ws-0347")
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

try:
    import yaml
    _YAML_AVAILABLE = True
except ImportError:
    _YAML_AVAILABLE = False


RECEIPTS_SUBDIR = Path("receipts") / "live-applies"
RECEIPT_SCHEMA_VERSION = "1.1.0"


class ApplyState(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"

    def is_terminal(self) -> bool:
        return self in {ApplyState.COMPLETED, ApplyState.FAILED, ApplyState.PARTIAL}

    def is_active(self) -> bool:
        return self is ApplyState.IN_PROGRESS


@dataclass
class WorkstreamApplyReceipt:
    workstream_id: str
    state: ApplyState
    schema_version: str = RECEIPT_SCHEMA_VERSION
    started_at: str = ""
    completed_at: str = ""
    applied_by: str = ""
    repo_version: str = ""
    adr: str = ""
    summary: str = ""
    targets: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["state"] = self.state.value
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkstreamApplyReceipt:
        state_raw = data.get("state", ApplyState.PENDING.value)
        try:
            state = ApplyState(state_raw)
        except ValueError:
            state = ApplyState.PENDING
        return cls(
            workstream_id=str(data.get("workstream_id", "")),
            state=state,
            schema_version=str(data.get("schema_version", RECEIPT_SCHEMA_VERSION)),
            started_at=str(data.get("started_at", "")),
            completed_at=str(data.get("completed_at", "")),
            applied_by=str(data.get("applied_by", "")),
            repo_version=str(data.get("repo_version", "")),
            adr=str(data.get("adr", "")),
            summary=str(data.get("summary", "")),
            targets=list(data.get("targets", [])),
            errors=list(data.get("errors", [])),
            notes=list(data.get("notes", [])),
        )


def _isoformat_now() -> str:
    import datetime
    return datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


class WorkstreamApplyReceipts:
    """Read and write workstream apply receipts.

    Args:
        repo_root: Path to the repository root. Receipts are stored under
                   {repo_root}/receipts/live-applies/.
    """

    def __init__(self, repo_root: Path | str = ".") -> None:
        self._receipts_dir = Path(repo_root) / RECEIPTS_SUBDIR

    def _receipt_path(self, workstream_id: str) -> Path:
        return self._receipts_dir / f"{workstream_id}-apply-receipt.yaml"

    def current_state(self, workstream_id: str) -> ApplyState | None:
        """Return current apply state or None if no receipt exists."""
        path = self._receipt_path(workstream_id)
        if not path.exists():
            return None
        receipt = self._read(path)
        return receipt.state if receipt else None

    def read(self, workstream_id: str) -> WorkstreamApplyReceipt | None:
        """Return the full receipt or None if not found."""
        path = self._receipt_path(workstream_id)
        if not path.exists():
            return None
        return self._read(path)

    def write(self, receipt: WorkstreamApplyReceipt) -> Path:
        """Write (or overwrite) a receipt. Returns the path written."""
        self._receipts_dir.mkdir(parents=True, exist_ok=True)
        path = self._receipt_path(receipt.workstream_id)
        data = receipt.as_dict()
        if _YAML_AVAILABLE:
            with path.open("w") as f:
                yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
        else:
            import json
            path = path.with_suffix(".json")
            with path.open("w") as f:
                json.dump(data, f, indent=2)
        return path

    def start(
        self,
        workstream_id: str,
        *,
        applied_by: str = "",
        repo_version: str = "",
        adr: str = "",
        summary: str = "",
        targets: list[dict[str, Any]] | None = None,
    ) -> WorkstreamApplyReceipt:
        """Transition to IN_PROGRESS state. Raises if already in_progress."""
        existing_state = self.current_state(workstream_id)
        if existing_state is ApplyState.IN_PROGRESS:
            raise RuntimeError(
                f"Workstream '{workstream_id}' apply is already in_progress — "
                "another agent may be running. Check the receipt before retrying."
            )
        receipt = WorkstreamApplyReceipt(
            workstream_id=workstream_id,
            state=ApplyState.IN_PROGRESS,
            started_at=_isoformat_now(),
            applied_by=applied_by,
            repo_version=repo_version,
            adr=adr,
            summary=summary,
            targets=targets or [],
        )
        self.write(receipt)
        return receipt

    def complete(
        self,
        workstream_id: str,
        *,
        notes: list[str] | None = None,
    ) -> WorkstreamApplyReceipt:
        """Transition to COMPLETED state."""
        return self._finish(workstream_id, ApplyState.COMPLETED, notes=notes)

    def fail(
        self,
        workstream_id: str,
        *,
        errors: list[str] | None = None,
        notes: list[str] | None = None,
    ) -> WorkstreamApplyReceipt:
        """Transition to FAILED state."""
        return self._finish(workstream_id, ApplyState.FAILED, errors=errors, notes=notes)

    def partial(
        self,
        workstream_id: str,
        *,
        errors: list[str] | None = None,
        notes: list[str] | None = None,
    ) -> WorkstreamApplyReceipt:
        """Transition to PARTIAL state (some targets succeeded, some failed)."""
        return self._finish(workstream_id, ApplyState.PARTIAL, errors=errors, notes=notes)

    def _finish(
        self,
        workstream_id: str,
        state: ApplyState,
        *,
        errors: list[str] | None = None,
        notes: list[str] | None = None,
    ) -> WorkstreamApplyReceipt:
        existing = self.read(workstream_id)
        if existing is None:
            existing = WorkstreamApplyReceipt(workstream_id=workstream_id, state=ApplyState.PENDING)
        updated = WorkstreamApplyReceipt(
            workstream_id=existing.workstream_id,
            state=state,
            schema_version=existing.schema_version,
            started_at=existing.started_at,
            completed_at=_isoformat_now(),
            applied_by=existing.applied_by,
            repo_version=existing.repo_version,
            adr=existing.adr,
            summary=existing.summary,
            targets=existing.targets,
            errors=errors or existing.errors,
            notes=notes or existing.notes,
        )
        self.write(updated)
        return updated

    def _read(self, path: Path) -> WorkstreamApplyReceipt | None:
        try:
            with path.open() as f:
                if _YAML_AVAILABLE:
                    data = yaml.safe_load(f)
                else:
                    import json
                    data = json.load(f)
            if not isinstance(data, dict):
                return None
            return WorkstreamApplyReceipt.from_dict(data)
        except Exception:
            return None

    def guard_not_completed(self, workstream_id: str) -> None:
        """Raise RuntimeError if the workstream was already successfully applied.

        Use this at the start of an apply to prevent duplicate applies:
            receipts.guard_not_completed("ws-0347")
        """
        state = self.current_state(workstream_id)
        if state is ApplyState.COMPLETED:
            raise RuntimeError(
                f"Workstream '{workstream_id}' is already COMPLETED. "
                "Delete the receipt to re-apply."
            )

    def guard_not_in_progress(self, workstream_id: str) -> None:
        """Raise RuntimeError if the workstream apply is currently in progress."""
        state = self.current_state(workstream_id)
        if state is ApplyState.IN_PROGRESS:
            raise RuntimeError(
                f"Workstream '{workstream_id}' apply is already IN_PROGRESS. "
                "Wait for it to finish or manually resolve the receipt."
            )
