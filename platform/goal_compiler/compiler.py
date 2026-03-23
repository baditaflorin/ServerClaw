from __future__ import annotations

import io
import importlib.util
import json
import re
import sys
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from maintenance_window_tool import list_active_windows_best_effort

from .rules import AliasConfig, GoalRule, GroupAlias, load_alias_config, load_goal_rules, match_rule
from .schema import ExecutionIntent, IntentScope, IntentTarget, RiskClass, RiskScore


REPO_PACKAGE_LOADER_PATH = Path(__file__).resolve().parents[2] / "scripts" / "repo_package_loader.py"
_LOADER_SPEC = importlib.util.spec_from_file_location("lv3_goal_compiler_repo_package_loader", REPO_PACKAGE_LOADER_PATH)
if _LOADER_SPEC is None or _LOADER_SPEC.loader is None:
    raise ImportError(f"Unable to load repo package loader from {REPO_PACKAGE_LOADER_PATH}")
_LOADER_MODULE = importlib.util.module_from_spec(_LOADER_SPEC)
_LOADER_SPEC.loader.exec_module(_LOADER_MODULE)
_WORLD_STATE_MODULE = _LOADER_MODULE.load_repo_package(
    "lv3_goal_compiler_world_state",
    Path(__file__).resolve().parents[1] / "world_state",
)
WorldStateClient = _WORLD_STATE_MODULE.WorldStateClient
WorldStateUnavailable = _WORLD_STATE_MODULE.WorldStateUnavailable


COMPILER_VERSION = "goal-compiler/0.1.0"
RISK_RANK = {
    RiskClass.LOW: 1,
    RiskClass.MEDIUM: 2,
    RiskClass.HIGH: 3,
    RiskClass.CRITICAL: 4,
}
RISK_SCORE = {
    RiskClass.LOW: 20,
    RiskClass.MEDIUM: 50,
    RiskClass.HIGH: 75,
    RiskClass.CRITICAL: 95,
}


@dataclass(frozen=True)
class CompilationResult:
    intent: ExecutionIntent
    matched_rule_id: str
    normalized_input: str
    dispatch_workflow_id: str | None
    dispatch_payload: dict[str, Any]


@dataclass(frozen=True)
class GoalCompilationError(Exception):
    code: str
    message: str
    raw_input: str
    details: dict[str, Any]

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


