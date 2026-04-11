#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from controller_automation_toolkit import (
    REPO_ROOT,
    SECRET_MANIFEST_PATH,
    WORKFLOW_CATALOG_PATH,
    emit_cli_error,
    load_json,
    load_yaml,
    parse_make_targets,
    repo_path,
)
from correction_loops import (
    CORRECTION_LOOP_CATALOG_PATH,
    load_correction_loop_catalog,
    resolve_workflow_correction_loop,
    validate_correction_loop_catalog,
)
from workbench_information_architecture import TASK_LANE_IDS, normalize_task_lane
from worktree_bootstrap import (
    load_bootstrap_catalog,
    resolve_workflow_manifest_ids,
    validate_bootstrap_catalog,
)

ALLOWED_ENTRYPOINT_KINDS = {"make_target"}
ALLOWED_LIVE_IMPACTS = {
    "repo_only",
    "host_live",
    "guest_live",
    "host_and_guest_live",
    "external_live",
}
ALLOWED_LIFECYCLE_STATUSES = {"active", "blocked"}
ALLOWED_EXECUTION_CLASSES = {"mutation", "diagnostic"}
ALLOWED_ESCALATION_ACTIONS = {"notify_and_abort", "abort_silently", "escalate_to_operator"}
ALLOWED_RESOURCE_CLAIM_ACCESS = {"read", "write", "exclusive"}
WORKFLOW_SECRET_FIELDS = ("required_secret_ids", "generated_secret_ids", "blocked_secret_ids")
EXECUTION_LANES_PATH = repo_path("config", "execution-lanes.yaml")
DEFAULT_PREFLIGHT_HEALTH_CHECK_TIMEOUT_SECONDS = 15


def load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def load_secret_manifest() -> dict:
    return load_json(SECRET_MANIFEST_PATH)


def load_workflow_catalog() -> dict:
    return load_json(WORKFLOW_CATALOG_PATH)


def load_workflow_defaults() -> dict:
    return load_yaml(repo_path("config", "workflow-defaults.yaml"))


def load_execution_lane_ids() -> set[str]:
    if not EXECUTION_LANES_PATH.exists():
        return set()
    payload = load_yaml(EXECUTION_LANES_PATH)
    lanes = payload.get("lanes", [])
    if not isinstance(lanes, list):
        raise ValueError("config/execution-lanes.yaml must define a lanes list")
    lane_ids: set[str] = set()
    for index, lane in enumerate(lanes):
        if not isinstance(lane, dict):
            raise ValueError(f"config/execution-lanes.yaml lane[{index}] must be a mapping")
        lane_id = lane.get("lane_id")
        if not isinstance(lane_id, str) or not lane_id.strip():
            raise ValueError(f"config/execution-lanes.yaml lane[{index}].lane_id must be a non-empty string")
        lane_ids.add(lane_id.strip())
    return lane_ids


def validate_budget_payload(payload: dict, workflow_id: str) -> None:
    if not isinstance(payload, dict):
        raise ValueError(f"workflow '{workflow_id}' budget must be a mapping")
    required_int_fields = (
        "max_duration_seconds",
        "max_steps",
        "max_concurrent_instances",
        "max_touched_hosts",
        "max_restarts",
        "max_rollback_depth",
    )
    for field in required_int_fields:
        value = payload.get(field)
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"workflow '{workflow_id}' budget field '{field}' must be an integer")
        if value < 0:
            raise ValueError(f"workflow '{workflow_id}' budget field '{field}' must be >= 0")
    if payload["max_duration_seconds"] < 1:
        raise ValueError(f"workflow '{workflow_id}' budget field 'max_duration_seconds' must be >= 1")
    if payload["max_steps"] < 1:
        raise ValueError(f"workflow '{workflow_id}' budget field 'max_steps' must be >= 1")
    if payload["max_concurrent_instances"] < 1:
        raise ValueError(f"workflow '{workflow_id}' budget field 'max_concurrent_instances' must be >= 1")
    escalation_action = payload.get("escalation_action")
    if escalation_action not in ALLOWED_ESCALATION_ACTIONS:
        raise ValueError(
            f"workflow '{workflow_id}' budget escalation_action must be one of {sorted(ALLOWED_ESCALATION_ACTIONS)}"
        )


