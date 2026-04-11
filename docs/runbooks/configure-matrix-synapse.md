# Configure Matrix Synapse

## Purpose

This runbook converges the repo-managed Matrix Synapse service defined by ADR
0255 and the first repo-managed mautrix bridge adapters from ADR 0256.

It covers:

- PostgreSQL database and role provisioning on `postgres`
- bridge-specific PostgreSQL databases and roles for `mautrix-discord` and `mautrix-whatsapp`
- Matrix Synapse runtime deployment on `docker-runtime`
- `mautrix-discord` and `mautrix-whatsapp` bridge deployment on `docker-runtime`
- a host-side Tailscale TCP proxy on `proxmox-host` for governed operator and automation access
- public publication of `matrix.example.com` through the shared NGINX edge with TLS
- controller-local bootstrap artifacts mirrored under `.local/matrix-synapse/`

## Preconditions

Before running the workflow, confirm:

1. the controller has the SSH key at `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519`
2. `postgres`, `docker-runtime`, and `nginx-edge` are already reachable through the Proxmox jump path
3. `HETZNER_DNS_API_TOKEN` is available for `matrix.example.com` publication and the shared edge certificate
4. OpenBao is already converged because the runtime uses the shared compose secret-injection helper

## Entrypoints

- syntax check: `make syntax-check-matrix-synapse`
- preflight: `make preflight WORKFLOW=converge-matrix-synapse`
- converge: `HETZNER_DNS_API_TOKEN=... make converge-matrix-synapse`

## Delivered Surfaces

The workflow manages these live surfaces:

- PostgreSQL database `matrix_synapse` on `postgres`
- PostgreSQL login role `matrix_synapse` on `postgres`
- PostgreSQL database `mautrix_discord` on `postgres`
- PostgreSQL login role `mautrix_discord` on `postgres`
- PostgreSQL database `mautrix_whatsapp` on `postgres`
- PostgreSQL login role `mautrix_whatsapp` on `postgres`
- Matrix Synapse runtime under `/opt/matrix-synapse` on `docker-runtime`
- `mautrix-discord` bridge runtime under `/opt/matrix-synapse/mautrix-discord` on `docker-runtime`
- `mautrix-whatsapp` bridge runtime under `/opt/matrix-synapse/mautrix-whatsapp` on `docker-runtime`
- public Matrix client endpoint at `https://matrix.example.com/_matrix/client/versions`
- Tailscale-only controller endpoint at `http://100.64.0.1:8015/_matrix/client/versions`
- repo-managed bootstrap admin account `@ops:matrix.example.com`
- repo-managed bridge bot accounts `@discordbot:matrix.example.com` and `@whatsappbot:matrix.example.com`
- repo-managed signing key, registration secret, and mirrored controller-local recovery artifacts

## Generated Local Artifacts

After a successful converge, these controller-local files should exist:

- `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/matrix-synapse/database-password.txt`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/matrix-synapse/mautrix-discord-database-password.txt`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/matrix-synapse/mautrix-whatsapp-database-password.txt`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/matrix-synapse/ops-password.txt`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/matrix-synapse/registration-shared-secret.txt`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/matrix-synapse/server-signing.key`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/matrix-synapse/mautrix-discord-as-token.txt`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/matrix-synapse/mautrix-discord-hs-token.txt`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/matrix-synapse/mautrix-discord-provisioning-shared-secret.txt`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/matrix-synapse/mautrix-discord-avatar-proxy-key.txt`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/matrix-synapse/mautrix-whatsapp-as-token.txt`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/matrix-synapse/mautrix-whatsapp-hs-token.txt`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/matrix-synapse/mautrix-whatsapp-provisioning-shared-secret.txt`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/matrix-synapse/mautrix-whatsapp-public-media-signing-key.txt`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/matrix-synapse/mautrix-whatsapp-encryption-pickle-key.txt`

Treat the entire `.local/matrix-synapse/` subtree as operational secret material and keep it out of git.

## Verification

Run these checks after converge:

1. `make syntax-check-matrix-synapse`
2. `curl -fsS https://matrix.example.com/_matrix/client/versions`
3. `curl -fsS http://100.64.0.1:8015/_matrix/client/versions`
4. `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.64.0.1 ops@10.10.10.20 'docker compose --file /opt/matrix-synapse/docker-compose.yml ps && sudo ls -l /opt/matrix-synapse/openbao /run/lv3-secrets/matrix-synapse /opt/matrix-synapse/mautrix-discord /opt/matrix-synapse/mautrix-whatsapp && sudo test ! -e /opt/matrix-synapse/matrix-synapse.env'`
5. `curl -fsS -X POST http://100.64.0.1:8015/_matrix/client/v3/login -H 'Content-Type: application/json' -d '{"type":"m.login.password","identifier":{"type":"m.id.user","user":"ops"},"password":"'"$(cat /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/matrix-synapse/ops-password.txt)"'"}'`
6. `python3 scripts/matrix_bridge_smoke.py --base-url https://matrix.example.com --username ops --password-file /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/matrix-synapse/ops-password.txt --bot-user-id @discordbot:matrix.example.com --bot-user-id @whatsappbot:matrix.example.com --timeout-seconds 90`

## Notes

- This rollout intentionally keeps Matrix Synapse client-facing but non-federating. The repo-managed listener publishes client APIs only and does not expose a federation listener on `8448`.
- Authentication remains inside Synapse itself. `matrix.example.com` is published through the shared edge with TLS, but it is not wrapped in the shared oauth2-proxy browser flow.
- The first bridge rollout deliberately pins the latest stable release tags that were realistic on 2026-03-30: `mautrix-discord v0.7.6` and `mautrix-whatsapp v0.2603.0` (also published upstream as `v26.03`). The floating `latest` tags resolved to newer commit builds, but those were not treated as the governed default for this repo-managed rollout.
- The host-side controller proxy is intended for governed operator and automation access. It mirrors the same client API surface over Tailscale at `http://100.64.0.1:8015`.
- The host-side controller proxy binds to the Tailscale address `100.64.0.1:8015`, not to `127.0.0.1:8015`, so host-local verification should target the Tailscale address explicitly.
- Public HTTPS/TLS assurance for Matrix is evaluated from `monitoring`
  through the shared internal edge target
  `https://10.10.10.10:443/_matrix/client/versions` with `matrix.example.com` as
  the Host and SNI override. Do not treat guest-local curls to
  `https://matrix.example.com` from `monitoring` as equivalent evidence, because
  guest-network hairpin access to the public host IP is not reliable.
- The mirrored server signing key is a recovery artifact. Rotating it changes the homeserver identity contract and must be planned explicitly instead of happening as a routine secret rollover.
- Discord and WhatsApp login credentials are intentionally not bootstrapped by this runbook. The managed smoke path only proves that both bridge bots come up, receive Matrix DMs, and answer their management-room `help` flow end to end.
