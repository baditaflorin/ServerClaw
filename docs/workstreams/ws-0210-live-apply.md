# Workstream ws-0210-live-apply: ADR 0210 Live Apply From Latest `origin/main`

- ADR: [ADR 0210](../adr/0210-canonical-domain-models-over-vendor-schemas.md)
- Title: Separate canonical publication models from delivery-adapter fields and verify the live public-surface automation path
- Status: in_progress
- Implemented In Repo Version: N/A
- Live Applied In Platform Version: N/A
- Implemented On: N/A
- Live Applied On: N/A
- Branch: `codex/ws-0210-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/worktree-ws-0210-live-apply`
- Owner: codex
- Depends On: `adr-0074-human-navigation-and-platform-ops-portal`, `adr-0076-subdomain-governance`, `adr-0139-subdomain-exposure-registry`, `adr-0207-anti-corruption-layers-at-provider-boundaries`
- Conflicts With: none
- Shared Surfaces: `config/subdomain-exposure-registry.json`, `docs/schema/subdomain-exposure-registry.schema.json`, `scripts/subdomain_exposure_audit.py`, `scripts/ops_portal/app.py`, `scripts/ops_portal/templates/partials/overview.html`, `collections/ansible_collections/lv3/platform/roles/ops_portal_runtime/defaults/main.yml`, `collections/ansible_collections/lv3/platform/roles/ops_portal_runtime/templates/ops-portal.env.j2`, `docs/runbooks/subdomain-exposure-audit.md`, `docs/runbooks/subdomain-governance.md`, `docs/runbooks/ops-portal-down.md`, `tests/test_subdomain_exposure_audit.py`, `tests/test_interactive_ops_portal.py`, `receipts/live-applies/2026-03-28-adr-0210-canonical-domain-models-live-apply.json`, `workstreams.yaml`

## Scope

- move the shared subdomain exposure registry from a flat adapter-shaped schema to a canonical publication model with explicit nested delivery-adapter details
- keep DNS, NGINX, and oauth2-proxy specifics at the adapter edge while shared consumers read the normalized publication contract
- expose the canonical publication contract in the interactive ops portal so the live platform reflects the ADR in a user-facing surface
- replay the affected runtime and audit automation from this isolated worktree, verify the platform result end to end, and record durable live-apply evidence

## Verification

- pending implementation

## Live Evidence

- pending live apply

## Outcome

- pending
