from __future__ import annotations

import importlib.util
import json
import os
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

from platform.ledger import LedgerWriter
from platform.ledger._common import REPO_ROOT, load_module_from_repo
from platform.world_state.client import WorldStateClient, WorldStateError

from .store import LoopStateStore


OBSERVED = "OBSERVED"
TRIAGED = "TRIAGED"
PROPOSING = "PROPOSING"
EXECUTING = "EXECUTING"
VERIFYING = "VERIFYING"
RESOLVED = "RESOLVED"
CASE_PROMOTED = "CASE_PROMOTED"
ESCALATED_FOR_APPROVAL = "ESCALATED_FOR_APPROVAL"
BLOCKED = "BLOCKED"
CLOSED_NO_ACTION = "CLOSED_NO_ACTION"

ACTIVE_LOOP_STATES = frozenset({OBSERVED, TRIAGED, PROPOSING, EXECUTING, VERIFYING})
TERMINAL_LOOP_STATES = frozenset({RESOLVED, CASE_PROMOTED, CLOSED_NO_ACTION})
PAUSED_LOOP_STATES = frozenset({ESCALATED_FOR_APPROVAL, BLOCKED})
OK_HEALTH_STATES = {"ok", "healthy", "up", "success", "active", "maintenance"}
RISK_RANK = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}


def utcnow() -> datetime:
    return datetime.now(UTC)


def isoformat(value: datetime | None = None) -> str:
    current = value or utcnow()
    return current.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _default_event_publisher(subject: str, payload: dict[str, Any]) -> None:
    nats_url = os.environ.get("LV3_NATS_URL", "").strip() or os.environ.get("LV3_LEDGER_NATS_URL", "").strip()
    if not nats_url:
        return
    drift_lib = load_module_from_repo(REPO_ROOT / "scripts" / "drift_lib.py", "lv3_closure_loop_drift_lib")
    drift_lib.publish_nats_events(
        [{"subject": subject, "payload": payload}],
        nats_url=nats_url,
        credentials=None,
    )


def load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault(name, module)
    spec.loader.exec_module(module)
    return module


def observation_finding_to_alert_payload(finding: dict[str, Any], *, fallback_ref: str) -> dict[str, Any] | None:
    if not isinstance(finding, dict):
        return None
    severity = str(finding.get("severity", "")).lower()
    if severity in {"ok", "suppressed"}:
        return None

    service_id = finding.get("service_id")
    if not isinstance(service_id, str) or not service_id.strip():
        details = finding.get("details")
        if isinstance(details, list):
            for item in details:
                if not isinstance(item, dict):
                    continue
                candidate = item.get("service_id")
                if isinstance(candidate, str) and candidate.strip():
                    service_id = candidate
                    break
    if not isinstance(service_id, str) or not service_id.strip():
        return None

    return {
        "service_id": service_id.strip(),
        "alert_name": str(finding.get("check") or finding.get("summary") or "observation_finding"),
        "status": "firing" if severity == "critical" else "warning",
        "severity": severity,
        "finding": finding,
        "incident_id": str(finding.get("finding_id") or finding.get("run_id") or fallback_ref),
    }


