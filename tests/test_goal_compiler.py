"""
Tests for scripts/goal_compiler — Deterministic Goal Compiler (ADR 0112).

These tests cover:
  - Normalisation (alias substitution, whitespace collapse)
  - Rule matching (template, contains patterns)
  - Alias group expansion
  - Target and scope resolution from the service catalog
  - Direct workflow-id shortcut
  - PARSE_ERROR when no rule matches
  - Risk score integration (basic numeric range checks)
  - YAML serialisation of CompiledIntent
  - Resolver helpers (resolve_target, resolve_scope, resolve_workflow_id) in isolation
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

from scripts.goal_compiler import (
    CompiledIntent,
    GoalCompilationError,
    GoalCompiler,
    IntentScope,
    IntentTarget,
    RiskClass,
    ScoringContext,
    resolve_scope,
    resolve_target,
    resolve_workflow_id,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


@pytest.fixture()
def compiler_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Minimal repo layout sufficient for the goal compiler."""
    # Suppress LV3_HEALTH_DSN etc. so platform helpers don't try to connect
    for key in ("LV3_HEALTH_DSN", "WORLD_STATE_DSN", "LV3_GRAPH_DSN", "LV3_LEDGER_DSN"):
        monkeypatch.delenv(key, raising=False)

    # Maintenance windows file (avoids real filesystem probe)
    mw_path = tmp_path / ".local" / "state" / "maintenance-windows.json"
    mw_path.parent.mkdir(parents=True, exist_ok=True)
    mw_path.write_text("{}\n", encoding="utf-8")
    monkeypatch.setenv("LV3_MAINTENANCE_WINDOWS_FILE", str(mw_path))

    _write(
        tmp_path / "config" / "service-capability-catalog.json",
        json.dumps(
            {
                "services": [
                    {
                        "id": "netbox",
                        "name": "NetBox",
                        "vm": "netbox-lv3",
                        "category": "observability",
                        "exposure": "private-only",
                        "lifecycle_status": "active",
                    },
                    {
                        "id": "grafana",
                        "name": "Grafana",
                        "vm": "monitoring-lv3",
                        "category": "observability",
                        "lifecycle_status": "active",
                    },
                    {
                        "id": "loki",
                        "name": "Loki",
                        "vm": "monitoring-lv3",
                        "category": "observability",
                        "lifecycle_status": "active",
                    },
                    {
                        "id": "prometheus",
                        "name": "Prometheus",
                        "vm": "monitoring-lv3",
                        "category": "observability",
                        "lifecycle_status": "active",
                    },
                    {
                        "id": "openbao",
                        "name": "OpenBao",
                        "vm": "docker-runtime-lv3",
                        "category": "security",
                        "lifecycle_status": "active",
                    },
                ]
            },
            indent=2,
        )
        + "\n",
    )
    _write(
        tmp_path / "config" / "workflow-catalog.json",
        json.dumps(
            {
                "workflows": {
                    "validate": {
                        "description": "Validate repository",
                        "live_impact": "repo_only",
                        "execution_class": "diagnostic",
                    },
                    "converge-netbox": {
                        "description": "Converge NetBox",
                        "live_impact": "guest_live",
                        "execution_class": "mutation",
                    },
                    "converge-grafana": {
                        "description": "Converge Grafana",
                        "live_impact": "guest_live",
                        "execution_class": "mutation",
                    },
                    "converge-monitoring": {
                        "description": "Converge monitoring stack",
                        "live_impact": "guest_live",
                        "execution_class": "mutation",
                    },
                    "configure-network": {
                        "description": "Configure host networking",
                        "live_impact": "host_live",
                        "execution_class": "mutation",
                    },
                    "rotate-secret": {
                        "description": "Rotate a managed secret",
                        "live_impact": "guest_live",
                        "execution_class": "mutation",
                        "rollback_verified": True,
                    },
                }
            },
            indent=2,
        )
        + "\n",
    )
    _write(
        tmp_path / "config" / "goal-compiler-rules.yaml",
        # Minimal rule table covering the patterns used in tests
        """
schema_version: 1.0.0
rules:
  - id: run-workflow
    patterns:
      - type: template
        value: run {workflow}
    action: execute
    target_kind: workflow
    default_risk_class: MEDIUM
    allowed_tools:
      - windmill-trigger
    rollback_path: null
    requires_approval_above: MEDIUM
    ttl_seconds: 300
    workflow_id: "{workflow}"
    workflow_candidates: []
    success_criteria:
      - workflow {workflow_id} returns success
    preconditions:
      - workflow {workflow} is defined and reachable
    scope_defaults:
      allowed_hosts: []
      allowed_services: []
      allowed_vmids: []

  - id: deploy-service
    patterns:
      - type: template
        value: deploy {service}
    action: deploy
    target_kind: service
    default_risk_class: MEDIUM
    allowed_tools:
      - windmill-trigger
      - ansible-playbook
    rollback_path: rollback-{service}
    requires_approval_above: LOW
    ttl_seconds: 300
    workflow_id: null
    workflow_candidates:
      - converge-{service}
      - deploy-{service}
    success_criteria:
      - workflow {workflow_id} returns success
      - service {service} reports healthy
    preconditions:
      - target service {service} is cataloged
    scope_defaults:
      allowed_hosts: []
      allowed_services: []
      allowed_vmids: []

  - id: converge-service
    patterns:
      - type: template
        value: converge {service}
      - type: template
        value: apply {service}
    action: converge
    target_kind: service
    default_risk_class: MEDIUM
    allowed_tools:
      - windmill-trigger
      - ansible-playbook
    rollback_path: rollback-{service}
    requires_approval_above: LOW
    ttl_seconds: 300
    workflow_id: null
    workflow_candidates:
      - converge-{service}
    success_criteria:
      - workflow {workflow_id} returns success
      - service {service} reports healthy
    preconditions:
      - target service {service} is cataloged
    scope_defaults:
      allowed_hosts: []
      allowed_services: []
      allowed_vmids: []

  - id: rotate-secret
    patterns:
      - type: template
        value: rotate secret for {service}
      - type: template
        value: rotate {service} credentials
    action: rotate
    target_kind: service
    default_risk_class: HIGH
    allowed_tools:
      - openbao-rotate
      - windmill-trigger
    rollback_path: restore-secret-from-openbao-snapshot
    requires_approval_above: LOW
    ttl_seconds: 300
    workflow_id: rotate-secret
    workflow_candidates: []
    success_criteria:
      - workflow {workflow_id} returns success
    preconditions:
      - secret catalog entry exists for {service}
    scope_defaults:
      allowed_hosts: []
      allowed_services: []
      allowed_vmids: []

  - id: check-platform-drift
    patterns:
      - type: template
        value: check platform drift
      - type: template
        value: check drift
    action: check
    target_kind: platform
    default_risk_class: LOW
    allowed_tools:
      - windmill-trigger
    rollback_path: null
    requires_approval_above: HIGH
    ttl_seconds: 300
    workflow_id: check-platform-drift
    workflow_candidates: []
    success_criteria:
      - drift report is recorded
    preconditions:
      - validation inputs for drift detection are available
    scope_defaults:
      allowed_hosts: []
      allowed_services: []
      allowed_vmids: []
""".strip()
        + "\n",
    )
    _write(
        tmp_path / "config" / "goal-compiler-aliases.yaml",
        """
schema_version: 1.0.0
phrase_aliases:
  the monitoring stack: monitoring stack
  monitoring stack: monitoring stack
service_aliases:
  grafana ui: grafana
  netbox ui: netbox
groups:
  monitoring stack:
    services:
      - grafana
      - loki
      - prometheus
    workflow_id: converge-monitoring
    hosts:
      - monitoring-lv3
""".strip()
        + "\n",
    )
    return tmp_path


