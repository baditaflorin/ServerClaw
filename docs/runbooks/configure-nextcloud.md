# Configure Nextcloud

## Purpose

This runbook converges the repo-managed `nextcloud` runtime on `docker-runtime-lv3`, provisions its PostgreSQL backend on `postgres-lv3`, and publishes `cloud.lv3.org` through the shared NGINX edge with the DAV redirect and large-upload settings required by ADR 0260.

## Managed Surfaces

- runtime role: `roles/nextcloud_runtime`
- database role: `roles/nextcloud_postgres`
- playbook: `playbooks/nextcloud.yml`
- live-apply wrapper: `playbooks/services/nextcloud.yml`
- public hostname: `https://cloud.lv3.org`
- controller-local artifacts: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/nextcloud/`

## Preconditions

- `make validate` passes
- the controller has the bootstrap SSH key configured for the Proxmox jump path
- `HETZNER_DNS_API_TOKEN` is available for public DNS publication and shared-edge certificate expansion
- OpenBao is already converged because the runtime uses the shared compose secret-injection helper

## Converge

On `main`, run:

```bash
HETZNER_DNS_API_TOKEN=... ALLOW_IN_PLACE_MUTATION=true make live-apply-service service=nextcloud env=production
```

That is the authoritative exact-main path because it replays the merged service wrapper and preserves the canonical platform-version update step.

On a non-`main` workstream branch where protected integration files must remain untouched, run:

```bash
HETZNER_DNS_API_TOKEN=... make converge-nextcloud
```

This workflow:

- ensures Hetzner DNS contains `cloud.lv3.org`
- provisions the `nextcloud` PostgreSQL role and database
- generates the database password, bootstrap admin password, and Redis password if missing
- stores runtime secrets through the shared OpenBao compose-env path
- starts or updates the Nextcloud, Redis, cron, and OpenBao-agent compose stack on `docker-runtime-lv3`
- re-renders the shared edge config so `cloud.lv3.org` is published with DAV well-known redirects and large-upload handling

## Verification

Public status:

```bash
curl -fsS https://cloud.lv3.org/status.php
```

DAV redirects:

```bash
curl -fsSI https://cloud.lv3.org/.well-known/caldav
curl -fsSI https://cloud.lv3.org/.well-known/carddav
```

Guest-local status:

```bash
ansible docker-runtime-lv3 \
  --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -e proxmox_guest_ssh_connection_mode=proxmox_host_jump \
  -m shell \
  -a 'curl -fsS http://127.0.0.1:8084/status.php'
```

Guest-local cron mode:

```bash
ansible docker-runtime-lv3 \
  --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -e proxmox_guest_ssh_connection_mode=proxmox_host_jump \
  -m shell \
  -a 'docker exec --user www-data nextcloud-app php occ config:app:get core backgroundjobs_mode'
```

Guest-local bootstrap admin query:

```bash
ansible docker-runtime-lv3 \
  --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -e proxmox_guest_ssh_connection_mode=proxmox_host_jump \
  -m shell \
  -a 'docker exec --user www-data nextcloud-app php occ user:info ops --output=json'
```

## Access Model

- `cloud.lv3.org` is intentionally app-authenticated, not edge-authenticated.
- The shared edge only publishes the route, large-upload policy, and DAV redirects.
- Routine login and session policy remain inside Nextcloud itself.

## Controller-Local Artifacts

- `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/nextcloud/database-password.txt`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/nextcloud/admin-password.txt`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/nextcloud/redis-password.txt`

These files are generated and mirrored by the repo-managed roles. They are not committed.

## Operational Notes

- Large uploads depend on both the shared edge publication settings and the Nextcloud PHP limits staying aligned at `16G`.
- CalDAV and CardDAV clients must use the published `/.well-known/caldav` and `/.well-known/carddav` redirects rather than hard-coding internal DAV paths.
- Background jobs must remain in `cron` mode because the repo-managed cron sidecar is the supported automation path.

## Rollback

- revert the repo change
- rerun `make converge-nextcloud`
- if the public route must be withdrawn immediately, rerun `make configure-edge-publication` after removing the `nextcloud` edge entry from repo state
