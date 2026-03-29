from __future__ import annotations

import importlib


_EXPORTS = {
    "ActiveJobRecord": ".watchdog",
    "BudgetedWorkflowScheduler": ".scheduler",
    "ConflictProbeResult": ".speculative",
    "ExecutionLane": ".lanes",
    "FileConcurrencyLockManager": ".scheduler",
    "FileLaneReservationStore": ".lanes",
    "HostTouchEstimate": ".budgets",
    "HttpWindmillClient": ".windmill_client",
    "IdempotencyStore": "platform.idempotency",
    "LaneBudget": ".lanes",
    "LaneReservationDecision": ".lanes",
    "LaneReservationRecord": ".lanes",
    "PostgresAdvisoryLockManager": ".scheduler",
    "ResourceReservation": ".lanes",
    "ResourceUsage": ".lanes",
    "RollbackDepthResult": ".rollback_guard",
    "RollbackGuard": ".rollback_guard",
    "SchedulerResult": ".scheduler",
    "SchedulerStateStore": ".watchdog",
    "SpeculativeExecutionRecord": ".speculative",
    "SpeculativeStateStore": ".speculative",
    "SpeculativeWorkflowPolicy": ".budgets",
    "WATCHDOG_POLL_INTERVAL_SECONDS": ".watchdog",
    "Watchdog": ".watchdog",
    "WatchdogViolation": ".watchdog",
    "WorkflowBudget": ".budgets",
    "WorkflowPolicy": ".budgets",
    "build_scheduler": ".scheduler",
    "estimate_touched_hosts": ".budgets",
    "load_default_budget": ".budgets",
    "load_default_resource_reservation": ".budgets",
    "load_execution_lanes": ".lanes",
    "load_workflow_policy": ".budgets",
    "resolve_execution_lane": ".lanes",
}

__all__ = [
    "ActiveJobRecord",
    "BudgetedWorkflowScheduler",
    "ConflictProbeResult",
    "ExecutionLane",
    "FileConcurrencyLockManager",
    "FileLaneReservationStore",
    "HostTouchEstimate",
    "HttpWindmillClient",
    "LaneBudget",
    "LaneReservationDecision",
    "LaneReservationRecord",
    "IdempotencyStore",
    "PostgresAdvisoryLockManager",
    "ResourceReservation",
    "ResourceUsage",
    "RollbackDepthResult",
    "RollbackGuard",
    "SchedulerResult",
    "SchedulerStateStore",
    "SpeculativeExecutionRecord",
    "SpeculativeStateStore",
    "SpeculativeWorkflowPolicy",
    "ConflictProbeResult",
    "WATCHDOG_POLL_INTERVAL_SECONDS",
    "Watchdog",
    "WatchdogViolation",
    "WorkflowBudget",
    "WorkflowPolicy",
    "build_scheduler",
    "estimate_touched_hosts",
    "load_default_budget",
    "load_default_resource_reservation",
    "load_execution_lanes",
    "load_workflow_policy",
    "resolve_execution_lane",
]


def __getattr__(name: str):
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = importlib.import_module(module_name, __name__)
    value = getattr(module, name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