# ---------------------------------------------------------------------------
# Normalisation tests
# ---------------------------------------------------------------------------


def test_normalize_collapses_whitespace(compiler_repo: Path) -> None:
    compiler = GoalCompiler(compiler_repo)
    assert compiler.normalize("  deploy   netbox  ") == "deploy netbox"


def test_normalize_lowercases(compiler_repo: Path) -> None:
    compiler = GoalCompiler(compiler_repo)
    assert compiler.normalize("Deploy NetBox") == "deploy netbox"


def test_normalize_applies_phrase_alias(compiler_repo: Path) -> None:
    compiler = GoalCompiler(compiler_repo)
    assert compiler.normalize("deploy the monitoring stack") == "deploy monitoring stack"


def test_normalize_applies_service_alias(compiler_repo: Path) -> None:
    compiler = GoalCompiler(compiler_repo)
    assert compiler.normalize("deploy grafana ui") == "deploy grafana"


# ---------------------------------------------------------------------------
# Rule matching / compilation tests
# ---------------------------------------------------------------------------


def test_compile_deploy_service_sets_action(compiler_repo: Path) -> None:
    compiler = GoalCompiler(compiler_repo)
    intent = compiler.compile("deploy netbox")
    assert intent.action == "deploy"
    assert intent.matched_rule_id == "deploy-service"


