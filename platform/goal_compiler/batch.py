from __future__ import annotations

import concurrent.futures
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from platform.diff_engine import DiffEngine
from platform.diff_engine.schema import SemanticDiff

from .compiler import CompiledIntentBatch, CompilationResult


def _access_conflicts(first: str, second: str) -> bool:
    lowered = {first.strip().lower(), second.strip().lower()}
    if "exclusive" in lowered:
        return True
    return lowered == {"write"}


def _dominant_access(accesses: set[str]) -> str:
    normalized = {item.strip().lower() for item in accesses if item}
    if "exclusive" in normalized:
        return "exclusive"
    if "write" in normalized:
        return "write"
    if "read" in normalized:
        return "read"
    return "unknown"


def _has_restart(change_kinds: set[str]) -> bool:
    return any(item in {"restart", "replace", "renew"} for item in change_kinds)


@dataclass(frozen=True)
class ResourceTouch:
    resource: str
    intent_ids: tuple[str, ...]
    accesses: dict[str, str]
    change_kinds: dict[str, tuple[str, ...]]

    def as_dict(self) -> dict[str, Any]:
        return {
            "resource": self.resource,
            "intent_ids": list(self.intent_ids),
            "accesses": dict(self.accesses),
            "change_kinds": {key: list(value) for key, value in self.change_kinds.items()},
        }


@dataclass(frozen=True)
class BatchConflict:
    conflict_type: str
    resource: str
    intent_ids: tuple[str, ...]
    blocking: bool
    resolution: str
    details: str | None = None

    def as_dict(self) -> dict[str, Any]:
        payload = {
            "conflict_type": self.conflict_type,
            "resource": self.resource,
            "intent_ids": list(self.intent_ids),
            "blocking": self.blocking,
            "resolution": self.resolution,
        }
        if self.details:
            payload["details"] = self.details
        return payload


@dataclass(frozen=True)
class ExecutionStage:
    stage_id: int
    intent_ids: tuple[str, ...]
    parallelism: str
    wait_for_stage: int | None = None

    def as_dict(self) -> dict[str, Any]:
        payload = {
            "stage_id": self.stage_id,
            "intent_ids": list(self.intent_ids),
            "parallelism": self.parallelism,
        }
        if self.wait_for_stage is not None:
            payload["wait_for_stage"] = self.wait_for_stage
        return payload


@dataclass(frozen=True)
class BatchExecutionPlan:
    batch_id: str
    stages: tuple[ExecutionStage, ...]
    rejected_intents: tuple[str, ...]
    rejected_reasons: dict[str, str]
    conflicts: tuple[BatchConflict, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "batch_id": self.batch_id,
            "stages": [item.as_dict() for item in self.stages],
            "rejected_intents": list(self.rejected_intents),
            "rejected_reasons": dict(self.rejected_reasons),
            "conflicts": [item.as_dict() for item in self.conflicts],
        }


@dataclass(frozen=True)
class BatchDryRunEntry:
    instruction: str
    compilation: CompilationResult
    semantic_diff: SemanticDiff | None
    error: str | None = None

    @property
    def intent_id(self) -> str:
        return self.compilation.intent.id

    @property
    def workflow_id(self) -> str | None:
        return self.compilation.dispatch_workflow_id

    def as_dict(self) -> dict[str, Any]:
        payload = {
            "instruction": self.instruction,
            "intent_id": self.intent_id,
            "workflow_id": self.workflow_id,
            "matched_rule_id": self.compilation.matched_rule_id,
            "dispatch_payload": self.compilation.dispatch_payload,
            "resource_claims": list(self.compilation.intent.resource_claims),
            "semantic_diff": self.semantic_diff.as_dict() if self.semantic_diff is not None else None,
        }
        if self.error:
            payload["error"] = self.error
        return payload


@dataclass(frozen=True)
class CombinedBatchDiff:
    batch_id: str
    total_changes: int
    resource_touches: tuple[ResourceTouch, ...]
    cross_intent_touches: tuple[ResourceTouch, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "batch_id": self.batch_id,
            "total_changes": self.total_changes,
            "resource_touches": [item.as_dict() for item in self.resource_touches],
            "cross_intent_touches": [item.as_dict() for item in self.cross_intent_touches],
        }


