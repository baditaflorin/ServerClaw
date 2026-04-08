"""
Deterministic Goal Compiler — main entry point (ADR 0112).

Pipeline
--------
1. Normalise:  collapse whitespace, lower-case, apply alias table from
               config/goal-compiler-aliases.yaml.
2. Match:      find the first matching rule in config/goal-compiler-rules.yaml.
3. Resolve:    map the captured service/workflow/vmid to catalog data via
               resolver.resolve_target and resolver.resolve_scope.
4. Score:      call the existing scripts/risk_scorer to compute a numeric risk
               score from the resolved intent.
5. Produce:    return a CompiledIntent dataclass that the caller can serialise
               to YAML for pre-execution review.

The compiler is CPU-only and deterministic for identical inputs and rule tables.
It does *not* execute mutations.

Usage
-----
    from scripts.goal_compiler import GoalCompiler, GoalCompilationError

    compiler = GoalCompiler(repo_root=Path("/path/to/repo"))
    intent = compiler.compile("deploy netbox")
    print(intent.as_yaml())
"""

from __future__ import annotations

import io
import json
import re
import sys
import uuid
from dataclasses import replace
from pathlib import Path
from typing import Any

import yaml

from .models import (
    CompiledIntent,
    IntentScope,
    IntentTarget,
    RISK_RANK,
    RiskClass,
    ScoringContext,
)
from .resolver import resolve_scope, resolve_target, resolve_workflow_id


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class GoalCompilationError(Exception):
    """Raised when an instruction cannot be compiled into a valid intent."""

    def __init__(self, code: str, message: str, raw_input: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.raw_input = raw_input
        self.details: dict[str, Any] = details or {}

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "raw_input": self.raw_input,
            "details": self.details,
        }

    def __repr__(self) -> str:  # noqa: D105
        return f"GoalCompilationError(code={self.code!r}, message={self.message!r})"


# ---------------------------------------------------------------------------
# Rule loading
# ---------------------------------------------------------------------------

_PLACEHOLDER_RE = re.compile(r"\{([a-z_][a-z0-9_]*)\}")


def _template_to_regex(template: str) -> str:
    """Convert a ``{placeholder}``-style template to a full-match regex."""
    cursor = 0
    parts: list[str] = ["^"]
    for m in _PLACEHOLDER_RE.finditer(template):
        literal = template[cursor : m.start()]
        parts.append(re.escape(literal))
        placeholder = m.group(1)
        parts.append(f"(?P<{placeholder}>[a-z0-9_./ -]+?)")
        cursor = m.end()
    parts.append(re.escape(template[cursor:]))
    parts.append("$")
    return "".join(parts)


class _RulePattern:
    __slots__ = ("kind", "value", "_compiled")

    def __init__(self, kind: str, value: str) -> None:
        self.kind = kind
        self.value = value
        self._compiled: re.Pattern[str] | None = None
        if kind in ("regex", "template"):
            regex = value if kind == "regex" else _template_to_regex(value)
            self._compiled = re.compile(regex)

    def match(self, text: str) -> dict[str, str] | None:
        if self.kind == "contains":
            return {} if self.value in text else None
        if self._compiled is not None:
            m = self._compiled.fullmatch(text)
            return m.groupdict() if m else None
        raise ValueError(f"Unsupported pattern kind '{self.kind}'")


class _GoalRule:
    __slots__ = (
        "rule_id",
        "patterns",
        "action",
        "target_kind",
        "default_risk_class",
        "allowed_tools",
        "rollback_path",
        "requires_approval_above",
        "ttl_seconds",
        "workflow_id",
        "workflow_candidates",
        "success_criteria",
        "preconditions",
        "scope_defaults",
    )

    def __init__(self, data: dict[str, Any]) -> None:
        self.rule_id: str = str(data["id"])
        self.patterns: list[_RulePattern] = [
            _RulePattern(kind=str(p["type"]), value=str(p["value"]))
            for p in data.get("patterns", [])
        ]
        self.action: str = str(data["action"])
        self.target_kind: str = str(data.get("target_kind", "service"))
        self.default_risk_class: RiskClass = RiskClass(str(data["default_risk_class"]))
        self.allowed_tools: list[str] = [str(t) for t in data.get("allowed_tools", [])]
        self.rollback_path: str | None = data.get("rollback_path")
        self.requires_approval_above: RiskClass = RiskClass(
            str(data.get("requires_approval_above", "LOW"))
        )
        self.ttl_seconds: int = int(data.get("ttl_seconds", 300))
        self.workflow_id: str | None = data.get("workflow_id")
        self.workflow_candidates: list[str] = [str(v) for v in data.get("workflow_candidates", [])]
        self.success_criteria: list[str] = [str(v) for v in data.get("success_criteria", [])]
        self.preconditions: list[str] = [str(v) for v in data.get("preconditions", [])]
        self.scope_defaults: dict[str, list[Any]] = {
            "allowed_hosts": list(data.get("scope_defaults", {}).get("allowed_hosts", [])),
            "allowed_services": list(data.get("scope_defaults", {}).get("allowed_services", [])),
            "allowed_vmids": list(data.get("scope_defaults", {}).get("allowed_vmids", [])),
        }

    def match(self, text: str) -> dict[str, str] | None:
        for pattern in self.patterns:
            captures = pattern.match(text)
            if captures is not None:
                return captures
        return None


