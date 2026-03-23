# ADR 0073: Environment Promotion Gate And Deployment Pipeline

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.79.0
- Implemented In Platform Version: not yet
- Implemented On: 2026-03-23
- Date: 2026-03-22

## Context

ADR 0072 defines a staging and production environment topology. That topology is only useful if there is a defined, governed, auditable path for moving a validated change from staging to production.

Currently, changes reach production via `make live-apply` executed by an operator against the production inventory. There is no intermediate gate, no evidence of staging validation, and no machine-readable record of which environment a change has been verified against.

With agents increasingly capable of proposing and initiating changes, a clear promotion model is essential. Without it, an agent-initiated change has no guard between a staging validation and a live mutation.

## Decision

We will define a formal promotion pipeline with three phases: **validate** → **stage** → **promote**.

### Pipeline phases

**Phase 1: Validate (repo-level)**
- `make validate` passes (YAML lint, schema validation, argument specs, ansible-lint)
- the change is on a `codex/` or `operator/` branch, not directly on `main`
- all new roles include `meta/argument_specs.yml` (ADR 0062)
- all new services are registered in the relevant catalogs (health-probe-catalog, image-catalog, secret-catalog)

**Phase 2: Stage (environment-level)**
- the playbook is run against the staging inventory: `make live-apply env=staging playbook=<name>`
- a staging receipt is written to `receipts/live-applies/staging/<date>-<playbook>.json`
- the staging health probe catalog is exercised: all probes in `health-probe-catalog.json` for the affected service return healthy
- if any probe fails, staging is not considered clean; the change must be fixed before proceeding

**Phase 3: Promote (production gate)**
- operator or privileged agent submits a promotion request via the command catalog (ADR 0048):
  ```json
  { "command": "promote-to-production",
    "args": { "branch": "codex/adr-0xyz-...", "staging_receipt": "receipts/live-applies/staging/..." },
    "approval_policy": "operator_approved" }
  ```
- the gate verifies: staging receipt exists, is less than 24 hours old, all probes passed, no open critical findings (ADR 0071) for the affected service
- if the gate passes, the production live-apply runs and a production receipt is written
- a mutation audit event (ADR 0066) is emitted covering the full promotion: staging receipt, gate outcome, production receipt

### Windmill workflow

A Windmill workflow (`deploy-and-promote`) encodes the three phases sequentially:

```
validate → stage-apply → stage-health-check → promotion-gate → prod-apply → prod-receipt
```

Each step is its own named workflow node with structured output. The workflow can be triggered by an agent (via the tool registry, ADR 0069) or by an operator through the Windmill UI.

### Promotion evidence schema

```json
{
  "promotion_id": "<uuid>",
  "branch": "codex/...",
  "playbook": "...",
  "staging_receipt": "receipts/live-applies/staging/...",
  "staging_health_check": { "passed": true, "checks": [...] },
  "gate_decision": "approved",
  "gate_actor": { "class": "operator", "id": "..." },
  "prod_receipt": "receipts/live-applies/prod/...",
  "ts": "<ISO-8601>"
}
```

Stored in `receipts/promotions/<uuid>.json`.

### Bypass (break-glass)

In a production incident requiring an immediate fix, an operator with break-glass access (ADR 0051) can run the production live-apply directly with `--extra-vars "bypass_promotion=true"`. This emits a `promotion_bypassed` audit event and requires a post-incident note within 24 hours.

## Consequences

- Every production change has a staging receipt as a prerequisite, making regressions introduced only in production extremely unlikely.
- Agent-initiated changes are bounded: an agent can trigger the full pipeline but cannot bypass the operator approval gate on the promotion step.
- The 24-hour staging receipt window prevents stale validations from being used to justify a production change.
- The promotion workflow is a Windmill-managed surface; if Windmill is unavailable, the break-glass path must be used and documented.

## Implementation Notes

- Repo automation now ships the promotion pipeline entrypoint at [scripts/promotion_pipeline.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/promotion_pipeline.py), the promotion receipt schema at [docs/schema/promotion-receipt.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/schema/promotion-receipt.json), and the operator runbook at [docs/runbooks/environment-promotion-pipeline.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/environment-promotion-pipeline.md).
- The command/workflow contracts are now first-class in [config/command-catalog.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/command-catalog.json) and [config/workflow-catalog.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/workflow-catalog.json), with `promote-to-production` enforcing operator approval before any governed production promotion.
- Live-apply receipt handling now supports staged receipts under [receipts/live-applies/staging/](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/receipts/live-applies/staging), and promotion evidence is reserved under [receipts/promotions/](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/receipts/promotions).
- The Windmill converge now seeds the repo-managed wrapper [config/windmill/scripts/deploy-and-promote.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/windmill/scripts/deploy-and-promote.py), so operators and agents call the same promotion logic rather than duplicating policy in a separate workflow definition.

## Boundaries

- This pipeline applies to service deployments and configuration changes. Infrastructure-level changes (new VM provisioning, bridge configuration, Proxmox settings) follow the existing command catalog flow with an operator approval gate but do not require a staging pre-validation because staging shares the same Proxmox host.
- The staging validation does not test external integrations (real DNS propagation, external SMTP relay). Those are validated post-promotion in production.
- Performance and load testing are out of scope for the first iteration of this pipeline.
