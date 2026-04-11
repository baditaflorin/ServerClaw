from __future__ import annotations

import json
from pathlib import Path

from platform.closure_loop import ClosureLoop, observation_finding_to_alert_payload
from platform.closure_loop.store import LoopStateStore


class FakeScheduler:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def submit(self, intent, *, requested_by: str = "operator:lv3_cli"):
        self.calls.append((intent.workflow_id, dict(intent.arguments)))
        return type(
            "SchedulerResult",
            (),
            {
                "status": "completed",
                "workflow_id": intent.workflow_id,
                "job_id": "job-1",
                "actor_intent_id": "intent-1",
                "output": {"ok": True},
                "reason": None,
                "budget": None,
                "metadata": {"requested_by": requested_by},
            },
        )()


def write_repo_basics(repo_root: Path) -> None:
    (repo_root / "config").mkdir(parents=True, exist_ok=True)
    (repo_root / "config" / "service-capability-catalog.json").write_text(
        json.dumps({"services": [{"id": "netbox", "name": "NetBox", "vm": "netbox-lv3", "lifecycle_status": "active"}]})
        + "\n",
        encoding="utf-8",
    )
    (repo_root / "config" / "workflow-catalog.json").write_text(
        json.dumps(
            {
                "workflows": {
                    "converge-netbox": {
                        "description": "Converge NetBox",
                        "live_impact": "guest_live",
                        "execution_class": "mutation",
                    }
                }
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (repo_root / "config" / "correction-loops.json").write_text(
        json.dumps(
            {
                "$schema": "docs/schema/correction-loop-catalog.schema.json",
                "schema_version": "1.0.0",
                "required_workflow_ids": ["platform-observation-loop"],
                "loops": [
                    {
                        "id": "runtime_self_correction_watchers",
                        "description": "Observation loop contract.",
                        "applies_to": {"workflow_ids": ["platform-observation-loop"]},
                        "invariant": "Loop state stays durable and bounded.",
                        "observation_sources": ["runs.json"],
                        "diagnosis_taxonomy": [
                            "transient_failure",
                            "contract_drift",
                            "dependency_outage",
                            "stale_input",
                            "irreversible_data_loss_risk",
                        ],
                        "repair_actions": [
                            {
                                "kind": "no_op",
                                "summary": "Already healthy.",
                                "requires_approval": False,
                                "destructive": False,
                            },
                            {
                                "kind": "reconcile",
                                "summary": "Replay the bounded loop tick.",
                                "requires_approval": False,
                                "destructive": False,
                            },
                            {
                                "kind": "escalate",
                                "summary": "Escalate when the loop hits a safety boundary.",
                                "requires_approval": True,
                                "destructive": False,
                            },
                        ],
                        "verification": {
                            "source": "service_health",
                            "success_signal": "The loop records a resolved run.",
                        },
                        "escalation": {
                            "boundary": "Re-triage budget exhausted.",
                            "target": "operator",
                            "runbook": "docs/runbooks/observation-to-action-closure-loop.md",
                        },
                        "retry_budget_cycles": 3,
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (repo_root / "config" / "controller-local-secrets.json").write_text(
        json.dumps({"secrets": {}}) + "\n", encoding="utf-8"
    )
    (repo_root / "docs" / "runbooks").mkdir(parents=True, exist_ok=True)
    (repo_root / "docs" / "runbooks" / "observation-to-action-closure-loop.md").write_text(
        "# Observation to action\n",
        encoding="utf-8",
    )


def test_auto_check_run_resolves_and_stops_on_verification_pass(tmp_path: Path) -> None:
    write_repo_basics(tmp_path)
    store = LoopStateStore(tmp_path / ".local" / "state" / "closure-loop" / "runs.json")
    loop = ClosureLoop(
        tmp_path,
        state_store=store,
        triage_report_builder=lambda _payload: {
            "affected_service": "netbox",
            "hypotheses": [
                {"rank": 1, "id": "tls-cert-expiry", "auto_check": True, "cheapest_first_action": "check cert"}
            ],
            "auto_check_result": {"status": "executed", "type": "cert_check"},
        },
        verification_provider=lambda _run, _proposal, _execution: {"passed": True, "goal_achieved": True},
    )

    run = loop.start(trigger_type="observation_finding", trigger_ref="finding-1", service_id="netbox")

    assert run["current_state"] == "RESOLVED"
    assert run["resolved_at"] is not None
    assert run["correction_loop"]["loop_id"] == "runtime_self_correction_watchers"
    assert [item["to_state"] for item in run["history"]] == [
        "TRIAGED",
        "PROPOSING",
        "EXECUTING",
        "VERIFYING",
        "RESOLVED",
    ]


def test_non_auto_check_run_escalates_then_approved_workflow_resolves(tmp_path: Path) -> None:
    write_repo_basics(tmp_path)
    scheduler = FakeScheduler()
    loop = ClosureLoop(
        tmp_path,
        state_store=LoopStateStore(tmp_path / ".local" / "state" / "closure-loop" / "runs.json"),
        triage_report_builder=lambda _payload: {
            "affected_service": "netbox",
            "hypotheses": [
                {
                    "rank": 1,
                    "id": "dependency-failure",
                    "auto_check": False,
                    "cheapest_first_action": "inspect upstream",
                }
            ],
            "auto_check_result": None,
        },
        verification_provider=lambda _run, _proposal, _execution: {"passed": True, "goal_achieved": True},
        scheduler=scheduler,
    )

    paused = loop.start(trigger_type="manual", trigger_ref="manual-1", service_id="netbox")
    assert paused["current_state"] == "ESCALATED_FOR_APPROVAL"

    resumed = loop.approve(paused["run_id"], instruction="converge netbox")

    assert resumed["current_state"] == "RESOLVED"
    assert scheduler.calls == [("converge-netbox", {"service": "netbox", "target": "netbox"})]


def test_failed_verification_retries_then_blocks(tmp_path: Path) -> None:
    write_repo_basics(tmp_path)
    triage_calls = {"count": 0}

    def build_report(_payload):
        triage_calls["count"] += 1
        return {
            "affected_service": "netbox",
            "hypotheses": [
                {"rank": 1, "id": "resource-exhaustion", "auto_check": True, "cheapest_first_action": "check pressure"}
            ],
            "auto_check_result": {"status": "executed", "type": "metric_query"},
        }

    loop = ClosureLoop(
        tmp_path,
        state_store=LoopStateStore(tmp_path / ".local" / "state" / "closure-loop" / "runs.json"),
        triage_report_builder=build_report,
        verification_provider=lambda _run, _proposal, _execution: {"passed": False, "goal_achieved": False},
    )

    run = loop.start(trigger_type="observation_finding", trigger_ref="finding-2", service_id="netbox")

    assert run["current_state"] == "BLOCKED"
    assert run["cycle_count"] == 3
    assert run["correction_loop"]["retry_budget_cycles"] == 3
    assert triage_calls["count"] == 4
    assert run["history"][-1]["to_state"] == "BLOCKED"


def test_observation_finding_payload_extracts_service_from_details() -> None:
    payload = observation_finding_to_alert_payload(
        {
            "severity": "critical",
            "check": "check-service-health",
            "details": [{"service_id": "netbox"}],
        },
        fallback_ref="run-1",
    )

    assert payload is not None
    assert payload["service_id"] == "netbox"
    assert payload["status"] == "firing"
