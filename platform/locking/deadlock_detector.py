from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from platform.concurrency import parse_timestamp
from platform.coordination import AgentCoordinationMap, AgentSessionEntry
from platform.intent_queue import IntentQueue, QueuedIntent
from platform.ledger import LedgerWriter

from .registry import ResourceLockRegistry


GraphPayload = dict[str, list[dict[str, str]]]


@dataclass(frozen=True)
class Participant:
    context_id: str
    agent_id: str
    priority: int
    intent_id: str | None


@dataclass(frozen=True)
class DeadlockResolution:
    cycle: list[str]
    victim: Participant
    survivors: list[Participant]
    resolution_action: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "cycle": list(self.cycle),
            "victim": {
                "context_id": self.victim.context_id,
                "agent_id": self.victim.agent_id,
                "priority": self.victim.priority,
                "intent_id": self.victim.intent_id,
            },
            "survivors": [
                {
                    "context_id": participant.context_id,
                    "agent_id": participant.agent_id,
                    "priority": participant.priority,
                    "intent_id": participant.intent_id,
                }
                for participant in self.survivors
            ],
            "resolution_action": self.resolution_action,
        }


class DeadlockDetector:
    def __init__(
        self,
        *,
        lock_registry: ResourceLockRegistry | None = None,
        coordination_map: AgentCoordinationMap | None = None,
        intent_queue: IntentQueue | None = None,
        ledger_writer: LedgerWriter | None = None,
        nats_publisher: Callable[[str, dict[str, Any]], None] | None = None,
        agent_notification_publisher: Callable[[str, dict[str, Any]], None] | None = None,
        job_canceller: Callable[[str], None] | None = None,
    ) -> None:
        self.lock_registry = lock_registry or ResourceLockRegistry()
        self.coordination_map = coordination_map or AgentCoordinationMap()
        self.intent_queue = intent_queue or IntentQueue()
        self.ledger_writer = ledger_writer
        self.nats_publisher = nats_publisher
        self.agent_notification_publisher = agent_notification_publisher
        self.job_canceller = job_canceller

    def build_wait_for_graph(self) -> GraphPayload:
        edges: list[dict[str, str]] = []
        seen: set[tuple[str, str, str]] = set()
        queue_entries = self.intent_queue.read_waiting()
        sessions = {entry.context_id: entry for entry in self.coordination_map.read_all()}

        for intent in queue_entries:
            for resource_path in intent.required_locks:
                holder = self.lock_registry.get_holder(resource_path, exclude_holder=f"agent:{intent.context_id}")
                if holder is None:
                    continue
                source = f"intent:{intent.intent_id}"
                target = holder if holder.startswith("agent:") else f"agent:{holder}"
                key = (source, target, resource_path)
                if key not in seen:
                    edges.append({"source": source, "target": target, "resource": resource_path})
                    seen.add(key)
                agent_source = f"agent:{intent.context_id}"
                key = (agent_source, target, resource_path)
                if key not in seen:
                    edges.append({"source": agent_source, "target": target, "resource": resource_path})
                    seen.add(key)

        for session in sessions.values():
            if session.status != "blocked" or not session.blocked_reason:
                continue
            if not session.blocked_reason.startswith("waiting_for:"):
                continue
            resource_path = session.blocked_reason.removeprefix("waiting_for:")
            holder = self.lock_registry.get_holder(resource_path, exclude_holder=f"agent:{session.context_id}")
            if holder is None:
                continue
            source = f"agent:{session.context_id}"
            target = holder if holder.startswith("agent:") else f"agent:{holder}"
            key = (source, target, resource_path)
            if key not in seen:
                edges.append({"source": source, "target": target, "resource": resource_path})
                seen.add(key)

        nodes = sorted({edge["source"] for edge in edges} | {edge["target"] for edge in edges})
        return {"nodes": [{"id": node} for node in nodes], "edges": edges}

    def detect_deadlocks(self, graph: GraphPayload) -> list[list[str]]:
        adjacency = self._adjacency(graph)
        index = 0
        stack: list[str] = []
        on_stack: set[str] = set()
        indices: dict[str, int] = {}
        low_links: dict[str, int] = {}
        cycles: list[list[str]] = []

        def strong_connect(node: str) -> None:
            nonlocal index
            indices[node] = index
            low_links[node] = index
            index += 1
            stack.append(node)
            on_stack.add(node)

            for target in adjacency.get(node, []):
                if target not in indices:
                    strong_connect(target)
                    low_links[node] = min(low_links[node], low_links[target])
                elif target in on_stack:
                    low_links[node] = min(low_links[node], indices[target])

            if low_links[node] != indices[node]:
                return
            component: list[str] = []
            while stack:
                current = stack.pop()
                on_stack.remove(current)
                component.append(current)
                if current == node:
                    break
            if len(component) > 1:
                cycles.append(sorted(component))
            elif component and component[0] in adjacency.get(component[0], set()):
                cycles.append(component)

        for node in sorted(adjacency):
            if node not in indices:
                strong_connect(node)
        return cycles

    def detect_livelocks(self, queue_entries: list[QueuedIntent], *, min_attempts: int = 4, older_than_seconds: int = 300) -> list[QueuedIntent]:
        now = self.intent_queue._now()  # noqa: SLF001 - shared clock for deterministic tests
        return [
            entry
            for entry in queue_entries
            if entry.status == "waiting"
            and entry.attempts >= min_attempts
            and (now - self._parse(entry.queued_at)).total_seconds() >= older_than_seconds
        ]

    def resolve_deadlock(self, cycle: list[str]) -> DeadlockResolution:
        participants = self._participants_for_cycle(cycle)
        if not participants:
            raise ValueError("deadlock cycle has no resolvable participants")
        victim = max(participants, key=lambda participant: (participant.priority, participant.context_id, participant.intent_id or ""))
        survivors = [participant for participant in participants if participant != victim]
        action = self.abort_agent_intent(victim, cycle=cycle, survivors=survivors)
        return DeadlockResolution(
            cycle=cycle,
            victim=victim,
            survivors=survivors,
            resolution_action=action,
        )

    def abort_agent_intent(self, victim: Participant, *, cycle: list[str], survivors: list[Participant]) -> str:
        if victim.intent_id and self.job_canceller is not None:
            self.job_canceller(victim.intent_id)
        self.lock_registry.release_all(f"agent:{victim.context_id}")
        self.lock_registry.release_all(victim.context_id)
        if victim.intent_id:
            self.intent_queue.requeue(victim.intent_id, delay_seconds=60, reason="deadlock_resolution_retry")
        session = self.coordination_map.read(victim.context_id)
        if session is not None:
            self.coordination_map.publish(self._aborted_session(session, cycle=cycle))
        if victim.intent_id and self.ledger_writer is not None:
            self.ledger_writer.write(
                event_type="execution.deadlock_aborted",
                actor="platform.deadlock_detector",
                actor_intent_id=victim.intent_id,
                target_kind="intent",
                target_id=victim.intent_id,
                metadata={
                    "deadlock_cycle": cycle,
                    "victim_context_id": victim.context_id,
                    "survivors": [participant.context_id for participant in survivors],
                    "aborted_by": "deadlock_detector",
                },
            )
        if self.nats_publisher is not None and victim.intent_id:
            event = self._build_event(
                "platform.execution.deadlock_aborted",
                {
                    "intent_id": victim.intent_id,
                    "victim_context_id": victim.context_id,
                    "cycle_nodes": cycle,
                },
                actor_id="platform.deadlock_detector",
                context_id=victim.context_id,
            )
            self.nats_publisher(event["topic"], event)
        if self.agent_notification_publisher is not None and victim.intent_id:
            self.agent_notification_publisher(
                f"platform.agent.deadlock_notification.{victim.context_id}",
                {
                    "type": "deadlock_aborted",
                    "intent_id": victim.intent_id,
                    "reason": "Aborted as the lowest-priority participant in a deadlock cycle.",
                    "retry_delay_seconds": 60,
                },
            )
        return "aborted_and_requeued"

    def run_once(self) -> dict[str, Any]:
        graph = self.build_wait_for_graph()
        cycles = self.detect_deadlocks(graph)
        resolutions = [self.resolve_deadlock(cycle) for cycle in cycles]
        waiting_entries = self.intent_queue.read_waiting()
        livelocks = self.detect_livelocks(waiting_entries)
        if self.nats_publisher is not None:
            for cycle in cycles:
                event = self._build_event(
                    "platform.execution.deadlock_detected",
                    {"cycle_nodes": cycle},
                    actor_id="platform.deadlock_detector",
                )
                self.nats_publisher(event["topic"], event)
            for entry in livelocks:
                event = self._build_event(
                    "platform.execution.livelock_detected",
                    {"intent_id": entry.intent_id, "attempts": entry.attempts},
                    actor_id="platform.deadlock_detector",
                    context_id=entry.context_id,
                )
                self.nats_publisher(event["topic"], event)
        return {
            "graph": graph,
            "deadlocks_detected": len(cycles),
            "deadlock_cycles": cycles,
            "resolutions": [resolution.as_dict() for resolution in resolutions],
            "livelocks_detected": len(livelocks),
            "livelocks": [entry.as_dict() for entry in livelocks],
        }

    @staticmethod
    def _adjacency(graph: GraphPayload) -> dict[str, set[str]]:
        adjacency: dict[str, set[str]] = {}
        for node in graph.get("nodes", []):
            node_id = str(node.get("id", "")).strip()
            if node_id:
                adjacency.setdefault(node_id, set())
        for edge in graph.get("edges", []):
            source = str(edge.get("source", "")).strip()
            target = str(edge.get("target", "")).strip()
            if not source or not target:
                continue
            adjacency.setdefault(source, set()).add(target)
            adjacency.setdefault(target, set())
        return adjacency

    def _participants_for_cycle(self, cycle: list[str]) -> list[Participant]:
        participants: dict[str, Participant] = {}
        for node in cycle:
            if node.startswith("agent:"):
                session = self.coordination_map.read(node.removeprefix("agent:"))
                if session is None:
                    continue
                participant = self._participant_from_session(session)
                participants[participant.context_id] = participant
                continue
            if node.startswith("intent:"):
                intent = self.intent_queue.get(node.removeprefix("intent:"))
                if intent is None:
                    continue
                participant = Participant(
                    context_id=intent.context_id,
                    agent_id=intent.agent_id,
                    priority=intent.priority,
                    intent_id=intent.intent_id,
                )
                participants[participant.context_id] = participant
        return sorted(participants.values(), key=lambda participant: (participant.priority, participant.context_id))

    def _participant_from_session(self, session: AgentSessionEntry) -> Participant:
        priority = 50
        if session.current_intent_id:
            queued = self.intent_queue.get(session.current_intent_id)
            if queued is not None:
                priority = queued.priority
        return Participant(
            context_id=session.context_id,
            agent_id=session.agent_id,
            priority=priority,
            intent_id=session.current_intent_id,
        )

    @staticmethod
    def _aborted_session(session: AgentSessionEntry, *, cycle: list[str]) -> AgentSessionEntry:
        return AgentSessionEntry(
            context_id=session.context_id,
            agent_id=session.agent_id,
            session_label=session.session_label,
            current_phase="idle",
            current_intent_id=session.current_intent_id,
            current_workflow_id=session.current_workflow_id,
            current_target=session.current_target,
            held_locks=[],
            held_lanes=list(session.held_lanes),
            reserved_budget=dict(session.reserved_budget),
            batch_id=session.batch_id,
            batch_stage=session.batch_stage,
            step_index=session.step_index,
            step_count=session.step_count,
            progress_pct=session.progress_pct,
            last_heartbeat=session.last_heartbeat,
            status="active",
            blocked_reason=f"deadlock_aborted:{','.join(cycle)}",
            error_count=session.error_count,
            started_at=session.started_at,
            estimated_completion=session.estimated_completion,
            expires_at=session.expires_at,
        )

    @staticmethod
    def _parse(value: str):
        return parse_timestamp(value)

    @staticmethod
    def _build_event(topic: str, payload: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        from platform.events import build_envelope

        return build_envelope(topic, payload, **kwargs)
