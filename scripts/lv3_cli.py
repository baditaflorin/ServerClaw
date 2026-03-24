#!/usr/bin/env python3

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import shlex
import socket
import ssl
import subprocess
import sys
import textwrap
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterable

import yaml

from dependency_graph import dependency_summary, load_dependency_graph
from repo_package_loader import load_repo_package

try:
    from search_fabric import SearchClient
except ImportError:  # pragma: no cover - packaged entrypoint path
    from scripts.search_fabric import SearchClient

CODE_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = CODE_ROOT
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from platform.scheduler import build_scheduler
from scripts.risk_scorer import ExecutionIntent, assemble_context, compile_workflow_intent, score_intent
CLI_VERSION = "0.1.0"
DEFAULT_STATUS_TIMEOUT_SECONDS = 3.0
DEFAULT_LOG_LINES = 20
DEFAULT_LOG_SINCE = "1h"
ACTIVE_BINDING_STATES = {"active", "planned"}
COMPLETION_SENTINEL = "# >>> lv3 completion >>>"
NO_COLOR = bool(os.environ.get("NO_COLOR"))
SERVICE_ALIASES = {
    "ops": "ops_portal",
    "changelog": "changelog_portal",
    "proxmox": "proxmox_ui",
}

GOAL_COMPILER_MODULE = load_repo_package("lv3_goal_compiler", CODE_ROOT / "platform" / "goal_compiler")
LEDGER_MODULE = load_repo_package("lv3_platform_ledger", CODE_ROOT / "platform" / "ledger")
AGENT_MODULE = load_repo_package("lv3_platform_agent", CODE_ROOT / "platform" / "agent")
GoalCompilationError = GOAL_COMPILER_MODULE.GoalCompilationError
GoalCompiler = GOAL_COMPILER_MODULE.GoalCompiler
LedgerWriter = LEDGER_MODULE.LedgerWriter
AgentStateClient = AGENT_MODULE.AgentStateClient


@dataclass(frozen=True)
class CommandPlan:
    label: str
    route: str
    command: list[str]
    receipt_hint: str | None = None


@dataclass(frozen=True)
class ProbeResult:
    service_id: str
    url: str
    healthy: bool
    health_text: str
    latency_seconds: float | None


def repo_path(*parts: str) -> Path:
    return REPO_ROOT.joinpath(*parts)


def load_json(path: Path, *, default: Any | None = None) -> Any:
    if not path.exists():
        if default is not None:
            return default
        raise FileNotFoundError(path)
    return json.loads(path.read_text())


def emit_json(payload: Any) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def load_service_catalog() -> list[dict[str, Any]]:
    payload = load_json(repo_path("config", "service-capability-catalog.json"))
    services = payload.get("services")
    if not isinstance(services, list):
        raise ValueError("config/service-capability-catalog.json must define a services list")
    return services


def load_service_map() -> dict[str, dict[str, Any]]:
    return {service["id"]: service for service in load_service_catalog()}


def load_health_probe_catalog() -> dict[str, Any]:
    payload = load_json(repo_path("config", "health-probe-catalog.json"))
    services = payload.get("services")
    if not isinstance(services, dict):
        raise ValueError("config/health-probe-catalog.json must define a services object")
    return services


def load_workflow_catalog() -> dict[str, dict[str, Any]]:
    payload = load_json(repo_path("config", "workflow-catalog.json"))
    workflows = payload.get("workflows")
    if not isinstance(workflows, dict):
        raise ValueError("config/workflow-catalog.json must define a workflows object")
    return workflows


def load_secret_manifest() -> dict[str, Any]:
    payload = load_json(repo_path("config", "controller-local-secrets.json"))
    secrets = payload.get("secrets")
    if not isinstance(secrets, dict):
        raise ValueError("config/controller-local-secrets.json must define a secrets object")
    return secrets


def parse_make_targets() -> set[str]:
    makefile = repo_path("Makefile")
    targets: set[str] = set()
    for line in makefile.read_text().splitlines():
        if not line or line.startswith("\t"):
            continue
        if ":=" in line or "?=" in line:
            continue
        if ":" not in line:
            continue
        target = line.split(":", 1)[0].strip()
        if target and target != ".PHONY" and " " not in target and "=" not in target:
            targets.add(target)
    return targets


def primary_service_url(service: dict[str, Any], environment: str = "production") -> str | None:
    environments = service.get("environments", {})
    if isinstance(environments, dict):
        binding = environments.get(environment)
        if isinstance(binding, dict) and binding.get("status") in ACTIVE_BINDING_STATES:
            url = binding.get("url")
            if isinstance(url, str) and url.strip():
                return url
    for field in ("public_url", "internal_url"):
        value = service.get(field)
        if isinstance(value, str) and value.strip():
            return value
    return None


def service_identifier_candidates(service: dict[str, Any]) -> list[str]:
    candidates = [service["id"], service.get("name", ""), service.get("vm", "")]
    public_url = service.get("public_url")
    if isinstance(public_url, str):
        candidates.append(public_url)
    return [candidate for candidate in candidates if candidate]


def get_service_or_exit(service_map: dict[str, dict[str, Any]], service_id: str) -> dict[str, Any]:
    service_id = SERVICE_ALIASES.get(service_id, service_id)
    service = service_map.get(service_id)
    if service is None:
        raise SystemExit(f"Unknown service '{service_id}'.")
    return service


def format_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, remainder = divmod(int(round(seconds)), 60)
    return f"{minutes}m {remainder:02d}s"


def compact_json(value: Any, *, limit: int = 80) -> str:
    rendered = json.dumps(value, sort_keys=True, separators=(",", ":"))
    if len(rendered) <= limit:
        return rendered
    return f"{rendered[: limit - 3]}..."


def strip_ansi(text: str) -> str:
    return text


def colorize(text: str, code: str, *, enabled: bool) -> str:
    if not enabled:
        return text
    return f"\033[{code}m{text}\033[0m"


def yes_no(value: bool) -> str:
    return "yes" if value else "no"


def command_string(command: Iterable[str]) -> str:
    return shlex.join(list(command))


def print_plan(plan: CommandPlan, *, no_color: bool) -> None:
    enabled = not no_color and not NO_COLOR
    print(colorize(f"lv3 {plan.label}", "1;36", enabled=enabled))
    print(f"Route:   {plan.route}")
    print(f"Command: {command_string(plan.command)}")


def run_plan(plan: CommandPlan, *, dry_run: bool, explain: bool, no_color: bool) -> int:
    print_plan(plan, no_color=no_color)
    if dry_run or explain:
        return 0

    started = time.monotonic()
    completed = subprocess.run(plan.command, cwd=REPO_ROOT, text=True, check=False)
    elapsed = time.monotonic() - started
    print(f"Exit:    {completed.returncode}")
    print(f"Total:   {format_duration(elapsed)}")
    if completed.returncode == 0 and plan.receipt_hint:
        receipt = find_latest_receipt(plan.receipt_hint)
        if receipt is not None:
            print(f"Receipt: {receipt.relative_to(REPO_ROOT)}")
    return completed.returncode


def resolve_deploy_command(service_id: str, environment: str) -> CommandPlan:
    remote_command = f"make live-apply-service service={shlex.quote(service_id)} env={shlex.quote(environment)}"
    return CommandPlan(
        label=f"deploy {service_id} --env {environment}",
        route="controller -> build server -> target service playbook",
        command=["make", "remote-exec", f"COMMAND={remote_command}"],
        receipt_hint=service_id,
    )


def resolve_lint_command(local: bool) -> CommandPlan:
    if local:
        return CommandPlan(
            label="lint --local",
            route="controller local validation path",
            command=["./scripts/validate_repo.sh", "yaml", "ansible-lint"],
        )
    return CommandPlan(
        label="lint",
        route="controller -> build server check runner",
        command=["make", "remote-lint"],
    )


def resolve_validate_command(strict: bool, service: str | None = None) -> CommandPlan:
    if service:
        return CommandPlan(
            label=f"validate --service {service}",
            route="controller local ADR 0107 completeness check",
            command=["python3", "scripts/validate_service_completeness.py", "--service", service],
        )
    if strict:
        return CommandPlan(
            label="validate --strict",
            route="controller -> build server full pre-push gate",
            command=["make", "remote-pre-push"],
        )
    return CommandPlan(
        label="validate",
        route="controller -> build server validation gate",
        command=["make", "remote-validate"],
    )