def test_compile_deploy_resolves_target_service(compiler_repo: Path) -> None:
    compiler = GoalCompiler(compiler_repo)
    intent = compiler.compile("deploy netbox")
    assert intent.target.kind == "service"
    assert intent.target.name == "netbox"
    assert "netbox" in intent.target.services


def test_compile_deploy_resolves_vm_host_from_catalog(compiler_repo: Path) -> None:
    compiler = GoalCompiler(compiler_repo)
    intent = compiler.compile("deploy netbox")
    assert "netbox-lv3" in intent.target.hosts
    assert "netbox-lv3" in intent.scope.allowed_hosts


def test_compile_deploy_resolves_workflow_id_from_candidates(compiler_repo: Path) -> None:
    compiler = GoalCompiler(compiler_repo)
    intent = compiler.compile("deploy netbox")
    assert intent.workflow_id == "converge-netbox"


def test_compile_deploy_requires_approval(compiler_repo: Path) -> None:
    # default_risk_class=MEDIUM, requires_approval_above=LOW → MEDIUM > LOW → True
    compiler = GoalCompiler(compiler_repo)
    intent = compiler.compile("deploy netbox")
    assert intent.requires_approval is True


def test_compile_rotate_sets_high_risk_class(compiler_repo: Path) -> None:
    compiler = GoalCompiler(compiler_repo)
    intent = compiler.compile("rotate secret for netbox")
    assert intent.risk_class == RiskClass.HIGH
    assert intent.workflow_id == "rotate-secret"
    assert "openbao-rotate" in intent.allowed_tools


def test_compile_check_drift_sets_low_risk_class(compiler_repo: Path) -> None:
    compiler = GoalCompiler(compiler_repo)
    intent = compiler.compile("check platform drift")
    assert intent.risk_class == RiskClass.LOW
    assert intent.requires_approval is False


def test_compile_converge_alternate_pattern(compiler_repo: Path) -> None:
    """The ``apply {service}`` pattern should match the converge-service rule."""
    compiler = GoalCompiler(compiler_repo)
    intent = compiler.compile("apply grafana")
    assert intent.matched_rule_id == "converge-service"
    assert intent.target.name == "grafana"


def test_compile_parse_error_is_explicit(compiler_repo: Path) -> None:
    compiler = GoalCompiler(compiler_repo)
    with pytest.raises(GoalCompilationError) as exc_info:
        compiler.compile("dploy netbox")
    error = exc_info.value
    assert error.code == "PARSE_ERROR"
    assert "normalized_input" in error.details
    assert error.details["normalized_input"] == "dploy netbox"


def test_compile_parse_error_includes_raw_input(compiler_repo: Path) -> None:
    compiler = GoalCompiler(compiler_repo)
    with pytest.raises(GoalCompilationError) as exc_info:
        compiler.compile("UNKNOWN OPERATION XYZ")
    assert exc_info.value.raw_input == "UNKNOWN OPERATION XYZ"


# ---------------------------------------------------------------------------
# Alias group expansion
# ---------------------------------------------------------------------------


def test_compile_alias_group_expands_to_multiple_services(compiler_repo: Path) -> None:
    compiler = GoalCompiler(compiler_repo)
    intent = compiler.compile("deploy the monitoring stack")
    assert intent.target.kind == "service_group"
    assert set(intent.target.services) == {"grafana", "loki", "prometheus"}


def test_compile_alias_group_uses_group_workflow_id(compiler_repo: Path) -> None:
    compiler = GoalCompiler(compiler_repo)
    intent = compiler.compile("deploy the monitoring stack")
    assert intent.workflow_id == "converge-monitoring"


