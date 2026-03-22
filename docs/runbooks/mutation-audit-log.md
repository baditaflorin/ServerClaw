# Mutation Audit Log

## Purpose

This runbook defines the structured mutation audit trail introduced by ADR 0066.

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
- the Windmill converge seeds `f/lv3/mutation_audit` as a reusable workflow helper
- operators can emit an explicit `manual` event from the controller

The default local sink on the controller is:

```bash
/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/state/mutation-audit/mutation-audit.jsonl
```

For live host-side rollout, point the sink at `/var/log/platform/mutation-audit.jsonl` and wire the same stream into Loki once ADR 0052 is applied.

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

## Notes

- OpenBao already writes its own audit-device log as part of the runtime config. Converging that raw feed into the structured mutation stream remains part of the live rollout work.
- NATS-triggered mutations and full manual-operation coverage still require the later control-plane workstreams that introduce those surfaces.
