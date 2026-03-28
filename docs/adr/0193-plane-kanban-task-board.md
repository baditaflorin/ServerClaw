# ADR 0193: Plane Kanban Task Board

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.177.27
- Implemented In Platform Version: 0.177.12
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

We will run a self-hosted Plane task board on `docker-runtime-lv3` and treat it as a repo-managed service.

The initial production contract is:

1. Plane runs as a compose-managed stack on `docker-runtime-lv3`.
2. Plane stores application state in the managed PostgreSQL VM and keeps cache, queue, and object-storage sidecars local to the runtime VM.
3. The browser surface is published at `tasks.lv3.org` behind the existing shared Keycloak-backed edge authentication path.
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
- the service adds another stateful application footprint to `docker-runtime-lv3`
- merge-to-`main` still needs the usual shared-truth updates after the live apply is verified on this branch

## Implementation Notes

This ADR is implemented by the `ws-0193-live-apply` workstream on branch `codex/ws-0193-live-apply`.

The live-apply branch must:

- add the Plane service to the repo-managed topology and validation catalogs
- converge the PostgreSQL and runtime automation
- publish `tasks.lv3.org` through the authenticated edge
- bootstrap the initial Plane workspace and project
- verify issue creation plus ADR synchronization end to end

Shared integration files remain intentionally unchanged on the workstream branch until merge to `main`.

## Live Apply Status

As of 2026-03-27, the full repo-managed Plane path is replayed and verified from this workstream branch across the Proxmox host, PostgreSQL VM, Docker runtime VM, and shared NGINX edge VM.

Verified live evidence includes:

- `ANSIBLE_HOST_KEY_CHECKING=False ansible-playbook -i inventory/hosts.yml playbooks/plane.yml --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -e env=production -e proxmox_guest_ssh_connection_mode=proxmox_host_jump` completed successfully
- `http://100.64.0.1:8011/api/instances/` returns `200`
- the seeded `lv3-platform` workspace and `ADR` project exist and are reachable through `make plane-manage`
- `scripts/sync_adrs_to_plane.py` synchronized 202 ADR records into Plane, and the full playbook replay now tolerates a transient first sync failure through role-level retries
- the docker-runtime stack is up on `docker-runtime-lv3`, with the Plane API, web, proxy, admin, live, worker, MinIO, RabbitMQ, and Valkey containers running
- `https://tasks.lv3.org/` returns `302` to the shared oauth2-proxy sign-in path, and that sign-in path returns `302` into the shared Keycloak realm instead of the previous `https://nginx.lv3.org/` fallback
- the shared NGINX edge certificate expansion now succeeds through the repo-managed `webroot` ACME path