@dataclass(frozen=True)
class BatchValidationResult:
    batch: CompiledIntentBatch
    dry_runs: tuple[BatchDryRunEntry, ...]
    combined_diff: CombinedBatchDiff
    execution_plan: BatchExecutionPlan
    validation_elapsed_ms: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "batch": self.batch.as_dict(),
            "dry_runs": [item.as_dict() for item in self.dry_runs],
            "combined_diff": self.combined_diff.as_dict(),
            "execution_plan": self.execution_plan.as_dict(),
            "validation_elapsed_ms": self.validation_elapsed_ms,
        }


class IntentBatchPlanner:
    def __init__(
        self,
        repo_root: Path | str,
        *,
        max_parallelism: int = 5,
        diff_engine: DiffEngine | None = None,
        ledger_writer: Any | None = None,
    ) -> None:
        self.repo_root = Path(repo_root)
        self.max_parallelism = max(1, max_parallelism)
        self.diff_engine = diff_engine or DiffEngine(repo_root=self.repo_root)
        self.ledger_writer = ledger_writer
        self._workflow_catalog = self._load_workflow_catalog()

    def plan(self, batch: CompiledIntentBatch) -> BatchValidationResult:
        started = time.monotonic()
        dry_runs = self._fan_out_dry_runs(batch)
        combined_diff = self._combine_dry_runs(batch.batch_id, dry_runs)
        execution_plan = self._generate_execution_plan(batch.batch_id, dry_runs, combined_diff)
        result = BatchValidationResult(
            batch=batch,
            dry_runs=dry_runs,
            combined_diff=combined_diff,
            execution_plan=execution_plan,
            validation_elapsed_ms=int((time.monotonic() - started) * 1000),
        )
        self._write_ledger_event(result)
        return result

    def _load_workflow_catalog(self) -> dict[str, dict[str, Any]]:
        import json

        payload = json.loads((self.repo_root / "config" / "workflow-catalog.json").read_text(encoding="utf-8"))
        workflows = payload.get("workflows")
        if not isinstance(workflows, dict):
            return {}
        return {str(key): value for key, value in workflows.items() if isinstance(value, dict)}

    def _fan_out_dry_runs(self, batch: CompiledIntentBatch) -> tuple[BatchDryRunEntry, ...]:
        results: dict[str, BatchDryRunEntry] = {}

        def compute_entry(instruction: str, compilation: CompilationResult) -> BatchDryRunEntry:
            workflow_id = compilation.dispatch_workflow_id
            if not workflow_id:
                return BatchDryRunEntry(
                    instruction=instruction,
                    compilation=compilation,
                    semantic_diff=None,
                    error="compiled intent has no dispatch workflow",
                )
            try:
                diff = self.diff_engine.compute(self._diff_payload(compilation))
            except Exception as exc:  # noqa: BLE001
                return BatchDryRunEntry(
                    instruction=instruction,
                    compilation=compilation,
                    semantic_diff=None,
                    error=str(exc),
                )
            return BatchDryRunEntry(
                instruction=instruction,
                compilation=compilation,
                semantic_diff=diff,
            )

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=min(self.max_parallelism, max(1, len(batch.results)))
        ) as executor:
            future_map = {
                executor.submit(compute_entry, instruction, compilation): compilation.intent.id
                for instruction, compilation in zip(batch.instructions, batch.results, strict=True)
            }
            for future in concurrent.futures.as_completed(future_map):
                entry = future.result()
                results[future_map[future]] = entry

        ordered = [results[item.intent.id] for item in batch.results]
        return tuple(ordered)

    def _diff_payload(self, compilation: CompilationResult) -> dict[str, Any]:
        workflow_id = compilation.dispatch_workflow_id
        workflow = self._workflow_catalog.get(workflow_id or "", {})
        target_service_id = compilation.intent.target.services[0] if compilation.intent.target.services else None
        target_vm = compilation.intent.scope.allowed_hosts[0] if compilation.intent.scope.allowed_hosts else None
        return {
            "intent_id": compilation.intent.id,
            "workflow_id": workflow_id,
            "arguments": compilation.dispatch_payload,
            "live_impact": str(workflow.get("live_impact", "guest_live")),
            "target_service_id": target_service_id,
            "target_vm": target_vm,
        }

    def _combine_dry_runs(self, batch_id: str, dry_runs: tuple[BatchDryRunEntry, ...]) -> CombinedBatchDiff:
        by_resource: dict[str, dict[str, dict[str, set[str]]]] = defaultdict(
            lambda: defaultdict(lambda: {"accesses": set(), "change_kinds": set()})
        )
        total_changes = 0

        for entry in dry_runs:
            if entry.error:
                continue
            for claim in entry.compilation.intent.resource_claims:
                resource = str(claim.get("resource", "")).strip()
                access = str(claim.get("access", "")).strip().lower()
                if not resource:
                    continue
                by_resource[resource][entry.intent_id]["accesses"].add(access or "unknown")
                by_resource[resource][entry.intent_id]["change_kinds"].add("claim")
            diff = entry.semantic_diff
            if diff is None:
                continue
            total_changes += diff.total_changes
            for changed in diff.changed_objects:
                resource = f"{changed.surface}:{changed.object_id}"
                by_resource[resource][entry.intent_id]["accesses"].add("write")
                by_resource[resource][entry.intent_id]["change_kinds"].add(changed.change_kind)

        resource_touches: list[ResourceTouch] = []
        cross_intent_touches: list[ResourceTouch] = []
        for resource, touched in sorted(by_resource.items()):
            intent_ids = tuple(touched.keys())
            payload = ResourceTouch(
                resource=resource,
                intent_ids=intent_ids,
                accesses={intent_id: _dominant_access(values["accesses"]) for intent_id, values in touched.items()},
                change_kinds={
                    intent_id: tuple(sorted(values["change_kinds"])) for intent_id, values in touched.items()
                },
            )
            resource_touches.append(payload)
            if len(intent_ids) > 1:
                cross_intent_touches.append(payload)

        return CombinedBatchDiff(
            batch_id=batch_id,
            total_changes=total_changes,
            resource_touches=tuple(resource_touches),
            cross_intent_touches=tuple(cross_intent_touches),
        )

    def _generate_execution_plan(
        self,
        batch_id: str,
        dry_runs: tuple[BatchDryRunEntry, ...],
        combined_diff: CombinedBatchDiff,
    ) -> BatchExecutionPlan:
        rejected_reasons: dict[str, str] = {
            entry.intent_id: f"dry_run_failed: {entry.error}" for entry in dry_runs if entry.error
        }
        dependencies: set[tuple[str, str]] = set()
        conflicts: list[BatchConflict] = []
        seen_conflicts: set[tuple[str, str, tuple[str, str]]] = set()
        order = {entry.intent_id: index for index, entry in enumerate(dry_runs)}

        for touch in combined_diff.cross_intent_touches:
            ids = list(touch.intent_ids)
            for index, first_id in enumerate(ids):
                for second_id in ids[index + 1 :]:
                    pair = tuple(sorted((first_id, second_id)))
                    first_access = touch.accesses.get(first_id, "unknown")
                    second_access = touch.accesses.get(second_id, "unknown")
                    first_change_kinds = set(touch.change_kinds.get(first_id, ()))
                    second_change_kinds = set(touch.change_kinds.get(second_id, ()))

                    if _has_restart(first_change_kinds) ^ _has_restart(second_change_kinds):
                        restart_id = first_id if _has_restart(first_change_kinds) else second_id
                        config_id = second_id if restart_id == first_id else first_id
                        dependencies.add((config_id, restart_id))
                        key = ("restart_during_config", touch.resource, pair)
                        if key not in seen_conflicts:
                            seen_conflicts.add(key)
                            conflicts.append(
                                BatchConflict(
                                    conflict_type="restart_during_config",
                                    resource=touch.resource,
                                    intent_ids=(config_id, restart_id),
                                    blocking=False,
                                    resolution=f"run {config_id} before {restart_id}",
                                )
                            )
                        continue

                    if _access_conflicts(first_access, second_access):
                        loser = max(pair, key=lambda item: order[item])
                        if loser not in rejected_reasons:
                            rejected_reasons[loser] = f"write_write_conflict on {touch.resource}"
                        key = ("write_write_conflict", touch.resource, pair)
                        if key not in seen_conflicts:
                            seen_conflicts.add(key)
                            conflicts.append(
                                BatchConflict(
                                    conflict_type="write_write_conflict",
                                    resource=touch.resource,
                                    intent_ids=pair,
                                    blocking=True,
                                    resolution=f"reject {loser}",
                                )
                            )
                        continue

                    if {first_access, second_access} == {"read", "write"}:
                        writer = first_id if first_access == "write" else second_id
                        reader = second_id if writer == first_id else first_id
                        dependencies.add((writer, reader))
                        key = ("read_after_write_dependency", touch.resource, pair)
                        if key not in seen_conflicts:
                            seen_conflicts.add(key)
                            conflicts.append(
                                BatchConflict(
                                    conflict_type="read_after_write_dependency",
                                    resource=touch.resource,
                                    intent_ids=(writer, reader),
                                    blocking=False,
                                    resolution=f"run {writer} before {reader}",
                                )
                            )

        remaining = [
            entry.intent_id
            for entry in dry_runs
            if entry.intent_id not in rejected_reasons
        ]
        dependency_map = {intent_id: set() for intent_id in remaining}
        for before_id, after_id in dependencies:
            if before_id in dependency_map and after_id in dependency_map:
                dependency_map[after_id].add(before_id)

        stages: list[ExecutionStage] = []
        stage_lookup: dict[str, int] = {}
        completed: set[str] = set()
        pending = list(remaining)

        while pending:
            ready = [intent_id for intent_id in pending if dependency_map[intent_id].issubset(completed)]
            if not ready:
                cycle_victim = pending[-1]
                rejected_reasons[cycle_victim] = "dependency_cycle"
                pending.pop()
                dependency_map.pop(cycle_victim, None)
                for deps in dependency_map.values():
                    deps.discard(cycle_victim)
                continue

            stage_id = len(stages) + 1
            wait_for_stage = None
            for intent_id in ready:
                for dependency in dependency_map[intent_id]:
                    wait_for_stage = max(wait_for_stage or 0, stage_lookup.get(dependency, 0)) or None
            stage = ExecutionStage(
                stage_id=stage_id,
                intent_ids=tuple(ready),
                parallelism="full" if len(ready) > 1 else "sequential",
                wait_for_stage=wait_for_stage,
            )
            stages.append(stage)
            for intent_id in ready:
                stage_lookup[intent_id] = stage_id
                completed.add(intent_id)
                pending.remove(intent_id)

        return BatchExecutionPlan(
            batch_id=batch_id,
            stages=tuple(stages),
            rejected_intents=tuple(rejected_reasons.keys()),
            rejected_reasons=rejected_reasons,
            conflicts=tuple(conflicts),
        )

    def _write_ledger_event(self, result: BatchValidationResult) -> None:
        if self.ledger_writer is None:
            return
        actor = result.batch.actor_id or "operator:lv3_cli"
        self.ledger_writer.write(
            event_type="intent.batch_plan",
            actor=actor,
            actor_intent_id=result.batch.batch_id,
            tool_id="goal_compiler.batch",
            target_kind="workflow",
            target_id=result.batch.batch_id,
            before_state=result.combined_diff.as_dict(),
            after_state=result.execution_plan.as_dict(),
            metadata={
                "instructions": list(result.batch.instructions),
                "dry_run_count": len(result.dry_runs),
                "max_parallelism": self.max_parallelism,
                "validation_elapsed_ms": result.validation_elapsed_ms,
            },
        )
