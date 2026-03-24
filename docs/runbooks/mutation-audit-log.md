# Mutation Audit Log

## Purpose

This runbook defines the structured mutation audit trail introduced by ADR 0066.

ADR 0115 supersedes ADR 0066 in the repository by adding the Postgres-backed mutation ledger. Use this runbook for the legacy JSONL/Loki event contract and the current dual-write bridge; use [docs/runbooks/mutation-ledger.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server-mutation-ledger/docs/runbooks/mutation-ledger.md) for the ledger schema, replay API, and audit-log migration workflow.

It covers:

- the canonical event schema
- the controller-side emitter and local JSON-lines sink
- Ansible callback emission for tagged mutation tasks
- command-catalog approval audit events
- the seeded Windmill helper for workflow-side emission

## Canonical Sources

- schema: [docs/schema/mutation-audit-event.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/schema/mutation-audit-event.json)
- controller emitter: [scripts/mutation_audit.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/mutation_audit.py)
- Ansible callback: [callback_plugins/mutation_audit.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/callback_plugins/mutation_audit.py)
- Windmill helper: [config/windmill/scripts/lv3-mutation-audit.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/windmill/scripts/lv3-mutation-audit.py)
- approval gate surface: [scripts/command_catalog.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/command_catalog.py)

## Event Contract

Each event records:

- `ts`: ISO-8601 UTC timestamp
- `actor.class`: `operator`, `agent`, `service`, or `automation`
- `actor.id`: the principal or runtime identity
- `surface`: `ansible`, `windmill`, `openbao`, `nats`, `command-catalog`, or `manual`
- `action`: stable lowercase verb-noun identifier such as `approve.command`
- `target`: resource or contract identifier
- `outcome`: `success`, `failure`, or `rejected`
- `correlation_id`: workflow, session, or job identifier
- `evidence_ref`: receipt path or related evidence reference when available

Keep events non-secret. Do not include passwords, tokens, request bodies, or other sensitive payload data.

## Current Repo Implementation

The current workstream branch implements these emission paths:

- `scripts/command_catalog.py --check-approval` emits `command-catalog` audit events for approvals and rejections
- tagged Ansible mutation tasks emit `ansible` audit events through the callback plugin
- the Windmill converge seeds `f/lv3/mutation_audit_emit` as a reusable workflow helper
- operators can emit an explicit `manual` event from the controller

The default local sink on the controller is:

```bash
/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/state/mutation-audit/mutation-audit.jsonl
```

Live host-side sinks now exist at:

```bash
/var/log/platform/mutation-audit.jsonl
```

on:

- `proxmox_florin`
- `docker-runtime-lv3`

ADR 0052 ships both host files into Loki under `{job="mutation-audit"}`. The controller-side emitter remains repo-local by default.

## Validate The Schema

```bash
scripts/mutation_audit.py --validate-schema
```

## Emit A Manual Event

```bash
scripts/mutation_audit.py \
  --emit \
  --actor-class operator \
  --actor-id ops \
  --surface manual \
  --action document.manual_change \
  --target proxmox_florin \
  --outcome success \
  --evidence-ref docs/runbooks/mutation-audit-log.md
```

## Audit A Command Approval

```bash
scripts/command_catalog.py \
  --check-approval \
  --command configure-network \
  --requester-class human_operator \
  --approver-classes human_operator \
  --validation-passed \
  --preflight-passed \
  --receipt-planned \
  --audit-correlation-id review-20260322-001 \
  --audit-actor-id ops
```

## Ansible Usage

The repository enables the `mutation_audit` callback globally in [ansible.cfg](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/ansible.cfg). A task emits only when:

1. it carries the `mutation` tag
2. it changes live state or fails while attempting a mutation

For stable action names, define task-local variables such as:

```yaml
vars:
  mutation_audit_action: start.windmill_stack
  mutation_audit_target: windmill-runtime
tags:
  - mutation
```

## Sink Configuration

Optional environment variables:

- `LV3_MUTATION_AUDIT_FILE`: override the local JSON-lines sink path, or set `off` to disable file writes
- `LV3_MUTATION_AUDIT_LOKI_URL`: Loki push endpoint for controller-side events
- `LV3_MUTATION_AUDIT_LOKI_LABELS`: JSON object with extra Loki labels
- `LV3_MUTATION_AUDIT_ACTOR_ID`: default actor id for Ansible callback events
- `LV3_MUTATION_AUDIT_CORRELATION_ID`: default correlation id for Ansible callback events
- `LV3_MUTATION_AUDIT_WEBHOOK`: webhook endpoint for the seeded Windmill helper
- `LV3_LEDGER_DSN`: optional Postgres DSN that enables dual-write from the controller emitter into `ledger.events`
- `LV3_LEDGER_NATS_URL`: optional NATS URL override for `platform.ledger.event_written` fan-out after successful inserts

## Notes

- The repo-managed Windmill helper path is `f/lv3/mutation_audit_emit`.
- OpenBao already writes its own audit-device log as part of the runtime config, and ADR 0052 ships that native audit feed into Loki with `job="mutation-audit"` and `surface="openbao"`.
- NATS-triggered mutations and full manual-operation coverage still require the later control-plane workstreams that introduce those surfaces.
