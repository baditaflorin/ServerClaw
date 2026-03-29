# Configure Matrix Synapse

## Purpose

This runbook converges the repo-managed Matrix Synapse service defined by ADR 0255.

It covers:

- PostgreSQL database and role provisioning on `postgres-lv3`
- Matrix Synapse runtime deployment on `docker-runtime-lv3`
- a host-side Tailscale TCP proxy on `proxmox_florin` for governed operator and automation access
- public publication of `matrix.lv3.org` through the shared NGINX edge with TLS
- controller-local bootstrap artifacts mirrored under `.local/matrix-synapse/`

## Preconditions

Before running the workflow, confirm:

1. the controller has the SSH key at `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519`
2. `postgres-lv3`, `docker-runtime-lv3`, and `nginx-lv3` are already reachable through the Proxmox jump path
3. `HETZNER_DNS_API_TOKEN` is available for `matrix.lv3.org` publication and the shared edge certificate
4. OpenBao is already converged because the runtime uses the shared compose secret-injection helper

## Entrypoints

- syntax check: `make syntax-check-matrix-synapse`
- preflight: `make preflight WORKFLOW=converge-matrix-synapse`
- converge: `HETZNER_DNS_API_TOKEN=... make converge-matrix-synapse`

## Delivered Surfaces

The workflow manages these live surfaces:

- PostgreSQL database `matrix_synapse` on `postgres-lv3`
- PostgreSQL login role `matrix_synapse` on `postgres-lv3`
- Matrix Synapse runtime under `/opt/matrix-synapse` on `docker-runtime-lv3`
- public Matrix client endpoint at `https://matrix.lv3.org/_matrix/client/versions`
- Tailscale-only controller endpoint at `http://100.64.0.1:8015/_matrix/client/versions`
- repo-managed bootstrap admin account `@ops:matrix.lv3.org`
- repo-managed signing key, registration secret, and mirrored controller-local recovery artifacts

## Generated Local Artifacts

After a successful converge, these controller-local files should exist:

- `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/matrix-synapse/database-password.txt`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/matrix-synapse/ops-password.txt`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/matrix-synapse/registration-shared-secret.txt`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/matrix-synapse/server-signing.key`

Treat the entire `.local/matrix-synapse/` subtree as operational secret material and keep it out of git.

## Verification

Run these checks after converge:

1. `make syntax-check-matrix-synapse`
2. `curl -fsS https://matrix.lv3.org/_matrix/client/versions`
3. `curl -fsS http://100.64.0.1:8015/_matrix/client/versions`
4. `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.64.0.1 ops@10.10.10.20 'docker compose --file /opt/matrix-synapse/docker-compose.yml ps && sudo ls -l /opt/matrix-synapse/openbao /run/lv3-secrets/matrix-synapse && sudo test ! -e /opt/matrix-synapse/matrix-synapse.env'`
5. `curl -fsS -X POST http://100.64.0.1:8015/_matrix/client/v3/login -H 'Content-Type: application/json' -d '{"type":"m.login.password","identifier":{"type":"m.id.user","user":"ops"},"password":"'"$(cat /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/matrix-synapse/ops-password.txt)"'"}'`

## Notes

- This rollout intentionally keeps Matrix Synapse client-facing but non-federating. The repo-managed listener publishes client APIs only and does not expose a federation listener on `8448`.
- Authentication remains inside Synapse itself. `matrix.lv3.org` is published through the shared edge with TLS, but it is not wrapped in the shared oauth2-proxy browser flow.
- The host-side controller proxy is intended for governed operator and automation access. It mirrors the same client API surface over Tailscale at `http://100.64.0.1:8015`.
- The host-side controller proxy binds to the Tailscale address `100.64.0.1:8015`, not to `127.0.0.1:8015`, so host-local verification should target the Tailscale address explicitly.
- The mirrored server signing key is a recovery artifact. Rotating it changes the homeserver identity contract and must be planned explicitly instead of happening as a routine secret rollover.
