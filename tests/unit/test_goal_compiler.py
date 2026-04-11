from __future__ import annotations

import json
from pathlib import Path

import platform as stdlib_platform
import pytest

from repo_package_loader import load_repo_package


GOAL_COMPILER_MODULE = load_repo_package(
    "lv3_goal_compiler_test",
    Path(__file__).resolve().parents[2] / "platform" / "goal_compiler",
)
GoalCompilationError = GOAL_COMPILER_MODULE.GoalCompilationError
GoalCompiler = GOAL_COMPILER_MODULE.GoalCompiler


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


@pytest.fixture()
def compiler_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    for key in ("LV3_HEALTH_DSN", "WORLD_STATE_DSN", "LV3_GRAPH_DSN", "LV3_LEDGER_DSN"):
        monkeypatch.delenv(key, raising=False)
    maintenance_state = tmp_path / ".local" / "state" / "maintenance-windows.json"
    maintenance_state.parent.mkdir(parents=True, exist_ok=True)
    maintenance_state.write_text("{}\n", encoding="utf-8")
    monkeypatch.setenv("LV3_MAINTENANCE_WINDOWS_FILE", str(maintenance_state))
    write(
        tmp_path / "config" / "service-capability-catalog.json",
        json.dumps(
            {
                "services": [
                    {"id": "netbox", "name": "NetBox", "vm": "netbox-lv3"},
                    {"id": "grafana", "name": "Grafana", "vm": "monitoring"},
                    {"id": "loki", "name": "Loki", "vm": "monitoring"},
                    {"id": "prometheus", "name": "Prometheus", "vm": "monitoring"},
                ]
            }
        )
        + "\n",
    )
    write(
        tmp_path / "config" / "workflow-catalog.json",
        json.dumps(
            {
                "workflows": {
                    "validate": {
                        "description": "Validate repository",
                        "live_impact": "repo_only",
                        "execution_class": "diagnostic",
                        "required_read_surfaces": ["search"],
                    },
                    "converge-netbox": {
                        "description": "Converge NetBox",
                        "live_impact": "guest_live",
                        "execution_class": "mutation",
                        "required_read_surfaces": ["world_state"],
                    },
                    "converge-monitoring": {
                        "description": "Converge monitoring",
                        "live_impact": "guest_live",
                        "execution_class": "mutation",
                        "required_read_surfaces": ["world_state"],
                    },
                    "converge-guest-network-policy": {
                        "description": "Converge guest network policy",
                        "live_impact": "host_and_guest_live",
                        "execution_class": "mutation",
                        "required_read_surfaces": ["world_state"],
                    },
                }
            }
        )
        + "\n",
    )
    write(
        tmp_path / "config" / "agent-policies.yaml",
        """
- agent_id: operator:lv3-cli
  description: operator
  identity_class: operator-agent
  trust_tier: T3
  read_surfaces:
    - maintenance_windows
    - search
    - world_state
  autonomous_actions:
    max_risk_class: MEDIUM
    allowed_workflow_tags:
      - diagnostic
      - converge
      - mutation
      - validation
    disallowed_workflow_ids:
      - destroy-vm
    max_daily_autonomous_executions: 50
  escalation:
    on_risk_above: MEDIUM
    escalation_target: operator
    escalation_event: platform.intent.rejected
- agent_id: agent/triage-loop
  description: triage
  identity_class: service-agent
  trust_tier: T2
  read_surfaces:
    - maintenance_windows
    - search
    - world_state
  autonomous_actions:
    max_risk_class: LOW
    allowed_workflow_tags:
      - diagnostic
      - validation
    disallowed_workflow_ids:
      - destroy-vm
    max_daily_autonomous_executions: 20
  escalation:
    on_risk_above: LOW
    escalation_target: mattermost:#platform-incidents
    escalation_event: platform.intent.rejected
- agent_id: agent/claude-code
  description: claude
  identity_class: operator-agent
  trust_tier: T3
  read_surfaces:
    - maintenance_windows
    - search
    - world_state
  autonomous_actions:
    max_risk_class: MEDIUM
    allowed_workflow_tags:
      - converge
      - diagnostic
    disallowed_workflow_ids:
      - destroy-vm
    max_daily_autonomous_executions: 50
  escalation:
    on_risk_above: MEDIUM
    escalation_target: operator
    escalation_event: platform.intent.rejected
""".strip()
        + "\n",
    )
    write(
        tmp_path / "inventory" / "hosts.yml",
        """
all:
  children:
    lv3_guests:
      hosts:
        netbox-lv3:
          ansible_host: 10.10.10.30
        monitoring:
          ansible_host: 10.10.10.40
""".strip()
        + "\n",
    )
    write(
        tmp_path / ".local" / "state" / "world-state" / "proxmox_vms.json",
        json.dumps(
            {
                "items": [
                    {"service_id": "netbox", "name": "netbox-lv3", "vmid": 130},
                    {"service_id": "grafana", "name": "monitoring", "vmid": 140},
                ]
            }
        )
        + "\n",
    )
    return tmp_path


