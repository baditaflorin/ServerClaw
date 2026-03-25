from __future__ import annotations

import json
import os
import subprocess
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha1
from pathlib import Path
from typing import Any, Iterator

from .schema import ConflictCheckResult, ConflictWarning, ResourceClaim


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STATE_SUBPATH = Path("lv3-conflicts") / "registry.json"
DEFAULT_DEDUP_WINDOW_SECONDS = 300


def _git_common_dir(repo_root: Path) -> Path | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--git-common-dir"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    value = completed.stdout.strip()
    if not value:
        return None
    path = Path(value)
    if not path.is_absolute():
        path = (repo_root / path).resolve()
    return path


def _default_state_path(repo_root: Path) -> Path:
    override = os.environ.get("LV3_CONFLICT_STATE_PATH", "").strip()
    if override:
        return Path(override).expanduser()
    common_dir = _git_common_dir(repo_root)
    if common_dir is not None:
        return common_dir / DEFAULT_STATE_SUBPATH
    return repo_root / ".local" / "state" / "conflicts" / "registry.json"


def _load_workflow_catalog(repo_root: Path) -> dict[str, dict[str, Any]]:
    payload = json.loads((repo_root / "config" / "workflow-catalog.json").read_text(encoding="utf-8"))
    workflows = payload.get("workflows")
    if not isinstance(workflows, dict):
        raise ValueError("config/workflow-catalog.json must define a workflows object")
    return workflows


