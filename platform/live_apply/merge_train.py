from __future__ import annotations

import json
import os
import shutil
import subprocess
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from platform.concurrency import default_state_path, locked_json_state
from scripts.controller_automation_toolkit import load_json, load_yaml, write_json


MERGE_TRAIN_STATE_ENV = "LV3_LIVE_APPLY_MERGE_TRAIN_STATE_PATH"
MERGE_TRAIN_STATE_SUBPATH = Path("lv3-live-apply") / "merge-train-state.json"
ROLLBACK_BUNDLE_DIR_ENV = "LV3_ROLLBACK_BUNDLE_DIR"
ROLLBACK_BUNDLE_SUBPATH = Path("receipts") / "rollback-bundles"
ALLOWED_SURFACE_MODES = {"exclusive", "shared_contract", "generated", "read_only"}
ALLOWED_ROLLBACK_STEP_KINDS = {"shell", "file_restore", "runbook"}


class MergeTrainError(RuntimeError):
    pass


@dataclass(frozen=True)
class QueueEntry:
    queue_id: str
    workstream_id: str
    queued_at: str
    requested_by: str
    reason: str | None
    status: str
    completion_metadata: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "queue_id": self.queue_id,
            "workstream_id": self.workstream_id,
            "queued_at": self.queued_at,
            "requested_by": self.requested_by,
            "reason": self.reason,
            "status": self.status,
            "completion_metadata": dict(self.completion_metadata),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> QueueEntry:
        return cls(
            queue_id=str(payload["queue_id"]),
            workstream_id=str(payload["workstream_id"]),
            queued_at=str(payload["queued_at"]),
            requested_by=str(payload.get("requested_by", "unknown")),
            reason=str(payload["reason"]) if payload.get("reason") else None,
            status=str(payload.get("status", "queued")),
            completion_metadata=dict(payload.get("completion_metadata", {}))
            if isinstance(payload.get("completion_metadata"), dict)
            else {},
        )


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_now() -> str:
    return utc_now().isoformat()


def repo_root_path(repo_root: Path | None = None) -> Path:
    return repo_root or Path(__file__).resolve().parents[2]


def workstreams_path(repo_root: Path | None = None) -> Path:
    return repo_root_path(repo_root) / "workstreams.yaml"


def merge_train_state_path(repo_root: Path | None = None) -> Path:
    base = repo_root_path(repo_root)
    return default_state_path(
        env_var=MERGE_TRAIN_STATE_ENV,
        repo_root=base,
        state_subpath=MERGE_TRAIN_STATE_SUBPATH,
    )


def rollback_bundle_dir(repo_root: Path | None = None) -> Path:
    base = repo_root_path(repo_root)
    override = os.environ.get(ROLLBACK_BUNDLE_DIR_ENV, "").strip()
    if override:
        return Path(override).expanduser()
    return base / ROLLBACK_BUNDLE_SUBPATH


def load_workstreams(repo_root: Path | None = None) -> dict[str, dict[str, Any]]:
    payload = load_yaml(workstreams_path(repo_root))
    workstreams = payload.get("workstreams")
    if not isinstance(workstreams, list):
        raise MergeTrainError("workstreams.yaml must define a workstreams list")
    result: dict[str, dict[str, Any]] = {}
    for item in workstreams:
        if not isinstance(item, dict):
            continue
        workstream_id = str(item.get("id", "")).strip()
        if not workstream_id:
            continue
        result[workstream_id] = item
    return result


def load_merge_train_state(repo_root: Path | None = None) -> dict[str, Any]:
    path = merge_train_state_path(repo_root)
    if not path.exists():
        return _empty_state()
    payload = load_json(path)
    if not isinstance(payload, dict):
        raise MergeTrainError(f"{path} must contain a JSON object")
    return payload