def test_platform_shim_preserves_stdlib_api() -> None:
    assert isinstance(stdlib_platform.system(), str)


def test_compile_deploy_service_with_scope_binding(compiler_repo: Path) -> None:
    compiler = GoalCompiler(compiler_repo)

    result = compiler.compile("deploy netbox")

    assert result.matched_rule_id == "deploy-service"
    assert result.dispatch_workflow_id == "converge-netbox"
    assert result.intent.action == "deploy"
    assert result.intent.target.services == ["netbox"]
    assert result.intent.scope.allowed_hosts == ["netbox-lv3"]
    assert result.intent.scope.allowed_vmids == [130]
    assert result.intent.requires_approval is True
    assert result.intent.resource_claims == [
        {"resource": "service:netbox", "access": "write"},
        {"resource": "vm:netbox-lv3", "access": "read"},
    ]


def test_compile_alias_group_uses_group_workflow(compiler_repo: Path) -> None:
    compiler = GoalCompiler(compiler_repo)

    result = compiler.compile("deploy the monitoring stack")

    assert result.intent.target.kind == "service_group"
    assert result.intent.target.services == ["grafana", "loki", "prometheus"]
    assert result.dispatch_workflow_id == "converge-monitoring"


def test_compile_direct_workflow_keeps_compatibility(compiler_repo: Path) -> None:
    compiler = GoalCompiler(compiler_repo)

    result = compiler.compile("validate", dispatch_args={"mode": "strict"})

    assert result.matched_rule_id == "direct-workflow-id"
    assert result.dispatch_workflow_id == "validate"
    assert result.dispatch_payload == {"mode": "strict"}
    assert result.intent.action == "execute"


def test_compile_enables_speculative_mode_when_requested(compiler_repo: Path) -> None:
    catalog_path = compiler_repo / "config" / "workflow-catalog.json"
    payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    payload["workflows"]["converge-netbox"]["speculative"] = {
        "eligible": True,
        "compensating_workflow_id": "rollback-netbox",
        "conflict_probe": {"path": "tests/fixtures/speculative_probe.py", "callable": "probe"},
        "probe_delay_seconds": 0,
        "rollback_window_seconds": 120,
    }
    payload["workflows"]["rollback-netbox"] = {
        "description": "Rollback NetBox",
        "live_impact": "guest_live",
    }
    catalog_path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    compiler = GoalCompiler(compiler_repo)
    result = compiler.compile("deploy netbox", allow_speculative=True)

    assert result.intent.execution_mode == "speculative"
    assert result.intent.compensating_workflow_id == "rollback-netbox"
    assert result.intent.rollback_window_seconds == 120
    assert result.dispatch_payload["execution_mode"] == "speculative"
    assert any("speculative execution enabled" in item for item in result.intent.preconditions)


def test_compile_parse_error_is_explicit(compiler_repo: Path) -> None:
    compiler = GoalCompiler(compiler_repo)

    with pytest.raises(GoalCompilationError) as excinfo:
        compiler.compile("dploy netbox")

    assert excinfo.value.code == "PARSE_ERROR"