def test_compile_alias_group_includes_declared_hosts(compiler_repo: Path) -> None:
    compiler = GoalCompiler(compiler_repo)
    intent = compiler.compile("deploy the monitoring stack")
    assert "monitoring-lv3" in intent.scope.allowed_hosts


# ---------------------------------------------------------------------------
# Direct workflow-id shortcut
# ---------------------------------------------------------------------------


def test_compile_direct_workflow_id(compiler_repo: Path) -> None:
    compiler = GoalCompiler(compiler_repo)
    intent = compiler.compile("validate")
    assert intent.matched_rule_id == "direct-workflow-id"
    assert intent.workflow_id == "validate"
    assert intent.action == "execute"


def test_compile_direct_workflow_passes_dispatch_args(compiler_repo: Path) -> None:
    compiler = GoalCompiler(compiler_repo)
    intent = compiler.compile("validate", dispatch_args={"mode": "strict"})
    assert intent.dispatch_payload == {"mode": "strict"}


def test_compile_direct_workflow_host_live_requires_approval(compiler_repo: Path) -> None:
    compiler = GoalCompiler(compiler_repo)
    intent = compiler.compile("configure-network")
    assert intent.risk_class == RiskClass.HIGH
    assert intent.requires_approval is True


# ---------------------------------------------------------------------------
# Risk scorer integration
# ---------------------------------------------------------------------------


def test_compile_produces_numeric_risk_score(compiler_repo: Path) -> None:
    compiler = GoalCompiler(compiler_repo)
    intent = compiler.compile("deploy netbox")
    assert intent.risk_score is not None
    assert 0.0 <= intent.risk_score <= 100.0


def test_compile_security_service_scores_higher_than_observability(compiler_repo: Path) -> None:
    compiler = GoalCompiler(compiler_repo)
    intent_netbox = compiler.compile("deploy netbox")
    intent_openbao = compiler.compile("deploy openbao")
    # openbao is category=security → "high" tier vs netbox "medium"
    assert intent_openbao.risk_score is not None
    assert intent_netbox.risk_score is not None
    assert intent_openbao.risk_score >= intent_netbox.risk_score


def test_compile_risk_breakdown_contains_expected_dimensions(compiler_repo: Path) -> None:
    compiler = GoalCompiler(compiler_repo)
    intent = compiler.compile("deploy netbox")
    assert "target_criticality" in intent.risk_score_breakdown
    assert "mutation_surface" in intent.risk_score_breakdown
    assert "rollback_confidence" in intent.risk_score_breakdown


def test_compile_scoring_context_included(compiler_repo: Path) -> None:
    compiler = GoalCompiler(compiler_repo)
    intent = compiler.compile("deploy netbox")
    ctx = intent.scoring_context
    assert "target_tier" in ctx
    assert "workflow_id" in ctx
    assert ctx["workflow_id"] == "converge-netbox"


# ---------------------------------------------------------------------------
# YAML serialisation
# ---------------------------------------------------------------------------


def test_as_yaml_round_trips_required_fields(compiler_repo: Path) -> None:
    compiler = GoalCompiler(compiler_repo)
    intent = compiler.compile("deploy netbox")
    yml_text = compiler.as_yaml(intent)
    import yaml

    loaded = yaml.safe_load(yml_text)
    assert loaded["action"] == "deploy"
    assert loaded["risk_class"] == "MEDIUM"
    assert loaded["requires_approval"] is True
    assert "workflow_id" in loaded
    assert loaded["workflow_id"] == "converge-netbox"


def test_as_dict_does_not_include_none_workflow_id(compiler_repo: Path) -> None:
    # check-platform-drift has a fixed workflow_id so let's use a service with one
    compiler = GoalCompiler(compiler_repo)
    intent = compiler.compile("check platform drift")
    d = intent.as_dict()
    # workflow_id is "check-platform-drift", not None
    assert d["workflow_id"] == "check-platform-drift"


# ---------------------------------------------------------------------------
# Resolver unit tests (in isolation)
# ---------------------------------------------------------------------------


def test_resolve_target_returns_service_with_host(compiler_repo: Path) -> None:
    target = resolve_target(
        target_kind="service",
        captures={"service": "netbox"},
        alias_groups={},
        service_aliases={},
        repo_root=compiler_repo,
    )
    assert target.kind == "service"
    assert target.name == "netbox"
    assert target.services == ["netbox"]
    assert "netbox-lv3" in target.hosts