class ClosureLoop:
    def __init__(
        self,
        repo_root: Path | str | None = None,
        *,
        state_store: LoopStateStore | None = None,
        triage_report_builder: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
        verification_provider: Callable[[dict[str, Any], dict[str, Any], Any], dict[str, Any]] | None = None,
        scheduler: Any | None = None,
        ledger_writer: LedgerWriter | None = None,
        event_publisher: Callable[[str, dict[str, Any]], None] | None = _default_event_publisher,
        world_state_client: WorldStateClient | None = None,
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self._repo_root = Path(repo_root) if repo_root is not None else REPO_ROOT
        self._state_store = state_store or LoopStateStore(
            self._repo_root / ".local" / "state" / "closure-loop" / "runs.json"
        )
        self._triage_report_builder = triage_report_builder or self._default_triage_report_builder
        self._verification_provider = verification_provider or self._default_verification_provider
        self._scheduler = scheduler
        self._ledger_writer = ledger_writer or LedgerWriter(
            file_path=self._repo_root / ".local" / "state" / "ledger" / "ledger.events.jsonl"
        )
        self._event_publisher = event_publisher
        self._world_state_client = world_state_client or WorldStateClient(self._repo_root)
        self._clock = clock

    def start(
        self,
        *,
        trigger_type: str,
        trigger_ref: str,
        service_id: str,
        trigger_payload: dict[str, Any] | None = None,
        state: str = OBSERVED,
        context_id: str | None = None,
        actor_id: str | None = None,
    ) -> dict[str, Any]:
        resolved_actor = actor_id or self._default_actor(trigger_type)
        payload = dict(trigger_payload or {})
        payload.setdefault("service_id", service_id)
        payload.setdefault("alert_name", trigger_type)
        payload.setdefault("status", "firing")
        run = {
            "run_id": str(uuid.uuid4()),
            "trigger_type": trigger_type,
            "trigger_ref": trigger_ref,
            "service_id": service_id,
            "current_state": state,
            "context_id": context_id,
            "triage_report": None,
            "proposed_intent": None,
            "execution_ref": None,
            "execution_result": None,
            "verification_result": None,
            "resolution": None,
            "escalation_reason": None,
            "trigger_payload": payload,
            "cycle_count": 0,
            "operator_approved": False,
            "approved_instruction": payload.get("approved_instruction"),
            "history": [],
            "created_at": isoformat(self._clock()),
            "updated_at": isoformat(self._clock()),
            "resolved_at": None,
        }
        self._state_store.upsert(run)
        return self._advance(run["run_id"], actor_id=resolved_actor)

    def status(self, run_id: str) -> dict[str, Any]:
        run = self._state_store.get(run_id)
        if run is None:
            raise KeyError(f"unknown loop run '{run_id}'")
        return run

    def approve(self, run_id: str, *, instruction: str | None = None, actor_id: str = "operator:lv3_cli") -> dict[str, Any]:
        run = self.status(run_id)
        run["operator_approved"] = True
        if instruction:
            run["approved_instruction"] = instruction
        run["updated_at"] = isoformat(self._clock())
        if run["current_state"] in PAUSED_LOOP_STATES:
            self._transition(
                run,
                PROPOSING,
                trigger="operator approval",
                actor=actor_id,
                clear_escalation=True,
            )
        else:
            self._state_store.upsert(run)
        return self._advance(run_id, actor_id=actor_id)

    def close(self, run_id: str, *, reason: str, actor_id: str = "operator:lv3_cli") -> dict[str, Any]:
        run = self.status(run_id)
        self._transition(
            run,
            CLOSED_NO_ACTION,
            trigger=f"operator close: {reason}",
            actor=actor_id,
            resolution={"status": "closed_no_action", "reason": reason},
            resolved=True,
        )
        return run

    def _advance(self, run_id: str, *, actor_id: str) -> dict[str, Any]:
        run = self.status(run_id)
        while run["current_state"] in ACTIVE_LOOP_STATES:
            state = run["current_state"]
            if state == OBSERVED:
                report = self._triage_report_builder(run["trigger_payload"])
                self._transition(
                    run,
                    TRIAGED,
                    trigger=f"auto-triage from {run['trigger_type']}",
                    actor=actor_id,
                    triage_report=report,
                )
                continue
            if state == TRIAGED:
                if self._goal_already_achieved(run):
                    self._transition(
                        run,
                        RESOLVED,
                        trigger="service already healthy",
                        actor=actor_id,
                        verification_result={"passed": True, "goal_achieved": True, "source": "service_health"},
                        resolution={"status": "resolved_without_execution"},
                        resolved=True,
                    )
                    continue
                proposal = self._build_proposal(run)
                if proposal is None:
                    self._transition(
                        run,
                        ESCALATED_FOR_APPROVAL,
                        trigger="top hypothesis requires approval",
                        actor=actor_id,
                        escalation_reason="top triage hypothesis is not auto-executable",
                    )
                    break
                self._transition(
                    run,
                    PROPOSING,
                    trigger=f"proposal ready: {proposal['kind']}",
                    actor=actor_id,
                    proposed_intent=proposal,
                )
                continue
            if state == PROPOSING:
                proposal = run.get("proposed_intent")
                if not isinstance(proposal, dict):
                    proposal = self._build_proposal(run)
                    if isinstance(proposal, dict):
                        run["proposed_intent"] = proposal
                        self._state_store.upsert(run)
                if not isinstance(proposal, dict):
                    self._transition(
                        run,
                        BLOCKED,
                        trigger="proposal missing",
                        actor=actor_id,
                        escalation_reason="closure loop could not build a proposal",
                    )
                    break
                if not self._policy_allows(run, proposal, actor_id=actor_id):
                    self._transition(
                        run,
                        ESCALATED_FOR_APPROVAL,
                        trigger="risk exceeds autonomous threshold",
                        actor=actor_id,
                        escalation_reason=f"risk class {proposal['risk_class']} exceeds {actor_id} autonomous threshold",
                    )
                    break
                if proposal["kind"] == "workflow" and self._has_active_conflict(run):
                    self._transition(
                        run,
                        ESCALATED_FOR_APPROVAL,
                        trigger="conflict detected",
                        actor=actor_id,
                        escalation_reason="another loop run is already acting on this service",
                    )
                    break
                if proposal["kind"] == "workflow" and not self._safe_to_mutate(run["service_id"]):
                    self._transition(
                        run,
                        BLOCKED,
                        trigger="service health unsafe",
                        actor=actor_id,
                        escalation_reason="service health is not safe for autonomous mutation",
                    )
                    break
                self._transition(
                    run,
                    EXECUTING,
                    trigger=f"executing {proposal['kind']}",
                    actor=actor_id,
                )
                continue
            if state == EXECUTING:
                proposal = run["proposed_intent"]
                result = self._execute(run, proposal, actor_id=actor_id)
                self._transition(
                    run,
                    VERIFYING,
                    trigger="execution completed",
                    actor=actor_id,
                    execution_result=result,
                )
                continue
            if state == VERIFYING:
                verification = self._verification_provider(run, run["proposed_intent"], run.get("execution_result"))
                if verification.get("passed") or verification.get("goal_achieved"):
                    resolution_status = "resolved"
                    target_state = RESOLVED
                    if verification.get("case_promoted"):
                        resolution_status = "case_promoted"
                        target_state = CASE_PROMOTED
                    self._transition(
                        run,
                        target_state,
                        trigger="verification passed",
                        actor=actor_id,
                        verification_result=verification,
                        resolution={"status": resolution_status, "verification": verification},
                        resolved=True,
                    )
                    continue
                if run["cycle_count"] < self._max_retriage_cycles(run["service_id"]):
                    run["cycle_count"] += 1
                    refreshed = self._triage_report_builder(
                        {
                            **run["trigger_payload"],
                            "signal_overrides": {
                                **(
                                    run["trigger_payload"].get("signal_overrides", {})
                                    if isinstance(run["trigger_payload"].get("signal_overrides"), dict)
                                    else {}
                                ),
                                "last_auto_check_failed": True,
                            },
                        }
                    )
                    self._transition(
                        run,
                        TRIAGED,
                        trigger=f"verification failed; re-triage cycle {run['cycle_count']}",
                        actor=actor_id,
                        triage_report=refreshed,
                        verification_result=verification,
                    )
                    continue
                self._transition(
                    run,
                    BLOCKED,
                    trigger="verification failed too many times",
                    actor=actor_id,
                    verification_result=verification,
                    escalation_reason="re-triage limit reached",
                )
                break
        return run

    def _default_actor(self, trigger_type: str) -> str:
        if trigger_type == "manual":
            return "operator:lv3_cli"
        return "agent/observation-loop"

    def _default_triage_report_builder(self, payload: dict[str, Any]) -> dict[str, Any]:
        scripts_dir = self._repo_root / "scripts"
        if str(scripts_dir) not in sys.path:
            sys.path.insert(0, str(scripts_dir))
        incident_triage = load_module("lv3_closure_loop_incident_triage", self._repo_root / "scripts" / "incident_triage.py")
        return incident_triage.build_report(payload)

    def _load_workflow_catalog(self) -> dict[str, Any]:
        payload = json.loads((self._repo_root / "config" / "workflow-catalog.json").read_text(encoding="utf-8"))
        workflows = payload.get("workflows", {})
        return workflows if isinstance(workflows, dict) else {}

    def _load_agent_policies(self) -> dict[str, Any]:
        path = self._repo_root / "config" / "agent-policies.yaml"
        if not path.exists():
            return {}
        try:
            import yaml
        except ModuleNotFoundError:
            return {}
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or []
        policies: dict[str, Any] = {}
        if not isinstance(payload, list):
            return policies
        for item in payload:
            if not isinstance(item, dict):
                continue
            agent_id = item.get("agent_id")
            if isinstance(agent_id, str) and agent_id.strip():
                policies[agent_id] = item
        return policies

    def _policy_max_risk(self, actor_id: str) -> str:
        policies = self._load_agent_policies()
        policy = policies.get(actor_id, {})
        actions = policy.get("autonomous_actions", {}) if isinstance(policy, dict) else {}
        candidate = actions.get("max_risk_class")
        if isinstance(candidate, str) and candidate.upper() in RISK_RANK:
            return candidate.upper()
        if actor_id.startswith("operator:"):
            return "MEDIUM"
        return "LOW"

    def _policy_allows(self, run: dict[str, Any], proposal: dict[str, Any], *, actor_id: str) -> bool:
        if run.get("operator_approved"):
            return True
        return RISK_RANK[proposal["risk_class"]] <= RISK_RANK[self._policy_max_risk(actor_id)]

    def _service_health_entry(self, service_id: str) -> dict[str, Any] | None:
        try:
            payload = self._world_state_client.get("service_health", allow_stale=True)
        except WorldStateError:
            return None
        services = payload.get("services", []) if isinstance(payload, dict) else []
        if not isinstance(services, list):
            return None
        for item in services:
            if isinstance(item, dict) and item.get("service_id") == service_id:
                return item
        return None

    def _goal_already_achieved(self, run: dict[str, Any]) -> bool:
        explicit = run["trigger_payload"].get("goal_achieved")
        if isinstance(explicit, bool):
            return explicit
        entry = self._service_health_entry(run["service_id"])
        if entry is None:
            return False
        return str(entry.get("status", "")).lower() in OK_HEALTH_STATES

    def _safe_to_mutate(self, service_id: str) -> bool:
        entry = self._service_health_entry(service_id)
        if entry is None:
            return True
        return str(entry.get("status", "")).lower() in OK_HEALTH_STATES

    def _top_hypothesis(self, run: dict[str, Any]) -> dict[str, Any] | None:
        report = run.get("triage_report")
        if not isinstance(report, dict):
            return None
        hypotheses = report.get("hypotheses", [])
        if not isinstance(hypotheses, list) or not hypotheses:
            return None
        for item in hypotheses:
            if isinstance(item, dict) and int(item.get("rank", 999)) == 1:
                return item
        return hypotheses[0] if isinstance(hypotheses[0], dict) else None

    def _build_proposal(self, run: dict[str, Any]) -> dict[str, Any] | None:
        hypothesis = self._top_hypothesis(run)
        if hypothesis is None:
            return None
        if hypothesis.get("auto_check") is True:
            auto_check = run["triage_report"].get("auto_check_result")
            if isinstance(auto_check, dict) and auto_check.get("status") == "executed":
                return {
                    "kind": "diagnostic_check",
                    "risk_class": "LOW",
                    "workflow_id": None,
                    "instruction": hypothesis.get("cheapest_first_action"),
                    "check_result": auto_check,
                    "hypothesis_id": hypothesis.get("id"),
                }
            return None

        if not run.get("operator_approved"):
            return None

        instruction = run.get("approved_instruction") or f"converge {run['service_id']}"
        from platform.goal_compiler import GoalCompiler

        compiler = GoalCompiler(self._repo_root)
        compiled = compiler.compile(str(instruction))
        return {
            "kind": "workflow",
            "risk_class": compiled.intent.risk_class.value,
            "workflow_id": compiled.dispatch_workflow_id,
            "instruction": instruction,
            "dispatch_payload": compiled.dispatch_payload,
            "compiled_intent": compiled.intent.as_dict(),
            "hypothesis_id": hypothesis.get("id"),
        }

    def _has_active_conflict(self, run: dict[str, Any]) -> bool:
        for other in self._state_store.list_runs():
            if str(other.get("run_id")) == run["run_id"]:
                continue
            if other.get("service_id") != run["service_id"]:
                continue
            if other.get("current_state") in {PROPOSING, EXECUTING, VERIFYING}:
                return True
        return False

    def _max_retriage_cycles(self, service_id: str) -> int:
        catalog = json.loads((self._repo_root / "config" / "service-capability-catalog.json").read_text(encoding="utf-8"))
        services = catalog.get("services", [])
        if not isinstance(services, list):
            return 3
        for item in services:
            if not isinstance(item, dict) or item.get("id") != service_id:
                continue
            automation = item.get("automation", {})
            if isinstance(automation, dict):
                value = automation.get("closure_loop_max_retriage_cycles")
                if isinstance(value, int):
                    return max(0, min(value, 5))
        return 3

    def _resolve_windmill_url(self) -> str | None:
        override = os.environ.get("LV3_WINDMILL_BASE_URL", "").strip()
        if override:
            return override.rstrip("/")
        catalog = json.loads((self._repo_root / "config" / "service-capability-catalog.json").read_text(encoding="utf-8"))
        for item in catalog.get("services", []):
            if not isinstance(item, dict) or item.get("id") != "windmill":
                continue
            for key in ("internal_url", "public_url"):
                value = item.get(key)
                if isinstance(value, str) and value.strip():
                    return value.rstrip("/")
        return None

    def _resolve_windmill_token(self) -> str | None:
        override = os.environ.get("LV3_WINDMILL_TOKEN", "").strip()
        if override:
            return override
        manifest_path = self._repo_root / "config" / "controller-local-secrets.json"
        if not manifest_path.exists():
            return None
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        entry = payload.get("secrets", {}).get("windmill_superadmin_secret")
        if not isinstance(entry, dict):
            return None
        candidate = entry.get("path")
        if not isinstance(candidate, str):
            return None
        path = Path(candidate).expanduser()
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8").strip()

    def _scheduler_client(self) -> Any:
        if self._scheduler is not None:
            return self._scheduler
        base_url = self._resolve_windmill_url()
        token = self._resolve_windmill_token()
        if not base_url or not token:
            raise RuntimeError("Windmill API base URL or token is unavailable")
        from platform.scheduler import build_scheduler

        self._scheduler = build_scheduler(base_url=base_url, token=token, repo_root=self._repo_root)
        return self._scheduler

    def _execute(self, run: dict[str, Any], proposal: dict[str, Any], *, actor_id: str) -> dict[str, Any]:
        if proposal["kind"] == "diagnostic_check":
            ref = f"auto-check:{proposal['hypothesis_id']}"
            run["execution_ref"] = ref
            return {
                "status": "completed",
                "execution_ref": ref,
                "output": proposal["check_result"],
            }

        scheduler = self._scheduler_client()
        payload = proposal.get("dispatch_payload", {})
        result = scheduler.submit(
            SimpleNamespace(
                workflow_id=proposal["workflow_id"],
                arguments=payload if isinstance(payload, dict) else {},
                target_vm=run["service_id"],
            ),
            requested_by=actor_id,
        )
        run["execution_ref"] = result.job_id or result.actor_intent_id
        return {
            "status": result.status,
            "job_id": result.job_id,
            "actor_intent_id": result.actor_intent_id,
            "reason": result.reason,
            "output": result.output,
            "metadata": result.metadata,
        }

    def _workflow_verification(self, proposal: dict[str, Any]) -> dict[str, Any] | None:
        workflow_id = proposal.get("workflow_id")
        if not isinstance(workflow_id, str) or not workflow_id.strip():
            return None
        workflow = self._load_workflow_catalog().get(workflow_id)
        if not isinstance(workflow, dict):
            return None
        verification = workflow.get("verification")
        return verification if isinstance(verification, dict) else None

    def _default_verification_provider(
        self,
        run: dict[str, Any],
        proposal: dict[str, Any],
        execution_result: Any,
    ) -> dict[str, Any]:
        del execution_result
        explicit = self._workflow_verification(proposal)
        service_id = run["service_id"]
        entry = self._service_health_entry(service_id)
        if explicit and explicit.get("type") == "health_probe":
            target = explicit.get("target")
            if isinstance(target, str) and target.strip():
                service_id = target
                entry = self._service_health_entry(service_id)

        if entry is None:
            return {
                "passed": True,
                "goal_achieved": True,
                "verification_skipped": True,
                "reason": "service health probe unavailable",
            }

        status = str(entry.get("status", "")).lower()
        return {
            "passed": status in OK_HEALTH_STATES,
            "goal_achieved": status in OK_HEALTH_STATES,
            "verification_skipped": False,
            "service_id": service_id,
            "observed_status": status,
            "detail": entry.get("detail"),
        }

    def _transition(
        self,
        run: dict[str, Any],
        to_state: str,
        *,
        trigger: str,
        actor: str,
        triage_report: dict[str, Any] | None = None,
        proposed_intent: dict[str, Any] | None = None,
        execution_result: dict[str, Any] | None = None,
        verification_result: dict[str, Any] | None = None,
        resolution: dict[str, Any] | None = None,
        escalation_reason: str | None = None,
        resolved: bool = False,
        clear_escalation: bool = False,
    ) -> None:
        from_state = run["current_state"]
        transition = {
            "at": isoformat(self._clock()),
            "from_state": from_state,
            "to_state": to_state,
            "trigger": trigger,
            "actor": actor,
        }
        history = run.get("history", [])
        if not isinstance(history, list):
            history = []
        history.append(transition)
        run["history"] = history
        run["current_state"] = to_state
        run["updated_at"] = transition["at"]
        if triage_report is not None:
            run["triage_report"] = triage_report
        if proposed_intent is not None:
            run["proposed_intent"] = proposed_intent
        if execution_result is not None:
            run["execution_result"] = execution_result
        if verification_result is not None:
            run["verification_result"] = verification_result
        if resolution is not None:
            run["resolution"] = resolution
        if clear_escalation:
            run["escalation_reason"] = None
        elif escalation_reason is not None:
            run["escalation_reason"] = escalation_reason
        if resolved:
            run["resolved_at"] = transition["at"]
        self._state_store.upsert(run)
        self._write_transition_event(run, transition, escalation_reason=escalation_reason)

    def _write_transition_event(
        self,
        run: dict[str, Any],
        transition: dict[str, Any],
        *,
        escalation_reason: str | None,
    ) -> None:
        metadata = {
            "run_id": run["run_id"],
            "from_state": transition["from_state"],
            "to_state": transition["to_state"],
            "trigger": transition["trigger"],
            "service_id": run["service_id"],
        }
        if escalation_reason:
            metadata["escalation_reason"] = escalation_reason
        self._ledger_writer.write(
            event_type="loop.state_transition",
            actor=f"closure-loop:{transition['actor']}",
            target_kind="service",
            target_id=run["service_id"],
            metadata=metadata,
        )
        subject = None
        event_type = None
        if transition["to_state"] == TRIAGED:
            subject = "platform.incident.opened"
            event_type = "incident.opened"
        elif transition["to_state"] in PAUSED_LOOP_STATES:
            subject = "platform.incident.escalated"
            event_type = "incident.escalated"
        elif transition["to_state"] in {RESOLVED, CASE_PROMOTED}:
            subject = "platform.incident.resolved"
            event_type = "incident.resolved"
        if event_type is not None:
            self._ledger_writer.write(
                event_type=event_type,
                actor="closure-loop",
                target_kind="service",
                target_id=run["service_id"],
                metadata={
                    "run_id": run["run_id"],
                    "state": transition["to_state"],
                    "trigger_ref": run["trigger_ref"],
                },
            )
        if subject and self._event_publisher is not None:
            self._event_publisher(
                subject,
                {
                    "run_id": run["run_id"],
                    "service_id": run["service_id"],
                    "state": transition["to_state"],
                    "trigger_type": run["trigger_type"],
                    "trigger_ref": run["trigger_ref"],
                    "ts": transition["at"],
                },
            )
