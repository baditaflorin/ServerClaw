from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any


VOLATILE_PARAM_KEYS = frozenset(
    {
        "actor_intent_id",
        "completed_at",
        "correlation_id",
        "created_at",
        "event_id",
        "idempotency_key",
        "intent_id",
        "job_id",
        "occurred_at",
        "request_id",
        "submitted_at",
        "timestamp",
        "trace_id",
        "updated_at",
    }
)


def _is_iso_timestamp(value: str) -> bool:
    candidate = value.strip()
    if not candidate:
        return False
    try:
        parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None or "T" in candidate


def _normalise_scalar(value: Any) -> Any:
    if isinstance(value, str):
        candidate = value.strip()
        if not candidate:
            return candidate
        try:
            uuid.UUID(candidate)
            return "<uuid>"
        except ValueError:
            pass
        if _is_iso_timestamp(candidate):
            return "<timestamp>"
        return candidate
    return value


def normalise_params(value: Any) -> Any:
    if isinstance(value, dict):
        normalised: dict[str, Any] = {}
        for key in sorted(value):
            if key.lower() in VOLATILE_PARAM_KEYS or key.lower().endswith(("_at", "_ts")):
                continue
            normalised[key] = normalise_params(value[key])
        return normalised
    if isinstance(value, list):
        return [normalise_params(item) for item in value]
    if isinstance(value, tuple):
        return [normalise_params(item) for item in value]
    return _normalise_scalar(value)


def compute_idempotency_key(
    workflow_id: str,
    target_service_id: str,
    params: dict[str, Any],
    actor_id: str,
    *,
    time_window_minutes: int = 60,
    now: datetime | None = None,
    exact_scope: str | None = None,
) -> str:
    current = (now or datetime.now(UTC)).astimezone(UTC).replace(second=0, microsecond=0)
    if exact_scope is not None and exact_scope.strip():
        window = f"scope:{exact_scope.strip()}"
    elif time_window_minutes <= 0:
        window = current.isoformat()
    else:
        bucket_minutes = current.minute - (current.minute % time_window_minutes)
        bucket = current.replace(minute=bucket_minutes)
        window = bucket.isoformat()

    stable_params = normalise_params(params)
    key_material = {
        "actor_id": actor_id,
        "params_hash": hashlib.sha256(json.dumps(stable_params, sort_keys=True).encode("utf-8")).hexdigest(),
        "target_service_id": target_service_id,
        "window": window,
        "workflow_id": workflow_id,
    }
    digest = hashlib.sha256(json.dumps(key_material, sort_keys=True).encode("utf-8")).hexdigest()
    return f"idem:{digest[:32]}"