def test_resolve_target_expands_alias_group(compiler_repo: Path) -> None:
    groups = {
        "monitoring stack": {
            "services": ["grafana", "loki", "prometheus"],
            "workflow_id": "converge-monitoring",
            "hosts": ["monitoring-lv3"],
        }
    }
    target = resolve_target(
        target_kind="service",
        captures={"service": "monitoring stack"},
        alias_groups=groups,
        service_aliases={},
        repo_root=compiler_repo,
    )
    assert target.kind == "service_group"
    assert set(target.services) == {"grafana", "loki", "prometheus"}
    assert "monitoring-lv3" in target.hosts


def test_resolve_target_workflow_kind(compiler_repo: Path) -> None:
    target = resolve_target(
        target_kind="workflow",
        captures={"workflow": "validate"},
        alias_groups={},
        service_aliases={},
        repo_root=compiler_repo,
    )
    assert target.kind == "workflow"
    assert target.name == "validate"
    assert target.services == []


def test_resolve_scope_merges_rule_defaults_and_target(compiler_repo: Path) -> None:
    target = IntentTarget(kind="service", name="netbox", services=["netbox"], hosts=["netbox-lv3"])
    scope = resolve_scope(
        rule_scope_defaults={"allowed_hosts": ["management-lv3"], "allowed_services": [], "allowed_vmids": []},
        target=target,
    )
    assert "management-lv3" in scope.allowed_hosts
    assert "netbox-lv3" in scope.allowed_hosts
    assert "netbox" in scope.allowed_services


def test_resolve_scope_deduplicates_hosts(compiler_repo: Path) -> None:
    target = IntentTarget(kind="service", name="grafana", services=["grafana"], hosts=["monitoring-lv3"])
    scope = resolve_scope(
        rule_scope_defaults={"allowed_hosts": ["monitoring-lv3"], "allowed_services": [], "allowed_vmids": []},
        target=target,
    )
    assert scope.allowed_hosts.count("monitoring-lv3") == 1


def test_resolve_workflow_id_prefers_group_alias(compiler_repo: Path) -> None:
    groups = {
        "monitoring stack": {
            "services": ["grafana", "loki", "prometheus"],
            "workflow_id": "converge-monitoring",
        }
    }
    target = IntentTarget(kind="service_group", name="monitoring stack", services=["grafana", "loki", "prometheus"])
    wf_id = resolve_workflow_id(
        rule_workflow_id=None,
        rule_workflow_candidates=["converge-{service}"],
        captures={},
        target=target,
        alias_groups=groups,
    )
    assert wf_id == "converge-monitoring"


def test_resolve_workflow_id_falls_back_to_candidate(compiler_repo: Path) -> None:
    target = IntentTarget(kind="service", name="netbox", services=["netbox"], hosts=["netbox-lv3"])
    wf_id = resolve_workflow_id(
        rule_workflow_id=None,
        rule_workflow_candidates=["converge-{service}", "deploy-{service}"],
        captures={"service": "netbox"},
        target=target,
        alias_groups={},
    )
    assert wf_id == "converge-netbox"


def test_resolve_workflow_id_uses_fixed_id(compiler_repo: Path) -> None:
    target = IntentTarget(kind="service", name="openbao", services=["openbao"])
    wf_id = resolve_workflow_id(
        rule_workflow_id="rotate-secret",
        rule_workflow_candidates=[],
        captures={"service": "openbao"},
        target=target,
        alias_groups={},
    )
    assert wf_id == "rotate-secret"


# ---------------------------------------------------------------------------
# ScoringContext model
# ---------------------------------------------------------------------------


def test_scoring_context_as_dict_has_required_keys() -> None:
    ctx = ScoringContext(
        workflow_id="converge-netbox",
        target_service_id="netbox",
        target_tier="medium",
        downstream_count=0,
        recent_failure_rate=0.0,
        expected_change_count=5,
        irreversible_count=0,
        unknown_count=0,
        rollback_verified=False,
        in_maintenance_window=False,
        active_incident=False,
        hours_since_last_mutation=72.0,
        stale=True,
        stale_reasons=("no live data",),
    )
    d = ctx.as_dict()
    assert d["target_tier"] == "medium"
    assert d["stale"] is True
    assert d["stale_reasons"] == ["no live data"]