def validate_resource_reservation_payload(payload: dict, workflow_id: str) -> None:
    if not isinstance(payload, dict):
        raise ValueError(f"workflow '{workflow_id}' resource_reservation must be a mapping")
    required_int_fields = ("cpu_milli", "memory_mb", "disk_iops", "estimated_duration_seconds")
    for field in required_int_fields:
        value = payload.get(field)
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"workflow '{workflow_id}' resource_reservation field '{field}' must be an integer")
        if value < 0:
            raise ValueError(f"workflow '{workflow_id}' resource_reservation field '{field}' must be >= 0")
    if payload["estimated_duration_seconds"] < 1:
        raise ValueError(
            f"workflow '{workflow_id}' resource_reservation field 'estimated_duration_seconds' must be >= 1"
        )


def validate_resource_claims(payload: object, workflow_id: str) -> None:
    if payload is None:
        return
    if not isinstance(payload, list):
        raise ValueError(f"workflow '{workflow_id}' resource_claims must be a list")
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            raise ValueError(f"workflow '{workflow_id}' resource_claims[{index}] must be a mapping")
        resource = item.get("resource")
        access = item.get("access")
        if not isinstance(resource, str) or not resource.strip():
            raise ValueError(f"workflow '{workflow_id}' resource_claims[{index}].resource must be a non-empty string")
        if access not in ALLOWED_RESOURCE_CLAIM_ACCESS:
            raise ValueError(
                f"workflow '{workflow_id}' resource_claims[{index}].access must be one of {sorted(ALLOWED_RESOURCE_CLAIM_ACCESS)}"
            )


def validate_secret_manifest(manifest: dict) -> None:
    secrets = manifest.get("secrets")
    if not isinstance(secrets, dict):
        raise ValueError("secret manifest must define an object-valued 'secrets' key")


def validate_preflight_health_checks(health_checks: object, workflow_id: str) -> None:
    if health_checks is None:
        return
    if not isinstance(health_checks, list):
        raise ValueError(f"workflow '{workflow_id}' preflight.health_checks must be a list")
    for index, check in enumerate(health_checks):
        path = f"workflow '{workflow_id}' preflight.health_checks[{index}]"
        if not isinstance(check, dict):
            raise ValueError(f"{path} must be a mapping")
        check_id = check.get("id")
        if not isinstance(check_id, str) or not check_id.strip():
            raise ValueError(f"{path}.id must be a non-empty string")
        description = check.get("description")
        if not isinstance(description, str) or not description.strip():
            raise ValueError(f"{path}.description must be a non-empty string")
        command = check.get("command")
        if not isinstance(command, str) or not command.strip():
            raise ValueError(f"{path}.command must be a non-empty string")
        timeout_seconds = check.get("timeout_seconds", DEFAULT_PREFLIGHT_HEALTH_CHECK_TIMEOUT_SECONDS)
        if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, int):
            raise ValueError(f"{path}.timeout_seconds must be an integer")
        if timeout_seconds < 1:
            raise ValueError(f"{path}.timeout_seconds must be >= 1")


