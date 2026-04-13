# ADR 0361: Semaphore Keycloak OIDC Integration

- Status: Accepted
- Implementation Status: Live applied
- Implemented In Repo Version: 0.178.130
- Implemented In Platform Version: 0.178.130
- Implemented On: 2026-04-13
- Date: 2026-04-07
- Concern: Identity, Automation, Private Access
- Depends on: ADR 0056 (Keycloak for operator and agent SSO), ADR 0149 (Semaphore for Ansible job management UI and API), ADR 0165 (Playbook / role metadata standard)
- Tags: semaphore, keycloak, oidc, sso, private-access

---

## Context

Semaphore was already the private Ansible job-management controller, but it was
still carrying a local-only login model and a draft OIDC setup that depended on
manual Keycloak client creation and a controller-local secret path under
`.local/semaphore/`.

That created four problems:

1. the desired Keycloak login path was not reconciled as part of the Semaphore
   playbook itself
2. the OIDC client secret was treated like a Semaphore-local artifact instead of
   a Keycloak-managed client credential
3. the controller-local secret path encouraged the wrong ownership boundary
4. the first draft workstream documentation contributed to the public secret
   exposure incident on 2026-04-11

## Decision

Make the Semaphore OIDC client a repo-managed Keycloak concern and converge it
as part of the normal Semaphore apply path.

### The repo-managed contract

- `playbooks/semaphore.yml` now reconciles the dedicated Keycloak `semaphore`
  client before the Semaphore runtime converge
- the mirrored client secret lives at
  `.local/keycloak/semaphore-client-secret.txt`
- `semaphore_runtime` requires that mirrored Keycloak secret locally instead of
  generating or restoring its own OIDC secret
- Semaphore keeps the repo-managed `ops-semaphore` admin login as a break-glass
  path while using Keycloak OIDC for routine operator sign-in

### Scope of the implementation

- move Semaphore controller-local artifacts to the shared local-overlay pattern
  that works from dedicated worktrees
- align the playbook, role defaults, and tests around the Keycloak-managed
  secret flow
- update the runbooks, service catalogs, dependency graph, and workstream
  records so they describe the same OIDC ownership boundary
- remove the stale manual draft instructions from the historical ws-0362 note

## Consequences

### Positive

- Semaphore now follows the same repo-managed OIDC pattern as the other
  Keycloak-backed services
- the Keycloak client secret sits under the correct owner path,
  `.local/keycloak/`, instead of the service-local `.local/semaphore/`
- a `make converge-semaphore` run is sufficient to reconcile both the dedicated
  Keycloak client and the Semaphore runtime
- the historical draft documentation no longer points operators at the leaked
  manual secret path

### Negative / Accepted Risk

- the live apply required manual recovery of three Docker Compose stacks on
  `docker-runtime` (`mail-platform`, `netbox`, and `keycloak`) because the
  Keycloak container had no network and the compose stacks were stopped after
  reachability was restored
- the Keycloak readiness probe (`http://127.0.0.1:19000/health/ready`) returned
  `Connection refused` until `docker compose ... up -d --force-recreate` was
  run for the Keycloak stack

## Verification

- focused Semaphore/Keycloak regression coverage passed:
  `35 passed in 5.23s`
- `make preflight WORKFLOW=converge-semaphore` passed and reported
  `keycloak_semaphore_client_secret` as present
- `./scripts/validate_repo.sh workstream-surfaces` passed
- `./scripts/validate_repo.sh agent-standards` reported a warning about a stale
  topology snapshot but no failures
- `make converge-semaphore env=production` completed successfully after the
  runtime recovery steps
- `GET /api/ping` returned `pong`
- `GET /auth/oidc/login` returned `200 OK`
- `make semaphore-manage ACTION=list-projects` succeeded
- the seeded `Semaphore Self-Test` template completed with status `success`

## Live Apply Evidence

- receipt: `receipts/live-applies/2026-04-13-adr-0361-semaphore-keycloak-oidc-live-apply.json`
- receipt: `receipts/live-applies/ws-0361-live-apply-apply-receipt.yaml`
- evidence summary: `receipts/live-applies/evidence/2026-04-13-ws-0361-summary.txt`