def enqueue_workstreams(
    workstream_ids: list[str],
    *,
    requested_by: str,
    reason: str | None = None,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    base = repo_root_path(repo_root)
    registry = load_workstreams(base)
    queued: list[dict[str, Any]] = []
    with locked_json_state(merge_train_state_path(base), default_factory=_empty_state) as state:
        items = [QueueEntry.from_dict(item) for item in state.get("items", []) if isinstance(item, dict)]
        for workstream_id in workstream_ids:
            workstream = _require_workstream(registry, workstream_id)
            validate_workstream_for_train(workstream, repo_root=base, run_checks=False)
            existing = next(
                (
                    item
                    for item in items
                    if item.workstream_id == workstream_id and item.status in {"queued", "planned", "running"}
                ),
                None,
            )
            if existing is not None:
                queued.append(existing.as_dict())
                continue
            entry = QueueEntry(
                queue_id=str(uuid.uuid4()),
                workstream_id=workstream_id,
                queued_at=iso_now(),
                requested_by=requested_by,
                reason=reason,
                status="queued",
                completion_metadata={},
            )
            items.append(entry)
            queued.append(entry.as_dict())
        state["items"] = [item.as_dict() for item in items]
    return {
        "status": "queued",
        "queued": queued,
        "queue_depth": len(
            [item for item in load_merge_train_state(base).get("items", []) if item.get("status") == "queued"]
        ),
    }


def plan_merge_train(
    *,
    repo_root: Path | None = None,
    workstream_ids: list[str] | None = None,
    run_checks: bool = True,
) -> dict[str, Any]:
    base = repo_root_path(repo_root)
    registry = load_workstreams(base)
    queued_items = _selected_queue_entries(base, workstream_ids)
    selected_ids = [item.workstream_id for item in queued_items]
    if not selected_ids:
        raise MergeTrainError("no merge-train workstreams are queued")

    workstreams: list[dict[str, Any]] = []
    queue_index = {item.workstream_id: index for index, item in enumerate(queued_items)}
    for workstream_id in selected_ids:
        workstream = _require_workstream(registry, workstream_id)
        validate_workstream_for_train(workstream, repo_root=base, run_checks=run_checks)
        workstreams.append(workstream)

    waves = _build_waves(workstreams, queue_index)
    surface_groups = {
        workstream["id"]: _shared_surface_groups(workstream) for workstream in workstreams
    }
    return {
        "schema_version": "1.0.0",
        "planned_at": iso_now(),
        "repo_root": str(base),
        "selection": selected_ids,
        "queue": [item.as_dict() for item in queued_items],
        "waves": waves,
        "workstreams": [
            {
                "id": workstream["id"],
                "branch": workstream["branch"],
                "doc": workstream.get("doc"),
                "depends_on": list(workstream.get("depends_on", [])),
                "shared_surfaces": sorted(surface_groups[workstream["id"]]),
                "rollback_strategy": str(workstream["live_apply"]["rollback_bundle"]["strategy"]),
            }
            for workstream in workstreams
        ],
    }


def create_rollback_bundle(
    *,
    repo_root: Path | None = None,
    plan: dict[str, Any],
) -> Path:
    base = repo_root_path(repo_root)
    bundle_id = f"{utc_now().strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}-merge-train"
    bundle_dir = rollback_bundle_dir(base)
    artifacts_root = bundle_dir / f"{bundle_id}.d"
    artifacts_root.mkdir(parents=True, exist_ok=True)
    bundle_path = bundle_dir / f"{bundle_id}.json"
    registry = load_workstreams(base)
    pre_apply_head = git_stdout(["git", "rev-parse", "HEAD"], repo_root=base).strip()
    repo_version = (base / "VERSION").read_text(encoding="utf-8").strip() if (base / "VERSION").exists() else "unknown"

    steps: list[dict[str, Any]] = []
    for workstream_id in plan["selection"]:
        workstream = _require_workstream(registry, workstream_id)
        rollback = workstream["live_apply"]["rollback_bundle"]
        for step_index, step in enumerate(rollback["steps"], start=1):
            serialized = _serialize_rollback_step(
                step,
                repo_root=base,
                artifacts_root=artifacts_root,
                workstream_id=workstream_id,
                step_index=step_index,
            )
            steps.append(serialized)

    steps.append(
        {
            "id": "git-revert-merge-commits",
            "kind": "git_revert_merges",
            "description": "Revert merge-train merge commits in reverse order.",
            "merge_commits": [],
        }
    )
    bundle = {
        "schema_version": "1.0.0",
        "bundle_id": bundle_id,
        "created_at": iso_now(),
        "repo_version_context": repo_version,
        "repo_root": str(base),
        "pre_apply_head": pre_apply_head,
        "selection": list(plan["selection"]),
        "waves": list(plan["waves"]),
        "steps": steps,
        "status": "created",
        "merge_commits": [],
        "artifacts_root": str(artifacts_root),
    }
    write_json(bundle_path, bundle, indent=2)
    return bundle_path


def execute_rollback_bundle(
    bundle_path: Path,
    *,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    base = repo_root_path(repo_root)
    bundle = load_json(bundle_path)
    if not isinstance(bundle, dict):
        raise MergeTrainError(f"{bundle_path} must contain a JSON object")
    step_results: list[dict[str, Any]] = []
    manual_required = False
    for step in bundle.get("steps", []):
        if not isinstance(step, dict):
            continue
        kind = str(step.get("kind", "")).strip()
        if kind == "shell":
            result = _run_step(step, repo_root=base)
            if result["returncode"] != 0:
                _update_bundle_status(bundle_path, status="rollback_failed", step_results=step_results + [result])
                raise MergeTrainError(f"rollback shell step failed: {step.get('id', 'unnamed-step')}")
            step_results.append(result)
            continue
        if kind == "file_restore":
            restored_paths = _restore_snapshot_step(step, repo_root=base)
            step_results.append(
                {
                    "id": step.get("id"),
                    "kind": kind,
                    "returncode": 0,
                    "restored_paths": restored_paths,
                }
            )
            continue
        if kind == "runbook":
            manual_required = True
            step_results.append(
                {
                    "id": step.get("id"),
                    "kind": kind,
                    "returncode": 0,
                    "manual_required": True,
                    "runbook": step.get("path"),
                }
            )
            continue
        if kind == "git_revert_merges":
            merge_commits = [
                str(commit).strip() for commit in step.get("merge_commits", []) if str(commit).strip()
            ]
            for commit in reversed(merge_commits):
                completed = subprocess.run(
                    ["git", "revert", "-m", "1", "--no-edit", commit],
                    cwd=base,
                    text=True,
                    capture_output=True,
                    check=False,
                )
                result = {
                    "id": step.get("id"),
                    "kind": kind,
                    "commit": commit,
                    "returncode": completed.returncode,
                    "stdout": completed.stdout,
                    "stderr": completed.stderr,
                }
                step_results.append(result)
                if completed.returncode != 0:
                    _update_bundle_status(bundle_path, status="rollback_failed", step_results=step_results)
                    raise MergeTrainError(f"failed to revert merge commit {commit}")
            continue
        raise MergeTrainError(f"unsupported rollback step kind '{kind}' in {bundle_path}")

    status = "manual_required" if manual_required else "rolled_back"
    _update_bundle_status(bundle_path, status=status, step_results=step_results)
    return {"status": status, "step_results": step_results}


def execute_merge_train(
    *,
    repo_root: Path | None = None,
    workstream_ids: list[str] | None = None,
    requested_by: str = "operator:merge-train",
    auto_rollback: bool = True,
) -> dict[str, Any]:
    base = repo_root_path(repo_root)
    plan = plan_merge_train(repo_root=base, workstream_ids=workstream_ids, run_checks=True)
    bundle_path = create_rollback_bundle(repo_root=base, plan=plan)
    queued = _selected_queue_entries(base, plan["selection"])
    _mark_queue_entries(base, queued, status="running")
    merge_commits: list[str] = []
    apply_results: list[dict[str, Any]] = []
    try:
        for workstream in plan["workstreams"]:
            merge_commit = _merge_branch(workstream["branch"], repo_root=base)
            merge_commits.append(merge_commit)
            _set_bundle_merge_commits(bundle_path, merge_commits)

        registry = load_workstreams(base)
        for wave in plan["waves"]:
            wave_result = {
                "wave_id": wave["wave_id"],
                "workstreams": [],
            }
            for workstream_id in wave["workstreams"]:
                workstream = _require_workstream(registry, workstream_id)
                result = _run_apply_plan(workstream, repo_root=base)
                wave_result["workstreams"].append(result)
            apply_results.append(wave_result)
    except Exception as exc:  # noqa: BLE001
        rollback_result = None
        if auto_rollback:
            rollback_result = execute_rollback_bundle(bundle_path, repo_root=base)
        _mark_queue_entries(
            base,
            queued,
            status="failed",
            metadata={
                "failed_at": iso_now(),
                "reason": str(exc),
                "rollback_bundle": str(bundle_path),
                "rollback_status": rollback_result["status"] if rollback_result else "not_run",
            },
        )
        return {
            "status": "failed",
            "reason": str(exc),
            "requested_by": requested_by,
            "plan": plan,
            "rollback_bundle": str(bundle_path),
            "merge_commits": merge_commits,
            "apply_results": apply_results,
            "rollback": rollback_result,
        }

    _update_bundle_status(bundle_path, status="completed")
    _mark_queue_entries(
        base,
        queued,
        status="applied",
        metadata={
            "applied_at": iso_now(),
            "rollback_bundle": str(bundle_path),
            "merge_commits": merge_commits,
        },
    )
    return {
        "status": "completed",
        "requested_by": requested_by,
        "plan": plan,
        "rollback_bundle": str(bundle_path),
        "merge_commits": merge_commits,
        "apply_results": apply_results,
    }


def validate_workstream_for_train(
    workstream: dict[str, Any],
    *,
    repo_root: Path,
    run_checks: bool,
) -> None:
    workstream_id = str(workstream.get("id", "")).strip()
    if not workstream_id:
        raise MergeTrainError("workstream entry is missing id")
    if not bool(workstream.get("ready_to_merge")):
        raise MergeTrainError(f"{workstream_id} is not ready_to_merge")
    branch = str(workstream.get("branch", "")).strip()
    if not branch:
        raise MergeTrainError(f"{workstream_id} is missing branch")
    _ensure_git_ref(branch, repo_root=repo_root)
    live_apply = workstream.get("live_apply")
    if not isinstance(live_apply, dict):
        raise MergeTrainError(f"{workstream_id} is missing live_apply metadata")

    docs = live_apply.get("docs")
    if not isinstance(docs, dict):
        raise MergeTrainError(f"{workstream_id} live_apply.docs must be defined")
    adr_refs = docs.get("adrs") or ([workstream.get("doc")] if workstream.get("doc") else [])
    if not isinstance(adr_refs, list) or not adr_refs:
        raise MergeTrainError(f"{workstream_id} must declare at least one ADR document")
    for path in adr_refs:
        _require_repo_file(path, repo_root, label=f"{workstream_id} ADR document")
    runbooks = docs.get("runbooks")
    if not isinstance(runbooks, list) or not runbooks:
        raise MergeTrainError(f"{workstream_id} must declare at least one runbook")
    for path in runbooks:
        _require_repo_file(path, repo_root, label=f"{workstream_id} runbook")

    ownership = live_apply.get("ownership", {})
    if not isinstance(ownership, dict):
        raise MergeTrainError(f"{workstream_id} live_apply.ownership must be a mapping")
    surfaces = ownership.get("surfaces")
    if surfaces is None:
        surfaces = [{"id": str(surface), "mode": "exclusive", "paths": []} for surface in workstream.get("shared_surfaces", [])]
    if not isinstance(surfaces, list) or not surfaces:
        raise MergeTrainError(f"{workstream_id} must declare owned surfaces")
    for index, surface in enumerate(surfaces):
        if not isinstance(surface, dict):
            raise MergeTrainError(f"{workstream_id} live_apply.ownership.surfaces[{index}] must be a mapping")
        surface_id = str(surface.get("id", "")).strip()
        mode = str(surface.get("mode", "")).strip()
        if not surface_id:
            raise MergeTrainError(f"{workstream_id} ownership surface {index} is missing id")
        if mode not in ALLOWED_SURFACE_MODES:
            raise MergeTrainError(
                f"{workstream_id} ownership surface '{surface_id}' must use mode in {sorted(ALLOWED_SURFACE_MODES)}"
            )

    checks = live_apply.get("validation_checks")
    if not isinstance(checks, list) or not checks:
        raise MergeTrainError(f"{workstream_id} must declare validation_checks")
    if run_checks:
        for check in checks:
            if not isinstance(check, dict):
                raise MergeTrainError(f"{workstream_id} validation check must be a mapping")
            result = _run_step(check, repo_root=repo_root)
            if result["returncode"] != 0:
                raise MergeTrainError(f"{workstream_id} validation check failed: {check.get('id', 'unnamed-check')}")

    apply_plan = live_apply.get("apply_plan")
    if not isinstance(apply_plan, dict):
        raise MergeTrainError(f"{workstream_id} must declare live_apply.apply_plan")
    waves = apply_plan.get("waves")
    if not isinstance(waves, list) or not waves:
        raise MergeTrainError(f"{workstream_id} apply plan must declare at least one wave")
    for index, wave in enumerate(waves):
        if not isinstance(wave, dict):
            raise MergeTrainError(f"{workstream_id} apply_plan.waves[{index}] must be a mapping")
        if not str(wave.get("wave_id", "")).strip():
            raise MergeTrainError(f"{workstream_id} apply_plan.waves[{index}] is missing wave_id")
        steps = wave.get("steps")
        if not isinstance(steps, list) or not steps:
            raise MergeTrainError(f"{workstream_id} apply_plan.waves[{index}] must declare steps")
        for step in steps:
            _validate_shell_step(step, label=f"{workstream_id} apply step")

    rollback_bundle = live_apply.get("rollback_bundle")
    if not isinstance(rollback_bundle, dict):
        raise MergeTrainError(f"{workstream_id} must declare live_apply.rollback_bundle")
    if not str(rollback_bundle.get("strategy", "")).strip():
        raise MergeTrainError(f"{workstream_id} rollback bundle must declare strategy")
    steps = rollback_bundle.get("steps")
    if not isinstance(steps, list) or not steps:
        raise MergeTrainError(f"{workstream_id} rollback bundle must declare steps")
    for step in steps:
        _validate_rollback_step(step, label=f"{workstream_id} rollback step")


def _validate_shell_step(step: Any, *, label: str) -> None:
    if not isinstance(step, dict):
        raise MergeTrainError(f"{label} must be a mapping")
    if not str(step.get("id", "")).strip():
        raise MergeTrainError(f"{label} is missing id")
    if step.get("argv") is not None:
        argv = step.get("argv")
        if not isinstance(argv, list) or not argv or not all(isinstance(item, str) and item.strip() for item in argv):
            raise MergeTrainError(f"{label} must define a non-empty argv list")
        return
    command = step.get("command")
    if not isinstance(command, str) or not command.strip():
        raise MergeTrainError(f"{label} must define command or argv")


def _validate_rollback_step(step: Any, *, label: str) -> None:
    if not isinstance(step, dict):
        raise MergeTrainError(f"{label} must be a mapping")
    if not str(step.get("id", "")).strip():
        raise MergeTrainError(f"{label} is missing id")
    kind = str(step.get("kind", "")).strip()
    if kind not in ALLOWED_ROLLBACK_STEP_KINDS:
        raise MergeTrainError(f"{label} must use kind in {sorted(ALLOWED_ROLLBACK_STEP_KINDS)}")
    if kind == "shell":
        _validate_shell_step(step, label=label)
        return
    if kind == "file_restore":
        paths = step.get("paths")
        if not isinstance(paths, list) or not paths or not all(isinstance(item, str) and item.strip() for item in paths):
            raise MergeTrainError(f"{label} must declare non-empty paths for file_restore")
        return
    path = step.get("path")
    if not isinstance(path, str) or not path.strip():
        raise MergeTrainError(f"{label} must declare a runbook path")


def _shared_surface_groups(workstream: dict[str, Any]) -> set[str]:
    live_apply = workstream.get("live_apply", {})
    ownership = live_apply.get("ownership", {}) if isinstance(live_apply, dict) else {}
    surfaces = ownership.get("surfaces") if isinstance(ownership, dict) else None
    if isinstance(surfaces, list) and surfaces:
        return {
            str(surface.get("id", "")).strip()
            for surface in surfaces
            if isinstance(surface, dict) and str(surface.get("id", "")).strip()
        }
    return {
        str(surface).strip()
        for surface in workstream.get("shared_surfaces", [])
        if isinstance(surface, str) and str(surface).strip()
    }


def _selected_queue_entries(repo_root: Path, requested_ids: list[str] | None) -> list[QueueEntry]:
    state = load_merge_train_state(repo_root)
    items = [QueueEntry.from_dict(item) for item in state.get("items", []) if isinstance(item, dict)]
    queued = [item for item in items if item.status == "queued"]
    if requested_ids is None:
        return sorted(queued, key=lambda item: (item.queued_at, item.queue_id))
    requested = {item for item in requested_ids}
    ordered = [item for item in sorted(queued, key=lambda entry: (entry.queued_at, entry.queue_id)) if item.workstream_id in requested]
    missing = sorted(requested - {item.workstream_id for item in ordered})
    if missing:
        raise MergeTrainError(f"workstreams are not queued: {', '.join(missing)}")
    return ordered


def _build_waves(workstreams: list[dict[str, Any]], queue_index: dict[str, int]) -> list[dict[str, Any]]:
    selected_ids = [str(workstream["id"]) for workstream in workstreams]
    indegree = {workstream_id: 0 for workstream_id in selected_ids}
    edges = {workstream_id: set() for workstream_id in selected_ids}

    for workstream in workstreams:
        source = str(workstream["id"])
        for dependency in workstream.get("depends_on", []):
            dependency_id = str(dependency).strip()
            if dependency_id not in indegree:
                continue
            if source not in edges[dependency_id]:
                edges[dependency_id].add(source)
                indegree[source] += 1

    by_surface: dict[str, list[str]] = {}
    for workstream in workstreams:
        for surface in sorted(_shared_surface_groups(workstream)):
            by_surface.setdefault(surface, []).append(str(workstream["id"]))
    for members in by_surface.values():
        if len(members) < 2:
            continue
        ordered = sorted(members, key=lambda workstream_id: queue_index.get(workstream_id, 0))
        for predecessor, successor in zip(ordered, ordered[1:]):
            if successor not in edges[predecessor]:
                edges[predecessor].add(successor)
                indegree[successor] += 1

    waves: list[dict[str, Any]] = []
    pending = set(selected_ids)
    wave_number = 1
    while pending:
        ready = sorted(
            [workstream_id for workstream_id in pending if indegree[workstream_id] == 0],
            key=lambda workstream_id: queue_index.get(workstream_id, 0),
        )
        if not ready:
            raise MergeTrainError("merge-train dependencies contain a cycle")
        waves.append({"wave_id": f"wave-{wave_number:02d}", "workstreams": ready})
        wave_number += 1
        for workstream_id in ready:
            pending.remove(workstream_id)
            for successor in edges[workstream_id]:
                indegree[successor] -= 1
    return waves


def _run_apply_plan(workstream: dict[str, Any], *, repo_root: Path) -> dict[str, Any]:
    plan = workstream["live_apply"]["apply_plan"]
    wave_results: list[dict[str, Any]] = []
    for wave in plan["waves"]:
        step_results = []
        for step in wave["steps"]:
            result = _run_step(step, repo_root=repo_root)
            step_results.append(result)
            if result["returncode"] != 0:
                raise MergeTrainError(f"{workstream['id']} apply step failed: {step.get('id', 'unnamed-step')}")
        wave_results.append({"wave_id": wave["wave_id"], "steps": step_results})
    return {"workstream_id": workstream["id"], "waves": wave_results}


def _serialize_rollback_step(
    step: dict[str, Any],
    *,
    repo_root: Path,
    artifacts_root: Path,
    workstream_id: str,
    step_index: int,
) -> dict[str, Any]:
    serialized = dict(step)
    kind = str(step["kind"])
    if kind != "file_restore":
        return serialized

    snapshot_entries = []
    snapshot_root = artifacts_root / workstream_id / f"step-{step_index:02d}"
    for raw_path in step["paths"]:
        relative = Path(str(raw_path))
        target = repo_root / relative
        snapshot_dir = snapshot_root / relative
        exists = target.exists()
        entry = {
            "path": str(relative),
            "exists": exists,
            "is_dir": target.is_dir() if exists else False,
            "snapshot_path": str(snapshot_dir),
        }
        if exists:
            snapshot_dir.parent.mkdir(parents=True, exist_ok=True)
            if target.is_dir():
                shutil.copytree(target, snapshot_dir, dirs_exist_ok=True)
            else:
                shutil.copy2(target, snapshot_dir)
        snapshot_entries.append(entry)
    serialized["snapshots"] = snapshot_entries
    return serialized


def _restore_snapshot_step(step: dict[str, Any], *, repo_root: Path) -> list[str]:
    restored: list[str] = []
    for snapshot in step.get("snapshots", []):
        if not isinstance(snapshot, dict):
            continue
        relative = Path(str(snapshot["path"]))
        destination = repo_root / relative
        snapshot_path = Path(str(snapshot["snapshot_path"]))
        existed = bool(snapshot.get("exists"))
        if destination.exists():
            if destination.is_dir():
                shutil.rmtree(destination)
            else:
                destination.unlink()
        if existed:
            destination.parent.mkdir(parents=True, exist_ok=True)
            if bool(snapshot.get("is_dir")):
                shutil.copytree(snapshot_path, destination)
            else:
                shutil.copy2(snapshot_path, destination)
        restored.append(str(relative))
    return restored


def _run_step(step: dict[str, Any], *, repo_root: Path) -> dict[str, Any]:
    command: list[str]
    if isinstance(step.get("argv"), list):
        command = [str(item) for item in step["argv"]]
    else:
        command = ["/bin/sh", "-lc", str(step["command"])]
    cwd = repo_root / str(step.get("cwd", "."))
    env = os.environ.copy()
    raw_env = step.get("env")
    if isinstance(raw_env, dict):
        env.update({str(key): str(value) for key, value in raw_env.items()})
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    return {
        "id": step.get("id"),
        "command": command,
        "cwd": str(cwd),
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def _merge_branch(branch: str, *, repo_root: Path) -> str:
    ref = _resolve_git_ref(branch, repo_root=repo_root)
    completed = subprocess.run(
        ["git", "merge", "--no-ff", "--no-edit", ref],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        abort = subprocess.run(
            ["git", "merge", "--abort"],
            cwd=repo_root,
            text=True,
            capture_output=True,
            check=False,
        )
        details = completed.stderr or completed.stdout or abort.stderr or abort.stdout
        raise MergeTrainError(f"failed to merge branch '{branch}': {details.strip()}")
    return git_stdout(["git", "rev-parse", "HEAD"], repo_root=repo_root).strip()


def _mark_queue_entries(
    repo_root: Path,
    entries: list[QueueEntry],
    *,
    status: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    queue_ids = {entry.queue_id for entry in entries}
    with locked_json_state(merge_train_state_path(repo_root), default_factory=_empty_state) as state:
        updated = []
        for item in state.get("items", []):
            entry = QueueEntry.from_dict(item)
            if entry.queue_id in queue_ids:
                entry = QueueEntry(
                    queue_id=entry.queue_id,
                    workstream_id=entry.workstream_id,
                    queued_at=entry.queued_at,
                    requested_by=entry.requested_by,
                    reason=entry.reason,
                    status=status,
                    completion_metadata=dict(metadata or {}),
                )
            updated.append(entry.as_dict())
        state["items"] = updated


def _set_bundle_merge_commits(bundle_path: Path, merge_commits: list[str]) -> None:
    bundle = load_json(bundle_path)
    if not isinstance(bundle, dict):
        raise MergeTrainError(f"{bundle_path} must contain a JSON object")
    bundle["merge_commits"] = list(merge_commits)
    for step in bundle.get("steps", []):
        if isinstance(step, dict) and step.get("kind") == "git_revert_merges":
            step["merge_commits"] = list(merge_commits)
    write_json(bundle_path, bundle, indent=2)


def _update_bundle_status(bundle_path: Path, *, status: str, step_results: list[dict[str, Any]] | None = None) -> None:
    bundle = load_json(bundle_path)
    if not isinstance(bundle, dict):
        raise MergeTrainError(f"{bundle_path} must contain a JSON object")
    bundle["status"] = status
    bundle["updated_at"] = iso_now()
    if step_results is not None:
        bundle["step_results"] = step_results
    write_json(bundle_path, bundle, indent=2)


def _ensure_git_ref(ref: str, *, repo_root: Path) -> None:
    _resolve_git_ref(ref, repo_root=repo_root)


def _resolve_git_ref(ref: str, *, repo_root: Path) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "--verify", ref],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode == 0:
        return ref
    remote_ref = f"origin/{ref}"
    completed = subprocess.run(
        ["git", "rev-parse", "--verify", remote_ref],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise MergeTrainError(f"branch '{ref}' is not available locally or on origin")
    return remote_ref


def _require_repo_file(path_ref: Any, repo_root: Path, *, label: str) -> None:
    if not isinstance(path_ref, str) or not path_ref.strip():
        raise MergeTrainError(f"{label} path is missing")
    path = repo_root / path_ref
    if not path.exists():
        raise MergeTrainError(f"{label} does not exist: {path_ref}")


def _require_workstream(registry: dict[str, dict[str, Any]], workstream_id: str) -> dict[str, Any]:
    if workstream_id not in registry:
        raise MergeTrainError(f"unknown workstream '{workstream_id}'")
    return registry[workstream_id]


def git_stdout(command: list[str], *, repo_root: Path) -> str:
    completed = subprocess.run(
        command,
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise MergeTrainError(completed.stderr.strip() or completed.stdout.strip() or "git command failed")
    return completed.stdout


def _empty_state() -> dict[str, Any]:
    return {"schema_version": "1.0.0", "items": []}
