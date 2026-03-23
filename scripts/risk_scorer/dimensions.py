from __future__ import annotations


def criticality_score(target_tier: str) -> float:
    normalized = target_tier.strip().lower()
    return {
        "low": 5.0,
        "medium": 15.0,
        "high": 22.0,
        "critical": 30.0,
    }.get(normalized, 15.0)


def fanout_score(downstream_count: int) -> float:
    if downstream_count <= 0:
        return 0.0
    if downstream_count == 1:
        return 5.0
    if downstream_count <= 3:
        return 10.0
    if downstream_count <= 6:
        return 15.0
    return 20.0


def failure_rate_score(recent_failure_rate: float) -> float:
    clamped = max(0.0, min(1.0, recent_failure_rate))
    return 15.0 * clamped


def surface_score(expected_change_count: int) -> float:
    if expected_change_count <= 0:
        return 0.0
    if expected_change_count <= 2:
        return 2.0
    if expected_change_count <= 5:
        return 5.0
    if expected_change_count <= 10:
        return 8.0
    return 10.0


def rollback_score(rollback_verified: bool) -> float:
    return 0.0 if rollback_verified else 10.0


def maintenance_score(in_maintenance_window: bool) -> float:
    return -15.0 if in_maintenance_window else 0.0


def incident_score(active_incident: bool) -> float:
    return 20.0 if active_incident else 0.0


def recency_score(hours_since_last_mutation: float | None) -> float:
    if hours_since_last_mutation is None:
        return 2.5
    if hours_since_last_mutation < 1:
        return 5.0
    if hours_since_last_mutation < 6:
        return 4.0
    if hours_since_last_mutation < 24:
        return 3.0
    if hours_since_last_mutation < 72:
        return 2.0
    if hours_since_last_mutation < 168:
        return 1.0
    return 0.0
