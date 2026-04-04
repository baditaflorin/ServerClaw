#!/usr/bin/env python3
"""Load, validate, attest, and evaluate ADR 0266 validation runner contracts."""

from __future__ import annotations

import argparse
import json
import platform as pyplatform
import shutil
import socket
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_CATALOG_PATH = REPO_ROOT / "config" / "validation-runner-contracts.json"
CONTRACT_SCHEMA_PATH = REPO_ROOT / "docs" / "schema" / "validation-runner-contracts.schema.json"
VALIDATION_GATE_PATH = REPO_ROOT / "config" / "validation-gate.json"
BUILD_SERVER_CONFIG_PATH = REPO_ROOT / "config" / "build-server.json"


@dataclass(frozen=True)
class LaneEligibility:
    lane_id: str
    eligible: bool
    reasons: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "eligible": self.eligible,
            "reasons": list(self.reasons),
        }


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def require_mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object")
    return value


def require_list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{path} must be a list")
    return value


def require_str(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path} must be a non-empty string")
    return value


def require_bool(value: Any, path: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{path} must be a boolean")
    return value


def require_string_list(value: Any, path: str) -> list[str]:
    values = [require_str(item, f"{path}[{index}]") for index, item in enumerate(require_list(value, path))]
    if len(values) != len(set(values)):
        raise ValueError(f"{path} must not contain duplicates")
    return values


def load_contract_catalog(path: Path = CONTRACT_CATALOG_PATH) -> dict[str, Any]:
    return require_mapping(load_json(path), str(path))


def _validate_schema(catalog: dict[str, Any]) -> None:
    try:
        import jsonschema  # type: ignore[import-untyped]
    except ModuleNotFoundError as exc:  # pragma: no cover - runtime guard
        raise RuntimeError(
            "Missing dependency: jsonschema. Run via 'uv run --with pyyaml --with jsonschema python ...'."
        ) from exc

    jsonschema.validate(instance=catalog, schema=load_json(CONTRACT_SCHEMA_PATH))


def _load_validation_gate(path: Path = VALIDATION_GATE_PATH) -> dict[str, Any]:
    return require_mapping(load_json(path), str(path))


def _load_build_server_config(path: Path = BUILD_SERVER_CONFIG_PATH) -> dict[str, Any]:
    return require_mapping(load_json(path), str(path))


def _validate_build_server_private_overlay_contract(build_server: dict[str, Any]) -> None:
    ssh_key = require_str(build_server.get("ssh_key"), "config/build-server.json.ssh_key")
    if "/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local" in ssh_key:
        raise ValueError(
            "config/build-server.json.ssh_key must not embed an operator workstation path; use a repo-relative .local alias"
        )
    if "hetzner_llm_agents_ed25519" in ssh_key:
        raise ValueError(
            "config/build-server.json.ssh_key must use the generic bootstrap alias, not the legacy deployment-specific key name"
        )

    ssh_options = [
        require_str(option, f"config/build-server.json.ssh_options[{index}]")
        for index, option in enumerate(require_list(build_server.get("ssh_options", []), "config/build-server.json.ssh_options"))
    ]
    for index, option in enumerate(ssh_options):
        if "/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local" in option:
            raise ValueError(
                "config/build-server.json.ssh_options "
                f"[{index}] must not embed an operator workstation path"
            )
        if "hetzner_llm_agents_ed25519" in option:
            raise ValueError(
                "config/build-server.json.ssh_options "
                f"[{index}] must not reference the legacy deployment-specific bootstrap key name"
            )


def validate_contract_catalog(
    catalog: dict[str, Any],
    *,
    validation_gate: dict[str, Any] | None = None,
    build_server_config: dict[str, Any] | None = None,
    catalog_path: Path = CONTRACT_CATALOG_PATH,
) -> None:
    _validate_schema(catalog)

    lane_catalog = require_mapping(catalog.get("lanes"), f"{catalog_path}.lanes")
    runner_catalog = require_mapping(catalog.get("runners"), f"{catalog_path}.runners")
    lane_ids = set(lane_catalog)
    runner_ids = set(runner_catalog)

    gate_manifest = validation_gate if validation_gate is not None else _load_validation_gate()
    gate_checks = set(require_mapping(gate_manifest, str(VALIDATION_GATE_PATH)))
    missing_gate_lanes = sorted(gate_checks - lane_ids)
    if missing_gate_lanes:
        raise ValueError(
            "config/validation-runner-contracts.json is missing gate lanes for: "
            + ", ".join(missing_gate_lanes)
        )

    build_server = build_server_config if build_server_config is not None else _load_build_server_config()
    _validate_build_server_private_overlay_contract(build_server)
    commands = require_mapping(build_server.get("commands"), "config/build-server.json.commands")
    for command_label, raw_command in commands.items():
        command = require_mapping(raw_command, f"config/build-server.json.commands.{command_label}")
        runner_id = command.get("runner_id")
        if runner_id is not None:
            runner_id = require_str(runner_id, f"config/build-server.json.commands.{command_label}.runner_id")
            if runner_id not in runner_ids:
                raise ValueError(
                    f"config/build-server.json.commands.{command_label}.runner_id references unknown runner '{runner_id}'"
                )
        fallback_runner_id = command.get("local_fallback_runner_id")
        if fallback_runner_id is not None:
            fallback_runner_id = require_str(
                fallback_runner_id,
                f"config/build-server.json.commands.{command_label}.local_fallback_runner_id",
            )
            if fallback_runner_id not in runner_ids:
                raise ValueError(
                    "config/build-server.json.commands."
                    f"{command_label}.local_fallback_runner_id references unknown runner '{fallback_runner_id}'"
                )

        validation_lanes = command.get("validation_lanes", [])
        if validation_lanes == "all-validation-gate-checks":
            validation_lane_ids = sorted(gate_checks)
        elif validation_lanes:
            validation_lane_ids = require_string_list(
                validation_lanes,
                f"config/build-server.json.commands.{command_label}.validation_lanes",
            )
        else:
            validation_lane_ids = []

        unknown_lanes = sorted(set(validation_lane_ids) - lane_ids)
        if unknown_lanes:
            raise ValueError(
                f"config/build-server.json.commands.{command_label}.validation_lanes includes unknown lanes: "
                + ", ".join(unknown_lanes)
            )

        for lane_id in validation_lane_ids:
            if runner_id is not None and lane_id not in runner_catalog[runner_id]["supported_validation_lanes"]:
                raise ValueError(
                    f"runner '{runner_id}' does not support validation lane '{lane_id}' declared by command '{command_label}'"
                )
            if fallback_runner_id is not None and lane_id not in runner_catalog[fallback_runner_id]["supported_validation_lanes"]:
                raise ValueError(
                    "local fallback runner "
                    f"'{fallback_runner_id}' does not support validation lane '{lane_id}' declared by command '{command_label}'"
                )


def normalize_cpu_architecture(raw_architecture: str) -> str:
    lowered = raw_architecture.strip().lower()
    aliases = {
        "amd64": "x86_64",
        "arm64": "arm64",
        "aarch64": "arm64",
        "x64": "x86_64",
        "x86_64": "x86_64",
    }
    return aliases.get(lowered, lowered or "unknown")


def resolve_binary(binary: str) -> str | None:
    candidate = Path(binary).expanduser()
    if candidate.is_absolute() or "/" in binary:
        return str(candidate.resolve()) if candidate.exists() else None
    return shutil.which(binary)


def detect_tool(binary: str, *, binary_override: str | None = None) -> dict[str, Any]:
    resolved = resolve_binary(binary_override or binary)
    payload: dict[str, Any] = {
        "available": bool(resolved),
        "path": resolved,
    }
    if not resolved:
        return payload

    try:
        completed = subprocess.run(
            [resolved, "--version"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return payload

    first_line = next(
        (line.strip() for line in f"{completed.stdout}\n{completed.stderr}".splitlines() if line.strip()),
        "",
    )
    if first_line:
        payload["version"] = first_line
    return payload


def detect_container_runtime(engine: str, *, binary_override: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "engine": engine,
        "supported": True,
        "available": False,
        "path": None,
        "server_reachable": False,
    }
    resolved = resolve_binary(binary_override or engine)
    payload["path"] = resolved
    if not resolved:
        payload["supported"] = False
        requested = binary_override or engine
        payload["error"] = f"{requested} binary is not available"
        return payload

    payload["available"] = True
    try:
        completed = subprocess.run(
            [resolved, "info", "--format", "{{.ServerVersion}}"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        payload["error"] = str(exc)
        return payload

    if completed.returncode == 0:
        payload["server_reachable"] = True
        payload["server_version"] = completed.stdout.strip()
        return payload

    error_text = "\n".join(part for part in [completed.stdout.strip(), completed.stderr.strip()] if part).strip()
    payload["error"] = error_text or f"{engine} info returned {completed.returncode}"
    return payload


def attest_runner(
    catalog: dict[str, Any],
    *,
    runner_id: str,
    workspace: Path,
    container_runtime_binary: str | None = None,
) -> dict[str, Any]:
    runners = require_mapping(catalog.get("runners"), "config/validation-runner-contracts.json.runners")
    if runner_id not in runners:
        raise ValueError(f"unknown validation runner contract: {runner_id}")
    runner = require_mapping(runners[runner_id], f"config/validation-runner-contracts.json.runners.{runner_id}")
    tool_names = sorted(set(require_string_list(runner.get("required_tools"), f"runner {runner_id} required_tools")))
    runtime_engine = require_mapping(
        runner.get("container_runtime"),
        f"runner {runner_id} container_runtime",
    )["engine"]
    tooling = {
        tool_name: detect_tool(
            tool_name,
            binary_override=container_runtime_binary if tool_name == runtime_engine else None,
        )
        for tool_name in tool_names
    }
    runtime = detect_container_runtime(
        runtime_engine,
        binary_override=container_runtime_binary,
    )
    workspace_path = workspace.resolve()
    usage = shutil.disk_usage(workspace_path)

    return {
        "attested_at": datetime.now(timezone.utc).isoformat(),
        "hostname": socket.gethostname(),
        "platform": sys.platform,
        "cpu_architecture": normalize_cpu_architecture(pyplatform.machine()),
        "emulation_support": require_string_list(
            runner.get("emulation_support"),
            f"config/validation-runner-contracts.json.runners.{runner_id}.emulation_support",
        ),
        "container_runtime": runtime,
        "tooling": tooling,
        "network_reachability_class": require_str(
            runner.get("network_reachability_class"),
            f"config/validation-runner-contracts.json.runners.{runner_id}.network_reachability_class",
        ),
        "scratch_space": {
            "workspace": str(workspace_path),
            "exists": workspace_path.exists(),
            "cleanup_guarantee": require_str(
                runner.get("scratch_cleanup_guarantee"),
                f"config/validation-runner-contracts.json.runners.{runner_id}.scratch_cleanup_guarantee",
            ),
            "free_bytes": usage.free,
        },
    }


def evaluate_lane_eligibility(
    catalog: dict[str, Any],
    *,
    runner_id: str,
    lane_id: str,
    attestation: dict[str, Any],
) -> LaneEligibility:
    lanes = require_mapping(catalog.get("lanes"), "config/validation-runner-contracts.json.lanes")
    runners = require_mapping(catalog.get("runners"), "config/validation-runner-contracts.json.runners")
    if runner_id not in runners:
        raise ValueError(f"unknown validation runner contract: {runner_id}")
    if lane_id not in lanes:
        raise ValueError(f"unknown validation lane: {lane_id}")

    lane = require_mapping(lanes[lane_id], f"config/validation-runner-contracts.json.lanes.{lane_id}")
    runner = require_mapping(runners[runner_id], f"config/validation-runner-contracts.json.runners.{runner_id}")
    reasons: list[str] = []

    supported_lanes = set(
        require_string_list(
            runner.get("supported_validation_lanes"),
            f"config/validation-runner-contracts.json.runners.{runner_id}.supported_validation_lanes",
        )
    )
    if lane_id not in supported_lanes:
        reasons.append(f"runner contract '{runner_id}' does not declare support for lane '{lane_id}'")

    allowed_architectures = set(
        require_string_list(
            lane.get("allowed_cpu_architectures"),
            f"config/validation-runner-contracts.json.lanes.{lane_id}.allowed_cpu_architectures",
        )
    )
    attested_architecture = require_str(attestation.get("cpu_architecture"), f"{runner_id} attestation cpu_architecture")
    if attested_architecture not in allowed_architectures:
        reasons.append(
            f"lane '{lane_id}' requires CPU architecture in {sorted(allowed_architectures)}, not '{attested_architecture}'"
        )
    declared_architectures = set(
        require_string_list(
            runner.get("cpu_architectures"),
            f"config/validation-runner-contracts.json.runners.{runner_id}.cpu_architectures",
        )
    )
    if attested_architecture not in declared_architectures:
        reasons.append(
            f"runner contract '{runner_id}' allows CPU architectures {sorted(declared_architectures)}, not '{attested_architecture}'"
        )

    if require_bool(lane.get("requires_container_runtime"), f"config/validation-runner-contracts.json.lanes.{lane_id}.requires_container_runtime"):
        runtime = require_mapping(attestation.get("container_runtime"), f"{runner_id} attestation container_runtime")
        if not require_bool(runtime.get("available"), f"{runner_id} attestation container_runtime.available"):
            reasons.append(
                runtime.get("error", "container runtime binary is unavailable")
                if isinstance(runtime.get("error"), str)
                else "container runtime binary is unavailable"
            )
        elif not require_bool(runtime.get("server_reachable"), f"{runner_id} attestation container_runtime.server_reachable"):
            reasons.append(
                runtime.get("error", "container runtime daemon is unreachable")
                if isinstance(runtime.get("error"), str)
                else "container runtime daemon is unreachable"
            )

    tooling = require_mapping(attestation.get("tooling"), f"{runner_id} attestation tooling")
    required_tools = require_string_list(lane.get("required_tools"), f"config/validation-runner-contracts.json.lanes.{lane_id}.required_tools")
    missing_tools = [
        tool_name
        for tool_name in required_tools
        if not require_bool(
            require_mapping(tooling.get(tool_name, {}), f"{runner_id} attestation tooling.{tool_name}").get("available", False),
            f"{runner_id} attestation tooling.{tool_name}.available",
        )
    ]
    if missing_tools:
        reasons.append(f"required tooling missing for lane '{lane_id}': {', '.join(sorted(missing_tools))}")

    allowed_reachability = set(
        require_string_list(
            lane.get("allowed_network_reachability_classes"),
            f"config/validation-runner-contracts.json.lanes.{lane_id}.allowed_network_reachability_classes",
        )
    )
    runner_reachability = require_str(
        attestation.get("network_reachability_class"),
        f"{runner_id} attestation network_reachability_class",
    )
    if runner_reachability not in allowed_reachability:
        reasons.append(
            f"lane '{lane_id}' requires network reachability class in {sorted(allowed_reachability)}, not '{runner_reachability}'"
        )

    if require_bool(
        lane.get("require_scratch_cleanup_guarantee"),
        f"config/validation-runner-contracts.json.lanes.{lane_id}.require_scratch_cleanup_guarantee",
    ):
        scratch = require_mapping(attestation.get("scratch_space"), f"{runner_id} attestation scratch_space")
        if not require_bool(scratch.get("exists"), f"{runner_id} attestation scratch_space.exists"):
            reasons.append("workspace scratch path does not exist")
        cleanup = require_str(scratch.get("cleanup_guarantee"), f"{runner_id} attestation scratch_space.cleanup_guarantee")
        if not cleanup:
            reasons.append("runner did not attest a scratch-space cleanup guarantee")

    return LaneEligibility(lane_id=lane_id, eligible=not reasons, reasons=tuple(reasons))


def build_runner_context(
    catalog: dict[str, Any],
    *,
    runner_id: str,
    workspace: Path,
    lanes: list[str] | None = None,
    container_runtime_binary: str | None = None,
) -> dict[str, Any]:
    runners = require_mapping(catalog.get("runners"), "config/validation-runner-contracts.json.runners")
    if runner_id not in runners:
        raise ValueError(f"unknown validation runner contract: {runner_id}")
    runner = require_mapping(runners[runner_id], f"config/validation-runner-contracts.json.runners.{runner_id}")
    attestation = attest_runner(
        catalog,
        runner_id=runner_id,
        workspace=workspace,
        container_runtime_binary=container_runtime_binary,
    )
    lane_ids = list(lanes or [])
    lane_evaluations = {
        lane_id: evaluate_lane_eligibility(catalog, runner_id=runner_id, lane_id=lane_id, attestation=attestation).as_dict()
        for lane_id in lane_ids
    }
    return {
        "id": runner_id,
        "execution_surface": runner["execution_surface"],
        "capability_contract": runner,
        "environment_attestation": attestation,
        "lane_evaluations": lane_evaluations,
    }


def _print_context_text(payload: dict[str, Any]) -> None:
    print(f"Runner: {payload['id']}")
    print(f"Execution surface: {payload['execution_surface']}")
    attestation = payload["environment_attestation"]
    print(f"Host: {attestation['hostname']} [{attestation['cpu_architecture']}]")
    runtime = attestation["container_runtime"]
    print(
        "Container runtime: "
        f"{runtime['engine']} available={runtime['available']} server_reachable={runtime['server_reachable']}"
    )
    for lane_id, evaluation in sorted(payload.get("lane_evaluations", {}).items()):
        print(f"Lane {lane_id}: {'eligible' if evaluation['eligible'] else 'runner_unavailable'}")
        for reason in evaluation["reasons"]:
            print(f"  - {reason}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect and validate ADR 0266 validation runner contracts.")
    parser.add_argument("--contracts", type=Path, default=CONTRACT_CATALOG_PATH, help="Validation runner contract catalog.")
    parser.add_argument("--validate", action="store_true", help="Validate the contract catalog against schema and call sites.")
    parser.add_argument("--runner", help="Runner id to attest.")
    parser.add_argument("--workspace", type=Path, default=REPO_ROOT, help="Workspace used for scratch-space attestation.")
    parser.add_argument("--lane", action="append", default=[], help="Lane id to evaluate against the selected runner.")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    catalog = load_contract_catalog(args.contracts)

    if args.validate:
        validate_contract_catalog(catalog)
        print(f"Validation runner contracts OK: {args.contracts}")
        return 0

    if not args.runner:
        parser.error("either pass --validate or select --runner")

    payload = build_runner_context(
        catalog,
        runner_id=args.runner,
        workspace=args.workspace.resolve(),
        lanes=list(args.lane),
    )
    if args.format == "json":
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        _print_context_text(payload)

    lane_evaluations = payload.get("lane_evaluations", {})
    return 0 if all(item.get("eligible", False) for item in lane_evaluations.values()) else 2


if __name__ == "__main__":
    raise SystemExit(main())
