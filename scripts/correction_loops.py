#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Final

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from controller_automation_toolkit import emit_cli_error, load_json, repo_path


CORRECTION_LOOP_CATALOG_PATH: Final[Path] = repo_path("config", "correction-loops.json")
SUPPORTED_SCHEMA_VERSION: Final[str] = "1.0.0"
REQUIRED_DIAGNOSES: Final[set[str]] = {
    "transient_failure",
    "contract_drift",
    "dependency_outage",
    "stale_input",
    "irreversible_data_loss_risk",
}
ALLOWED_REPAIR_ACTION_KINDS: Final[set[str]] = {"no_op", "reconcile", "rollback", "replace", "escalate"}


def load_correction_loop_catalog(path: Path = CORRECTION_LOOP_CATALOG_PATH) -> dict[str, Any]:
    return load_json(path)


def _require_mapping(value: object, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object")
    return dict(value)


def _require_list(value: object, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{path} must be a list")
    return list(value)


def _require_str(value: object, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path} must be a non-empty string")
    return value


def _require_bool(value: object, path: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{path} must be a boolean")
    return value


def _require_int(value: object, path: str, *, minimum: int = 0, maximum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{path} must be an integer")
    if value < minimum:
        raise ValueError(f"{path} must be >= {minimum}")
    if maximum is not None and value > maximum:
        raise ValueError(f"{path} must be <= {maximum}")
    return value


def _require_string_list(value: object, path: str) -> list[str]:
    items = _require_list(value, path)
    result: list[str] = []
    for index, item in enumerate(items):
        result.append(_require_str(item, f"{path}[{index}]"))
    if len(result) != len(set(result)):
        raise ValueError(f"{path} must not contain duplicates")
    return result


def workflow_matches_loop(loop: dict[str, Any], workflow_id: str) -> bool:
    selectors = _require_mapping(loop.get("applies_to"), f"correction loop '{loop.get('id', '<unknown>')}'.applies_to")
    for candidate in selectors.get("workflow_ids", []):
        if candidate == workflow_id:
            return True
    for prefix in selectors.get("workflow_id_prefixes", []):
        if workflow_id.startswith(prefix):
            return True
    return False


def matching_workflow_correction_loops(catalog: dict[str, Any], workflow_id: str) -> list[dict[str, Any]]:
    loops = _require_list(catalog.get("loops"), "config/correction-loops.json.loops")
    return [loop for loop in loops if isinstance(loop, dict) and workflow_matches_loop(loop, workflow_id)]


def resolve_workflow_correction_loop(catalog: dict[str, Any], workflow_id: str) -> dict[str, Any] | None:
    matches = matching_workflow_correction_loops(catalog, workflow_id)
    if not matches:
        return None
    if len(matches) > 1:
        match_ids = ", ".join(sorted(str(loop.get("id")) for loop in matches))
        raise ValueError(f"workflow '{workflow_id}' matches multiple correction loops: {match_ids}")
    return matches[0]


def _required_workflow_ids(workflow_catalog: dict[str, Any], catalog: dict[str, Any]) -> set[str]:
    workflows = _require_mapping(workflow_catalog.get("workflows"), "config/workflow-catalog.json.workflows")
    required = {
        workflow_id
        for workflow_id, workflow in workflows.items()
        if isinstance(workflow, dict) and workflow.get("execution_class", "mutation") == "mutation"
    }
    required.update(_require_string_list(catalog.get("required_workflow_ids", []), "config/correction-loops.json.required_workflow_ids"))
    return required


def validate_correction_loop_catalog(catalog: dict[str, Any], workflow_catalog: dict[str, Any]) -> None:
    if catalog.get("$schema") != "docs/schema/correction-loop-catalog.schema.json":
        raise ValueError("config/correction-loops.json.$schema must be 'docs/schema/correction-loop-catalog.schema.json'")
    if catalog.get("schema_version") != SUPPORTED_SCHEMA_VERSION:
        raise ValueError(f"config/correction-loops.json.schema_version must be '{SUPPORTED_SCHEMA_VERSION}'")

    workflows = _require_mapping(workflow_catalog.get("workflows"), "config/workflow-catalog.json.workflows")
    loops = _require_list(catalog.get("loops"), "config/correction-loops.json.loops")
    if not loops:
        raise ValueError("config/correction-loops.json.loops must not be empty")

    seen_ids: set[str] = set()
    matched_workflow_ids: set[str] = set()
    for index, loop in enumerate(loops):
        path = f"config/correction-loops.json.loops[{index}]"
        loop = _require_mapping(loop, path)
        loop_id = _require_str(loop.get("id"), f"{path}.id")
        if loop_id in seen_ids:
            raise ValueError(f"{path}.id '{loop_id}' is duplicated")
        seen_ids.add(loop_id)

        _require_str(loop.get("description"), f"{path}.description")
        selectors = _require_mapping(loop.get("applies_to"), f"{path}.applies_to")
        workflow_ids = _require_string_list(selectors.get("workflow_ids", []), f"{path}.applies_to.workflow_ids")
        workflow_id_prefixes = _require_string_list(
            selectors.get("workflow_id_prefixes", []),
            f"{path}.applies_to.workflow_id_prefixes",
        )
        if not workflow_ids and not workflow_id_prefixes:
            raise ValueError(f"{path}.applies_to must declare at least one workflow id or workflow prefix")

        loop_matches: set[str] = set()
        for workflow_id in workflow_ids:
            if workflow_id not in workflows:
                raise ValueError(f"{path}.applies_to.workflow_ids references unknown workflow '{workflow_id}'")
            loop_matches.add(workflow_id)
        for prefix in workflow_id_prefixes:
            for workflow_id in workflows:
                if workflow_id.startswith(prefix):
                    loop_matches.add(workflow_id)
        if not loop_matches:
            raise ValueError(f"{path}.applies_to does not match any workflow in config/workflow-catalog.json")

        _require_str(loop.get("invariant"), f"{path}.invariant")
        observation_sources = _require_string_list(loop.get("observation_sources"), f"{path}.observation_sources")
        if not observation_sources:
            raise ValueError(f"{path}.observation_sources must not be empty")

        diagnosis_taxonomy = set(
            _require_string_list(loop.get("diagnosis_taxonomy"), f"{path}.diagnosis_taxonomy")
        )
        if not REQUIRED_DIAGNOSES.issubset(diagnosis_taxonomy):
            missing = sorted(REQUIRED_DIAGNOSES - diagnosis_taxonomy)
            raise ValueError(f"{path}.diagnosis_taxonomy is missing required diagnoses: {', '.join(missing)}")

        repair_actions = _require_list(loop.get("repair_actions"), f"{path}.repair_actions")
        if len(repair_actions) < 2:
            raise ValueError(f"{path}.repair_actions must declare at least two ordered actions")
        action_kinds: list[str] = []
        for action_index, action in enumerate(repair_actions):
            action_path = f"{path}.repair_actions[{action_index}]"
            action = _require_mapping(action, action_path)
            kind = _require_str(action.get("kind"), f"{action_path}.kind")
            if kind not in ALLOWED_REPAIR_ACTION_KINDS:
                raise ValueError(f"{action_path}.kind must be one of {sorted(ALLOWED_REPAIR_ACTION_KINDS)}")
            action_kinds.append(kind)
            _require_str(action.get("summary"), f"{action_path}.summary")
            requires_approval = _require_bool(action.get("requires_approval"), f"{action_path}.requires_approval")
            destructive = _require_bool(action.get("destructive"), f"{action_path}.destructive")
            if destructive and not requires_approval:
                raise ValueError(f"{action_path} destructive actions must require approval")
            if kind == "escalate" and destructive:
                raise ValueError(f"{action_path} escalate actions must not be marked destructive")
        if action_kinds[0] != "no_op":
            raise ValueError(f"{path}.repair_actions must start with a no_op action")
        if "reconcile" not in action_kinds:
            raise ValueError(f"{path}.repair_actions must include a reconcile action")
        if "escalate" not in action_kinds:
            raise ValueError(f"{path}.repair_actions must include an escalate action")
        if len(action_kinds) != len(set(action_kinds)):
            raise ValueError(f"{path}.repair_actions must not repeat action kinds")
        if action_kinds.index("reconcile") < action_kinds.index("no_op"):
            raise ValueError(f"{path}.repair_actions must not place reconcile before no_op")
        if action_kinds.index("escalate") < action_kinds.index("reconcile"):
            raise ValueError(f"{path}.repair_actions must not place escalate before reconcile")

        verification = _require_mapping(loop.get("verification"), f"{path}.verification")
        _require_str(verification.get("source"), f"{path}.verification.source")
        _require_str(verification.get("success_signal"), f"{path}.verification.success_signal")

        escalation = _require_mapping(loop.get("escalation"), f"{path}.escalation")
        _require_str(escalation.get("boundary"), f"{path}.escalation.boundary")
        _require_str(escalation.get("target"), f"{path}.escalation.target")
        runbook = _require_str(escalation.get("runbook"), f"{path}.escalation.runbook")
        if not repo_path(runbook).is_file():
            raise ValueError(f"{path}.escalation.runbook references missing path '{runbook}'")

        retry_budget_cycles = loop.get("retry_budget_cycles")
        if retry_budget_cycles is not None:
            _require_int(retry_budget_cycles, f"{path}.retry_budget_cycles", minimum=0, maximum=5)

        overlap = matched_workflow_ids & loop_matches
        if overlap:
            duplicates = ", ".join(sorted(overlap))
            raise ValueError(f"{path}.applies_to overlaps with another correction loop for workflows: {duplicates}")
        matched_workflow_ids.update(loop_matches)

    required = _required_workflow_ids(workflow_catalog, catalog)
    uncovered = sorted(required - matched_workflow_ids)
    if uncovered:
        raise ValueError(
            "config/correction-loops.json does not cover every governed self-correction surface: "
            + ", ".join(uncovered)
        )


def _format_loop(loop: dict[str, Any]) -> list[str]:
    lines = [
        f"Correction loop: {loop['id']}",
        f"Description: {loop['description']}",
        f"Invariant: {loop['invariant']}",
        "Observation sources:",
    ]
    for item in loop["observation_sources"]:
        lines.append(f"  - {item}")
    lines.append("Repair actions:")
    for action in loop["repair_actions"]:
        approval = "approval" if action["requires_approval"] else "auto"
        lines.append(f"  - {action['kind']} [{approval}]: {action['summary']}")
    lines.append(f"Verification: {loop['verification']['source']}")
    lines.append(f"Success signal: {loop['verification']['success_signal']}")
    lines.append(f"Escalation boundary: {loop['escalation']['boundary']}")
    lines.append(f"Escalation target: {loop['escalation']['target']}")
    lines.append(f"Escalation runbook: {loop['escalation']['runbook']}")
    if loop.get("retry_budget_cycles") is not None:
        lines.append(f"Retry budget cycles: {loop['retry_budget_cycles']}")
    return lines


def list_correction_loops(catalog: dict[str, Any], workflow_catalog: dict[str, Any]) -> int:
    workflows = _require_mapping(workflow_catalog.get("workflows"), "config/workflow-catalog.json.workflows")
    print(f"Correction loop catalog: {CORRECTION_LOOP_CATALOG_PATH}")
    print("Available correction loops:")
    for loop in _require_list(catalog.get("loops"), "config/correction-loops.json.loops"):
        loop = _require_mapping(loop, "config/correction-loops.json.loops[*]")
        matches = sorted(
            workflow_id for workflow_id in workflows if workflow_matches_loop(loop, workflow_id)
        )
        print(f"  - {loop['id']} ({len(matches)} workflow(s))")
    return 0


def show_correction_loop_for_workflow(catalog: dict[str, Any], workflow_id: str) -> int:
    loop = resolve_workflow_correction_loop(catalog, workflow_id)
    if loop is None:
        print(f"No correction loop found for workflow: {workflow_id}", file=sys.stderr)
        return 2
    for line in _format_loop(loop):
        print(line)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect or validate the repository correction-loop catalog.")
    parser.add_argument("--list", action="store_true", help="List available correction loops.")
    parser.add_argument("--workflow", help="Show the correction loop that applies to one workflow.")
    parser.add_argument("--validate", action="store_true", help="Validate the correction-loop catalog.")
    args = parser.parse_args()

    try:
        catalog = load_correction_loop_catalog()
        workflow_catalog = load_json(repo_path("config", "workflow-catalog.json"))
        validate_correction_loop_catalog(catalog, workflow_catalog)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return emit_cli_error("Correction-loop catalog", exc)

    if args.validate:
        print(f"Correction-loop catalog OK: {CORRECTION_LOOP_CATALOG_PATH}")
        return 0
    if args.workflow:
        return show_correction_loop_for_workflow(catalog, args.workflow)
    return list_correction_loops(catalog, workflow_catalog)


if __name__ == "__main__":
    sys.exit(main())