def remote_tofu_shell(environment: str, action: str, *, target: str | None = None) -> str:
    env_dir = f"tofu/environments/{environment}"
    checks = [
        f"test -d {shlex.quote(env_dir)} || {{ echo 'Missing OpenTofu environment: {env_dir}' >&2; exit 1; }}",
        "command -v tofu >/dev/null 2>&1 || { echo 'Missing opentofu (tofu) on execution host' >&2; exit 1; }",
    ]
    base = f"cd {shlex.quote(env_dir)}"
    if action == "plan":
        command = "tofu plan"
    elif action == "apply":
        command = "tofu apply -auto-approve"
    elif action == "drift":
        command = "tofu plan -detailed-exitcode"
    elif action == "destroy":
        if not target:
            raise ValueError("destroy requires a tofu target")
        command = f"tofu destroy -target={shlex.quote(target)} -auto-approve"
    elif action == "list":
        command = "tofu state list || true"
    else:
        raise ValueError(f"Unsupported tofu action '{action}'")
    return " && ".join([*checks, base, command])


def resolve_diff_command(environment: str) -> CommandPlan:
    if "drift-report" in parse_make_targets():
        return CommandPlan(
            label=f"diff --env {environment}",
            route="controller local full-platform drift check",
            command=["make", "drift-report", f"ENV={environment}"],
        )
    if "tofu-drift" in parse_make_targets():
        return CommandPlan(
            label=f"diff --env {environment}",
            route="controller -> build server OpenTofu drift check",
            command=["make", "tofu-drift", f"ENV={environment}"],
        )
    return CommandPlan(
        label=f"diff --env {environment}",
            route="controller -> build server OpenTofu drift check",
            command=["make", "remote-exec", f"COMMAND={remote_tofu_shell(environment, 'drift')}"],
    )


def resolve_vm_command(
    action: str,
    environment: str,
    *,
    vm_name: str | None = None,
    force: bool = False,
) -> CommandPlan:
    if action == "create":
        label = f"vm create {vm_name or ''}".strip()
        if "remote-tofu-apply" in parse_make_targets():
            return CommandPlan(
                label=label,
                route="controller -> build server -> Proxmox API apply",
                command=["make", "remote-tofu-apply", f"ENV={environment}"],
            )
        return CommandPlan(
            label=label,
            route="controller -> build server -> Proxmox API apply",
            command=["make", "remote-exec", f"COMMAND={remote_tofu_shell(environment, 'apply')}"],
        )
    if action == "destroy":
        if not vm_name:
            raise SystemExit("lv3 vm destroy requires a VM name.")
        if not force:
            raise SystemExit("lv3 vm destroy requires --force.")
        target = f"module.{vm_name}"
        return CommandPlan(
            label=f"vm destroy {vm_name} --env {environment}",
            route="controller -> build server -> Proxmox API destroy",
            command=["make", "remote-exec", f"COMMAND={remote_tofu_shell(environment, 'destroy', target=target)}"],
        )
    if action == "resize":
        env_main = repo_path("tofu", "environments", environment, "main.tf")
        editor = os.environ.get("EDITOR")
        if not editor:
            raise SystemExit("Set $EDITOR before using lv3 vm resize.")
        return CommandPlan(
            label=f"vm resize {vm_name or ''} --env {environment}".strip(),
            route="controller local editor -> repository IaC",
            command=shlex.split(editor) + [str(env_main)],
        )
    raise SystemExit(f"Unsupported vm action '{action}'.")


def secret_get_command(secret_path: str) -> CommandPlan:
    return CommandPlan(
        label=f"secret get {secret_path}",
        route="controller -> OpenBao CLI",
        command=["openbao", "kv", "get", "-format=json", secret_path],
    )


def secret_rotate_command(secret_id: str) -> CommandPlan:
    return CommandPlan(
        label=f"secret rotate {secret_id}",
        route="controller -> repo-managed rotation workflow",
        command=["make", "rotate-secret", f"SECRET_ID={secret_id}"],
    )


def resolve_capacity_command(output_format: str, *, no_live_metrics: bool) -> CommandPlan:
    command = ["make", "capacity-report", f"FORMAT={output_format}"]
    if no_live_metrics:
        command.append("NO_LIVE_METRICS=true")
    return CommandPlan(
        label=f"capacity --format {output_format}",
        route="controller local capacity model report",
        command=command,
    )


def fixture_command(
    action: str,
    fixture_name: str | None = None,
    *,
    purpose: str | None = None,
    owner: str | None = None,
    lifetime_hours: float | None = None,
    policy: str | None = None,
    extend: bool = False,
    vmid: int | None = None,
    receipt_id: str | None = None,
) -> CommandPlan:
    action_map = {
        "create": "up",
        "up": "up",
        "destroy": "down",
        "down": "down",
        "list": "list",
    }
    target = f"fixture-{action_map[action]}"
    command = ["make", target]
    if fixture_name:
        command.append(f"FIXTURE={fixture_name}")
    if purpose:
        command.append(f"PURPOSE={purpose}")
    if owner:
        command.append(f"OWNER={owner}")
    if lifetime_hours is not None:
        command.append(f"LIFETIME_HOURS={lifetime_hours}")
    if policy:
        command.append(f"EPHEMERAL_POLICY={policy}")
    if extend:
        command.append("ALLOW_EXTEND=1")
    if vmid is not None:
        command.append(f"VMID={vmid}")
    if receipt_id:
        command.append(f"RECEIPT_ID={receipt_id}")
    return CommandPlan(
        label=f"fixture {action} {fixture_name or ''}".strip(),
        route="controller -> repo-managed ephemeral VM lifecycle helper",
        command=command,
    )


def operator_inventory_command(operator_id: str, *, offline: bool) -> CommandPlan:
    command = ["uvx", "--from", "pyyaml", "python", "scripts/operator_access_inventory.py", "--id", operator_id]
    if offline:
        command.append("--offline")
    return CommandPlan(
        label=f"operator inventory {operator_id}",
        route="controller local operator access inventory",
        command=command,
    )


def scaffold_command(service_name: str) -> CommandPlan:
    return CommandPlan(
        label=f"scaffold {service_name}",
        route="controller local service scaffold generator",
        command=["make", "scaffold-service", f"NAME={service_name}"],
    )


def promote_command(branch: str, service: str, staging_receipt: str, dry_run: bool) -> CommandPlan:
    command = [
        "make",
        "promote",
        f"SERVICE={service}",
        f"STAGING_RECEIPT={staging_receipt}",
        f"BRANCH={branch}",
    ]
    if dry_run:
        command.append("DRY_RUN=true")
    return CommandPlan(
        label=f"promote {branch}",
        route="controller -> promotion pipeline",
        command=command,
    )


def windmill_url(service_map: dict[str, dict[str, Any]]) -> str:
    service = get_service_or_exit(service_map, "windmill")
    url = primary_service_url(service)
    if not url:
        raise SystemExit("Windmill URL is not defined in the service catalog.")
    return url.rstrip("/")


def load_secret_file(secret_id: str) -> str:
    manifest = load_secret_manifest()
    entry = manifest.get(secret_id)
    if not isinstance(entry, dict):
        raise SystemExit(f"Unknown controller-local secret '{secret_id}'.")
    path = entry.get("path")
    if not isinstance(path, str):
        raise SystemExit(f"Secret '{secret_id}' does not define a file path.")
    secret_path = Path(path)
    if not secret_path.exists():
        raise SystemExit(f"Secret file not found: {secret_path}")
    return secret_path.read_text(encoding="utf-8").strip()


