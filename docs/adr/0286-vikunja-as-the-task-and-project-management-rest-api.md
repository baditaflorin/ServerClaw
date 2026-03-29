# ADR 0286: Vikunja As The Task And Project Management REST API

- Status: Accepted
- Implementation Status: Not Implemented
- Implemented In Repo Version: N/A
- Implemented In Platform Version: N/A
- Date: 2026-03-29

## Context

The platform has no structured task and project tracking layer. Operator
action items from alerts, deployment outcomes, and maintenance windows are
tracked in Mattermost threads, Outline documents, or sticky notes. There is
no API to:

- create a task programmatically when an alert fires (e.g. "Trivy found a
  critical CVE—create a remediation task and assign it")
- query open tasks by project, label, or assignee from a Windmill approval
  flow
- close a task when an automated remediation completes and emit the state
  change to NATS JetStream

The result is that automated platform workflows cannot record the human work
they trigger, and there is no queryable registry of outstanding operator
obligations. Checking what needs to be done requires reading Mattermost
history.

Vikunja is a CPU-only, open-source task management service. It exposes a
complete REST API with a published OpenAPI specification served at
`/api/v1/docs.json`. Every operation—project CRUD, task creation, label
management, assignee updates, comment creation, and webhook configuration—is
available as a documented, authenticated HTTP call. The web UI is built
entirely on top of this API; no management operation is GUI-only.

## Decision

We will deploy **Vikunja** as the task and project management REST API for
the platform.

### Deployment rules

- Vikunja runs as a Docker Compose service on the docker-runtime VM using
  the official `vikunja/vikunja` image (the all-in-one frontend+API image)
- Authentication is delegated to Keycloak via OIDC (ADR 0063); local
  Vikunja accounts are disabled except for the break-glass service account
  whose API token is stored in OpenBao (ADR 0077)
- The service is published under the platform subdomain model (ADR 0021) at
  `tasks.<domain>`; the REST API is at `tasks.<domain>/api/v1/`
- Vikunja uses the shared PostgreSQL cluster (ADR 0042) with a dedicated
  `vikunja` database
- Persistent state is included in the backup scope (ADR 0086)
- Secrets (database password, OIDC client credentials, JWT secret) are
  injected from OpenBao following ADR 0077

### API-first operation rules

- Projects (equivalent to boards or spaces) and their initial label set are
  declared in the Ansible role `defaults/main.yml` project manifest and
  created idempotently via the Vikunja REST API on each converge; projects
  are never created exclusively through the web UI
- Platform automation that generates operator work items calls the task
  creation API (`POST /api/v1/projects/{projectId}/tasks`); standard fields
  are:
  - `title` — concise description of the required action
  - `description` — Markdown body with context, links to relevant ADRs or
    alerts, and acceptance criteria
  - `due_date` — ISO 8601 timestamp; mandatory for security remediation tasks
  - `labels` — at least one label from the platform taxonomy
    (`security`, `maintenance`, `deployment`, `incident`, `review`)
  - `assignees` — the responsible operator's Keycloak user ID
- Automated remediations that resolve a task call `POST
  /api/v1/tasks/{taskId}` with `done: true` and append a completion comment
  via `POST /api/v1/tasks/{taskId}/comments`
- Task state changes (created, completed, overdue) are pushed to NATS
  JetStream (ADR 0276) via Vikunja webhooks (`POST /api/v1/webhooks`);
  downstream consumers can react to task events without polling the API
- The Vikunja API token for automation is stored in OpenBao and retrieved
  at Windmill script initialisation; it is scoped to the specific project
  the automation owns

### Alert-to-task integration rules

- the Prometheus Alertmanager webhook receiver calls a Windmill flow that
  creates a Vikunja task in the `platform-ops` project for every alert
  that reaches `firing` state with severity `critical` or `warning`
- the task title follows the template:
  `[{severity}] {alert_name} on {instance}`
- the Alertmanager receiver fires a second call when the alert resolves,
  closing the corresponding task via API and appending the resolved
  timestamp as a comment

## Consequences

**Positive**

- Platform alerts automatically produce traceable operator tasks; there is
  a queryable API to see what is outstanding without reading Mattermost.
- Automated remediations can close their own tasks via API, keeping the
  task list accurate without manual housekeeping.
- The project and label taxonomy is version-controlled in the Ansible role;
  the task structure is reproducible after a fresh deploy.
- Vikunja webhooks to NATS JetStream decouple downstream consumers (e.g.
  a Windmill SLA reporting flow) from polling the task API.

**Negative / Trade-offs**

- Vikunja is a task tracking surface, not a full project management suite;
  complex dependencies, Gantt views, and resource planning are out of scope.
- The alert-to-task integration creates tasks for every firing alert; noisy
  alerts will produce a cluttered task list. Alert quality must be maintained
  to keep the task list actionable.

## Boundaries

- Vikunja tracks operator tasks and project work items; it does not replace
  Mattermost (ADR 0074) for real-time team communication or Outline for
  long-form documentation.
- Vikunja tasks are the human-work complement to automated Windmill flows;
  they record what a human must do, not what the automation does.
- Vikunja is not used for customer-facing issue tracking; it is an internal
  operator tool.
- The Vikunja web UI is available for task management; bulk operations and
  project setup performed through the UI that modify the project catalogue
  declared in the Ansible role are treated as drift and reconciled on the
  next converge.

## Related ADRs

- ADR 0021: Public subdomain publication at the NGINX edge
- ADR 0042: PostgreSQL as the shared relational database
- ADR 0063: Keycloak SSO for internal services
- ADR 0077: Compose secrets injection pattern
- ADR 0086: Backup and recovery for stateful services
- ADR 0096: SLO probes and Blackbox exporter
- ADR 0124: Ntfy for push notifications
- ADR 0276: NATS JetStream as the platform event bus

## References

- <https://vikunja.io/docs/api/>
- <https://try.vikunja.io/api/v1/docs>
