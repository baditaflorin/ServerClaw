# ADR 0361: Semaphore Keycloak OIDC Integration

- Status: Accepted
- Implementation Status: Partial
- Implemented In Repo Version: not yet merged
- Implemented In Platform Version: not yet applied
- Implemented On: 2026-04-11
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

- live apply from this workstation is currently blocked by host reachability:
  `make converge-semaphore env=production` reached the scoped Ansible run and
  then failed when SSH to `proxmox-host` at `100.64.0.1:22` timed out
- direct probes to `65.108.75.123:22`, `100.118.189.95:22`,
  `100.118.189.95:2222`, `10.10.10.92:22`, `http://100.64.0.1:8020`, and
  `https://100.64.0.1:8006/api2/json/` were also unreachable from this machine
  during the same session
- `tailscale status --json` still showed the subnet-router peer online, but the
  local client reported coordination-server health warnings and both
  `tailscale ping 100.64.0.1` and `tailscale ping 10.10.10.92` timed out

## Verification

- focused Semaphore/Keycloak regression coverage passed:
  `32 passed in 3.19s`
- targeted controller-local and catalog validation reported `25 passed, 1
  failed`; the lone failure is unrelated current-mainline drift in
  `tests/test_dependency_graph.py` because `litellm` is now a direct hard
  dependency of `postgres` but the baseline assertion set has not yet been
  updated
- `make syntax-check-semaphore` passed
- `make preflight WORKFLOW=converge-semaphore` passed and correctly reported
  `keycloak_semaphore_client_secret` as absent-before-apply
- the branch-local workstream registry and ownership surfaces were regenerated
  and validated

## Remaining Apply Step

This ADR is repository-ready but not yet live-applied.

When host reachability is restored:

1. rerun `make converge-semaphore env=production`
2. verify the private controller `/api/ping` and `/auth/oidc/login` endpoints
3. verify `make semaphore-manage ACTION=list-projects`
4. run the seeded `Semaphore Self-Test` template
5. record the final live-apply receipt(s)
6. update this ADR from `Partial` to `Live applied`
