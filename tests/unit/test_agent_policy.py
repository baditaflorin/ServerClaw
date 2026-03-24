from __future__ import annotations

import json
from pathlib import Path

from platform.agent_policy import AgentPolicyEngine, DailyExecutionCounter, PolicyOutcome
from platform.goal_compiler.schema import RiskClass


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def policy_repo(tmp_path: Path) -> Path:
    write(
        tmp_path / "config" / "agent-policies.yaml",
        """
- agent_id: agent/triage-loop
  description: test triage
  identity_class: service-agent
  trust_tier: T2
  read_surfaces:
    - search
    - world_state
  autonomous_actions:
    max_risk_class: LOW
    allowed_workflow_tags:
      - diagnostic
    disallowed_workflow_ids:
      - converge-netbox
    max_daily_autonomous_executions: 1
  escalation:
    on_risk_above: LOW
    escalation_target: mattermost:#platform-incidents
    escalation_event: platform.intent.rejected
""".strip()
        + "\n",
    )
    write(
        tmp_path / "config" / "workflow-catalog.json",
        json.dumps(
            {
                "workflows": {
                    "validate": {
                        "description": "Validate",
                        "live_impact": "repo_only",
                        "execution_class": "diagnostic",
                        "required_read_surfaces": ["search"],
                    },
                    "converge-guest-network-policy": {
                        "description": "Converge",
                        "live_impact": "host_and_guest_live",
                        "execution_class": "mutation",
                        "required_read_surfaces": ["world_state"],
                    },
                }
            }
        )
        + "\n",
    )
    return tmp_path


def test_agent_policy_allows_bounded_diagnostic_workflow(tmp_path: Path) -> None:
    repo_root = policy_repo(tmp_path)
    engine = AgentPolicyEngine(repo_root)

    decision = engine.evaluate(
        actor_id="agent/triage-loop",
        workflow_id="validate",
        risk_class=RiskClass.LOW,
        required_read_surfaces=["search"],
        autonomous=True,
        current_daily_executions=0,
    )

    assert decision.outcome == PolicyOutcome.ALLOW


def test_agent_policy_escalates_risk_above_autonomous_limit(tmp_path: Path) -> None:
    repo_root = policy_repo(tmp_path)
    engine = AgentPolicyEngine(repo_root)

    decision = engine.evaluate(
        actor_id="agent/triage-loop",
        workflow_id="converge-guest-network-policy",
        risk_class=RiskClass.HIGH,
        required_read_surfaces=["world_state"],
        autonomous=True,
        current_daily_executions=0,
    )

    assert decision.outcome == PolicyOutcome.DENY
    assert decision.reason == "workflow_tag_not_allowed"


def test_daily_execution_counter_tracks_utc_day(tmp_path: Path) -> None:
    counter = DailyExecutionCounter(tmp_path / ".local" / "state" / "agent-policy" / "counts.json")

    assert counter.get("agent/triage-loop") == 0
    assert counter.increment("agent/triage-loop") == 1
    assert counter.increment("agent/triage-loop") == 2
    assert counter.get("agent/triage-loop") == 2