def validate_workflow_catalog(catalog: dict, secret_manifest: dict, bootstrap_catalog: dict | None = None) -> None:
    workflows = catalog.get("workflows")
    secrets = secret_manifest["secrets"]
    make_targets = parse_make_targets()
    defaults = load_workflow_defaults()
    if bootstrap_catalog is None:
        bootstrap_catalog = load_bootstrap_catalog()
    validate_bootstrap_catalog(bootstrap_catalog)
    defaults_payload = defaults.get("default_budget")
    if not isinstance(defaults_payload, dict):
        raise ValueError("config/workflow-defaults.yaml must define default_budget")
    validate_budget_payload(defaults_payload, "default_budget")
    default_reservation_payload = defaults.get("default_resource_reservation")
    if not isinstance(default_reservation_payload, dict):
        raise ValueError("config/workflow-defaults.yaml must define default_resource_reservation")
    validate_resource_reservation_payload(default_reservation_payload, "default_resource_reservation")
    execution_lane_ids = load_execution_lane_ids()

    if not isinstance(workflows, dict):
        raise ValueError("workflow catalog must define an object-valued 'workflows' key")

    for workflow_id, workflow in workflows.items():
        if not isinstance(workflow.get("description"), str) or not workflow["description"].strip():
            raise ValueError(f"workflow '{workflow_id}' must define a non-empty description")

        lifecycle_status = workflow.get("lifecycle_status")
        if lifecycle_status not in ALLOWED_LIFECYCLE_STATUSES:
            raise ValueError(f"workflow '{workflow_id}' has invalid lifecycle_status '{lifecycle_status}'")

        execution_class = workflow.get("execution_class", "mutation")
        if execution_class not in ALLOWED_EXECUTION_CLASSES:
            raise ValueError(f"workflow '{workflow_id}' has invalid execution_class '{execution_class}'")
        target_lane = workflow.get("target_lane")
        if target_lane is not None:
            if not isinstance(target_lane, str) or not target_lane.strip():
                raise ValueError(f"workflow '{workflow_id}' target_lane must be a non-empty string")
            if target_lane not in execution_lane_ids:
                raise ValueError(f"workflow '{workflow_id}' references unknown target_lane '{target_lane}'")
        dedup_window = workflow.get("dedup_window_seconds")
        if dedup_window is not None and (
            isinstance(dedup_window, bool) or not isinstance(dedup_window, int) or dedup_window < 0
        ):
            raise ValueError(f"workflow '{workflow_id}' dedup_window_seconds must be an integer >= 0")
        validate_resource_claims(workflow.get("resource_claims"), workflow_id)
        tags = workflow.get("tags", [])
        if not isinstance(tags, list):
            raise ValueError(f"workflow '{workflow_id}' tags must be a list")
        for index, tag in enumerate(tags):
            if not isinstance(tag, str) or not tag.strip():
                raise ValueError(f"workflow '{workflow_id}' tags[{index}] must be a non-empty string")
        human_navigation = workflow.get("human_navigation")
        if human_navigation is not None:
            if not isinstance(human_navigation, dict):
                raise ValueError(f"workflow '{workflow_id}' human_navigation must be a mapping")
            launcher = human_navigation.get("launcher")
            if launcher is not None:
                if not isinstance(launcher, dict):
                    raise ValueError(f"workflow '{workflow_id}' human_navigation.launcher must be a mapping")
                enabled = launcher.get("enabled")
                if not isinstance(enabled, bool):
                    raise ValueError(f"workflow '{workflow_id}' human_navigation.launcher.enabled must be a boolean")
                if enabled:
                    lane = normalize_task_lane(launcher.get("lane"), default="")
                    if lane not in TASK_LANE_IDS:
                        raise ValueError(
                            f"workflow '{workflow_id}' human_navigation.launcher.lane must be one of "
                            f"{sorted(TASK_LANE_IDS)}"
                        )
                    if not isinstance(launcher.get("label"), str) or not launcher["label"].strip():
                        raise ValueError(
                            f"workflow '{workflow_id}' human_navigation.launcher.label must be a non-empty string"
                        )
                    if not isinstance(launcher.get("description"), str) or not launcher["description"].strip():
                        raise ValueError(
                            f"workflow '{workflow_id}' human_navigation.launcher.description must be a non-empty string"
                        )
                    href = launcher.get("href")
                    if not isinstance(href, str) or not href.strip():
                        raise ValueError(
                            f"workflow '{workflow_id}' human_navigation.launcher.href must be a non-empty string"
                        )
                    personas = launcher.get("personas", [])
                    if not isinstance(personas, list):
                        raise ValueError(f"workflow '{workflow_id}' human_navigation.launcher.personas must be a list")
                    for index, persona in enumerate(personas):
                        if not isinstance(persona, str) or not persona.strip():
                            raise ValueError(
                                f"workflow '{workflow_id}' human_navigation.launcher.personas[{index}] must be a non-empty string"
                            )
        required_read_surfaces = workflow.get("required_read_surfaces", [])
        if not isinstance(required_read_surfaces, list):
            raise ValueError(f"workflow '{workflow_id}' required_read_surfaces must be a list")
        for index, surface in enumerate(required_read_surfaces):
            if not isinstance(surface, str) or not surface.strip():
                raise ValueError(f"workflow '{workflow_id}' required_read_surfaces[{index}] must be a non-empty string")

        budget = dict(defaults_payload)
        workflow_budget = workflow.get("budget", {})
        if workflow_budget is None:
            workflow_budget = {}
        if not isinstance(workflow_budget, dict):
            raise ValueError(f"workflow '{workflow_id}' budget must be a mapping")
        budget.update(workflow_budget)
        validate_budget_payload(budget, workflow_id)
        reservation = dict(default_reservation_payload)
        workflow_reservation = workflow.get("resource_reservation", {})
        if workflow_reservation is None:
            workflow_reservation = {}
        if not isinstance(workflow_reservation, dict):
            raise ValueError(f"workflow '{workflow_id}' resource_reservation must be a mapping")
        reservation.update(workflow_reservation)
        if execution_class == "mutation":
            validate_resource_reservation_payload(reservation, workflow_id)

        preferred_entrypoint = workflow.get("preferred_entrypoint")
        if not isinstance(preferred_entrypoint, dict):
            raise ValueError(f"workflow '{workflow_id}' must define preferred_entrypoint")

        entrypoint_kind = preferred_entrypoint.get("kind")
        if entrypoint_kind not in ALLOWED_ENTRYPOINT_KINDS:
            raise ValueError(f"workflow '{workflow_id}' has unsupported entrypoint kind '{entrypoint_kind}'")

        if entrypoint_kind == "make_target":
            target = preferred_entrypoint.get("target")
            command = preferred_entrypoint.get("command")
            if not isinstance(target, str) or not target:
                raise ValueError(f"workflow '{workflow_id}' make_target entrypoint needs target")
            if target not in make_targets:
                raise ValueError(f"workflow '{workflow_id}' references unknown Make target '{target}'")
            if not isinstance(command, str) or not command.strip():
                raise ValueError(f"workflow '{workflow_id}' make_target entrypoint needs a command string")

        preflight = workflow.get("preflight")
        if not isinstance(preflight, dict):
            raise ValueError(f"workflow '{workflow_id}' must define a preflight object")

        if not isinstance(preflight.get("required"), bool):
            raise ValueError(f"workflow '{workflow_id}' preflight.required must be boolean")

        for field in WORKFLOW_SECRET_FIELDS:
            secret_ids = preflight.get(field, [])
            if not isinstance(secret_ids, list):
                raise ValueError(f"workflow '{workflow_id}' field '{field}' must be a list")
            for secret_id in secret_ids:
                if secret_id not in secrets:
                    raise ValueError(f"workflow '{workflow_id}' references unknown secret '{secret_id}'")
        bootstrap_manifest_ids = preflight.get("bootstrap_manifest_ids", [])
        if not isinstance(bootstrap_manifest_ids, list):
            raise ValueError(f"workflow '{workflow_id}' field 'bootstrap_manifest_ids' must be a list")
        for index, manifest_id in enumerate(bootstrap_manifest_ids):
            if not isinstance(manifest_id, str) or not manifest_id.strip():
                raise ValueError(f"workflow '{workflow_id}' bootstrap_manifest_ids[{index}] must be a non-empty string")
        resolve_workflow_manifest_ids(bootstrap_catalog, workflow)
        validate_preflight_health_checks(preflight.get("health_checks", []), workflow_id)

        validation_targets = workflow.get("validation_targets")
        if not isinstance(validation_targets, list):
            raise ValueError(f"workflow '{workflow_id}' must define validation_targets as a list")
        for target in validation_targets:
            if target not in make_targets:
                raise ValueError(f"workflow '{workflow_id}' references unknown validation target '{target}'")

        live_impact = workflow.get("live_impact")
        if live_impact not in ALLOWED_LIVE_IMPACTS:
            raise ValueError(f"workflow '{workflow_id}' has invalid live_impact '{live_impact}'")

        owner_runbook = workflow.get("owner_runbook")
        if not isinstance(owner_runbook, str) or not owner_runbook:
            raise ValueError(f"workflow '{workflow_id}' must define owner_runbook")
        if not (REPO_ROOT / owner_runbook).is_file():
            raise ValueError(f"workflow '{workflow_id}' references missing owner_runbook '{owner_runbook}'")

        implementation_refs = workflow.get("implementation_refs")
        if not isinstance(implementation_refs, list) or not implementation_refs:
            raise ValueError(f"workflow '{workflow_id}' must define a non-empty implementation_refs list")
        for path_str in implementation_refs:
            if not (REPO_ROOT / path_str).exists():
                raise ValueError(f"workflow '{workflow_id}' references missing implementation path '{path_str}'")

        outputs = workflow.get("outputs")
        if not isinstance(outputs, list) or not outputs:
            raise ValueError(f"workflow '{workflow_id}' must define a non-empty outputs list")

        verification_commands = workflow.get("verification_commands")
        if not isinstance(verification_commands, list) or not verification_commands:
            raise ValueError(f"workflow '{workflow_id}' must define a non-empty verification_commands list")

        speculative = workflow.get("speculative")
        if speculative is not None:
            if not isinstance(speculative, dict):
                raise ValueError(f"workflow '{workflow_id}' speculative config must be a mapping")
            eligible = speculative.get("eligible", False)
            if not isinstance(eligible, bool):
                raise ValueError(f"workflow '{workflow_id}' speculative.eligible must be boolean")
            if eligible:
                compensating_workflow_id = speculative.get("compensating_workflow_id")
                if not isinstance(compensating_workflow_id, str) or not compensating_workflow_id.strip():
                    raise ValueError(
                        f"workflow '{workflow_id}' speculative.compensating_workflow_id must be a non-empty string"
                    )
                if compensating_workflow_id not in workflows:
                    raise ValueError(
                        f"workflow '{workflow_id}' speculative.compensating_workflow_id references "
                        f"unknown workflow '{compensating_workflow_id}'"
                    )
                conflict_probe = speculative.get("conflict_probe")
                if not isinstance(conflict_probe, dict):
                    raise ValueError(f"workflow '{workflow_id}' speculative.conflict_probe must be a mapping")
                callable_name = conflict_probe.get("callable")
                if not isinstance(callable_name, str) or not callable_name.strip():
                    raise ValueError(
                        f"workflow '{workflow_id}' speculative.conflict_probe.callable must be a non-empty string"
                    )
                path_value = conflict_probe.get("path")
                module_value = conflict_probe.get("module")
                if path_value is None and module_value is None:
                    raise ValueError(
                        f"workflow '{workflow_id}' speculative.conflict_probe must define either path or module"
                    )
                if path_value is not None and (not isinstance(path_value, str) or not path_value.strip()):
                    raise ValueError(
                        f"workflow '{workflow_id}' speculative.conflict_probe.path must be a non-empty string"
                    )
                if module_value is not None and (not isinstance(module_value, str) or not module_value.strip()):
                    raise ValueError(
                        f"workflow '{workflow_id}' speculative.conflict_probe.module must be a non-empty string"
                    )
                probe_delay_seconds = speculative.get("probe_delay_seconds", 30)
                if isinstance(probe_delay_seconds, bool) or not isinstance(probe_delay_seconds, int):
                    raise ValueError(f"workflow '{workflow_id}' speculative.probe_delay_seconds must be an integer")
                if probe_delay_seconds < 0:
                    raise ValueError(f"workflow '{workflow_id}' speculative.probe_delay_seconds must be >= 0")
                rollback_window_seconds = speculative.get("rollback_window_seconds", 300)
                if isinstance(rollback_window_seconds, bool) or not isinstance(rollback_window_seconds, int):
                    raise ValueError(f"workflow '{workflow_id}' speculative.rollback_window_seconds must be an integer")
                if rollback_window_seconds < 1:
                    raise ValueError(f"workflow '{workflow_id}' speculative.rollback_window_seconds must be >= 1")


