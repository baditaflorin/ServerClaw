from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from platform.catalogs import load_command_catalog, load_workflow_catalog
from platform.repo import load_yaml, parse_make_targets, repo_path


CONTRACTS_DIR = repo_path("config", "contracts")
WORKSTREAMS_PATH = repo_path("workstreams.yaml")
SEMVER_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")
ALLOWED_COMPATIBILITY_POLICIES = {
    "backward_compatible_minor",
    "backward_compatible_patch",
    "versioned_breaking_change",
}
ALLOWED_WORKSTREAM_STATUSES = {
    "blocked",
    "implemented",
    "in_progress",
    "live_applied",
    "merged",
    "planned",
    "ready",
    "ready_for_merge",
}


def _require_mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be a mapping")
    return value


def _require_list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{path} must be a list")
    return value


def _require_non_empty_string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path} must be a non-empty string")
    return value.strip()


def _require_bool(value: Any, path: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{path} must be a boolean")
    return value


def _require_string_list(value: Any, path: str) -> list[str]:
    items = _require_list(value, path)
    result: list[str] = []
    for index, item in enumerate(items):
        result.append(_require_non_empty_string(item, f"{path}[{index}]"))
    if not result:
        raise ValueError(f"{path} must not be empty")
    return result


def _require_string_list_allow_empty(value: Any, path: str) -> list[str]:
    items = _require_list(value, path)
    result: list[str] = []
    for index, item in enumerate(items):
        result.append(_require_non_empty_string(item, f"{path}[{index}]"))
    return result


def _require_semver(value: Any, path: str) -> str:
    value = _require_non_empty_string(value, path)
    if not SEMVER_PATTERN.fullmatch(value):
        raise ValueError(f"{path} must use semantic version format")
    return value


def _resolve_repo_path(path: str) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return repo_path(path)

def _is_playbook_reference(path: str) -> bool:
    candidate = Path(path)
    if candidate.suffix.lower() not in {".yml", ".yaml"}:
        return False
    return "playbooks" in candidate.parts


def _is_playbook_ref(path: str) -> bool:
    """Backward-compatible alias kept for existing tests/importers."""
    return _is_playbook_reference(path)


def _workflow_playbook_candidates(workflow_id: str) -> list[Path]:
    if not workflow_id.startswith("converge-"):
        return []
    slug = workflow_id.removeprefix("converge-")
    return [
        repo_path("playbooks", f"{slug}.yml"),
        repo_path("playbooks", "services", f"{slug}.yml"),
        repo_path("collections", "ansible_collections", "lv3", "platform", "playbooks", f"{slug}.yml"),
        repo_path("collections", "ansible_collections", "lv3", "platform", "playbooks", "services", f"{slug}.yml"),
    ]
def _validate_declared_paths(paths: list[str], *, field: str, contract_id: str) -> None:
    for index, raw_path in enumerate(paths):
        resolved = _resolve_repo_path(raw_path)
        if not resolved.exists():
            raise ValueError(f"{contract_id}.{field}[{index}] references missing path '{raw_path}'")


def _validate_schema_block(value: Any, path: str) -> dict[str, Any]:
    schema = _require_mapping(value, path)
    _require_non_empty_string(schema.get("type"), f"{path}.type")
    _require_string_list(schema.get("required_fields"), f"{path}.required_fields")
    return schema


def load_contracts() -> list[dict[str, Any]]:
    if not CONTRACTS_DIR.exists():
        raise ValueError(f"missing contract directory: {CONTRACTS_DIR}")
    contracts: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for path in sorted(CONTRACTS_DIR.glob("*.yaml")):
        contract = _require_mapping(load_yaml(path), str(path))
        contract["__path__"] = path
        contract_id = _require_non_empty_string(contract.get("contract_id"), f"{path}.contract_id")
        if contract_id in seen_ids:
            raise ValueError(f"duplicate contract_id '{contract_id}'")
        seen_ids.add(contract_id)
        contracts.append(contract)
    if not contracts:
        raise ValueError(f"no contract definitions found in {CONTRACTS_DIR}")
    return contracts


def validate_contract_metadata(contract: dict[str, Any]) -> dict[str, Any]:
    path = Path(contract["__path__"])
    base = str(path)
    schema_version = _require_non_empty_string(contract.get("schema_version"), f"{base}.schema_version")
    if schema_version != "1.0.0":
        raise ValueError(f"{base}.schema_version must be 1.0.0")
    contract_id = _require_non_empty_string(contract.get("contract_id"), f"{base}.contract_id")
    _require_non_empty_string(contract.get("owner"), f"{base}.owner")
    _require_semver(contract.get("version"), f"{base}.version")
    compatibility = _require_non_empty_string(contract.get("compatibility"), f"{base}.compatibility")
    if compatibility not in ALLOWED_COMPATIBILITY_POLICIES:
        raise ValueError(
            f"{base}.compatibility must be one of {sorted(ALLOWED_COMPATIBILITY_POLICIES)}"
        )
    producer_paths = _require_string_list(contract.get("producer_paths"), f"{base}.producer_paths")
    consumer_paths = _require_string_list(contract.get("consumer_paths"), f"{base}.consumer_paths")
    _validate_declared_paths(producer_paths, field="producer_paths", contract_id=contract_id)
    _validate_declared_paths(consumer_paths, field="consumer_paths", contract_id=contract_id)
    _validate_schema_block(contract.get("input_schema"), f"{base}.input_schema")
    _validate_schema_block(contract.get("output_schema"), f"{base}.output_schema")
    validator = _require_non_empty_string(contract.get("validator"), f"{base}.validator")
    _require_string_list(contract.get("fixtures"), f"{base}.fixtures")
    metadata = contract.get("metadata")
    if metadata is not None:
        _require_mapping(metadata, f"{base}.metadata")
    contract["validator"] = validator
    contract["producer_paths"] = producer_paths
    contract["consumer_paths"] = consumer_paths
    return contract


def validate_workstream_registry_contract(contract: dict[str, Any]) -> None:
    registry = _require_mapping(load_yaml(WORKSTREAMS_PATH), str(WORKSTREAMS_PATH))
    delivery_model = _require_mapping(registry.get("delivery_model"), "workstreams.yaml.delivery_model")
    branch_prefix = _require_non_empty_string(delivery_model.get("branch_prefix"), "workstreams.yaml.delivery_model.branch_prefix")
    doc_root = Path(
        _require_non_empty_string(delivery_model.get("workstream_doc_root"), "workstreams.yaml.delivery_model.workstream_doc_root")
    )
    workstreams = _require_list(registry.get("workstreams"), "workstreams.yaml.workstreams")
    required_fields = contract["output_schema"]["required_fields"]

    seen_ids: set[str] = set()
    for index, item in enumerate(workstreams):
        workstream = _require_mapping(item, f"workstreams.yaml.workstreams[{index}]")
        for field in required_fields:
            if field not in workstream:
                raise ValueError(f"workstreams.yaml.workstreams[{index}] missing required field '{field}'")
        workstream_id = _require_non_empty_string(workstream.get("id"), f"workstreams.yaml.workstreams[{index}].id")
        if workstream_id in seen_ids:
            raise ValueError(f"duplicate workstream id '{workstream_id}' in workstreams.yaml")
        seen_ids.add(workstream_id)
        _require_non_empty_string(workstream.get("adr"), f"workstreams.yaml.workstreams[{index}].adr")
        _require_non_empty_string(workstream.get("title"), f"workstreams.yaml.workstreams[{index}].title")
        status = _require_non_empty_string(workstream.get("status"), f"workstreams.yaml.workstreams[{index}].status")
        if status not in ALLOWED_WORKSTREAM_STATUSES:
            raise ValueError(
                f"workstreams.yaml.workstreams[{index}].status must be one of {sorted(ALLOWED_WORKSTREAM_STATUSES)}"
            )
        _require_non_empty_string(workstream.get("owner"), f"workstreams.yaml.workstreams[{index}].owner")
        branch = _require_non_empty_string(workstream.get("branch"), f"workstreams.yaml.workstreams[{index}].branch")
        extra_prefixes = delivery_model.get("allowed_extra_prefixes") or []
        allowed_prefixes = [branch_prefix] + list(extra_prefixes)
        if branch != "main" and not any(branch.startswith(p) for p in allowed_prefixes):
            raise ValueError(
                f"workstreams.yaml.workstreams[{index}].branch must be 'main' or start with '{branch_prefix}'"
            )
        _require_non_empty_string(
            workstream.get("worktree_path"),
            f"workstreams.yaml.workstreams[{index}].worktree_path",
        )
        doc_path = Path(
            _require_non_empty_string(workstream.get("doc"), f"workstreams.yaml.workstreams[{index}].doc")
        )
        current_doc_path = repo_path("docs", "workstreams", doc_path.name)
        if not doc_path.exists() and not current_doc_path.exists():
            raise ValueError(f"workstreams.yaml.workstreams[{index}].doc points to missing file '{doc_path}'")
        if doc_root not in doc_path.parents and current_doc_path.parent != repo_path("docs", "workstreams"):
            raise ValueError(
                f"workstreams.yaml.workstreams[{index}].doc must live under '{doc_root}'"
            )
        _require_string_list_allow_empty(
            workstream.get("depends_on"),
            f"workstreams.yaml.workstreams[{index}].depends_on",
        )
        conflicts_with = workstream.get("conflicts_with")
        if conflicts_with is None:
            raise ValueError(f"workstreams.yaml.workstreams[{index}].conflicts_with must be present")
        _require_list(conflicts_with, f"workstreams.yaml.workstreams[{index}].conflicts_with")
        _require_string_list(workstream.get("shared_surfaces"), f"workstreams.yaml.workstreams[{index}].shared_surfaces")
        _require_bool(workstream.get("ready_to_merge"), f"workstreams.yaml.workstreams[{index}].ready_to_merge")
        _require_bool(workstream.get("live_applied"), f"workstreams.yaml.workstreams[{index}].live_applied")


def validate_converge_workflow_contract(contract: dict[str, Any]) -> None:
    workflow_catalog = load_workflow_catalog()
    command_catalog = load_command_catalog()
    workflows = _require_mapping(workflow_catalog.get("workflows"), "config/workflow-catalog.json.workflows")
    commands = _require_mapping(command_catalog.get("commands"), "config/command-catalog.json.commands")
    make_targets = parse_make_targets()

    metadata = _require_mapping(contract.get("metadata"), f"{contract['contract_id']}.metadata")
    workflow_prefix = _require_non_empty_string(metadata.get("workflow_prefix"), f"{contract['contract_id']}.metadata.workflow_prefix")
    required_validation_target = _require_non_empty_string(
        metadata.get("required_validation_target"),
        f"{contract['contract_id']}.metadata.required_validation_target",
    )
    receipt_required = _require_bool(
        metadata.get("receipt_required"),
        f"{contract['contract_id']}.metadata.receipt_required",
    )
    generic_targets = _require_string_list(
        metadata.get("generic_live_apply_targets"),
        f"{contract['contract_id']}.metadata.generic_live_apply_targets",
    )
    for target in generic_targets:
        if target not in make_targets:
            raise ValueError(f"{contract['contract_id']} requires missing Make target '{target}'")

    matching_workflows = [
        (workflow_id, _require_mapping(workflow, f"config/workflow-catalog.json.workflows.{workflow_id}"))
        for workflow_id, workflow in sorted(workflows.items())
        if workflow_id.startswith(workflow_prefix)
    ]
    if not matching_workflows:
        raise ValueError(f"{contract['contract_id']} did not match any workflows with prefix '{workflow_prefix}'")

    for workflow_id, workflow in matching_workflows:
        entrypoint = _require_mapping(
            workflow.get("preferred_entrypoint"),
            f"config/workflow-catalog.json.workflows.{workflow_id}.preferred_entrypoint",
        )
        kind = _require_non_empty_string(entrypoint.get("kind"), f"config/workflow-catalog.json.workflows.{workflow_id}.preferred_entrypoint.kind")
        if kind != "make_target":
            raise ValueError(f"workflow '{workflow_id}' must use a make_target preferred entrypoint")
        target = _require_non_empty_string(
            entrypoint.get("target"),
            f"config/workflow-catalog.json.workflows.{workflow_id}.preferred_entrypoint.target",
        )
        if target != workflow_id:
            raise ValueError(
                f"workflow '{workflow_id}' must use a same-name Make target; found '{target}'"
            )
        if target not in make_targets:
            raise ValueError(f"workflow '{workflow_id}' references missing Make target '{target}'")

        validation_targets = _require_string_list(
            workflow.get("validation_targets"),
            f"config/workflow-catalog.json.workflows.{workflow_id}.validation_targets",
        )
        if required_validation_target not in validation_targets:
            raise ValueError(
                f"workflow '{workflow_id}' must include validation target '{required_validation_target}'"
            )

        live_impact = _require_non_empty_string(
            workflow.get("live_impact"),
            f"config/workflow-catalog.json.workflows.{workflow_id}.live_impact",
        )
        if live_impact == "repo_only":
            raise ValueError(f"workflow '{workflow_id}' must not declare repo_only live impact")

        runbook_path = _resolve_repo_path(
            _require_non_empty_string(
                workflow.get("owner_runbook"),
                f"config/workflow-catalog.json.workflows.{workflow_id}.owner_runbook",
            )
        )
        if not runbook_path.exists():
            raise ValueError(f"workflow '{workflow_id}' references missing runbook '{runbook_path}'")

        implementation_refs = _require_string_list(
            workflow.get("implementation_refs"),
            f"config/workflow-catalog.json.workflows.{workflow_id}.implementation_refs",
        )
        referenced_playbooks = [
            _resolve_repo_path(path)
            for path in implementation_refs
            if _is_playbook_reference(path)
        ]
        referenced_playbooks.extend(_workflow_playbook_candidates(workflow_id))
        if not referenced_playbooks or not any(path.exists() for path in referenced_playbooks):
            raise ValueError(
                f"workflow '{workflow_id}' must reference at least one existing playbook in implementation_refs"
            )

        command = commands.get(workflow_id)
        if not isinstance(command, dict):
            raise ValueError(f"missing command contract for workflow '{workflow_id}'")
        command_workflow_id = _require_non_empty_string(
            command.get("workflow_id"),
            f"config/command-catalog.json.commands.{workflow_id}.workflow_id",
        )
        if command_workflow_id != workflow_id:
            raise ValueError(
                f"command '{workflow_id}' must reference workflow '{workflow_id}', found '{command_workflow_id}'"
            )
        evidence = _require_mapping(
            command.get("evidence"),
            f"config/command-catalog.json.commands.{workflow_id}.evidence",
        )
        if _require_bool(
            evidence.get("live_apply_receipt_required"),
            f"config/command-catalog.json.commands.{workflow_id}.evidence.live_apply_receipt_required",
        ) != receipt_required:
            raise ValueError(
                f"command '{workflow_id}' receipt requirement does not match contract '{contract['contract_id']}'"
            )


VALIDATORS = {
    "validate_workstream_registry_contract": validate_workstream_registry_contract,
    "validate_converge_workflow_contract": validate_converge_workflow_contract,
}


def validate_contracts() -> list[dict[str, Any]]:
    validated: list[dict[str, Any]] = []
    for contract in load_contracts():
        normalized = validate_contract_metadata(contract)
        validator = VALIDATORS.get(normalized["validator"])
        if validator is None:
            raise ValueError(f"unknown contract validator '{normalized['validator']}'")
        validator(normalized)
        validated.append(normalized)
    return validated


def find_contract(contract_id: str) -> dict[str, Any]:
    for contract in validate_contracts():
        if contract["contract_id"] == contract_id:
            return contract
    raise ValueError(f"unknown contract_id '{contract_id}'")


def check_live_apply_target(target_ref: str) -> dict[str, str]:
    validate_contracts()
    target_kind, separator, target_name = target_ref.partition(":")
    if not separator or not target_name:
        raise ValueError("live apply target must use '<service|group|site>:<name>'")

    if target_kind == "service":
        playbook = repo_path("playbooks", "services", f"{target_name}.yml")
    elif target_kind == "group":
        playbook = repo_path("playbooks", "groups", f"{target_name}.yml")
    elif target_kind == "site":
        if target_name != "site":
            raise ValueError("site live apply must use 'site:site'")
        playbook = repo_path("playbooks", "site.yml")
    else:
        raise ValueError("live apply target kind must be one of: service, group, site")

    if not playbook.exists():
        raise ValueError(f"live apply target '{target_ref}' references missing playbook '{playbook}'")

    return {"target": target_ref, "playbook": str(playbook)}
