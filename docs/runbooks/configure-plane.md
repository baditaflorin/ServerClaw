# Configure Plane

## Purpose

This runbook defines the repo-managed Plane runtime for platform work tracking and ADR synchronization on `docker-runtime`.

Plane is published at `tasks.example.com`, but browser access is gated by the shared Authentik-backed edge auth flow. API automation uses the Proxmox host's private Tailscale TCP proxy. Do not pin a Tailscale IP in committed files or local auth artifacts: the address can change when a node is re-enrolled.

The shared edge certificate now expands through the repo-managed NGINX `webroot` ACME path on `nginx-edge`. Hetzner DNS still governs the public A records, but routine Plane edge certificate expansion no longer depends on DNS-01 propagation.

## Canonical Surfaces

- playbook: [playbooks/plane.yml](../../playbooks/plane.yml)
- roles: [plane_postgres](../../collections/ansible_collections/lv3/platform/roles/plane_postgres) and [plane_runtime](../../collections/ansible_collections/lv3/platform/roles/plane_runtime)
- bootstrap helper: [scripts/plane_bootstrap.py](../../scripts/plane_bootstrap.py)
- governed wrappers: [scripts/plane_tool.py](../../scripts/plane_tool.py) and [scripts/sync_adrs_to_plane.py](../../scripts/sync_adrs_to_plane.py)
- controller-local auth artifacts: `.local/plane/`

## Access Model

- public browser surface: `https://tasks.example.com`
- private controller path: `http://127.0.0.1:18093` while the operator SSH forward is running
- public access is protected by the shared oauth2-proxy and Authentik edge flow
- controller-local auth artifacts are mirrored under `.local/plane/`
- the workspace slug is deployment-specific and stored in `.local/plane/admin-auth.json`; project identifiers are read from that workspace
- ADR markdown under `docs/adr/` is synchronized into Plane issues through the repo-managed wrapper instead of ad hoc UI entry

### Open the private controller tunnel

The API endpoint is intentionally not published without authentication. If the workstation cannot connect directly to the tailnet proxy, forward it through the existing Proxmox SSH access path. Read the current management Tailscale address from the local deployment identity/inventory, the Plane proxy port from `platform_port_assignments.plane_host_proxy_port`, and use the operator's existing SSH alias for the Proxmox host:

```bash
ssh -NT \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=3 \
  -L "127.0.0.1:18093:${MANAGEMENT_TAILSCALE_IPV4}:${PLANE_HOST_PROXY_PORT}" \
  "${PROXMOX_HOST_SSH_ALIAS}"
```

Set those three shell variables from the local identity, inventory, and SSH configuration before running the command. Keep the SSH process in the foreground while using the Plane CLI; this makes forwarding failures visible. The listener must remain bound to `127.0.0.1`, never a LAN or public address. The matching `base_url` in `.local/plane/admin-auth.json` is `http://127.0.0.1:18093`.

Verify the forward before running authenticated automation:

```bash
curl -fsS http://127.0.0.1:18093/api/instances/
```

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
make plane-manage ACTION=list-projects
```

List seeded ADR issues:

```bash
make plane-manage ACTION=list-issues PLANE_ARGS='--project ADR'
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
2. Start the private controller tunnel, then run `curl -fsS http://127.0.0.1:18093/api/instances/`
3. `make plane-manage ACTION=whoami`
4. `make plane-manage ACTION=list-projects`
5. `make plane-manage ACTION=list-issues PLANE_ARGS='--project ADR'`
6. `make plane-manage ACTION=sync-adrs`
7. `curl -I https://tasks.example.com/`
8. If the API is healthy but the application is not, inspect the Plane runtime through the repo-managed service runbook and approved SSH alias; do not expose or list secret/data directories.

If step 7 returns `302` to `/oauth2/sign_in`, treat that as the expected authenticated public entrypoint. A second probe to the quoted sign-in URL should then return `302` into `https://id.example.com/...`.

If step 7 returns `308` to `https://nginx.example.com/`, treat that as a shared NGINX publication blocker rather than a Plane runtime failure. The loopback-forwarded controller path remains the authoritative automation surface until the edge publication lane is reconciled.

If the shared publication lane fails because `build/changelog-portal/` or `build/docs-portal/` is missing, regenerate the shared static artifacts first and then replay the edge publication only:

```bash
make generate-ops-portal
make generate-changelog-portal
make docs
make configure-edge-publication env=production
```

## Operating Rules

- keep public browser access behind the shared edge auth flow
- use the loopback-forwarded private controller path and governed wrapper for bootstrap and API automation
- treat the Plane bootstrap workspace and ADR project as repo-managed seed state
- document any emergency UI-authored mutation immediately and bring it back to repo truth in the same turn