def test_compile_rejects_unsafe_health(compiler_repo: Path) -> None:
    snapshot_dir = compiler_repo / ".local" / "state" / "world-state"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    (snapshot_dir / "service_health.json").write_text(
        json.dumps(
            {
                "services": [{"service_id": "netbox", "status": "down"}],
                "collected_at": "2026-03-24T10:00:00Z",
            }
        )
        + "\n"
    )

    compiler = GoalCompiler(compiler_repo)

    with pytest.raises(GoalCompilationError) as excinfo:
        compiler.compile("deploy netbox")

    assert excinfo.value.code == "HEALTH_UNSAFE"


def test_compile_force_unsafe_health_allows_instruction(compiler_repo: Path) -> None:
    snapshot_dir = compiler_repo / ".local" / "state" / "world-state"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    (snapshot_dir / "service_health.json").write_text(
        json.dumps(
            {
                "services": [{"service_id": "netbox", "status": "down"}],
                "collected_at": "2026-03-24T10:00:00Z",
            }
        )
        + "\n"
    )

    compiler = GoalCompiler(compiler_repo)
    result = compiler.compile("deploy netbox", force_unsafe_health=True)

    assert result.dispatch_workflow_id == "converge-netbox"
    assert result.intent.requires_approval is True


def test_compile_batch_preserves_instruction_order(compiler_repo: Path) -> None:
    compiler = GoalCompiler(compiler_repo)

    batch = compiler.compile_batch(["deploy netbox", "deploy grafana"], actor_id="operator:lv3-cli")

    assert batch.actor_id == "operator:lv3-cli"
    assert batch.instructions == ("deploy netbox", "deploy grafana")
    assert [item.dispatch_workflow_id for item in batch.results] == ["converge-netbox", "converge-grafana"]


def test_compile_uses_llm_fallback_for_unmatched_instruction(compiler_repo: Path) -> None:
    class FakeLLMClient:
        def __init__(self) -> None:
            self.calls = 0

        def complete(self, prompt: str, *, use_case: str, max_tokens: int = 128, temperature: float = 0.0) -> str:
            self.calls += 1
            assert use_case == "goal_compiler_normalisation"
            assert "please ship netbox" in prompt
            return "deploy netbox"

    llm_client = FakeLLMClient()
    compiler = GoalCompiler(compiler_repo, llm_client=llm_client)

    result = compiler.compile("please ship netbox")

    assert result.dispatch_workflow_id == "converge-netbox"
    assert result.normalized_input == "deploy netbox"
    assert llm_client.calls == 1


def test_compile_parse_error_only_calls_llm_once(compiler_repo: Path) -> None:
    class FakeLLMClient:
        def __init__(self) -> None:
            self.calls = 0

        def complete(self, prompt: str, *, use_case: str, max_tokens: int = 128, temperature: float = 0.0) -> str:
            self.calls += 1
            assert use_case == "goal_compiler_normalisation"
            assert "dploy netbox" in prompt
            return "still unknown"

    llm_client = FakeLLMClient()
    compiler = GoalCompiler(compiler_repo, llm_client=llm_client)

    with pytest.raises(GoalCompilationError) as excinfo:
        compiler.compile("dploy netbox")

    assert excinfo.value.code == "PARSE_ERROR"
    assert excinfo.value.details == {
        "normalized_input": "dploy netbox",
        "llm_normalized_input": "still unknown",
    }
    assert llm_client.calls == 1


def test_compile_denies_out_of_bounds_workflow_tags(compiler_repo: Path) -> None:
    compiler = GoalCompiler(compiler_repo)

    with pytest.raises(GoalCompilationError) as excinfo:
        compiler.compile("deploy netbox", actor_id="agent/triage-loop", autonomous=True)

    assert excinfo.value.code == "CAPABILITY_DENIED"
    assert excinfo.value.details["reason"] == "workflow_tag_not_allowed"


def test_compile_escalates_risk_above_actor_limit(compiler_repo: Path) -> None:
    compiler = GoalCompiler(compiler_repo)

    with pytest.raises(GoalCompilationError) as excinfo:
        compiler.compile("converge-guest-network-policy", actor_id="agent/claude-code", autonomous=True)

    assert excinfo.value.code == "CAPABILITY_ESCALATION_REQUIRED"
    assert excinfo.value.details["reason"] == "capability_bound_exceeded"
