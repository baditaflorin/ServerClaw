# ADR 0193: Plane Kanban Task Board

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.177.27
- Implemented In Platform Version: 0.130.34
- Implemented On: 2026-03-27
- Date: 2026-03-27

## Context

The platform now has enough live services and decision history that infrastructure work is harder to coordinate from ADR markdown and ad hoc task notes alone.

The repo already has:

- repo-managed service catalogs and live-apply workflows
- authenticated internal browser surfaces through the shared NGINX edge
- controller-local automation identities and secrets for service bootstraps

What is still missing is a repo-governed task board that can represent active infrastructure work without introducing manual drift or a hidden SaaS-only operating path.

## Decision

We will run a self-hosted Plane task board on `docker-runtime` and treat it as a repo-managed service.

The initial production contract is:

1. Plane runs as a compose-managed stack on `docker-runtime`.
2. Plane stores application state in the managed PostgreSQL VM and keeps cache, queue, and object-storage sidecars local to the runtime VM.
3. The browser surface is published at `tasks.example.com` behind the existing shared Keycloak-backed edge authentication path.
4. Controller and automation access uses a dedicated Proxmox-host Tailscale TCP proxy.
5. Repo automation bootstraps the initial admin, workspace, project, and API token locally.
6. ADR metadata can be synchronized into Plane issues idempotently by repo-managed automation.

## Consequences

**Positive**

- active infrastructure work gains a durable, searchable board without leaving repo-managed automation
- ADR state can be projected into a task board without hand-created duplicate issues
- browser access stays inside the existing LV3 edge authentication model

**Negative / Trade-offs**

- Plane does not yet integrate with the shared Keycloak realm as an in-app OIDC client, so the browser SSO story is edge-auth only for now
- the service adds another stateful application footprint to `docker-runtime`
- merge-to-`main` still needs the usual shared-truth updates after the live apply is verified on this branch

## Implementation Notes

This ADR was first implemented by the `ws-0193-live-apply` workstream on branch `codex/ws-0193-live-apply`.

The live-apply branch:

- add the Plane service to the repo-managed topology and validation catalogs
- converge the PostgreSQL and runtime automation
- publish `tasks.example.com` through the authenticated edge
- bootstrap the initial Plane workspace and project
- verify issue creation plus ADR synchronization end to end

The follow-on `ws-0193-main-merge` workstream replayed the service from the latest merged `origin/main`, recorded the final mainline receipt, and updated the protected integration truth after the replay was verified.

## Live Apply Status

As of 2026-03-28, the merged-main replay is verified across the Proxmox host, PostgreSQL VM, Docker runtime VM, and shared NGINX edge VM.

Verified live evidence includes:

- `make live-apply-service service=plane env=production ALLOW_IN_PLACE_MUTATION=true` reconverged the Proxmox host, PostgreSQL VM, Docker runtime VM, Plane bootstrap, and ADR-sync path from the merged-main candidate
- `make configure-edge-publication env=production` completed successfully after regenerating the shared `build/changelog-portal` and `build/docs-portal` artifacts needed by the NGINX publication lane
- `http://100.64.0.1:8011/api/instances/` returns `200`
- `make plane-manage ACTION=whoami` reports the seeded `ops@example.com` identity against workspace `lv3-platform`, project `ADR`, and private controller URL `http://100.64.0.1:8011`
- the controller-local ADR sync summary at `.local/plane/adr-sync-summary.json` now records 218 synchronized ADR issues for the live `ADR` Plane project
- `https://tasks.example.com/` returns `302` to the shared oauth2-proxy sign-in path, confirming the authenticated public entrypoint instead of the previous `https://nginx.example.com/` fallback

The merged-main replay also confirmed two shared dependency repairs that are now part of the recorded evidence:

- the missing provider-side Hetzner A records for `coolify.example.com` and `apps.example.com` were repaired to match repo intent before the shared DNS lane was replayed
- the Plane runtime secret-injection lane now depends on OpenBao already being unsealed; the mainline replay was only resumed once the local OpenBao API again reported `sealed: false`
