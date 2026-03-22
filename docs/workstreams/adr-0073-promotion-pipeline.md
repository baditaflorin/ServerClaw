# Workstream ADR 0073: Environment Promotion Gate And Deployment Pipeline

- ADR: [ADR 0073](../adr/0073-environment-promotion-gate-and-deployment-pipeline.md)
- Title: Formal staging-to-production promotion workflow with evidence gates and operator approval
- Status: ready
- Branch: `codex/adr-0073-promotion-pipeline`
- Worktree: `../proxmox_florin_server-promotion-pipeline`
- Owner: codex
- Depends On: `adr-0072-staging-environment`, `adr-0044-windmill`, `adr-0048-command-catalog`, `adr-0064-health-probe-contracts`, `adr-0066-mutation-audit-log`
- Conflicts With: none
- Shared Surfaces: `config/command-catalog.json`, `receipts/`, Windmill workflows, `Makefile`

## Scope

- create Windmill workflow `deploy-and-promote` with five sequential nodes: validate → stage-apply → stage-health-check → promotion-gate → prod-apply → prod-receipt
- add `promote-to-production` command to `config/command-catalog.json` with `operator_approved` approval policy
- define promotion receipt schema in `docs/schema/promotion-receipt.json`
- write staging receipts to `receipts/live-applies/staging/` (separate from production `receipts/live-applies/`)
- write promotion receipts to `receipts/promotions/`
- add `make promote SERVICE=<name> STAGING_RECEIPT=<path>` convenience target
- document the promotion model in `docs/runbooks/environment-promotion-pipeline.md`
- add `bypass_promotion` audit event emission to the break-glass path

## Non-Goals

- automated rollback on promotion failure (first iteration: operator-initiated rollback only)
- performance or load testing as part of the pipeline (out of scope per ADR)

## Expected Repo Surfaces

- Windmill workflow definition for `deploy-and-promote`
- `docs/schema/promotion-receipt.json`
- `receipts/live-applies/staging/` directory
- `receipts/promotions/` directory
- updated `config/command-catalog.json`
- `docs/runbooks/environment-promotion-pipeline.md`
- updated `Makefile` with `promote` target
- `docs/adr/0073-environment-promotion-gate-and-deployment-pipeline.md`
- `docs/workstreams/adr-0073-promotion-pipeline.md`
- `workstreams.yaml`

## Expected Live Surfaces

- `deploy-and-promote` Windmill workflow available in the `lv3` workspace
- `promote-to-production` available as an approvable command in the command catalog
- `receipts/promotions/` directory writable by the automation identity

## Verification

- run a full promotion of a low-risk service (e.g. ops portal static files) through the pipeline end-to-end
- verify staging receipt written before promotion gate is evaluated
- verify production receipt written after promotion completes
- verify bypass path emits `promotion_bypassed` audit event in Loki

## Merge Criteria

- at least one real promotion has been executed and a receipt is in `receipts/promotions/`
- the operator approval gate blocks promotion without an explicit approval event
- health check failure in staging correctly blocks the pipeline before the production step
- all receipt files are valid against their JSON schemas

## Notes For The Next Assistant

- implement the staging health check step first — it is the most critical gate and the easiest to validate independently
- the Windmill workflow can be developed and tested in staging Windmill before deploying to production Windmill
- the `deploy-and-promote` workflow should call existing playbooks via the Windmill Ansible runner, not duplicate their task logic
