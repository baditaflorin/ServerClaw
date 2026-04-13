# Workstream ws-0361-live-apply: ADR 0361 Semaphore Keycloak OIDC Integration

- ADR: [ADR 0361](../adr/0361-semaphore-keycloak-oidc-integration.md)
- Title: verify and live-apply the repo-managed Semaphore Keycloak OIDC flow from the latest origin/main
- Status: merged
- Included In Repo Version: 0.178.130
- Branch-Local Receipt: `receipts/live-applies/2026-04-13-adr-0361-semaphore-keycloak-oidc-live-apply.json`
- Evidence Summary: `receipts/live-applies/evidence/2026-04-13-ws-0361-summary.txt`
- Prior Receipt: `receipts/live-applies/2026-04-11-adr-0361-semaphore-keycloak-oidc-live-apply.json`
- Mainline Receipt: `receipts/live-applies/2026-04-13-adr-0361-semaphore-keycloak-oidc-live-apply.json`
- Implemented On: 2026-04-13
- Live Applied On: 2026-04-13
- Live Applied In Platform Version: 0.178.130
- Original Branch Base: `origin/main@86390fcc8a07fca2a58670f60ec4cf6b9d0278eb`
- Latest Upstream Checked: `origin/main@258e264c6ff5cde2ba4ea822442567fb0f9bf7a4`
- Branch: `codex/ws-0361-live-apply`
- Worktree: `.worktrees/ws-0361-live-apply`
- Owner: codex
- Depends On: `ADR 0056`, `ADR 0149`, `ADR 0165`, `ADR 0167`, `ADR 0361`
- Conflicts With: none

## Scope

- move Semaphore from a controller-generated OIDC secret to a dedicated repo-managed Keycloak client secret mirrored under `.local/keycloak/`
- converge the Keycloak client before the Semaphore runtime so the controller always consumes the live Keycloak secret contract
- update the Semaphore runbooks, service catalogs, workstream state, and postmortem follow-up so the rotated-secret workflow is clear and reproducible
- verify the repo automation path and the live Semaphore converge from the latest exact-main base

## Outcome

- dedicated worktree and branch created from `origin/main@86390fcc8a07fca2a58670f60ec4cf6b9d0278eb`
- Semaphore and Keycloak role wiring now reconciles the dedicated Keycloak client before the Semaphore runtime and consumes the mirrored secret from `.local/keycloak/semaphore-client-secret.txt`
- the service catalogs, dependency graph, runbooks, active workstream record, and sanitized historical `ws-0362` note now describe the same repo-managed OIDC boundary
- `make converge-semaphore env=production` completed after restoring reachability and recovering the affected compose stacks on `docker-runtime`

## Verification

- `uv run --with pytest --with pyyaml python -m pytest -q tests/test_semaphore_runtime_role.py tests/test_semaphore_playbook.py tests/test_keycloak_runtime_role.py` passed with `35 passed in 5.23s`
- `make preflight WORKFLOW=converge-semaphore` passed and reported `keycloak_semaphore_client_secret` as present
- `./scripts/validate_repo.sh workstream-surfaces` passed
- `./scripts/validate_repo.sh agent-standards` reported a warning about a stale topology snapshot but no failures
- `GET /api/ping` returned `pong`
- `GET /auth/oidc/login` returned `200 OK`
- `make semaphore-manage ACTION=list-projects` succeeded
- `Semaphore Self-Test` template completed with status `success`

## Live Apply Notes

- recovered `mail-platform`, `netbox`, and `keycloak` compose stacks on `docker-runtime` after regaining host access
- forced a Keycloak container recreate to restore network connectivity before the readiness probe succeeded

## Notes

- protected integration files were updated during the exact-main integration step (VERSION, changelog, README status blocks, versions/stack.yaml)
