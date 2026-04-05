# ADR 0360: Plane as Agent Task HQ — Live Work Tracking for LLM Agents

- Status: Accepted
- Implementation Status: In Progress
- Implemented In Repo Version: not applicable
- Implemented In Platform Version: not applicable
- Implemented On: not applicable
- Date: 2026-04-05
- Tags: platform, plane, agents, observability, workflow, automation

## Context

### How agent work is tracked today

Agent work is currently tracked ad-hoc across three disconnected surfaces:

1. **Git worktrees** — each agent session creates a branch (`claude/<name>`) and a
   worktree under `.claude/worktrees/<name>`. The branch name is the only
   persistent identity for the session.

2. **Workstream YAML files** (`workstreams/active/<id>.yaml`) — created by the
   agent before work begins, regenerated into `workstreams.yaml`. These record
   intent and branch state but are static: they do not update as work progresses
   and are not human-interactive at runtime.

3. **ADR markdown** — architectural decisions land in `docs/adr/` and are
   synchronized into Plane issues via `scripts/sync_adrs_to_plane.py`. This
   gives a durable record of *decisions* but not of *in-flight work or task
   assignments*.

There is no live, observable view of what agents are doing. A human cannot open
a dashboard and see "three agents are active; one is writing the Keycloak role,
one is doing a live-apply, one is stuck on a failing test." Agents cannot assign
sub-tasks to other agents or leave notes that survive their session. Humans
cannot add a task to an active agent session without committing a file to git.

The Plane instance at `tasks.lv3.org` (ADR 0193) is currently used only for the
ADR synchronization project. It is a capable task board sitting mostly idle
while the real operational picture lives scattered across shell sessions and YAML
files.

### Why this matters now

As the number of concurrent agent sessions grows, the coordination gap gets
worse. An agent working on a database migration and another working on a network
policy can silently conflict. A human reviewing work has no way to prioritize
without reading every active branch. There is no place to say "block this agent
until the postgres role is merged."

## Decision

Plane becomes the **primary human-visible and agent-visible surface for
in-flight work**. Git (workstreams, branches, ADRs) remains authoritative for
the *record of decisions and history*. Plane is the *live projection* of that
record — the HQ where work is observable, assignable, and composable.

### 1. A dedicated Plane project for agent work

A second Plane project, **"Agent Work"** (identifier `AW`), is created alongside
the existing `ADR` project. This project holds one issue per active worktree
session. It is distinct from the ADR project so that structural decisions and
active work do not pollute each other.

### 2. Agent identity inside Plane

Each Claude Code worktree session is identified by its **worktree name**
(e.g. `pensive-heyrovsky`, `ws-0360-main-merge`). This becomes the issue title
prefix. Because Plane issues can have assignees, a shared automation user
(`lv3-automation@lv3.org`) owns all agent-created issues. The worktree name
distinguishes sessions; assignee ownership is uniform across all automated
work.

There is intentionally no per-LLM-model identity or per-conversation identity.
The session boundary is the worktree. One worktree = one Plane issue.

### 3. Issue lifecycle

| Event | Agent action |
|-------|-------------|
| Worktree registered (workstream opened) | Create Plane issue in `AW` with title `[<worktree>] <workstream summary>`, status **In Progress**, label `agent` |
| Work blocked (waiting on dependency or user input) | Transition issue to **Blocked**, add a comment with the blocker description |
| ADR produced | Add a link to the ADR issue in the `ADR` project as a related issue |
| Branch pushed / PR ready | Add PR URL as a comment, transition to **In Review** |
| Workstream closed / branch merged | Transition to **Done**, add final commit hash |

Agents update the issue at natural checkpoints only — not on every file edit.
The goal is signal density, not noise.

### 4. Humans can interact via Plane

A human can:
- Add a comment to a running agent's issue — the agent checks for comments when
  it reads its own issue at session start and after each major step
- Change the issue status to **Blocked** to signal the agent should pause
- Create a sub-issue in `AW` and assign it to the agent's issue as a dependency
- Add labels to influence routing (e.g. `needs-review`, `fast-track`)

Agents are not expected to poll Plane continuously. The contract is: read your
own issue at session start; read it again after a major milestone (e.g.
post-converge, post-test). This is enough for human oversight without adding
latency to every file operation.

### 5. Dual-write strategy

Git is authoritative. Plane is a projection. The rules are:

- If Plane is unreachable, agents continue without blocking. The workstream YAML
  is the fallback record.
- If a Plane issue diverges from the workstream YAML (e.g. issue says Done but
  branch is still open), the workstream YAML wins.
- Plane issue IDs are recorded in the workstream YAML under
  `plane_issue_id: AW-<n>` after creation. This is the sync anchor for future
  updates.
- The `scripts/sync_plane_agent_issues.py` script (to be written) handles
  idempotent create-or-update for any workstream file that has an active agent
  branch. It is called by the same hooks that regenerate `workstreams.yaml`.

### 6. When NOT to use Plane for tracking

Plane is the right tool when:
- Work spans multiple commits or sessions
- A human might need to prioritize, block, or redirect the work
- The work produces an observable artifact (ADR, PR, live-apply)
- Multiple agents are working on related concerns

