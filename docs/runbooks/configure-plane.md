# Configure Plane

## Purpose

This runbook defines the repo-managed Plane runtime for the LV3 task board and ADR synchronization workflow on `docker-runtime-lv3`.

Plane is public on this platform at `tasks.lv3.org`, but browser access is gated by the shared Keycloak-backed edge auth flow. The private controller path remains available through the Proxmox host Tailscale TCP proxy for governed bootstrap and API automation.

The shared edge certificate now expands through the repo-managed NGINX `webroot` ACME path on `nginx-lv3`. Hetzner DNS still governs the public A records, but routine Plane edge certificate expansion no longer depends on DNS-01 propagation.

## Canonical Surfaces

- playbook: [playbooks/plane.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/playbooks/plane.yml)
- roles: [roles/plane_postgres](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/plane_postgres) and [roles/plane_runtime](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/plane_runtime)
- bootstrap helper: [scripts/plane_bootstrap.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/plane_bootstrap.py)
- governed wrappers: [scripts/plane_tool.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/plane_tool.py) and [scripts/sync_adrs_to_plane.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/sync_adrs_to_plane.py)
- controller-local auth artifacts: `.local/plane/`

## Access Model

- public browser surface: `https://tasks.lv3.org`
- private controller path: `http://100.64.0.1:8011`
- public access is protected by the shared oauth2-proxy and Keycloak edge flow
- controller-local auth artifacts are mirrored under `.local/plane/`
- the seeded workspace is `lv3-platform` and the seeded project identifier is `ADR`
- ADR markdown under `docs/adr/` is synchronized into Plane issues through the repo-managed wrapper instead of ad hoc UI entry

## Primary Commands

Syntax-check the workflow:

```bash
make syntax-check-plane
```

Converge Plane live:

```bash
HETZNER_DNS_API_TOKEN=... make converge-plane
```

Show the bootstrap identity:

```bash
make plane-manage ACTION=whoami
```

List Plane projects:

```bash
make plane-manage ACTION=list-projects PLANE_ARGS='--workspace lv3-platform'
```

List seeded ADR issues:

```bash
make plane-manage ACTION=list-issues PLANE_ARGS='--workspace lv3-platform --project ADR'
```

Synchronize ADR markdown into Plane:

```bash
make plane-manage ACTION=sync-adrs
```

## Generated Local Artifacts

The workflow maintains controller-local artifacts under `.local/plane/`:

- `database-password.txt`
- `secret-key.txt`
- `live-server-secret-key.txt`
- `rabbitmq-password.txt`
- `aws-secret-access-key.txt`
- `bootstrap-admin-password.txt`
- `api-token.txt`
- `admin-auth.json`
- `bootstrap-spec.json`
- `adr-sync-summary.json`

## Verification

After a converge:

1. `make syntax-check-plane`
2. `curl -fsS http://100.64.0.1:8011/api/instances/`
3. `make plane-manage ACTION=whoami`
4. `make plane-manage ACTION=list-projects PLANE_ARGS='--workspace lv3-platform'`
5. `make plane-manage ACTION=list-issues PLANE_ARGS='--workspace lv3-platform --project ADR'`
6. `make plane-manage ACTION=sync-adrs`
7. `curl -I https://tasks.lv3.org/`
8. `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.64.0.1 ops@10.10.10.20 'docker compose --file /opt/plane/docker-compose.yml ps && sudo ls -l /run/lv3-secrets/plane /etc/lv3/plane /opt/plane/data'`

If step 7 returns `302` to `/oauth2/sign_in`, treat that as the expected authenticated public entrypoint. A second probe to the quoted sign-in URL should then return `302` into `https://sso.lv3.org/...`.

If step 7 returns `308` to `https://nginx.lv3.org/`, treat that as a shared NGINX publication blocker rather than a Plane runtime failure. The controller path at `http://100.64.0.1:8011` remains the authoritative automation surface until the edge publication lane is reconciled.

## Operating Rules

- keep public browser access behind the shared edge auth flow
- use the private controller path and governed wrapper for bootstrap and API automation
- treat the Plane bootstrap workspace and ADR project as repo-managed seed state
- document any emergency UI-authored mutation immediately and bring it back to repo truth in the same turn
