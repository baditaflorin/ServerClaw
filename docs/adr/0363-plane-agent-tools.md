# ADR 0370: Plane Agent Tools — Programmatic Task Management for Agents

- Status: Accepted
- Implementation Status: Not Implemented
- Implemented In Repo Version: not applicable
- Implemented In Platform Version: not applicable
- Implemented On: not applicable
- Date: 2026-04-06
- Tags: agents, tools, plane, tasks, api, automation

## Context

ADR 0360 established Plane as the Agent Task HQ. ADR 0069 provides the governed
tool registry. ADR 0369 defines the reusable pattern for service API tools.

Currently, the only way for agents to interact with Plane is through
`sync_plane_agent_issues.py`, which operates at the workstream level. Agents
cannot create ad-hoc tasks, list tasks, update status, or add comments
programmatically through the tool registry.

The PlaneClient at `platform/ansible/plane.py` already supports all of these
operations. The infrastructure exists; what is missing is the governed tool
surface.

The immediate pain point: agents cannot create a blocking task (e.g. "Hetzner
DNS brownout blocks scheduler.lv3.org deployment") without human intervention.

## Decision

### Tools added to the agent tool registry

Five Plane tools, following the ADR 0369 gateway pattern:

| Tool name | Category | approval_required | PlaneClient method |
|---|---|---|---|
| `list-plane-tasks` | observe | false | `list_issues()` |
| `get-plane-task` | observe | false | issue detail endpoint |
| `create-plane-task` | execute | true | `create_issue()` |
| `update-plane-task` | execute | false | `update_issue()` |
| `add-plane-comment` | execute | false | `add_comment()` |

### list-plane-tasks (observe)

List issues in a Plane project with optional state filter. Defaults to AW
(Agent Work) project.

- Input: `project` (optional, default "AW"), `state_name` (optional filter)
- Output: `{count, tasks: [{id, name, state_name, priority, created_at}]}`

### get-plane-task (observe)

Get full details of a single issue by UUID.

- Input: `issue_id` (required), `project` (optional)
- Output: Full Plane issue object with resolved `state_name`

### create-plane-task (execute, approval_required)

Create a new issue. This is the key tool that enables agents to track blockers,
follow-up tasks, and operational findings.

- Input: `title` (required), plus optional `description_html`, `project`,
  `state_name` (default "Todo"), `label_names`, `priority`
- Output: Created issue with `id`, `name`, `state_name`, `project_identifier`

### update-plane-task (execute)

Update status, title, labels, or description of an existing issue.

- Input: `issue_id` (required), plus optional `state_name`, `name`,
  `description_html`, `priority`, `project`
- Output: Updated issue object

### add-plane-comment (execute)

Add a comment to an existing issue.

- Input: `issue_id` (required), `comment_html` (required), `project` (optional)
- Output: Created comment object with `id`

### Credential and context resolution

Following ADR 0369:

- Auth file: `.local/plane/admin-auth.json` (already exists, contains
  `base_url`, `api_token`, `workspace_slug`, `verify_ssl`)
- Environment override: `LV3_PLANE_AUTH_FILE`
- Project resolution: The `project` input accepts a project identifier string
  ("AW", "ADR"). Resolved to UUID via `PlaneClient.list_projects()`.

### State and label resolution

- `state_name` resolved via `PlaneClient.list_states()` matching by `name`
- `label_names` resolved via `PlaneClient.list_labels()`, with auto-creation
  of missing labels

## Consequences

### Positive

- Agents can create tasks programmatically, unblocking operational tracking
- Plane becomes a two-way surface: humans create tasks for agents, agents
  create tasks for humans or other agents
- All Plane tool calls are audit-logged via the existing mutation audit
- The tools reuse PlaneClient, inheriting retry and rate-limit handling

### Negative / Trade-offs

- `create-plane-task` requires human approval, adding friction; intentional
  for the first iteration and can be relaxed once audit proves reliable
- State and label resolution adds 2-3 extra API calls per invocation;
  negligible at self-hosted rate limits
- Tools default to AW project; ADR project requires explicit `project: "ADR"`

## Related ADRs

- ADR 0069: Agent tool registry and governed tool calls
- ADR 0360: Plane as Agent Task HQ
- ADR 0369: Agent Service API Gateway pattern
- ADR 0368: Nomad OIDC and agent tools (prior art)