def _normalize_service_id(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    candidate = value.strip().lower().replace("-", "_")
    return candidate or None


def _intent_payload(intent: Any) -> dict[str, Any]:
    if hasattr(intent, "as_dict"):
        payload = intent.as_dict()
        if isinstance(payload, dict):
            return payload
    if isinstance(intent, dict):
        return dict(intent)
    payload: dict[str, Any] = {}
    for field in (
        "workflow_id",
        "arguments",
        "target_service_id",
        "target_vm",
        "intent_id",
        "id",
        "resource_claims",
        "conflict_warnings",
    ):
        if hasattr(intent, field):
            payload[field] = getattr(intent, field)
    return payload


def _format_resource(template: str, context: dict[str, Any]) -> str:
    mapping = {key: "" if value is None else value for key, value in context.items()}
    try:
        rendered = template.format_map(mapping)
    except (KeyError, ValueError):
        rendered = template
    return rendered.strip()


def _claim_context(payload: dict[str, Any]) -> dict[str, Any]:
    arguments = payload.get("arguments", {})
    if not isinstance(arguments, dict):
        arguments = {}
    service_id = _normalize_service_id(payload.get("target_service_id")) or _normalize_service_id(
        arguments.get("service") or arguments.get("service_id") or arguments.get("target_service")
    )
    secret_id = arguments.get("secret_id")
    operator_id = arguments.get("operator_id")
    email = arguments.get("email")
    return {
        "workflow_id": payload.get("workflow_id", ""),
        "service": service_id or "",
        "target_service_id": service_id or "",
        "target_vm": payload.get("target_vm") or arguments.get("target_vm") or arguments.get("target") or "",
        "target": arguments.get("target") or service_id or "",
        "secret_id": secret_id if isinstance(secret_id, str) else "",
        "operator_id": operator_id if isinstance(operator_id, str) else "",
        "email": email if isinstance(email, str) else "",
    }


def infer_resource_claims(intent: Any, *, repo_root: Path | None = None) -> list[ResourceClaim]:
    base = repo_root or REPO_ROOT
    payload = _intent_payload(intent)
    workflow_id = str(payload.get("workflow_id", "")).strip()
    workflows = _load_workflow_catalog(base)
    workflow = workflows.get(workflow_id, {})
    execution_class = str(workflow.get("execution_class", "mutation"))
    default_access = "read" if execution_class == "diagnostic" else "write"
    claims: list[ResourceClaim] = []
    context = _claim_context(payload)

    raw_claims = workflow.get("resource_claims", [])
    if isinstance(raw_claims, list):
        for index, item in enumerate(raw_claims):
            if not isinstance(item, dict):
                raise ValueError(f"workflow '{workflow_id}' resource_claims[{index}] must be a mapping")
            resource = _format_resource(str(item.get("resource", "")), context)
            access = str(item.get("access", "")).strip()
            if resource and access:
                claims.append(ResourceClaim(resource=resource, access=access))

    if claims:
        return _deduplicate_claims(claims)

    service_id = context["target_service_id"]
    target_vm = str(context["target_vm"]).strip()
    arguments = payload.get("arguments", {})
    if not isinstance(arguments, dict):
        arguments = {}

    if service_id:
        claims.append(ResourceClaim(resource=f"service:{service_id}", access=default_access))
    if target_vm:
        claims.append(ResourceClaim(resource=f"vm:{target_vm}", access="read"))
    secret_id = arguments.get("secret_id")
    if isinstance(secret_id, str) and secret_id.strip():
        claims.append(ResourceClaim(resource=f"secret:{secret_id.strip()}", access=default_access))
    if not claims:
        claims.append(ResourceClaim(resource=f"workflow:{workflow_id}", access=default_access))
    return _deduplicate_claims(claims)


def dedup_window_seconds(workflow_id: str, *, repo_root: Path | None = None) -> int:
    base = repo_root or REPO_ROOT
    workflows = _load_workflow_catalog(base)
    workflow = workflows.get(workflow_id, {})
    configured = workflow.get("dedup_window_seconds")
    if isinstance(configured, int) and configured >= 0:
        return configured
    if workflow.get("execution_class", "mutation") == "diagnostic":
        return 0
    return DEFAULT_DEDUP_WINDOW_SECONDS


def _deduplicate_claims(claims: list[ResourceClaim]) -> list[ResourceClaim]:
    unique: dict[tuple[str, str], ResourceClaim] = {}
    for claim in claims:
        unique[(claim.resource, claim.access)] = claim
    return list(unique.values())


def _canonical_argument_hash(arguments: dict[str, Any]) -> str:
    return sha1(json.dumps(arguments, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _primary_target_resource(payload: dict[str, Any], claims: list[ResourceClaim]) -> str:
    for prefix in ("service:", "secret:", "vm:", "identity:", "dns:", "host:"):
        for claim in claims:
            if claim.resource.startswith(prefix):
                return claim.resource
    if claims:
        return claims[0].resource
    return f"workflow:{payload.get('workflow_id', '')}"


def _access_conflicts(first: str, second: str) -> bool:
    if "exclusive" in {first, second}:
        return True
    return first == "write" and second == "write"


def _dependency_map(repo_root: Path) -> dict[str, set[str]]:
    path = repo_root / "config" / "dependency-graph.json"
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    edges = payload.get("edges")
    if not isinstance(edges, list):
        return {}
    mapping: dict[str, set[str]] = {}
    for item in edges:
        if not isinstance(item, dict):
            continue
        source = _normalize_service_id(item.get("from"))
        target = _normalize_service_id(item.get("to"))
        if not source or not target:
            continue
        mapping.setdefault(source, set()).add(target)
    return mapping


@dataclass(frozen=True)
class _StoredIntent:
    actor_intent_id: str
    workflow_id: str
    actor: str
    target_service_id: str | None
    target_resource: str
    dedup_signature: str | None
    dedup_window_seconds: int
    registered_at: str
    expires_at: str
    claims: list[ResourceClaim]
    output: Any = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "actor_intent_id": self.actor_intent_id,
            "workflow_id": self.workflow_id,
            "actor": self.actor,
            "target_service_id": self.target_service_id,
            "target_resource": self.target_resource,
            "dedup_signature": self.dedup_signature,
            "dedup_window_seconds": self.dedup_window_seconds,
            "registered_at": self.registered_at,
            "expires_at": self.expires_at,
            "claims": [claim.as_dict() for claim in self.claims],
            "output": self.output,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> _StoredIntent:
        claims = payload.get("claims", [])
        return cls(
            actor_intent_id=str(payload["actor_intent_id"]),
            workflow_id=str(payload["workflow_id"]),
            actor=str(payload["actor"]),
            target_service_id=_normalize_service_id(payload.get("target_service_id")),
            target_resource=str(payload["target_resource"]),
            dedup_signature=str(payload["dedup_signature"]) if payload.get("dedup_signature") else None,
            dedup_window_seconds=int(payload.get("dedup_window_seconds", 0)),
            registered_at=str(payload["registered_at"]),
            expires_at=str(payload["expires_at"]),
            claims=[ResourceClaim.from_dict(item) for item in claims if isinstance(item, dict)],
            output=payload.get("output"),
        )


class IntentConflictRegistry:
    def __init__(
        self,
        *,
        repo_root: Path | None = None,
        state_path: Path | None = None,
        now_fn: Any | None = None,
    ) -> None:
        self._repo_root = repo_root or REPO_ROOT
        self._state_path = state_path or _default_state_path(self._repo_root)
        self._lock_path = self._state_path.with_suffix(".lock")
        self._now = now_fn or (lambda: datetime.now(UTC))
        self._dependency_index = _dependency_map(self._repo_root)

    def preview_intent(
        self,
        intent: Any,
        *,
        actor_intent_id: str,
        actor: str,
    ) -> ConflictCheckResult:
        candidate = self._candidate(intent, actor_intent_id=actor_intent_id, actor=actor)
        with self._locked_state() as state:
            self._purge(state)
            duplicate = self._duplicate(state, candidate)
            if duplicate is not None:
                return ConflictCheckResult(
                    status="duplicate",
                    resolution="deduplicate",
                    conflicting_intent_id=duplicate.actor_intent_id,
                    conflicting_actor=duplicate.actor,
                    conflict_type="duplicate",
                    message="matching intent completed recently",
                    dedup_output=duplicate.output,
                    resource_claims=candidate.claims,
                    warnings=self._warnings(state, candidate),
                )
            conflict = self._claim_conflict(state, candidate)
            if conflict is not None:
                return ConflictCheckResult(
                    status="conflict",
                    resolution="reject",
                    conflicting_intent_id=conflict.actor_intent_id,
                    conflicting_actor=conflict.actor,
                    conflict_type="write_write",
                    message=f"{conflict.workflow_id} already holds a conflicting claim",
                    resource_claims=candidate.claims,
                    warnings=self._warnings(state, candidate),
                )
            return ConflictCheckResult(
                status="clear",
                resolution="allow",
                resource_claims=candidate.claims,
                warnings=self._warnings(state, candidate),
            )

    def register_intent(
        self,
        intent: Any,
        *,
        actor_intent_id: str,
        actor: str,
        ttl_seconds: int,
        allow_conflicts: bool = False,
    ) -> ConflictCheckResult:
        candidate = self._candidate(intent, actor_intent_id=actor_intent_id, actor=actor, ttl_seconds=ttl_seconds)
        with self._locked_state() as state:
            self._purge(state)
            duplicate = self._duplicate(state, candidate)
            warnings = self._warnings(state, candidate)
            if duplicate is not None:
                return ConflictCheckResult(
                    status="duplicate",
                    resolution="deduplicate",
                    conflicting_intent_id=duplicate.actor_intent_id,
                    conflicting_actor=duplicate.actor,
                    conflict_type="duplicate",
                    message="matching intent completed recently",
                    dedup_output=duplicate.output,
                    resource_claims=candidate.claims,
                    warnings=warnings,
                )
            conflict = self._claim_conflict(state, candidate)
            if conflict is not None:
                if allow_conflicts:
                    active = state.setdefault("active", {})
                    active[candidate.actor_intent_id] = candidate.as_dict()
                    return ConflictCheckResult(
                        status="speculative",
                        resolution="allow_with_probe",
                        conflicting_intent_id=conflict.actor_intent_id,
                        conflicting_actor=conflict.actor,
                        conflict_type="write_write",
                        message=f"{conflict.workflow_id} already holds a conflicting claim",
                        resource_claims=candidate.claims,
                        warnings=warnings,
                    )
                return ConflictCheckResult(
                    status="conflict",
                    resolution="reject",
                    conflicting_intent_id=conflict.actor_intent_id,
                    conflicting_actor=conflict.actor,
                    conflict_type="write_write",
                    message=f"{conflict.workflow_id} already holds a conflicting claim",
                    resource_claims=candidate.claims,
                    warnings=warnings,
                )
            active = state.setdefault("active", {})
            active[candidate.actor_intent_id] = candidate.as_dict()
            return ConflictCheckResult(
                status="clear",
                resolution="allow",
                resource_claims=candidate.claims,
                warnings=warnings,
            )

    def complete_intent(self, actor_intent_id: str, *, status: str, output: Any = None) -> None:
        with self._locked_state() as state:
            self._purge(state)
            active = state.setdefault("active", {})
            payload = active.pop(actor_intent_id, None)
            if payload is None:
                return
            record = _StoredIntent.from_dict(payload)
            if status != "completed" or record.dedup_window_seconds <= 0:
                return
            history = state.setdefault("history", [])
            now = self._timestamp(self._now())
            history.append(
                {
                    **record.as_dict(),
                    "output": output,
                    "completed_at": now,
                    "keep_until": self._timestamp(self._now() + timedelta(seconds=record.dedup_window_seconds)),
                }
            )

    def _candidate(
        self,
        intent: Any,
        *,
        actor_intent_id: str,
        actor: str,
        ttl_seconds: int | None = None,
    ) -> _StoredIntent:
        payload = _intent_payload(intent)
        arguments = payload.get("arguments", {})
        if not isinstance(arguments, dict):
            arguments = {}
        claims = infer_resource_claims(payload, repo_root=self._repo_root)
        now = self._now()
        dedup_seconds = dedup_window_seconds(str(payload.get("workflow_id", "")), repo_root=self._repo_root)
        signature = None
        if dedup_seconds > 0:
            signature = ":".join(
                [
                    str(payload.get("workflow_id", "")),
                    _primary_target_resource(payload, claims),
                    _canonical_argument_hash(arguments),
                ]
            )
        return _StoredIntent(
            actor_intent_id=actor_intent_id,
            workflow_id=str(payload.get("workflow_id", "")),
            actor=actor,
            target_service_id=_normalize_service_id(payload.get("target_service_id")),
            target_resource=_primary_target_resource(payload, claims),
            dedup_signature=signature,
            dedup_window_seconds=dedup_seconds,
            registered_at=self._timestamp(now),
            expires_at=self._timestamp(now + timedelta(seconds=(ttl_seconds or 0))),
            claims=claims,
        )

    def _duplicate(self, state: dict[str, Any], candidate: _StoredIntent) -> _StoredIntent | None:
        if not candidate.dedup_signature:
            return None
        for raw in state.get("history", []):
            if not isinstance(raw, dict):
                continue
            if raw.get("dedup_signature") != candidate.dedup_signature:
                continue
            return _StoredIntent.from_dict(raw)
        return None

    def _claim_conflict(self, state: dict[str, Any], candidate: _StoredIntent) -> _StoredIntent | None:
        for raw in state.get("active", {}).values():
            if not isinstance(raw, dict):
                continue
            active = _StoredIntent.from_dict(raw)
            for claim in candidate.claims:
                for existing in active.claims:
                    if claim.resource != existing.resource:
                        continue
                    if _access_conflicts(claim.access, existing.access):
                        return active
        return None

    def _warnings(self, state: dict[str, Any], candidate: _StoredIntent) -> list[ConflictWarning]:
        if not candidate.target_service_id:
            return []
        dependencies = self._dependency_index.get(candidate.target_service_id, set())
        if not dependencies:
            return []
        warnings: list[ConflictWarning] = []
        for raw in state.get("active", {}).values():
            if not isinstance(raw, dict):
                continue
            active = _StoredIntent.from_dict(raw)
            if active.target_service_id not in dependencies:
                continue
            if not any(claim.resource.startswith("service:") and claim.access in {"write", "exclusive"} for claim in active.claims):
                continue
            warnings.append(
                ConflictWarning(
                    conflict_type="cascade_conflict",
                    conflicting_intent_id=active.actor_intent_id,
                    message=(
                        f"dependency service '{active.target_service_id}' is already mid-change via {active.workflow_id}"
                    ),
                )
            )
        return warnings

    def _purge(self, state: dict[str, Any]) -> None:
        now = self._now()
        active = state.setdefault("active", {})
        expired = [
            intent_id
            for intent_id, payload in active.items()
            if isinstance(payload, dict) and self._parse_timestamp(str(payload.get("expires_at", ""))) <= now
        ]
        for intent_id in expired:
            active.pop(intent_id, None)
        history = state.setdefault("history", [])
        state["history"] = [
            payload
            for payload in history
            if isinstance(payload, dict) and self._parse_timestamp(str(payload.get("keep_until", ""))) > now
        ]

    @contextmanager
    def _locked_state(self) -> Iterator[dict[str, Any]]:
        import fcntl

        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock_path.open("a+", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                if self._state_path.exists():
                    raw = self._state_path.read_text(encoding="utf-8").strip()
                    state = json.loads(raw) if raw else self._empty_state()
                else:
                    state = self._empty_state()
                yield state
                self._state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    @staticmethod
    def _empty_state() -> dict[str, Any]:
        return {"schema_version": "1.0.0", "active": {}, "history": []}

    @staticmethod
    def _timestamp(value: datetime) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).isoformat()

    @staticmethod
    def _parse_timestamp(value: str) -> datetime:
        candidate = value.strip()
        if candidate.endswith("Z"):
            candidate = candidate[:-1] + "+00:00"
        parsed = datetime.fromisoformat(candidate)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