def _load_rules(path: Path) -> list[_GoalRule]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return [_GoalRule(item) for item in payload.get("rules", []) if isinstance(item, dict)]


def _load_aliases(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {
        "phrase_aliases": dict(payload.get("phrase_aliases") or {}),
        "service_aliases": dict(payload.get("service_aliases") or {}),
        "groups": {
            str(name): data
            for name, data in (payload.get("groups") or {}).items()
            if isinstance(data, dict)
        },
    }


def _match_rule(
    text: str, rules: list[_GoalRule]
) -> tuple[_GoalRule, dict[str, str]] | None:
    for rule in rules:
        captures = rule.match(text)
        if captures is not None:
            return rule, captures
    return None


# ---------------------------------------------------------------------------
# Risk scorer integration
# ---------------------------------------------------------------------------

_COMPILER_VERSION = "goal-compiler/scripts/0.1.0"

_TIER_FROM_IMPACT = {
    "host_live": "critical",
    "host_and_guest_live": "critical",
    "external_live": "high",
    "guest_live": "medium",
    "repo_only": "low",
}


def _build_scoring_context(
    workflow_id: str | None,
    target: IntentTarget,
    service_catalog: dict[str, dict[str, Any]],
    workflow_catalog: dict[str, dict[str, Any]],
    *,
    stale_reasons: list[str],
) -> ScoringContext:
    """
    Build a ScoringContext for the risk_scorer from catalog data alone.

    This is the compile-time equivalent of risk_scorer.context.assemble_context.
    It does not touch the filesystem for receipts or the graph DSN — it uses
    catalog-declared defaults.  This keeps the compiler CPU-only.
    """
    target_service_id: str | None = target.services[0] if target.services else None

    # Infer target tier from service catalog or workflow live_impact
    target_tier = "medium"
    if target_service_id and target_service_id in service_catalog:
        catalog_entry = service_catalog[target_service_id]
        category = str(catalog_entry.get("category", "")).strip().lower()
        exposure = str(catalog_entry.get("exposure", "")).strip().lower()
        if target_service_id in {"proxmox_ui", "openbao", "step_ca"}:
            target_tier = "critical"
        elif category in {"security", "infrastructure"}:
            target_tier = "high"
        elif exposure in {"edge-published", "edge-static"}:
            target_tier = "high"
        else:
            target_tier = "medium"
    elif workflow_id and workflow_id in workflow_catalog:
        live_impact = str(workflow_catalog[workflow_id].get("live_impact", "guest_live"))
        target_tier = _TIER_FROM_IMPACT.get(live_impact, "medium")
        stale_reasons.append("criticality tier inferred from workflow live_impact at compile time")
    else:
        stale_reasons.append("criticality tier defaulted to medium (no catalog entry)")

    # Downstream count: catalog does not carry this at compile time
    downstream_count = 0
    stale_reasons.append("downstream count defaulted to 0 at compile time")

    # Expected change count from workflow defaults
    expected_change_count = 5
    irreversible_count = 0
    unknown_count = 0
    rollback_verified = False
    if workflow_id and workflow_id in workflow_catalog:
        wf = workflow_catalog[workflow_id]
        expected_change_count = int(wf.get("expected_change_count", 5))
        irreversible_count = int(wf.get("irreversible_count", 0))
        unknown_count = int(wf.get("unknown_count", 0))
        rollback_verified = bool(wf.get("rollback_verified", False))

    return ScoringContext(
        workflow_id=workflow_id or "",
        target_service_id=target_service_id,
        target_tier=target_tier,
        downstream_count=downstream_count,
        recent_failure_rate=0.0,
        expected_change_count=expected_change_count,
        irreversible_count=irreversible_count,
        unknown_count=unknown_count,
        rollback_verified=rollback_verified,
        in_maintenance_window=False,
        active_incident=False,
        hours_since_last_mutation=72.0,
        stale=bool(stale_reasons),
        stale_reasons=tuple(stale_reasons),
    )


def _load_dimensions_module() -> Any:
    """
    Load scripts/risk_scorer/dimensions.py directly via importlib.

    We cannot ``import scripts.risk_scorer.dimensions`` through the normal
    import path because ``scripts/risk_scorer/__init__.py`` re-exports
    ``context.py`` which does a top-level import of ``maintenance_window_tool``.
    That module loads platform dependencies (platform.datetime_compat, etc.) at
    import time, which fails in lightweight test environments.

    By loading ``dimensions.py`` directly we only pull in pure math functions
    with no external dependencies.
    """
    import importlib.util

    dimensions_path = Path(__file__).resolve().parents[1] / "risk_scorer" / "dimensions.py"
    if not dimensions_path.exists():
        return None
    spec = importlib.util.spec_from_file_location("_goal_compiler_risk_dimensions", dimensions_path)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
    except Exception:
        return None
    return mod


def _run_risk_scorer(
    workflow_id: str | None,
    target: IntentTarget,
    rule_risk_class: RiskClass,
    scoring_ctx: ScoringContext,
    repo_root: Path,
) -> tuple[float, dict[str, float]]:
    """
    Compute a numeric risk score using the dimension functions from
    scripts/risk_scorer/dimensions.py.

    Returns (score, dimension_breakdown).  Falls back to (50.0, {}) if the
    scorer is not importable (e.g. during unit tests without full dependencies).

    The dimensions module is loaded via ``importlib.util.spec_from_file_location``
    to avoid triggering the transitive top-level imports in
    ``scripts/risk_scorer/__init__.py`` → ``context.py`` → ``maintenance_window_tool``.
    """
    dims = _load_dimensions_module()
    if dims is None:
        return 50.0, {}

    try:
        criticality_score = dims.criticality_score
        failure_rate_score = dims.failure_rate_score
        fanout_score = dims.fanout_score
        maintenance_score = dims.maintenance_score
        recency_score = dims.recency_score
        rollback_score = dims.rollback_score
        surface_score = dims.surface_score
    except AttributeError:
        return 50.0, {}

    breakdown = {
        "target_criticality": criticality_score(scoring_ctx.target_tier),
        "dependency_fanout": fanout_score(scoring_ctx.downstream_count),
        "historical_failure": failure_rate_score(scoring_ctx.recent_failure_rate),
        "mutation_surface": surface_score(
            scoring_ctx.expected_change_count,
            irreversible_count=scoring_ctx.irreversible_count,
            unknown_count=scoring_ctx.unknown_count,
        ),
        "rollback_confidence": rollback_score(scoring_ctx.rollback_verified),
        "maintenance_window": maintenance_score(scoring_ctx.in_maintenance_window),
        "active_incident": 20.0 if scoring_ctx.active_incident else 0.0,
        "recency": recency_score(scoring_ctx.hours_since_last_mutation),
    }
    if scoring_ctx.stale:
        breakdown["stale_context_penalty"] = 10.0

    raw = sum(breakdown.values())
    score = max(0.0, min(100.0, raw))
    return score, breakdown


# ---------------------------------------------------------------------------
# Main GoalCompiler class
# ---------------------------------------------------------------------------


class GoalCompiler:
    """
    Deterministic goal compiler (ADR 0112).

    Transforms a natural-language operator instruction into a typed
    ``CompiledIntent`` in three CPU-only stages:
      1. Normalise
      2. Match against the rule table
      3. Resolve target + scope + risk score
    """

    COMPILER_VERSION = _COMPILER_VERSION

    def __init__(
        self,
        repo_root: Path | str,
        *,
        stderr: Any = None,
    ) -> None:
        self.repo_root = Path(repo_root)
        self.stderr = stderr or sys.stderr
        _default_root = Path(__file__).resolve().parents[2]

        rules_path = self.repo_root / "config" / "goal-compiler-rules.yaml"
        aliases_path = self.repo_root / "config" / "goal-compiler-aliases.yaml"

        # Fall back to the repo's own config files if the provided root doesn't have them
        if not rules_path.exists():
            rules_path = _default_root / "config" / "goal-compiler-rules.yaml"
        if not aliases_path.exists():
            aliases_path = _default_root / "config" / "goal-compiler-aliases.yaml"

        self._rules = _load_rules(rules_path)
        self._aliases = _load_aliases(aliases_path)
        self._service_catalog: dict[str, dict[str, Any]] | None = None
        self._workflow_catalog: dict[str, dict[str, Any]] | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def compile(
        self,
        raw_input: str,
        *,
        dispatch_args: dict[str, Any] | None = None,
        actor_id: str | None = None,
    ) -> CompiledIntent:
        """
        Compile *raw_input* into a ``CompiledIntent``.

        Parameters
        ----------
        raw_input:
            The natural-language instruction (e.g. ``"deploy netbox"``).
        dispatch_args:
            Optional additional key-value pairs merged into the dispatch payload.
        actor_id:
            Optional actor identifier for logging.  Not used for policy enforcement
            in this layer (that lives in platform/goal_compiler).
        """
        normalized = self.normalize(raw_input)

        # --- direct workflow-id shortcut ---
        direct = self._try_direct_workflow(normalized, raw_input=raw_input, dispatch_args=dispatch_args or {})
        if direct is not None:
            return direct

        matched = _match_rule(normalized, self._rules)
        if matched is None:
            raise GoalCompilationError(
                code="PARSE_ERROR",
                message=f"Unrecognised instruction '{raw_input.strip()}'",
                raw_input=raw_input,
                details={"normalized_input": normalized},
            )

        rule, captures = matched
        captures = {k: v.strip() for k, v in captures.items() if v is not None}

        target = resolve_target(
            target_kind=rule.target_kind,
            captures=captures,
            alias_groups=self._aliases["groups"],
            service_aliases=self._aliases["service_aliases"],
            repo_root=self.repo_root,
        )
        scope = resolve_scope(rule.scope_defaults, target)
        workflow_id = resolve_workflow_id(
            rule_workflow_id=rule.workflow_id,
            rule_workflow_candidates=rule.workflow_candidates,
            captures=captures,
            target=target,
            alias_groups=self._aliases["groups"],
        )
        dispatch_payload = self._build_payload(rule, captures, target, dispatch_args or {})

        preconditions = self._render_list(rule.preconditions, captures, target, workflow_id)
        preconditions.extend(self._maintenance_preconditions(target))
        preconditions.append("no active incident is declared for the target scope")

        success_criteria = self._render_list(rule.success_criteria, captures, target, workflow_id)
        rollback_path = self._render(rule.rollback_path, captures, target, workflow_id)

        risk_class = rule.default_risk_class
        requires_approval = RISK_RANK[risk_class] > RISK_RANK[rule.requires_approval_above]

        # --- risk scoring ---
        stale_reasons: list[str] = []
        scoring_ctx = _build_scoring_context(
            workflow_id=workflow_id,
            target=target,
            service_catalog=self._load_service_catalog(),
            workflow_catalog=self._load_workflow_catalog(),
            stale_reasons=stale_reasons,
        )
        risk_score, risk_breakdown = _run_risk_scorer(
            workflow_id=workflow_id,
            target=target,
            rule_risk_class=risk_class,
            scoring_ctx=scoring_ctx,
            repo_root=self.repo_root,
        )

        return CompiledIntent(
            id=str(uuid.uuid4()),
            created_at=self._utc_now(),
            raw_input=raw_input.strip(),
            action=rule.action,
            target=target,
            scope=scope,
            preconditions=preconditions,
            risk_class=risk_class,
            allowed_tools=rule.allowed_tools,
            rollback_path=rollback_path,
            success_criteria=success_criteria,
            ttl_seconds=rule.ttl_seconds,
            requires_approval=requires_approval,
            compiled_by=self.COMPILER_VERSION,
            workflow_id=workflow_id,
            dispatch_payload=dispatch_payload,
            risk_score=risk_score,
            risk_score_breakdown=risk_breakdown,
            scoring_context=scoring_ctx.as_dict(),
            matched_rule_id=rule.rule_id,
            normalized_input=normalized,
        )

    def normalize(self, raw_input: str) -> str:
        """Apply whitespace collapse and alias substitutions."""
        normalized = " ".join(raw_input.strip().lower().split())
        for source, target in sorted(
            self._aliases["phrase_aliases"].items(), key=lambda t: len(t[0]), reverse=True
        ):
            normalized = re.sub(rf"\b{re.escape(source)}\b", str(target), normalized)
        for source, target in sorted(
            self._aliases["service_aliases"].items(), key=lambda t: len(t[0]), reverse=True
        ):
            normalized = re.sub(rf"\b{re.escape(source)}\b", str(target), normalized)
        return normalized

    def as_yaml(self, intent: CompiledIntent) -> str:
        """Serialise a CompiledIntent to a human-readable YAML string."""
        return yaml.dump(intent.as_dict(), sort_keys=False, allow_unicode=True)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _try_direct_workflow(
        self,
        normalized: str,
        *,
        raw_input: str,
        dispatch_args: dict[str, Any],
    ) -> CompiledIntent | None:
        """Return a CompiledIntent if *normalized* is a verbatim workflow ID."""
        workflows = self._load_workflow_catalog()
        if normalized not in workflows:
            return None

        wf = workflows[normalized]
        live_impact = str(wf.get("live_impact", "guest_live"))
        risk_class = {
            "repo_only": RiskClass.LOW,
            "guest_live": RiskClass.MEDIUM,
            "external_live": RiskClass.MEDIUM,
            "host_live": RiskClass.HIGH,
            "host_and_guest_live": RiskClass.HIGH,
        }.get(live_impact, RiskClass.MEDIUM)
        requires_approval = RISK_RANK[risk_class] >= RISK_RANK[RiskClass.HIGH]

        target = IntentTarget(kind="workflow", name=normalized)
        scope = IntentScope()
        stale_reasons: list[str] = []
        scoring_ctx = _build_scoring_context(
            workflow_id=normalized,
            target=target,
            service_catalog=self._load_service_catalog(),
            workflow_catalog=workflows,
            stale_reasons=stale_reasons,
        )
        risk_score, risk_breakdown = _run_risk_scorer(
            workflow_id=normalized,
            target=target,
            rule_risk_class=risk_class,
            scoring_ctx=scoring_ctx,
            repo_root=self.repo_root,
        )

        return CompiledIntent(
            id=str(uuid.uuid4()),
            created_at=self._utc_now(),
            raw_input=raw_input.strip(),
            action="execute",
            target=target,
            scope=scope,
            preconditions=["workflow route resolves in Windmill"],
            risk_class=risk_class,
            allowed_tools=["windmill-trigger"],
            rollback_path=None,
            success_criteria=[f"workflow {normalized} returns success"],
            ttl_seconds=300,
            requires_approval=requires_approval,
            compiled_by=self.COMPILER_VERSION,
            workflow_id=normalized,
            dispatch_payload=dispatch_args,
            risk_score=risk_score,
            risk_score_breakdown=risk_breakdown,
            scoring_context=scoring_ctx.as_dict(),
            matched_rule_id="direct-workflow-id",
            normalized_input=normalized,
        )

    def _maintenance_preconditions(self, target: IntentTarget) -> list[str]:
        """Return maintenance-window preconditions (best-effort, never raises)."""
        try:
            from maintenance_window_tool import list_active_windows_best_effort  # type: ignore[import]
            windows = list_active_windows_best_effort()
        except Exception:
            windows = {}

        if not target.services:
            return ["maintenance window check completed"]

        active = [
            svc
            for svc in target.services
            if f"maintenance/{svc}" in windows or "maintenance/all" in windows
        ]
        if active:
            return [f"maintenance window already active for {', '.join(active)}"]
        return ["no active maintenance window blocks this scope"]

    def _build_payload(
        self,
        rule: _GoalRule,
        captures: dict[str, str],
        target: IntentTarget,
        extra: dict[str, Any],
    ) -> dict[str, Any]:
        payload = dict(extra)
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
        return [
            rendered
            for value in values
            if (rendered := self._render(value, captures, target, workflow_id))
        ]

    def _render(
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
            return value.format_map(mapping) or None
        except (KeyError, ValueError):
            return value or None

    def _load_service_catalog(self) -> dict[str, dict[str, Any]]:
        if self._service_catalog is None:
            path = self.repo_root / "config" / "service-capability-catalog.json"
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                services = payload.get("services", [])
                self._service_catalog = {
                    item["id"]: item
                    for item in services
                    if isinstance(item, dict) and isinstance(item.get("id"), str)
                }
            except (OSError, json.JSONDecodeError):
                self._service_catalog = {}
        return self._service_catalog

    def _load_workflow_catalog(self) -> dict[str, dict[str, Any]]:
        if self._workflow_catalog is None:
            path = self.repo_root / "config" / "workflow-catalog.json"
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                workflows = payload.get("workflows", {})
                self._workflow_catalog = workflows if isinstance(workflows, dict) else {}
            except (OSError, json.JSONDecodeError):
                self._workflow_catalog = {}
        return self._workflow_catalog

    @staticmethod
    def _utc_now() -> str:
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
