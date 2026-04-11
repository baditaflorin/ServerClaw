# ADR 0066: Structured Mutation Audit Log

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.78.0
- Implemented In Platform Version: 0.37.0
- Implemented On: 2026-03-23
- Date: 2026-03-22

## Context

Live-apply receipts (ADR 0032) record structured evidence after successful convergence runs. However, receipts only cover Ansible playbook applies. The following mutation classes currently leave no structured trail:

- Windmill workflow executions that mutate live state
- OpenBao token operations and policy changes
- command-catalog approvals and rejections
- NATS message publications that trigger downstream mutations
- manual operator actions outside of managed playbooks

Without a unified audit trail, post-incident reconstruction requires correlating Grafana logs, git history, and human memory — all of which are incomplete for ad hoc mutations.

## Decision

We will emit a structured JSON mutation audit event for every platform mutation across all governed surfaces.

Event schema (stored in `docs/schema/mutation-audit-event.json`):

```json
{
  "ts": "<ISO-8601>",
  "actor": { "class": "operator|agent|service|automation", "id": "<principal>" },
  "surface": "ansible|windmill|openbao|nats|command-catalog|manual",
  "action": "<verb>.<noun>",
  "target": "<resource identifier>",
  "outcome": "success|failure|rejected",
  "correlation_id": "<workflow or session id>",
  "evidence_ref": "<receipt path or URL if applicable>"
}
```

Emission points:

1. Ansible roles emit audit events via a post-task callback plugin (`callback_plugins/mutation_audit.py`) that fires after any task tagged `mutation`
2. Windmill workflows call a shared audit helper at job start and end
3. the command-catalog approval gate emits events for approvals, rejections, and executions
4. OpenBao audit device is configured to forward to the same sink

Sink: events are written to Loki (ADR 0052) under a dedicated label `{job="mutation-audit"}` and simultaneously appended to a local JSON-lines file at `/var/log/platform/mutation-audit.jsonl` on the host as a durable offline record.

Agents can query the Loki label for audit events without SSH access to reconstruct what changed and when.

## Consequences

- Post-incident reconstruction across all mutation surfaces becomes a single Loki query instead of multi-system correlation.
- Agents gain a canonical mutation history they can summarize or diff against repo state.
- Every mutation surface must be instrumented; missing a surface means incomplete audit data until it is added.
- The audit log must not contain secrets or PII; instrumentation code must scrub before emitting.

## Implementation Notes

- This workstream branch adds the canonical schema at [docs/schema/mutation-audit-event.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/docs/schema/mutation-audit-event.json), a shared controller-side emitter at [scripts/mutation_audit.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/scripts/mutation_audit.py), and the Ansible callback at [callback_plugins/mutation_audit.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/callback_plugins/mutation_audit.py).
- Repo automation ships the canonical schema at [docs/schema/mutation-audit-event.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/docs/schema/mutation-audit-event.json), the shared controller-side emitter at [scripts/mutation_audit.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/scripts/mutation_audit.py), and the Ansible callback at [callback_plugins/mutation_audit.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/callback_plugins/mutation_audit.py).
- Command-catalog approval checks emit structured events, and the Windmill converge now seeds and verifies the reusable `f/lv3/mutation_audit_emit` helper in the managed workspace.
- Host-local JSONL sinks at `/var/log/platform/mutation-audit.jsonl` are verified live on both `proxmox-host` and `docker-runtime`, and ADR 0052 ships those files into Loki under the `mutation-audit` job.
- OpenBao's native audit-device file remains its own raw feed at `/opt/openbao/logs/audit.log`, but ADR 0052 now scrapes that file through the same mutation-audit log-shipping path on `docker-runtime`.

## Boundaries

- Read-only operations (queries, health checks, status reads) are not audited at this layer.
- The audit log supplements but does not replace git history or live-apply receipts.
- Compliance-grade immutable audit storage is out of scope; this is an operational audit layer.