class GoalCompiler:
    def __init__(self, repo_root: Path | str, *, stderr: Any = sys.stderr) -> None:
        self.repo_root = Path(repo_root)
        self.stderr = stderr
        default_repo_root = Path(__file__).resolve().parents[2]
        rules_path = self.repo_root / "config" / "goal-compiler-rules.yaml"
        aliases_path = self.repo_root / "config" / "goal-compiler-aliases.yaml"
        if not rules_path.exists():
            rules_path = default_repo_root / "config" / "goal-compiler-rules.yaml"
        if not aliases_path.exists():
            aliases_path = default_repo_root / "config" / "goal-compiler-aliases.yaml"
        self.rules = load_goal_rules(rules_path)
        self.aliases = load_alias_config(aliases_path)
        self.world_state = WorldStateClient(self.repo_root)

    def compile(self, raw_input: str, *, dispatch_args: dict[str, Any] | None = None) -> CompilationResult:
        normalized = self.normalize(raw_input)
        direct_workflow = self._match_direct_workflow(normalized, dispatch_args=dispatch_args)
        if direct_workflow is not None:
            return direct_workflow

        matched = match_rule(normalized, self.rules)
        if matched is None:
            raise GoalCompilationError(
                code="PARSE_ERROR",
                message=f"Unrecognised instruction '{raw_input.strip()}'",
                raw_input=raw_input,
                details={"normalized_input": normalized},
            )
        rule, captures = matched
        captures = {key: value.strip() for key, value in captures.items() if value is not None}
        target = self._resolve_target(rule, captures)
        scope = self._bind_scope(rule, target)
        workflow_id = self._resolve_workflow_id(rule, captures, target)
        workflow_payload = self._build_dispatch_payload(rule, captures, target, dispatch_args or {})
        success_criteria = self._render_list(rule.success_criteria, captures, target, workflow_id)
        preconditions = self._inject_preconditions(rule, captures, target)
        risk_class = rule.default_risk_class
        requires_approval = RISK_RANK[risk_class] > RISK_RANK[rule.requires_approval_above]

        intent = ExecutionIntent(
            id=str(uuid.uuid4()),
            created_at=self._utc_now(),
            raw_input=raw_input.strip(),
            action=rule.action,
            target=target,
            scope=scope,
            preconditions=preconditions,
            risk_class=risk_class,
            allowed_tools=rule.allowed_tools,
            rollback_path=self._render_template(rule.rollback_path, captures, target, workflow_id),
            success_criteria=success_criteria,
            ttl_seconds=rule.ttl_seconds,
            requires_approval=requires_approval,
            compiled_by=COMPILER_VERSION,
            risk_score=RiskScore(
                source="rule_table",
                value=RISK_SCORE[risk_class],
                reasons=[f"matched rule {rule.rule_id}"],
            ),
        )
        return CompilationResult(
            intent=intent,
            matched_rule_id=rule.rule_id,
            normalized_input=normalized,
            dispatch_workflow_id=workflow_id,
            dispatch_payload=workflow_payload,
        )

    def normalize(self, raw_input: str) -> str:
        normalized = " ".join(raw_input.strip().lower().split())
        for source, target in sorted(self.aliases.phrase_aliases.items(), key=lambda item: len(item[0]), reverse=True):
            normalized = re.sub(rf"\b{re.escape(source)}\b", target, normalized)
        for source, target in sorted(self.aliases.service_aliases.items(), key=lambda item: len(item[0]), reverse=True):
            normalized = re.sub(rf"\b{re.escape(source)}\b", target, normalized)
        return normalized

    def _match_direct_workflow(
        self,
        normalized: str,
        *,
        dispatch_args: dict[str, Any] | None,
    ) -> CompilationResult | None:
        workflows = self._load_workflow_catalog()
        if normalized not in workflows and "/" not in normalized:
            return None
        workflow_id = normalized
        risk_class = self._risk_for_live_impact(workflows.get(workflow_id, {}).get("live_impact"))
        intent = ExecutionIntent(
            id=str(uuid.uuid4()),
            created_at=self._utc_now(),
            raw_input=normalized,
            action="execute",
            target=IntentTarget(kind="workflow", name=workflow_id),
            scope=IntentScope(),
            preconditions=["workflow route resolves in Windmill"],
            risk_class=risk_class,
            allowed_tools=["windmill-trigger"],
            rollback_path=None,
            success_criteria=[f"workflow {workflow_id} returns success"],
            ttl_seconds=300,
            requires_approval=RISK_RANK[risk_class] >= RISK_RANK[RiskClass.HIGH],
            compiled_by=COMPILER_VERSION,
            risk_score=RiskScore(source="workflow_catalog", value=RISK_SCORE[risk_class], reasons=["direct workflow invocation"]),
        )
        return CompilationResult(
            intent=intent,
            matched_rule_id="direct-workflow-id",
            normalized_input=normalized,
            dispatch_workflow_id=workflow_id,
            dispatch_payload=dispatch_args or {},
        )

    def _resolve_target(self, rule: GoalRule, captures: dict[str, str]) -> IntentTarget:
        if rule.target_kind == "workflow":
            workflow = captures.get("workflow", "")
            return IntentTarget(kind="workflow", name=workflow)

        service_name = captures.get("service") or captures.get("target")
        if service_name:
            group = self.aliases.groups.get(service_name)
            if group is not None:
                return IntentTarget(
                    kind="service_group",
                    name=service_name,
                    services=list(group.services),
                    hosts=list(group.hosts),
                )
            service_id = self.aliases.service_aliases.get(service_name, service_name)
            host = self._load_service_map().get(service_id, {}).get("vm")
            return IntentTarget(
                kind="service",
                name=service_id,
                services=[service_id],
                hosts=[host] if isinstance(host, str) and host else [],
            )

        vmid = captures.get("vmid")
        if vmid:
            return IntentTarget(kind="vmid", name=vmid, vmids=[int(vmid)])

        name = captures.get("name", rule.target_kind)
        return IntentTarget(kind=rule.target_kind, name=name)

    def _bind_scope(self, rule: GoalRule, target: IntentTarget) -> IntentScope:
        allowed_hosts = list(dict.fromkeys(rule.scope_defaults.get("allowed_hosts", []) + target.hosts))
        allowed_services = list(dict.fromkeys(rule.scope_defaults.get("allowed_services", []) + target.services))
        allowed_vmids = list(dict.fromkeys(rule.scope_defaults.get("allowed_vmids", []) + target.vmids))

        try:
            world_state = self.world_state.get("proxmox_vms", allow_stale=True)
        except WorldStateUnavailable:
            world_state = None

        if world_state is not None:
            vm_items = world_state.get("items") if isinstance(world_state, dict) else world_state
            if isinstance(vm_items, list):
                for item in vm_items:
                    if not isinstance(item, dict):
                        continue
                    service_id = str(item.get("service_id", "")).strip()
                    vm_name = str(item.get("name", "")).strip()
                    if service_id and service_id in target.services:
                        if vm_name and vm_name not in allowed_hosts:
                            allowed_hosts.append(vm_name)
                        if isinstance(item.get("vmid"), int) and item["vmid"] not in allowed_vmids:
                            allowed_vmids.append(item["vmid"])
                    if target.kind == "vmid" and isinstance(item.get("vmid"), int) and item["vmid"] in target.vmids:
                        if vm_name and vm_name not in allowed_hosts:
                            allowed_hosts.append(vm_name)

        return IntentScope(
            allowed_hosts=allowed_hosts,
            allowed_services=allowed_services,
            allowed_vmids=allowed_vmids,
        )

    def _inject_preconditions(self, rule: GoalRule, captures: dict[str, str], target: IntentTarget) -> list[str]:
        preconditions = self._render_list(rule.preconditions, captures, target, None)
        active_windows = list_active_windows_best_effort(stderr=io.StringIO())
        if target.services:
            active = []
            for service_id in target.services:
                if f"maintenance/{service_id}" in active_windows or "maintenance/all" in active_windows:
                    active.append(service_id)
            if active:
                preconditions.append(f"maintenance window already active for {', '.join(active)}")
            else:
                preconditions.append("no active maintenance window blocks this scope")
        else:
            preconditions.append("maintenance window check completed")
        preconditions.append("no active incident is declared for the target scope")
        return preconditions

    def _resolve_workflow_id(self, rule: GoalRule, captures: dict[str, str], target: IntentTarget) -> str | None:
        group = self.aliases.groups.get(target.name)
        if group is not None and group.workflow_id:
            return group.workflow_id
        if rule.workflow_id:
            return self._render_template(rule.workflow_id, captures, target, None)
        for candidate in rule.workflow_candidates:
            rendered = self._render_template(candidate, captures, target, None)
            if rendered:
                return rendered
        return None

    def _build_dispatch_payload(
        self,
        rule: GoalRule,
        captures: dict[str, str],
        target: IntentTarget,
        dispatch_args: dict[str, Any],
    ) -> dict[str, Any]:
        payload = dict(dispatch_args)
        if target.services and "service" not in payload:
            payload["service"] = target.services[0]
        if len(target.services) > 1 and "services" not in payload:
            payload["services"] = ",".join(target.services)
        if target.vmids and "vmid" not in payload:
            payload["vmid"] = str(target.vmids[0])
        if target.name and "target" not in payload and rule.target_kind != "workflow":
            payload["target"] = target.name
        return payload

    def _render_list(
        self,
        values: list[str],
        captures: dict[str, str],
        target: IntentTarget,
        workflow_id: str | None,
    ) -> list[str]:
        rendered = []
        for value in values:
            item = self._render_template(value, captures, target, workflow_id)
            if item:
                rendered.append(item)
        return rendered

    def _render_template(
        self,
        value: str | None,
        captures: dict[str, str],
        target: IntentTarget,
        workflow_id: str | None,
    ) -> str | None:
        if value is None:
            return None
        mapping = {
            **captures,
            "service": target.services[0] if target.services else target.name,
            "target": target.name,
            "workflow_id": workflow_id or "",
        }
        try:
            return value.format_map(mapping)
        except (KeyError, ValueError):
            return value

    def _load_service_map(self) -> dict[str, dict[str, Any]]:
        payload = json.loads((self.repo_root / "config" / "service-capability-catalog.json").read_text(encoding="utf-8"))
        return {service["id"]: service for service in payload.get("services", []) if isinstance(service, dict) and service.get("id")}

    def _load_workflow_catalog(self) -> dict[str, dict[str, Any]]:
        payload = json.loads((self.repo_root / "config" / "workflow-catalog.json").read_text(encoding="utf-8"))
        workflows = payload.get("workflows")
        if not isinstance(workflows, dict):
            return {}
        return workflows

    def _risk_for_live_impact(self, live_impact: Any) -> RiskClass:
        mapping = {
            "repo_only": RiskClass.LOW,
            "guest_live": RiskClass.MEDIUM,
            "external_live": RiskClass.MEDIUM,
            "host_live": RiskClass.HIGH,
            "host_and_guest_live": RiskClass.HIGH,
        }
        return mapping.get(str(live_impact), RiskClass.MEDIUM)

    def _utc_now(self) -> str:
        return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