Use plain git (workstream YAML only, no Plane issue) when:
- Single-commit fixes initiated and completed in one session
- Automated housekeeping (e.g. version bumps, manifest regeneration) that
  produces no ADR and requires no human review
- Runbook-only changes with no architectural surface

Use GitHub/Gitea Issues instead of Plane when:
- The task is a public-facing bug report intended for contributors outside the
  platform team
- The issue originates from an external repo consumer and should live beside
  that repo's issue tracker

### 7. Cross-surface sync

A single agent action (e.g. completing a live-apply) may legitimately need to
update three surfaces:

```
git workstream YAML  →  plane AW issue  →  ADR implementation status
```

The agent script for closing a workstream is responsible for all three writes in
sequence. If any one fails, the others are still attempted (best-effort), and the
YAML write is always done last (authoritative fallback). The sequence:

1. Transition Plane issue to Done, add final commit as comment
2. Update ADR `Implementation Status` field if this workstream implemented an ADR
3. Close the workstream YAML (`status: merged`, `merged_at: <date>`)
4. Regenerate `workstreams.yaml`

Because scripts write to multiple places, the scripts must be idempotent: running
them twice must produce the same result, not duplicate Plane comments or toggle
ADR status.

### 8. Agent-to-agent coordination via Plane

An agent can create a **dependency link** from its own issue to another agent's
issue in Plane. This signals "I am blocked on `pensive-heyrovsky` finishing
before I can start my live-apply." Plane's blocking/blocked-by link type is used
for this. The blocking agent checks its issue at its next checkpoint and sees the
downstream dependency.

This replaces the current ad-hoc pattern of agents serializing by branch name
convention alone.

## Consequences

### Positive

- Humans get a live, readable view of what all agents are doing without reading
  YAML files or git logs.
- Humans can assign work to agents by adding a comment or sub-issue to an active
  agent session.
- Agent-to-agent coordination gets an explicit dependency graph (Plane
  blocking/blocked-by) instead of implicit branch naming.
- Plane's search and label system lets humans filter "show me all agent issues
  touching keycloak" across sessions.
- ADR decisions, live work, and historical record are linked via Plane's related
  issues — Plane becomes the connective tissue, not a silo.

### Negative / Trade-offs

- Agents must implement Plane API calls at defined lifecycle points. This adds
  ~1–3 Plane API calls per session. At Plane's self-hosted rate limits this is
  negligible, but it is a new dependency.
- If Plane is down or unreachable, the tracking layer degrades gracefully but
  humans lose visibility. The mitigation is the workstream YAML fallback and
  the Uptime Kuma monitor on `tasks.lv3.org`.
- The `plane_issue_id` field in workstream YAML creates a soft coupling between
  git state and Plane state. Over time, stale `Done` issues in Plane may not
  match merged branches if the sync script is not run on close. The `--repair`
  flag in the sync script handles drift.
- Agent sessions that crash without cleanup leave `In Progress` issues orphaned.
  A nightly cron job closes any `AW` issue whose branch no longer exists in git.

## Limitations of Plane as the sole tracking surface

Plane is a task board. It is not:
- A real-time message queue (use ntfy or Matrix for instant agent alerts)
- A structured config registry (use openbao or inventory vars for facts)
- A log aggregation tool (use Loki/Grafana for agent execution logs)
- A CI/CD pipeline view (use Woodpecker/Gitea Actions for build status)

Tasks that need **immediate human notification** should use ntfy. Tasks that need
**structured query by other agents at runtime** should use the Plane API
(lightweight) or a workstream YAML key (durable). Tasks that need **log-level
audit** should use structured Ansible callback logs.

The value of Plane is its *human interface*: rich labels, status transitions,
comments, related issues, and a board view. Do not try to make it do the job of
ntfy, Loki, or openbao.

## Implementation Notes

Phase 1 (this ADR):
1. Create the `AW` Plane project via `scripts/bootstrap_plane.py --project agent-work`
   (extend the existing bootstrap script).
2. Add `plane_issue_id` as an optional field to the workstream YAML schema.
3. Write `scripts/sync_plane_agent_issues.py` — create-or-update idempotent, reads
   `workstreams/active/*.yaml`, maps to `AW` issues, records `plane_issue_id` back.
4. Add `sync_plane_agent_issues.py` call to the workstream-close step in the
   agent protocol (AGENTS.md and CLAUDE.md).
5. Deploy via `make converge-plane env=production` after the RabbitMQ secret fix
   in this same branch lands.

Phase 2 (follow-on):
- Add the human comment-read step to the CLAUDE.md session start checklist
- Add nightly orphan-close cron via Windmill
- Cross-link ADR issues to `AW` issues in the sync script

## Related ADRs

- ADR 0193: Plane Kanban Task Board (deployed Plane, ADR sync)
- ADR 0163: Multi-Agent Handoff Protocol
- ADR 0130: Agent State Persistence Across Workflow Boundaries
- ADR 0044: Windmill for Agent and Operator Workflows
- ADR 0146: Langfuse for Agent Observability
