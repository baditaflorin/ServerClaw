# Configure n8n

## Purpose

This runbook converges the repo-managed `n8n` runtime on `docker-runtime-lv3`, provisions its PostgreSQL backend on `postgres-lv3`, and publishes `n8n.lv3.org` through the shared NGINX edge.

## Managed Surfaces

- runtime role: `roles/n8n_runtime`
- database role: `roles/n8n_postgres`
- playbook: `playbooks/n8n.yml`
- public hostname: `https://n8n.lv3.org`
- controller-local artifacts: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/n8n/`

## Preconditions

- `make validate` passes
- the controller has the bootstrap SSH key configured for the Proxmox jump path
- `HETZNER_DNS_API_TOKEN` is available for public DNS publication
- OpenBao is already converged because the runtime uses the shared compose secret-injection helper

## Converge

```bash
HETZNER_DNS_API_TOKEN=... make converge-n8n
```

This workflow:

- ensures Hetzner DNS contains `n8n.lv3.org`
- provisions the `n8n` PostgreSQL role and database
- generates the database password, owner password, and encryption key if missing
- stores runtime secrets through the shared OpenBao compose-env path
- starts or updates the n8n compose stack on `docker-runtime-lv3`
- re-renders the shared edge config so `n8n.lv3.org` is published

## Verification

Public health:

```bash
curl -fsS https://n8n.lv3.org/healthz
```

Guest-local readiness:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -o IdentitiesOnly=yes \
  -J ops@100.118.189.95 \
  ops@10.10.10.20 \
  'curl -fsS http://127.0.0.1:5678/healthz/readiness'
```

Guest-local owner login:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -o IdentitiesOnly=yes \
  -J ops@100.118.189.95 \
  ops@10.10.10.20 \
  "curl -fsS -X POST http://127.0.0.1:5678/rest/login \
    -H 'Content-Type: application/json' \
    -d '{\"emailOrLdapLoginId\":\"ops@lv3.org\",\"password\":\"$(cat /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/n8n/owner-password.txt)\"}'"
```

## Access Model

- The editor at `https://n8n.lv3.org/` is protected by the shared oauth2-proxy and Keycloak edge flow.
- The following paths are intentionally unauthenticated at the edge:
  - `/healthz`
  - `/webhook/`
  - `/webhook-test/`
  - `/webhook-waiting/`

This split is deliberate. Human operators use the protected editor path, while machine callers must reach webhook endpoints without browser SSO.

## Controller-Local Artifacts

- `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/n8n/database-password.txt`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/n8n/owner-password.txt`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/n8n/encryption-key.txt`

These files are generated and mirrored by the repo-managed roles. They are not committed.

## Workflow Management Boundary

Do not wire automatic workflow import into converge.

Upstream `n8n import:workflow` can deactivate workflows on import. Keep workflow import and export as an explicit operator step until the platform has a safer repo-to-runtime promotion path for n8n content.

## Optional API Key Bootstrap

The runtime leaves n8n's public API available behind the normal application auth boundary, but the repo does not auto-create a broad-scope API key.

If an API key is required:

1. sign in through `https://n8n.lv3.org`
2. create the narrowest key and scopes that satisfy the integration
3. store the resulting credential under the repo's controller-local secret management path before automating any use of it

## Rollback

- revert the repo change
- rerun `make converge-n8n`
- if the public route must be withdrawn immediately, rerun `make configure-edge-publication` after removing the `n8n` edge entry from repo state
