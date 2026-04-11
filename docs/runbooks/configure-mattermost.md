# Configure Mattermost

## Purpose

This runbook converges the private Mattermost ChatOps surface defined by ADR 0057.

It covers:

- PostgreSQL database and role provisioning on `postgres`
- private Mattermost runtime deployment on `docker-runtime`
- a host-side Tailscale TCP proxy on `proxmox-host` for operator access
- repo-managed bootstrap of the `lv3` team, collaboration channels, and incoming webhooks
- Grafana contact-point routing to the Mattermost `platform-alerts` channel
- controller-local bootstrap artifacts mirrored under `.local/mattermost/`

## Preconditions

Before running the workflow, confirm:

1. the controller has the SSH key at `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519`
2. `postgres`, `docker-runtime`, and `monitoring` are already reachable through the Proxmox jump path
3. the Proxmox host is reachable on its Tailscale address `100.118.189.95`

## Entrypoints

- syntax check: `make syntax-check-mattermost`
- preflight: `make preflight WORKFLOW=converge-mattermost`
- converge: `make converge-mattermost`

## Delivered Surfaces

The workflow manages these live surfaces:

- PostgreSQL database `mattermost` on `postgres`
- PostgreSQL login role `mattermost_admin` plus support role `mattermost_user` on `postgres`
- Mattermost runtime under `/opt/mattermost` on `docker-runtime`
- Tailscale-only operator entrypoint at `http://100.118.189.95:8066`
- repo-managed team `lv3`
- repo-managed channels `platform-alerts`, `workflow-events`, `change-approvals`, `agent-handoffs`, and `mail-ops`
- repo-managed channels `platform-alerts-critical` and `platform-ops` for ADR 0097 alert routing
- repo-managed incoming webhooks mirrored locally for the managed channels
- Grafana contact point `lv3-mattermost-platform-alerts` on `monitoring`

## Generated Local Artifacts

After a successful converge, these controller-local files should exist:

- `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/mattermost/database-password.txt`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/mattermost/admin-password.txt`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/mattermost/incoming-webhooks.json`

Treat the entire `.local/mattermost/` subtree as operational secret material and keep it out of git.

The webhook manifest now includes the repo-managed keys used by Alertmanager routing:

- `alerts`
- `alerts_critical`
- `ops`

## Verification

Run these checks after converge:

1. `make syntax-check-mattermost`
2. `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.118.189.95 ops@10.10.10.20 'docker compose --file /opt/mattermost/docker-compose.yml ps && sudo ls -l /opt/mattermost/openbao /run/lv3-secrets/mattermost && sudo test ! -e /opt/mattermost/mattermost.env'`
3. `curl -s http://100.118.189.95:8066/api/v4/system/ping`
4. `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.118.189.95 ops@10.10.10.20 'docker exec lv3-mattermost /mattermost/bin/mmctl --local team search lv3 --json'`
5. `python -m json.tool /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/mattermost/incoming-webhooks.json`

## Notes

- Mattermost stays private-only in this rollout. There is no public edge publication and no public DNS record for it.
- This rollout intentionally uses a repo-managed local admin plus incoming webhook model first. Shared SSO through Keycloak remains a follow-on integration under ADR 0056 instead of blocking the private ChatOps surface entirely.
- Chat channels are a collaboration surface, not the source of truth. Final decisions, live-apply evidence, and durable operational state still belong in ADRs, runbooks, receipts, and repo-managed automation.
- The webhook manifest includes internal URLs for service-to-service routing and external URLs for operator access through the Proxmox host Tailscale proxy.
- ADR 0097 uses the `alerts_critical` webhook for critical Alertmanager notifications and `ops` for informational operator events.