def parse_kv_pairs(pairs: list[str]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for pair in pairs:
        if "=" not in pair:
            raise SystemExit(f"Expected key=value, got '{pair}'.")
        key, value = pair.split("=", 1)
        payload[key] = value
    return payload


def build_execution_intent(workflow_name: str, args: list[str]) -> ExecutionIntent:
    payload = parse_kv_pairs(args)
    compiled = compile_workflow_intent(workflow_name, payload, repo_root=REPO_ROOT)
    context = assemble_context(compiled, repo_root=REPO_ROOT)
    risk = score_intent(compiled, context, repo_root=REPO_ROOT)
    return ExecutionIntent(
        intent_id=compiled["intent_id"],
        workflow_id=compiled["workflow_id"],
        workflow_description=compiled["workflow_description"],
        arguments=payload,
        live_impact=compiled["live_impact"],
        target_service_id=compiled["target_service_id"],
        target_vm=compiled["target_vm"],
        rule_risk_class=compiled["rule_risk_class"],
        computed_risk_class=risk.risk_class,
        final_risk_class=risk.final_risk_class,
        requires_approval=risk.approval_gate in {"HARD", "BLOCK"},
        rollback_verified=compiled["rollback_verified"],
        expected_change_count=compiled["expected_change_count"],
        irreversible_count=compiled["irreversible_count"],
        unknown_count=compiled["unknown_count"],
        scoring_context=context.as_dict(),
        risk_score=risk,
        semantic_diff=compiled.get("semantic_diff"),
    )


def semantic_diff_symbol(change_kind: str, confidence: str) -> str:
    if confidence == "unknown" or change_kind == "unknown":
        return "?"
    return {
        "create": "+",
        "update": "~",
        "delete": "-",
        "restart": "!",
        "renew": "!",
        "replace": "!",
    }.get(change_kind, "~")


def print_semantic_diff(intent: ExecutionIntent) -> None:
    diff = intent.semantic_diff
    if diff is None:
        print("Predicted changes: unavailable")
        return
    print(f"Predicted changes ({diff.total_changes} objects):")
    if not diff.changed_objects:
        print("  none")
    for item in diff.changed_objects:
        symbol = semantic_diff_symbol(item.change_kind, item.confidence)
        detail = item.notes or ""
        print(f"  {symbol} {item.surface}:{item.object_id} {item.change_kind} {detail}".rstrip())
    adapters = ", ".join(diff.adapters_used) if diff.adapters_used else "none"
    print(
        f"Irreversible: {diff.irreversible_count}   Unknown: {diff.unknown_count}   "
        f"Adapters used: {adapters}"
    )


def print_compiled_intent(intent: ExecutionIntent) -> None:
    print_semantic_diff(intent)
    print("Compiled intent:")
    print(yaml.safe_dump(intent.as_dict(), sort_keys=False, default_flow_style=False).rstrip())


def maybe_write_compiled_intent_event(
    intent: ExecutionIntent,
    *,
    dsn: str | None = None,
    writer_factory: Any | None = None,
) -> dict[str, Any] | None:
    resolved_dsn = (dsn if dsn is not None else os.environ.get("LV3_LEDGER_DSN", "")).strip()
    if not resolved_dsn or resolved_dsn.lower() == "off":
        return None
    if writer_factory is None:
        from platform.ledger import LedgerWriter

        writer_factory = LedgerWriter

    target_id = intent.target_service_id or intent.workflow_id
    target_kind = "service" if intent.target_service_id else "workflow"
    return writer_factory(dsn=resolved_dsn).write(
        event_type="intent.compiled",
        actor="operator:lv3_cli",
        actor_intent_id=intent.intent_id,
        tool_id="lv3_cli",
        target_kind=target_kind,
        target_id=target_id,
        before_state=intent.semantic_diff.as_dict() if intent.semantic_diff is not None else None,
        after_state=intent.as_dict(),
    )


def print_goal_compiled_intent(result: Any) -> None:
    print("Compiled Intent:")
    print(yaml.safe_dump(result.intent.as_dict(), sort_keys=False).rstrip())
    print(f"Matched Rule: {result.matched_rule_id}")
    if result.dispatch_workflow_id:
        print(f"Dispatch Workflow: {result.dispatch_workflow_id}")


def enforce_risk_gate(intent: ExecutionIntent, *, approve_risk: bool, risk_override: bool) -> int:
    if intent.risk_score.approval_gate == "BLOCK" and not risk_override:
        print(
            f"Risk gate BLOCK: {intent.workflow_id} scored {intent.risk_score.score:.1f} "
            f"({intent.final_risk_class.value}). Re-run with --risk-override to proceed.",
            file=sys.stderr,
        )
        return 2
    if intent.risk_score.approval_gate == "HARD" and not approve_risk:
        print(
            f"Risk gate HARD: {intent.workflow_id} scored {intent.risk_score.score:.1f} "
            f"({intent.final_risk_class.value}). Re-run with --approve-risk to proceed.",
            file=sys.stderr,
        )
        return 2
    return 0


def run_windmill_request(
    workflow_name: str,
    payload: dict[str, Any],
    *,
    dry_run: bool,
    explain: bool,
    no_color: bool,
    intent: ExecutionIntent | None = None,
) -> int:
    service_map = load_service_map()
    base_url = windmill_url(service_map)
    token = load_secret_file("windmill_superadmin_secret")
    script_path = workflow_name if "/" in workflow_name else f"f/lv3/{workflow_name}"
    encoded_path = urllib.parse.quote(script_path, safe="")
    url = f"{base_url}/api/w/lv3/jobs/run_wait_result/p/{encoded_path}"
    encoded_payload = json.dumps(payload).encode("utf-8")
    plan = CommandPlan(
        label=f"run {workflow_name}",
        route="controller -> budgeted scheduler -> Windmill API",
        command=[
            "curl",
            "-X",
            "POST",
            "-H",
            "Authorization: Bearer <redacted>",
            "-H",
            "Content-Type: application/json",
            url,
            "--data-binary",
            encoded_payload.decode("utf-8"),
        ],
    )
    print_plan(plan, no_color=no_color)
    if dry_run or explain:
        return 0

    scheduler = build_scheduler(
        base_url=base_url,
        token=token,
        workspace="lv3",
        repo_root=REPO_ROOT,
    )
    scheduler_intent = intent or SimpleNamespace(
        workflow_id=workflow_name,
        arguments=payload,
        target_vm=payload.get("target_vm") or payload.get("target"),
    )
    try:
        result = scheduler.submit(scheduler_intent, requested_by="operator:lv3_cli")
    except (urllib.error.URLError, RuntimeError) as exc:
        print(f"Windmill API error: {exc}", file=sys.stderr)
        return 1

    if result.status in {"concurrency_limit", "rollback_depth_exceeded", "budget_exceeded"}:
        print(
            f"Scheduler rejected {workflow_name}: {result.status}"
            + (f" ({result.reason})" if result.reason else ""),
            file=sys.stderr,
        )
        return 1
    if result.output is not None:
        if isinstance(result.output, str):
            print(result.output)
        else:
            print(json.dumps(result.output, indent=2, sort_keys=True))
    if result.status in {"failed", "aborted"}:
        print(
            f"Workflow {workflow_name} ended with status {result.status}.",
            file=sys.stderr,
        )
        return 1
    return 0


def run_windmill_workflow(
    workflow_name: str,
    args: list[str],
    *,
    dry_run: bool,
    explain: bool,
    no_color: bool,
    approve_risk: bool = False,
    risk_override: bool = False,
) -> int:
    intent = build_execution_intent(workflow_name, args)
    maybe_write_compiled_intent_event(intent)
    print_compiled_intent(intent)
    if not (dry_run or explain):
        blocked = enforce_risk_gate(intent, approve_risk=approve_risk, risk_override=risk_override)
        if blocked:
            return blocked
    return run_windmill_request(
        workflow_name,
        intent.arguments,
        dry_run=dry_run,
        explain=explain,
        no_color=no_color,
        intent=intent,
    )


def prompt_for_intent_approval() -> bool:
    response = input("Approval required. Execute this intent? [y/N]: ").strip().lower()
    return response in {"y", "yes"}


def run_compiled_instruction(
    instruction: str,
    args: list[str],
    *,
    dry_run: bool,
    explain: bool,
    no_color: bool,
) -> int:
    compiler = GoalCompiler(REPO_ROOT)
    ledger = LedgerWriter(
        file_path=REPO_ROOT / ".local" / "state" / "ledger" / "ledger.events.jsonl",
        nats_publisher=None,
    )
    parsed_args = parse_kv_pairs(args)
    try:
        result = compiler.compile(instruction, dispatch_args=parsed_args)
    except GoalCompilationError as exc:
        ledger.write(
            event_type="intent.rejected",
            actor="operator:lv3-cli",
            target_kind="instruction",
            target_id=instruction,
            metadata={
                "error_code": exc.code,
                "error_message": exc.message,
                "raw_input": exc.raw_input,
                "details": exc.details,
            },
        )
        print(str(exc), file=sys.stderr)
        return 2

    print_goal_compiled_intent(result)
    ledger.write(
        event_type="intent.compiled",
        actor="operator:lv3-cli",
        target_kind=result.intent.target.kind,
        target_id=result.intent.target.name,
        actor_intent_id=result.intent.id,
        after_state=result.intent.as_dict(),
        metadata={
            "matched_rule_id": result.matched_rule_id,
            "normalized_input": result.normalized_input,
            "dispatch_workflow_id": result.dispatch_workflow_id,
        },
    )

    if dry_run or explain:
        if result.dispatch_workflow_id:
            return run_windmill_request(
                result.dispatch_workflow_id,
                result.dispatch_payload,
                dry_run=True,
                explain=explain,
                no_color=no_color,
            )
        return 0

    if result.intent.requires_approval:
        if not prompt_for_intent_approval():
            ledger.write(
                event_type="intent.rejected",
                actor="operator:lv3-cli",
                target_kind=result.intent.target.kind,
                target_id=result.intent.target.name,
                actor_intent_id=result.intent.id,
                metadata={"reason": "approval_denied", "dispatch_workflow_id": result.dispatch_workflow_id},
            )
            print("Execution cancelled.", file=sys.stderr)
            return 1
        ledger.write(
            event_type="intent.approved",
            actor="operator:lv3-cli",
            target_kind=result.intent.target.kind,
            target_id=result.intent.target.name,
            actor_intent_id=result.intent.id,
            after_state=result.intent.as_dict(),
            metadata={"dispatch_workflow_id": result.dispatch_workflow_id},
        )

    if result.dispatch_workflow_id is None:
        print("No workflow route is available for this intent.", file=sys.stderr)
        return 1

    return run_windmill_request(
        result.dispatch_workflow_id,
        result.dispatch_payload,
        dry_run=False,
        explain=False,
        no_color=no_color,
    )


def should_run_direct_workflow(instruction: str) -> bool:
    normalized = instruction.strip()
    workflows = load_workflow_catalog()
    return normalized in workflows or "/" in normalized


def open_service_url(service_id: str, environment: str, *, dry_run: bool, explain: bool, no_color: bool) -> int:
    service = get_service_or_exit(load_service_map(), service_id)
    url = primary_service_url(service, environment)
    if not url:
        raise SystemExit(f"Service '{service_id}' does not define a browsable URL.")
    plan = CommandPlan(
        label=f"open {service_id}",
        route="controller local browser",
        command=["python3", "-m", "webbrowser", url],
    )
    print_plan(plan, no_color=no_color)
    if dry_run or explain:
        return 0
    return 0 if webbrowser.open(url) else 1


def impact_command(service_id: str) -> int:
    graph = load_dependency_graph(
        repo_path("config", "dependency-graph.json"),
        service_catalog_path=repo_path("config", "service-capability-catalog.json"),
        validate_schema=False,
    )
    summary = dependency_summary(SERVICE_ALIASES.get(service_id, service_id), graph)
    service_map = load_service_map()

    def service_names(service_ids: list[str]) -> str:
        return ", ".join(service_map[item]["name"] if item in service_map else item for item in service_ids)

    print(f"Service: {summary['name']} ({summary['service']})")
    print(f"Recovery tier: {summary['tier']}")
    print("Depends on:")
    rendered = 0
    for edge_type, label in (
        ("hard", "Hard"),
        ("soft", "Soft"),
        ("startup_only", "Startup-only"),
        ("reads_from", "Reads-from"),
    ):
        services = summary["depends_on"][edge_type]
        if services:
            rendered += 1
            print(f"  {label}: {service_names(services)}")
    if rendered == 0:
        print("  none")
    print(
        "Impact if this service fails:"
        f"\n  Direct hard: {service_names(summary['impact']['direct_hard']) if summary['impact']['direct_hard'] else 'none'}"
        f"\n  Transitive hard: {service_names(summary['impact']['transitive_hard']) if summary['impact']['transitive_hard'] else 'none'}"
        f"\n  Direct soft: {service_names(summary['impact']['direct_soft']) if summary['impact']['direct_soft'] else 'none'}"
        f"\n  Startup-only: {service_names(summary['impact']['direct_startup_only']) if summary['impact']['direct_startup_only'] else 'none'}"
        f"\n  Reads-from: {service_names(summary['impact']['direct_reads_from']) if summary['impact']['direct_reads_from'] else 'none'}"
    )
    return 0


def http_probe(url: str, *, timeout: float, validate_tls: bool) -> ProbeResult:
    started = time.monotonic()
    request = urllib.request.Request(url, headers={"User-Agent": "lv3-cli/0.1.0"})
    context = None
    if url.startswith("https://") and not validate_tls:
        context = ssl._create_unverified_context()
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
            status = response.status
        elapsed = time.monotonic() - started
        healthy = 200 <= status < 400
        return ProbeResult(
            service_id="",
            url=url,
            healthy=healthy,
            health_text=f"{'OK' if healthy else 'BAD'} {status}",
            latency_seconds=elapsed,
        )
    except urllib.error.URLError as exc:
        return ProbeResult(service_id="", url=url, healthy=False, health_text=str(exc.reason), latency_seconds=None)


def tcp_probe(host: str, port: int, *, timeout: float) -> ProbeResult:
    started = time.monotonic()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            elapsed = time.monotonic() - started
            return ProbeResult(service_id="", url=f"tcp://{host}:{port}", healthy=True, health_text="OK tcp", latency_seconds=elapsed)
    except OSError as exc:
        return ProbeResult(service_id="", url=f"tcp://{host}:{port}", healthy=False, health_text=str(exc), latency_seconds=None)


def probe_one_service(
    service: dict[str, Any],
    health_probes: dict[str, Any],
    *,
    environment: str,
    timeout: float,
) -> ProbeResult:
    url = primary_service_url(service, environment) or "-"
    parsed = urllib.parse.urlparse(url) if url != "-" else None

    if parsed and parsed.scheme in {"http", "https"}:
        probe = health_probes.get(service.get("health_probe_id"), {})
        validate_tls = True
        if isinstance(probe, dict):
            readiness = probe.get("readiness")
            if isinstance(readiness, dict) and isinstance(readiness.get("validate_tls"), bool):
                validate_tls = readiness["validate_tls"]
        result = http_probe(url, timeout=timeout, validate_tls=validate_tls)
    elif parsed and parsed.scheme == "ssh":
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 22
        result = tcp_probe(host, port, timeout=timeout)
    else:
        probe = health_probes.get(service.get("health_probe_id"), {})
        readiness = probe.get("readiness") if isinstance(probe, dict) else None
        if isinstance(readiness, dict) and readiness.get("kind") == "tcp":
            result = tcp_probe(str(readiness.get("host")), int(readiness.get("port")), timeout=timeout)
            url = f"tcp://{readiness.get('host')}:{readiness.get('port')}"
        else:
            result = ProbeResult(service_id="", url=url, healthy=False, health_text="no reachable probe", latency_seconds=None)

    return ProbeResult(
        service_id=service["id"],
        url=url,
        healthy=result.healthy,
        health_text=result.health_text,
        latency_seconds=result.latency_seconds,
    )


def print_status_table(results: list[tuple[dict[str, Any], ProbeResult]], *, no_color: bool) -> None:
    enabled = not no_color and not NO_COLOR
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    print(f"PLATFORM STATUS (lv3)  {now}")
    print("-" * 92)
    print(f"{'SERVICE':<20} {'VM':<20} {'URL':<34} {'HEALTH':<10} {'LATENCY':>7}")
    overall_ok = True
    for service, result in results:
        if not result.healthy:
            overall_ok = False
        plain_status = result.health_text[:10]
        status_label = colorize(
            plain_status,
            "32" if result.healthy else "31",
            enabled=enabled,
        )
        latency = "-" if result.latency_seconds is None else f"{result.latency_seconds:.2f}s"
        status_cell = plain_status if not enabled else status_label
        print(
            f"{service['id']:<20} "
            f"{str(service.get('vm', '-')):<20} "
            f"{result.url[:34]:<34} "
            f"{status_cell:<10} "
            f"{latency:>7}"
        )
    latest = find_latest_receipt(None)
    if latest is not None:
        print()
        print(f"Last deploy: {latest.stem}")
    if not overall_ok:
        raise SystemExit(1)


def status_command(service_id: str | None, environment: str, *, timeout: float, no_color: bool) -> int:
    service_map = load_service_map()
    health_probes = load_health_probe_catalog()
    if service_id:
        services = [get_service_or_exit(service_map, service_id)]
    else:
        services = sorted(
            [service for service in service_map.values() if service.get("lifecycle_status") == "active"],
            key=lambda item: item["id"],
        )
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(12, len(services) or 1)) as executor:
        futures = {
            executor.submit(
                probe_one_service,
                service,
                health_probes,
                environment=environment,
                timeout=timeout,
            ): service
            for service in services
        }
        results = [(service, future.result()) for future, service in futures.items()]
    results.sort(key=lambda item: item[0]["id"])
    print_status_table(results, no_color=no_color)
    return 0