def list_workflows(catalog: dict) -> int:
    print(f"Workflow catalog: {WORKFLOW_CATALOG_PATH}")
    print("Available workflows:")
    for workflow_id, workflow in sorted(catalog["workflows"].items()):
        command = workflow["preferred_entrypoint"]["command"]
        impact = workflow["live_impact"]
        status = workflow["lifecycle_status"]
        execution_class = workflow.get("execution_class", "mutation")
        print(f"  - {workflow_id} [{status}, {impact}, {execution_class}]: {command}")
    return 0


def show_workflow(catalog: dict, workflow_id: str) -> int:
    workflow = catalog["workflows"].get(workflow_id)
    if workflow is None:
        print(f"Unknown workflow: {workflow_id}", file=sys.stderr)
        return 2

    print(f"Workflow: {workflow_id}")
    print(f"Description: {workflow['description']}")
    print(f"Lifecycle: {workflow['lifecycle_status']}")
    print(f"Live impact: {workflow['live_impact']}")
    print(f"Execution class: {workflow.get('execution_class', 'mutation')}")
    print(f"Dedup window: {workflow.get('dedup_window_seconds', 'default')}")
    print(f"Entrypoint: {workflow['preferred_entrypoint']['command']}")
    print(f"Runbook: {workflow['owner_runbook']}")
    if workflow.get("target_lane"):
        print(f"Target lane: {workflow['target_lane']}")
    print("Budget:")
    defaults = load_workflow_defaults().get("default_budget", {})
    budget = dict(defaults if isinstance(defaults, dict) else {})
    workflow_budget = workflow.get("budget", {})
    if isinstance(workflow_budget, dict):
        budget.update(workflow_budget)
    for key, value in budget.items():
        print(f"  - {key}: {value}")
    if workflow.get("execution_class", "mutation") == "mutation":
        print("Resource reservation:")
        reservation = dict(load_workflow_defaults().get("default_resource_reservation", {}))
        workflow_reservation = workflow.get("resource_reservation", {})
        if isinstance(workflow_reservation, dict):
            reservation.update(workflow_reservation)
        for key, value in reservation.items():
            print(f"  - {key}: {value}")
    print("Validation targets:")
    for target in workflow["validation_targets"]:
        print(f"  - make {target}")

    claims = workflow.get("resource_claims", [])
    if claims:
        print("Resource claims:")
        for claim in claims:
            print(f"  - {claim['resource']} ({claim['access']})")

    preflight = workflow["preflight"]
    if preflight["required"]:
        print("Preflight secrets:")
        for field in WORKFLOW_SECRET_FIELDS:
            for secret_id in preflight.get(field, []):
                print(f"  - {field}: {secret_id}")
    else:
        print("Preflight secrets: none")
    bootstrap_catalog = load_bootstrap_catalog()
    validate_bootstrap_catalog(bootstrap_catalog)
    manifest_ids = resolve_workflow_manifest_ids(bootstrap_catalog, workflow)
    if manifest_ids:
        print("Bootstrap manifests:")
        for manifest_id in manifest_ids:
            manifest = bootstrap_catalog["manifests"][manifest_id]
            print(f"  - {manifest_id}: {manifest['description']}")
    else:
        print("Bootstrap manifests: none")
    health_checks = preflight.get("health_checks", [])
    if health_checks:
        print("Preflight health checks:")
        for check in health_checks:
            timeout_seconds = check.get("timeout_seconds", DEFAULT_PREFLIGHT_HEALTH_CHECK_TIMEOUT_SECONDS)
            print(f"  - {check['id']} ({timeout_seconds}s): {check['description']}")
    else:
        print("Preflight health checks: none")

    print("Implementation refs:")
    for path_str in workflow["implementation_refs"]:
        print(f"  - {path_str}")

    print("Outputs:")
    for output in workflow["outputs"]:
        print(f"  - {output}")

    print("Verification commands:")
    for command in workflow["verification_commands"]:
        print(f"  - {command}")

    if CORRECTION_LOOP_CATALOG_PATH.exists():
        correction_catalog = load_correction_loop_catalog()
        correction_loop = resolve_workflow_correction_loop(correction_catalog, workflow_id)
        if correction_loop is not None:
            print("Correction loop:")
            print(f"  - id: {correction_loop['id']}")
            print(f"  - invariant: {correction_loop['invariant']}")
            print(f"  - verification: {correction_loop['verification']['source']}")
            print(f"  - escalation: {correction_loop['escalation']['target']}")
            if correction_loop.get("retry_budget_cycles") is not None:
                print(f"  - retry_budget_cycles: {correction_loop['retry_budget_cycles']}")
            print("  - repair actions:")
            for action in correction_loop["repair_actions"]:
                approval = "approval" if action["requires_approval"] else "auto"
                print(f"    {action['kind']} [{approval}]: {action['summary']}")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect or validate the repository workflow execution catalog.")
    parser.add_argument("--list", action="store_true", help="List available workflows.")
    parser.add_argument("--workflow", help="Show one workflow from the catalog.")
    parser.add_argument("--validate", action="store_true", help="Validate the workflow catalog.")
    args = parser.parse_args()

    try:
        secret_manifest = load_secret_manifest()
        validate_secret_manifest(secret_manifest)
        catalog = load_workflow_catalog()
        bootstrap_catalog = load_bootstrap_catalog()
        validate_bootstrap_catalog(bootstrap_catalog)
        validate_workflow_catalog(catalog, secret_manifest, bootstrap_catalog)
        if CORRECTION_LOOP_CATALOG_PATH.exists():
            correction_catalog = load_correction_loop_catalog()
            validate_correction_loop_catalog(correction_catalog, catalog)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return emit_cli_error("Workflow catalog", exc)

    if args.validate:
        print(f"Workflow catalog OK: {WORKFLOW_CATALOG_PATH}")
        return 0

    if args.workflow:
        return show_workflow(catalog, args.workflow)

    return list_workflows(catalog)


if __name__ == "__main__":
    sys.exit(main())
