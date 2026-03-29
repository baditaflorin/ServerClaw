from __future__ import annotations

from typing import Any


RUNTIME_STATE_STARTUP = "startup"
RUNTIME_STATE_READY = "ready"
RUNTIME_STATE_DEGRADED = "degraded"
RUNTIME_STATE_FAILED = "failed"
RUNTIME_STATE_UNKNOWN = "unknown"

RUNTIME_STATES = {
    RUNTIME_STATE_STARTUP,
    RUNTIME_STATE_READY,
    RUNTIME_STATE_DEGRADED,
    RUNTIME_STATE_FAILED,
}

LEGACY_STATUS_BY_RUNTIME_STATE = {
    RUNTIME_STATE_STARTUP: "starting",
    RUNTIME_STATE_READY: "healthy",
    RUNTIME_STATE_DEGRADED: "degraded",
    RUNTIME_STATE_FAILED: "down",
}

RUNTIME_STATE_BY_STATUS = {
    "ok": RUNTIME_STATE_READY,
    "healthy": RUNTIME_STATE_READY,
    "ready": RUNTIME_STATE_READY,
    "warn": RUNTIME_STATE_DEGRADED,
    "warning": RUNTIME_STATE_DEGRADED,
    "degraded": RUNTIME_STATE_DEGRADED,
    "starting": RUNTIME_STATE_STARTUP,
    "startup": RUNTIME_STATE_STARTUP,
    "down": RUNTIME_STATE_FAILED,
    "failed": RUNTIME_STATE_FAILED,
    "error": RUNTIME_STATE_FAILED,
    "unhealthy": RUNTIME_STATE_FAILED,
    "unreachable": RUNTIME_STATE_FAILED,
}


def normalize_runtime_state(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    if normalized in RUNTIME_STATES:
        return normalized
    return RUNTIME_STATE_BY_STATUS.get(normalized)


def canonical_runtime_state(entry: dict[str, Any]) -> str:
    return (
        normalize_runtime_state(entry.get("runtime_state"))
        or normalize_runtime_state(entry.get("status"))
        or RUNTIME_STATE_UNKNOWN
    )


def legacy_status_for_runtime_state(runtime_state: str) -> str:
    normalized = normalize_runtime_state(runtime_state)
    if normalized is None:
        return "unknown"
    return LEGACY_STATUS_BY_RUNTIME_STATE.get(normalized, "unknown")


def phase_supported(result: dict[str, Any] | None) -> bool:
    if not isinstance(result, dict):
        return False
    return result.get("supported", True) is not False


def phase_ok(result: dict[str, Any] | None) -> bool:
    return phase_supported(result) and result.get("ok") is True


def phase_failed(result: dict[str, Any] | None) -> bool:
    return phase_supported(result) and result.get("ok") is False


def classify_runtime_state(
    phase_results: dict[str, dict[str, Any]],
    *,
    degraded_active: bool,
) -> tuple[str, str]:
    startup = phase_results.get("startup")
    liveness = phase_results.get("liveness")
    readiness = phase_results.get("readiness")

    if phase_failed(liveness):
        return RUNTIME_STATE_FAILED, "liveness probe failed"

    if phase_failed(startup) and phase_ok(liveness):
        return RUNTIME_STATE_STARTUP, "startup probe has not completed yet"

    if phase_failed(readiness):
        if phase_ok(liveness) and startup is None:
            return RUNTIME_STATE_STARTUP, "readiness is still converging after liveness passed"
        return RUNTIME_STATE_FAILED, "readiness probe failed"

    if degraded_active:
        return RUNTIME_STATE_DEGRADED, "declared degraded mode is active"

    if any(phase_supported(result) for result in phase_results.values()):
        return RUNTIME_STATE_READY, "all supported probe phases passed"

    return RUNTIME_STATE_UNKNOWN, "no supported runtime probes were executable"


def runtime_state_score(runtime_state: str) -> tuple[float, str]:
    normalized = normalize_runtime_state(runtime_state)
    if normalized == RUNTIME_STATE_READY:
        return 1.0, "service is ready"
    if normalized == RUNTIME_STATE_STARTUP:
        return 0.7, "service is still starting"
    if normalized == RUNTIME_STATE_DEGRADED:
        return 0.5, "service is degraded"
    if normalized == RUNTIME_STATE_FAILED:
        return 0.0, "service has failed"
    return 0.8, "service state is unknown; treated as cautionary"