def find_latest_receipt(service_hint: str | None) -> Path | None:
    receipts_dir = repo_path("receipts", "live-applies")
    receipts = sorted(receipts_dir.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not receipts:
        return None
    if not service_hint:
        return receipts[0]
    service_hint = service_hint.replace("-", "_")
    for receipt in receipts:
        try:
            payload = json.loads(receipt.read_text())
        except json.JSONDecodeError:
            continue
        haystacks = [
            receipt.stem,
            str(payload.get("summary", "")),
            str(payload.get("workflow_id", "")),
            " ".join(str(target.get("name", "")) for target in payload.get("targets", [])),
        ]
        normalized = " ".join(haystacks).replace("-", "_")
        if service_hint in normalized:
            return receipt
    return receipts[0]


def resolve_vm_inventory() -> list[tuple[str, str | None, str]]:
    inventory_path = repo_path("inventory", "hosts.yml")
    current_host: str | None = None
    host_ip: dict[str, str] = {}
    for raw_line in inventory_path.read_text().splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if line.startswith("        ") and stripped.endswith(":") and not stripped.startswith("ansible_"):
            current_host = stripped[:-1]
            host_ip.setdefault(current_host, "")
            continue
        if "ansible_host:" in stripped and current_host:
            host_ip[current_host] = stripped.split(":", 1)[1].strip()
    result = []
    service_map = load_service_map()
    seen_hosts: set[str] = set()
    for service in service_map.values():
        vm = service.get("vm")
        if isinstance(vm, str) and vm not in seen_hosts:
            seen_hosts.add(vm)
            result.append((vm, host_ip.get(vm) or None, service["id"]))
    return sorted(result)


def vm_list_command(environment: str) -> int:
    print(f"VM INVENTORY ({environment})")
    print("-" * 72)
    print(f"{'VM':<24} {'ADDRESS':<18} {'SERVICE'}")
    for vm_name, address, service_id in resolve_vm_inventory():
        print(f"{vm_name:<24} {str(address or '-'):18} {service_id}")
    return 0


def ssh_command(vm_name: str, *, dry_run: bool, explain: bool, no_color: bool) -> int:
    address = None
    for candidate, addr, _service in resolve_vm_inventory():
        if candidate == vm_name:
            address = addr
            break
    if vm_name == "proxmox_florin" and address is None:
        address = "100.118.189.95"
    if not address:
        raise SystemExit(f"Unknown VM '{vm_name}'.")
    plan = CommandPlan(
        label=f"ssh {vm_name}",
        route="controller -> VM SSH session",
        command=["ssh", f"ops@{address}"],
    )
    print_plan(plan, no_color=no_color)
    if dry_run or explain:
        return 0
    os.execvp(plan.command[0], plan.command)
    return 0


def parse_since(value: str) -> datetime:
    unit = value[-1:]
    number = value[:-1]
    if unit not in {"m", "h", "d"} or not number.isdigit():
        raise SystemExit("Use --since with one of <Nm|Nh|Nd>, for example 10m or 2h.")
    count = int(number)
    delta = {"m": timedelta(minutes=count), "h": timedelta(hours=count), "d": timedelta(days=count)}[unit]
    return datetime.now(UTC) - delta


def loki_query_url(service_map: dict[str, dict[str, Any]]) -> str:
    if os.environ.get("LV3_LOKI_URL"):
        return os.environ["LV3_LOKI_URL"]
    grafana_service = get_service_or_exit(service_map, "grafana")
    monitoring_vm = grafana_service.get("vm")
    for vm_name, address, _service in resolve_vm_inventory():
        if vm_name == monitoring_vm and address:
            return f"http://{address}:3100/loki/api/v1/query_range"
    return "http://10.10.10.40:3100/loki/api/v1/query_range"


def logs_command(service_id: str, *, tail: int, since: str, dry_run: bool, explain: bool, no_color: bool) -> int:
    service_map = load_service_map()
    url = loki_query_url(service_map)
    start = parse_since(since)
    params = {
        "query": f'{{service="{service_id}"}}',
        "limit": str(tail),
        "direction": "backward",
        "start": str(int(start.timestamp() * 1_000_000_000)),
    }
    full_url = f"{url}?{urllib.parse.urlencode(params)}"
    plan = CommandPlan(
        label=f"logs {service_id}",
        route="controller -> Loki query API",
        command=["curl", full_url],
    )
    print_plan(plan, no_color=no_color)
    if dry_run or explain:
        return 0

    request = urllib.request.Request(full_url, headers={"User-Agent": "lv3-cli/0.1.0"})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        print(f"Loki query failed: {exc}", file=sys.stderr)
        return 1

    results = payload.get("data", {}).get("result", [])
    if not results:
        print("No log lines found.")
        return 0
    lines: list[tuple[int, str]] = []
    for stream in results:
        stream_labels = stream.get("stream", {})
        label_text = ",".join(f"{key}={value}" for key, value in sorted(stream_labels.items()))
        for ts, line in stream.get("values", []):
            lines.append((int(ts), f"[{label_text}] {line.rstrip()}"))
    for _ts, line in sorted(lines, key=lambda item: item[0])[-tail:]:
        print(line)
    return 0


def search_command(query: str, *, collection: str | None, limit: int, rebuild: bool) -> int:
    client = SearchClient(REPO_ROOT)
    payload = client.query(query, collection=collection, limit=limit, rebuild=rebuild)
    if not payload["results"]:
        print(f"No results for '{query}'.")
        return 0
    for result in payload["results"]:
        print(f"[{result['collection']}] {result['title']}  {result['score']:.2f}  {result.get('url') or '-'}")
    return 0


def agent_state_client(agent_id: str, task_id: str) -> AgentStateClient:
    return AgentStateClient(agent_id=agent_id, task_id=task_id)


def agent_state_show_command(agent_id: str, task_id: str, *, json_output: bool) -> int:
    entries = agent_state_client(agent_id, task_id).list_entries()
    if json_output:
        emit_json(
            {
                "agent_id": agent_id,
                "task_id": task_id,
                "entries": [
                    {
                        "key": entry.key,
                        "value": entry.value,
                        "context_id": entry.context_id,
                        "written_at": entry.written_at.isoformat(),
                        "expires_at": entry.expires_at.isoformat(),
                        "version": entry.version,
                    }
                    for entry in entries
                ],
            }
        )
        return 0
    if not entries:
        print("No non-expired state entries found.")
        return 0
    print(f"{'KEY':<24} {'VALUE':<80} {'WRITTEN_AT':<20} {'EXPIRES_AT':<20} {'VER':>3}")
    for entry in entries:
        print(
            f"{entry.key:<24} "
            f"{compact_json(entry.value):<80} "
            f"{entry.written_at.strftime('%Y-%m-%dT%H:%M:%SZ'):<20} "
            f"{entry.expires_at.strftime('%Y-%m-%dT%H:%M:%SZ'):<20} "
            f"{entry.version:>3}"
        )
    return 0


def agent_state_delete_command(agent_id: str, task_id: str, *, key: str) -> int:
    deleted = agent_state_client(agent_id, task_id).delete(key)
    if deleted:
        print(f"Deleted {key} from {agent_id}/{task_id}.")
        return 0
    print(f"State key not found: {key}", file=sys.stderr)
    return 1


def agent_state_verify_command(agent_id: str, task_id: str, *, digest: str, json_output: bool) -> int:
    result = agent_state_client(agent_id, task_id).validate_handoff(digest)
    if json_output:
        emit_json(
            {
                "agent_id": result.agent_id,
                "task_id": result.task_id,
                "expected_digest": result.expected_digest,
                "actual_digest": result.actual_digest,
                "matched": result.matched,
                "key_count": result.key_count,
            }
        )
    else:
        print(f"Integrity: {'ok' if result.matched else 'mismatch'}")
        print(f"Expected:  {result.expected_digest}")
        print(f"Observed:  {result.actual_digest}")
        print(f"Key count: {result.key_count}")
    return 0 if result.matched else 1


def generate_completion_script(shell_name: str) -> str:
    function_name = "_lv3_completion"
    if shell_name == "bash":
        return textwrap.dedent(
            f"""
            {COMPLETION_SENTINEL}
            {function_name}() {{
              local cur="${{COMP_WORDS[COMP_CWORD]}}"
              COMPREPLY=($(COMP_WORDS="${{COMP_WORDS[*]}}" COMP_CWORD=$COMP_CWORD lv3 __complete "$cur"))
            }}
            complete -F {function_name} lv3
            # <<< lv3 completion <<<
            """
        ).strip() + "\n"
    if shell_name == "zsh":
        return textwrap.dedent(
            f"""
            {COMPLETION_SENTINEL}
            {function_name}() {{
              local -a reply
              reply=("${{(@f)$(COMP_WORDS="$words" COMP_CWORD=$CURRENT lv3 __complete "$words[CURRENT]")}}")
              _describe 'values' reply
            }}
            compdef {function_name} lv3
            # <<< lv3 completion <<<
            """
        ).strip() + "\n"
    raise SystemExit("Completion shell must be one of: bash, zsh.")


def install_completion(shell_name: str) -> int:
    rc_map = {"bash": Path.home() / ".bashrc", "zsh": Path.home() / ".zshrc"}
    rc_path = rc_map[shell_name]
    block = generate_completion_script(shell_name)
    if rc_path.exists() and COMPLETION_SENTINEL in rc_path.read_text():
        print(f"Completion already installed in {rc_path}.")
        return 0
    with rc_path.open("a", encoding="utf-8") as handle:
        if rc_path.stat().st_size:
            handle.write("\n")
        handle.write(block)
    print(f"Installed lv3 completion into {rc_path}.")
    return 0


def completion_candidates(words: list[str], current: str) -> list[str]:
    top_level = [
        "agent",
        "deploy",
        "impact",
        "lint",
        "validate",
        "search",
        "status",
        "vm",
        "secret",
        "fixture",
        "scaffold",
        "diff",
        "capacity",
        "promote",
        "run",
        "logs",
        "ssh",
        "open",
        "operator",
        "release",
    ]
    if len(words) <= 1:
        return [candidate for candidate in top_level if candidate.startswith(current)]
    if words[1] in {"deploy", "impact", "status", "logs", "open"}:
        candidates = sorted(set(load_service_map()) | set(SERVICE_ALIASES))
        return [service_id for service_id in candidates if service_id.startswith(current)]
    if words[1] == "validate" and "--service" in words:
        candidates = sorted(set(load_service_map()) | set(SERVICE_ALIASES))
        return [service_id for service_id in candidates if service_id.startswith(current)]
    if words[1] == "run":
        return [workflow_id for workflow_id in sorted(load_workflow_catalog()) if workflow_id.startswith(current)]
    if words[1] == "ssh":
        return [vm_name for vm_name, _address, _service in resolve_vm_inventory() if vm_name.startswith(current)]
    if words[1] == "vm" and len(words) == 3:
        return [action for action in ["create", "destroy", "resize", "list"] if action.startswith(current)]
    if words[1] == "fixture" and len(words) == 3:
        return [action for action in ["create", "destroy", "list", "up", "down"] if action.startswith(current)]
    if words[1] == "fixture" and len(words) == 4 and words[2] in {"up", "down", "create", "destroy"}:
        fixtures_dir = repo_path("tests", "fixtures")
        candidates = []
        if fixtures_dir.exists():
            for path in sorted(fixtures_dir.glob("*-fixture.yml")):
                candidates.append(path.name.removesuffix("-fixture.yml"))
        return [fixture_id for fixture_id in sorted(dict.fromkeys(candidates)) if fixture_id.startswith(current)]
    if words[1] == "secret" and len(words) == 3:
        return [action for action in ["get", "rotate"] if action.startswith(current)]
    if words[1] == "operator" and len(words) == 3:
        return [action for action in ["add", "remove", "inventory"] if action.startswith(current)]
    if words[1] == "agent" and len(words) == 3:
        return [action for action in ["state"] if action.startswith(current)]
    if words[1:3] == ["agent", "state"] and len(words) == 4:
        return [action for action in ["show", "delete", "verify"] if action.startswith(current)]
    if words[1] == "release" and len(words) == 3:
        return [action for action in ["status", "tag"] if action.startswith(current)]
    return []


def handle_completion(current: str) -> int:
    words = os.environ.get("COMP_WORDS", "").split()
    if not words:
        words = sys.argv[1:]
    for candidate in completion_candidates(words, current):
        print(candidate)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Unified operator CLI for the LV3 platform.")
    parser.add_argument("--version", action="store_true", help="Print the lv3 CLI version.")
    parser.add_argument("--no-color", action="store_true", help="Disable ANSI colors.")
    parser.add_argument("--install-completion", choices=["bash", "zsh"], help="Install shell completion into the default rc file.")

    subparsers = parser.add_subparsers(dest="command")

    deploy = subparsers.add_parser("deploy", help="Deploy one service.")
    deploy.add_argument("service")
    deploy.add_argument("--env", default="production", choices=["production", "staging"])
    deploy.add_argument("--dry-run", action="store_true")
    deploy.add_argument("--explain", action="store_true")

    impact = subparsers.add_parser("impact", help="Show dependency and failure impact for one service.")
    impact.add_argument("service")

    lint = subparsers.add_parser("lint", help="Run repository lint checks.")
    lint.add_argument("--local", action="store_true")
    lint.add_argument("--dry-run", action="store_true")
    lint.add_argument("--explain", action="store_true")

    validate = subparsers.add_parser("validate", help="Run repository validation.")
    validate.add_argument("--strict", action="store_true")
    validate.add_argument("--service")
    validate.add_argument("--dry-run", action="store_true")
    validate.add_argument("--explain", action="store_true")

    search = subparsers.add_parser("search", help="Query the local platform search fabric.")
    search.add_argument("query")
    search.add_argument("--collection")
    search.add_argument("--limit", type=int, default=10)
    search.add_argument("--rebuild", action="store_true")

    status = subparsers.add_parser("status", help="Show service health status.")
    status.add_argument("service", nargs="?")
    status.add_argument("--env", default="production", choices=["production", "staging"])
    status.add_argument("--timeout", type=float, default=DEFAULT_STATUS_TIMEOUT_SECONDS)

    vm = subparsers.add_parser("vm", help="Operate on VM lifecycle routes.")
    vm_subparsers = vm.add_subparsers(dest="vm_action", required=True)
    vm_create = vm_subparsers.add_parser("create", help="Apply the VM environment.")
    vm_create.add_argument("name", nargs="?")
    vm_create.add_argument("--env", default="production", choices=["production", "staging"])
    vm_create.add_argument("--dry-run", action="store_true")
    vm_create.add_argument("--explain", action="store_true")
    vm_destroy = vm_subparsers.add_parser("destroy", help="Destroy one VM target.")
    vm_destroy.add_argument("name")
    vm_destroy.add_argument("--env", default="production", choices=["production", "staging"])
    vm_destroy.add_argument("--force", action="store_true")
    vm_destroy.add_argument("--dry-run", action="store_true")
    vm_destroy.add_argument("--explain", action="store_true")
    vm_resize = vm_subparsers.add_parser("resize", help="Open the VM IaC file in $EDITOR.")
    vm_resize.add_argument("name", nargs="?")
    vm_resize.add_argument("--env", default="production", choices=["production", "staging"])
    vm_resize.add_argument("--dry-run", action="store_true")
    vm_resize.add_argument("--explain", action="store_true")
    vm_list = vm_subparsers.add_parser("list", help="List known VMs.")
    vm_list.add_argument("--env", default="production", choices=["production", "staging"])

    secret = subparsers.add_parser("secret", help="Access managed secrets.")
    secret_subparsers = secret.add_subparsers(dest="secret_action", required=True)
    secret_get = secret_subparsers.add_parser("get", help="Read a secret through OpenBao.")
    secret_get.add_argument("path")
    secret_get.add_argument("--dry-run", action="store_true")
    secret_get.add_argument("--explain", action="store_true")
    secret_rotate = secret_subparsers.add_parser("rotate", help="Rotate one managed secret.")
    secret_rotate.add_argument("secret_id")
    secret_rotate.add_argument("--dry-run", action="store_true")
    secret_rotate.add_argument("--explain", action="store_true")

    fixture = subparsers.add_parser("fixture", help="Manage ephemeral fixtures.")
    fixture_subparsers = fixture.add_subparsers(dest="fixture_action", required=True)
    fixture_create = fixture_subparsers.add_parser("create", aliases=["up"], help="Create one ephemeral fixture VM.")
    fixture_create.add_argument("name", nargs="?")
    fixture_create.add_argument("--purpose")
    fixture_create.add_argument("--owner")
    fixture_create.add_argument("--lifetime-hours", type=float)
    fixture_create.add_argument(
        "--policy",
        default="adr-development",
        choices=["adr-development", "extended-fixture", "integration-test", "restore-verification"],
    )
    fixture_create.add_argument("--extend", action="store_true")
    fixture_create.add_argument("--dry-run", action="store_true")
    fixture_create.add_argument("--explain", action="store_true")
    fixture_destroy = fixture_subparsers.add_parser("destroy", aliases=["down"], help="Destroy one ephemeral fixture VM.")
    fixture_destroy.add_argument("name", nargs="?")
    fixture_destroy.add_argument("--vmid", type=int)
    fixture_destroy.add_argument("--receipt-id")
    fixture_destroy.add_argument("--dry-run", action="store_true")
    fixture_destroy.add_argument("--explain", action="store_true")
    fixture_list = fixture_subparsers.add_parser("list", help="List active fixtures.")
    fixture_list.add_argument("--dry-run", action="store_true")
    fixture_list.add_argument("--explain", action="store_true")

    scaffold = subparsers.add_parser("scaffold", help="Scaffold a new service.")
    scaffold.add_argument("name")
    scaffold.add_argument("--dry-run", action="store_true")
    scaffold.add_argument("--explain", action="store_true")

    diff = subparsers.add_parser("diff", help="Show infrastructure drift.")
    diff.add_argument("--env", default="production", choices=["production", "staging"])
    diff.add_argument("--dry-run", action="store_true")
    diff.add_argument("--explain", action="store_true")

    capacity = subparsers.add_parser("capacity", help="Render the platform capacity report.")
    capacity.add_argument("--format", choices=["text", "markdown", "json", "prometheus"], default="text")
    capacity.add_argument("--no-live-metrics", action="store_true")
    capacity.add_argument("--dry-run", action="store_true")
    capacity.add_argument("--explain", action="store_true")

    promote = subparsers.add_parser("promote", help="Run the promotion pipeline.")
    promote.add_argument("branch")
    promote.add_argument("--service", required=True)
    promote.add_argument("--staging-receipt", required=True)
    promote.add_argument("--to", choices=["staging", "production"], default="production")
    promote.add_argument("--dry-run", action="store_true")
    promote.add_argument("--explain", action="store_true")

    run = subparsers.add_parser("run", help="Compile and trigger one platform instruction.")
    run.add_argument("instruction", nargs="+")
    run.add_argument("--args", nargs="*", default=[])
    run.add_argument("--approve-risk", action="store_true", help="Acknowledge a HIGH risk score and proceed.")
    run.add_argument("--risk-override", action="store_true", help="Override a BLOCK gate for a CRITICAL risk score.")
    run.add_argument("--dry-run", action="store_true")
    run.add_argument("--explain", action="store_true")

    logs = subparsers.add_parser("logs", help="Query service logs from Loki.")
    logs.add_argument("service")
    logs.add_argument("--tail", type=int, default=DEFAULT_LOG_LINES)
    logs.add_argument("--since", default=DEFAULT_LOG_SINCE)
    logs.add_argument("--dry-run", action="store_true")
    logs.add_argument("--explain", action="store_true")

    ssh = subparsers.add_parser("ssh", help="Open an SSH session to one VM.")
    ssh.add_argument("vm_name")
    ssh.add_argument("--dry-run", action="store_true")
    ssh.add_argument("--explain", action="store_true")

    open_parser = subparsers.add_parser("open", help="Open one service URL.")
    open_parser.add_argument("service")
    open_parser.add_argument("--env", default="production", choices=["production", "staging"])
    open_parser.add_argument("--dry-run", action="store_true")
    open_parser.add_argument("--explain", action="store_true")

    release = subparsers.add_parser("release", help="Prepare repository releases and show readiness.")
    release.add_argument("--version", help="Explicit release version to prepare.")
    release.add_argument("--bump", choices=["major", "minor", "patch"], help="Semantic version bump to prepare.")
    release.add_argument("--platform-impact", help="One-line platform impact summary for the release notes.")
    release.add_argument("--released-on", help="Release date in YYYY-MM-DD format.")
    release.add_argument("--dry-run", action="store_true")
    release_subparsers = release.add_subparsers(dest="release_action")
    release_status = release_subparsers.add_parser("status", help="Show release blockers and product readiness.")
    release_status.add_argument("--json", action="store_true")
    release_status.add_argument("--timeout", type=float, default=2.0)
    release_tag = release_subparsers.add_parser("tag", help="Create the annotated release tag for the current VERSION.")
    release_tag.add_argument("--version", help="Version to tag. Defaults to the current VERSION file.")
    release_tag.add_argument("--push", action="store_true")
    release_tag.add_argument("--dry-run", action="store_true")

    operator = subparsers.add_parser("operator", help="Manage human operator access.")
    operator_subparsers = operator.add_subparsers(dest="operator_action", required=True)
    operator_add = operator_subparsers.add_parser("add", help="Run the operator onboarding workflow.")
    operator_add.add_argument("--name", required=True)
    operator_add.add_argument("--email", required=True)
    operator_add.add_argument("--role", required=True, choices=["admin", "operator", "viewer"])
    operator_add.add_argument("--ssh-key", default="")
    operator_add.add_argument("--id")
    operator_add.add_argument("--keycloak-username")
    operator_add.add_argument("--tailscale-login-email")
    operator_add.add_argument("--tailscale-device-name")
    operator_add.add_argument("--dry-run", action="store_true")
    operator_add.add_argument("--explain", action="store_true")

    operator_remove = operator_subparsers.add_parser("remove", help="Run the operator offboarding workflow.")
    operator_remove.add_argument("--id", required=True)
    operator_remove.add_argument("--reason")
    operator_remove.add_argument("--dry-run", action="store_true")
    operator_remove.add_argument("--explain", action="store_true")

    operator_inventory = operator_subparsers.add_parser("inventory", help="Show one operator access inventory.")
    operator_inventory.add_argument("--id", required=True)
    operator_inventory.add_argument("--offline", action="store_true")
    operator_inventory.add_argument("--dry-run", action="store_true")
    operator_inventory.add_argument("--explain", action="store_true")

    agent = subparsers.add_parser("agent", help="Inspect persisted agent scratch state.")
    agent_subparsers = agent.add_subparsers(dest="agent_action", required=True)
    agent_state = agent_subparsers.add_parser("state", help="Inspect one persisted agent task namespace.")
    agent_state_subparsers = agent_state.add_subparsers(dest="agent_state_action", required=True)

    agent_state_show = agent_state_subparsers.add_parser("show", help="Show active keys for one agent/task.")
    agent_state_show.add_argument("--agent", required=True)
    agent_state_show.add_argument("--task", required=True)
    agent_state_show.add_argument("--json", action="store_true")

    agent_state_delete = agent_state_subparsers.add_parser("delete", help="Delete one persisted state key.")
    agent_state_delete.add_argument("--agent", required=True)
    agent_state_delete.add_argument("--task", required=True)
    agent_state_delete.add_argument("--key", required=True)

    agent_state_verify = agent_state_subparsers.add_parser("verify", help="Verify a handoff state digest.")
    agent_state_verify.add_argument("--agent", required=True)
    agent_state_verify.add_argument("--task", required=True)
    agent_state_verify.add_argument("--digest", required=True)
    agent_state_verify.add_argument("--json", action="store_true")

    completion = subparsers.add_parser("__complete")
    completion.add_argument("current", nargs="?", default="")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code) if isinstance(exc.code, int) else 2
    no_color = bool(getattr(args, "no_color", False))

    if args.version:
        print(CLI_VERSION)
        return 0
    if args.install_completion:
        return install_completion(args.install_completion)
    if args.command == "__complete":
        return handle_completion(args.current)
    if not args.command:
        parser.print_help()
        return 0

    if args.command == "deploy":
        return run_plan(resolve_deploy_command(args.service, args.env), dry_run=args.dry_run, explain=args.explain, no_color=no_color)
    if args.command == "impact":
        return impact_command(args.service)
    if args.command == "lint":
        return run_plan(resolve_lint_command(args.local), dry_run=args.dry_run, explain=args.explain, no_color=no_color)
    if args.command == "validate":
        return run_plan(
            resolve_validate_command(args.strict, args.service),
            dry_run=args.dry_run,
            explain=args.explain,
            no_color=no_color,
        )
    if args.command == "search":
        return search_command(args.query, collection=args.collection, limit=args.limit, rebuild=args.rebuild)
    if args.command == "status":
        return status_command(args.service, args.env, timeout=args.timeout, no_color=no_color)
    if args.command == "vm":
        if args.vm_action == "list":
            return vm_list_command(args.env)
        plan = resolve_vm_command(args.vm_action, args.env, vm_name=getattr(args, "name", None), force=getattr(args, "force", False))
        return run_plan(plan, dry_run=getattr(args, "dry_run", False), explain=getattr(args, "explain", False), no_color=no_color)
    if args.command == "secret":
        if args.secret_action == "get":
            return run_plan(secret_get_command(args.path), dry_run=args.dry_run, explain=args.explain, no_color=no_color)
        return run_plan(secret_rotate_command(args.secret_id), dry_run=args.dry_run, explain=args.explain, no_color=no_color)
    if args.command == "fixture":
        return run_plan(
            fixture_command(
                args.fixture_action,
                getattr(args, "name", None),
                purpose=getattr(args, "purpose", None),
                owner=getattr(args, "owner", None),
                lifetime_hours=getattr(args, "lifetime_hours", None),
                policy=getattr(args, "policy", None),
                extend=getattr(args, "extend", False),
                vmid=getattr(args, "vmid", None),
                receipt_id=getattr(args, "receipt_id", None),
            ),
            dry_run=args.dry_run,
            explain=args.explain,
            no_color=no_color,
        )
    if args.command == "scaffold":
        return run_plan(scaffold_command(args.name), dry_run=args.dry_run, explain=args.explain, no_color=no_color)
    if args.command == "diff":
        return run_plan(resolve_diff_command(args.env), dry_run=args.dry_run, explain=args.explain, no_color=no_color)
    if args.command == "capacity":
        return run_plan(
            resolve_capacity_command(args.format, no_live_metrics=args.no_live_metrics),
            dry_run=args.dry_run,
            explain=args.explain,
            no_color=no_color,
        )
    if args.command == "promote":
        return run_plan(
            promote_command(args.branch, args.service, args.staging_receipt, args.dry_run),
            dry_run=args.dry_run,
            explain=args.explain,
            no_color=no_color,
        )
    if args.command == "run":
        instruction = " ".join(args.instruction)
        if should_run_direct_workflow(instruction):
            return run_windmill_workflow(
                instruction,
                args.args,
                dry_run=args.dry_run,
                explain=args.explain,
                no_color=no_color,
                approve_risk=args.approve_risk,
                risk_override=args.risk_override,
            )
        return run_compiled_instruction(
            instruction,
            args.args,
            dry_run=args.dry_run,
            explain=args.explain,
            no_color=no_color,
        )
    if args.command == "logs":
        return logs_command(args.service, tail=args.tail, since=args.since, dry_run=args.dry_run, explain=args.explain, no_color=no_color)
    if args.command == "ssh":
        return ssh_command(args.vm_name, dry_run=args.dry_run, explain=args.explain, no_color=no_color)
    if args.command == "open":
        return open_service_url(args.service, args.env, dry_run=args.dry_run, explain=args.explain, no_color=no_color)
    if args.command == "release":
        import release_manager

        forwarded_args: list[str] = []
        if args.release_action == "status":
            forwarded_args.append("status")
            if args.json:
                forwarded_args.append("--json")
            if args.timeout != 2.0:
                forwarded_args.extend(["--timeout", str(args.timeout)])
            return release_manager.main(forwarded_args)
        if args.release_action == "tag":
            forwarded_args.append("tag")
            if args.version:
                forwarded_args.extend(["--version", args.version])
            if args.push:
                forwarded_args.append("--push")
            if args.dry_run:
                forwarded_args.append("--dry-run")
            return release_manager.main(forwarded_args)
        if args.version:
            forwarded_args.extend(["--version", args.version])
        if args.bump:
            forwarded_args.extend(["--bump", args.bump])
        if args.platform_impact:
            forwarded_args.extend(["--platform-impact", args.platform_impact])
        if args.released_on:
            forwarded_args.extend(["--released-on", args.released_on])
        if args.dry_run:
            forwarded_args.append("--dry-run")
        return release_manager.main(forwarded_args)
    if args.command == "agent":
        if args.agent_action == "state":
            if args.agent_state_action == "show":
                return agent_state_show_command(args.agent, args.task, json_output=args.json)
            if args.agent_state_action == "delete":
                return agent_state_delete_command(args.agent, args.task, key=args.key)
            if args.agent_state_action == "verify":
                return agent_state_verify_command(args.agent, args.task, digest=args.digest, json_output=args.json)
    if args.command == "operator":
        if args.operator_action == "add":
            workflow_args = [
                f"name={args.name}",
                f"email={args.email}",
                f"role={args.role}",
                f"ssh_key={args.ssh_key}",
            ]
            if args.id:
                workflow_args.append(f"operator_id={args.id}")
            if args.keycloak_username:
                workflow_args.append(f"keycloak_username={args.keycloak_username}")
            if args.tailscale_login_email:
                workflow_args.append(f"tailscale_login_email={args.tailscale_login_email}")
            if args.tailscale_device_name:
                workflow_args.append(f"tailscale_device_name={args.tailscale_device_name}")
            return run_windmill_workflow(
                "operator-onboard",
                workflow_args,
                dry_run=args.dry_run,
                explain=args.explain,
                no_color=no_color,
            )
        if args.operator_action == "remove":
            workflow_args = [f"operator_id={args.id}"]
            if args.reason:
                workflow_args.append(f"reason={args.reason}")
            return run_windmill_workflow(
                "operator-offboard",
                workflow_args,
                dry_run=args.dry_run,
                explain=args.explain,
                no_color=no_color,
            )
        return run_plan(
            operator_inventory_command(args.id, offline=args.offline),
            dry_run=args.dry_run,
            explain=args.explain,
            no_color=no_color,
        )

    raise SystemExit(f"Unhandled command '{args.command}'.")


if __name__ == "__main__":
    sys.exit(main())
