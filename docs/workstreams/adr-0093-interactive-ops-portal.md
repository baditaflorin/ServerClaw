# Workstream ADR 0093: Interactive Ops Portal with Live Actions

- ADR: [ADR 0093](../adr/0093-interactive-ops-portal.md)
- Title: FastHTML-based interactive ops portal replacing the static generated portal with live actions, deployment streaming, and drift visibility
- Status: live_applied
- Branch: `codex/live-apply-0093`
- Worktree: `.worktrees/live-apply-0093`
- Owner: codex
- Depends On: `adr-0092-platform-api-gateway`, `adr-0056-keycloak`, `adr-0058-nats`, `adr-0066-audit-log`, `adr-0074-ops-portal`, `adr-0080-maintenance-window`, `adr-0091-drift-detection`
- Conflicts With: `adr-0074-ops-portal` (replaces static generation)
- Shared Surfaces: `scripts/generate_ops_portal.py`, nginx edge, `config/subdomain-catalog.json`

## Scope

- write `scripts/ops_portal/app.py` — FastHTML application with all portal sections
- write Ansible role `ops_portal_runtime` — deploys the portal Compose stack
- write `playbooks/services/ops-portal.yml` — service deployment playbook
- update nginx vhost `ops.lv3.org` — switch from static file serving to proxy to port 8092
- register Keycloak client `ops-portal` (with `offline_access` scope for SSE sessions)
- add health probe for portal to `config/health-probe-catalog.json`
- update `config/service-capability-catalog.json` — ops-portal entry updated (was edge-static, now edge-published dynamic)
- add `config/api-gateway-catalog.json` entry for ops-portal
- write `docs/runbooks/ops-portal-down.md`
- keep `scripts/generate_ops_portal.py` running; rename its output to `receipts/ops-portal-snapshot.html`

## Non-Goals

- Replacing Portainer (Docker operations remain there)
- Replacing the Proxmox UI (VM operations remain there)
- Building a general-purpose infrastructure UI
- Mobile-responsive design (desktop browser only for now)

## Expected Repo Surfaces

- `scripts/ops_portal/` (new directory: `app.py`, `templates/`, `static/`)
- `roles/ops_portal_runtime/`
- `playbooks/services/ops-portal.yml`
- `config/health-probe-catalog.json` (patched)
- `config/service-capability-catalog.json` (patched)
- `config/api-gateway-catalog.json` (patched)
- `docs/runbooks/ops-portal-down.md`
- `docs/adr/0093-interactive-ops-portal.md`
- `docs/workstreams/adr-0093-interactive-ops-portal.md`

## Expected Live Surfaces

- `https://ops.lv3.org` renders the interactive portal (requires Keycloak login)
- Service status panel shows all services with health traffic lights
- Drift status panel shows drift report from last run
- Deployment console renders a live SSE log stream when a deployment is triggered

## Verification

- Log in at `ops.lv3.org` with Keycloak credentials; portal renders without JavaScript errors
- Click "Health check" on any service; result appears in the portal within 5 seconds
- Trigger a check-mode deployment of `uptime-kuma`; log stream appears in the browser
- Mutation audit log shows the health check event with the Keycloak operator identity
- `ops.lv3.org/health` returns HTTP 200 (unauthenticated health endpoint for the portal itself)

## Merge Criteria

- Portal is deployed and accessible at `ops.lv3.org` behind Keycloak OIDC
- All six portal sections render without errors
- At least one action (health check) is functional end-to-end with audit log recording
- Health probe passes in `config/health-probe-catalog.json`

## Notes For The Next Assistant

- Repository implementation is merged in `0.97.0`
- Live cutover completed on `2026-03-24`; `ops.lv3.org` now serves the interactive runtime through the OIDC-protected nginx edge with the corrected `8092` host-port contract
- The rollout required re-syncing the docker-runtime guest firewall, the Proxmox VM firewall for VM `120`, and the nginx edge vhost so every layer converged on the new `8092` publish target
- The portal uses FastAPI + HTMX-augmented Jinja templates rather than a separate frontend build
- The edge config now forwards `X-Auth-Request-*` headers and the access token from `oauth2-proxy`; the portal stores the token in the server-side session and uses it for gateway calls
- The legacy static generator is preserved as an archive path through `receipts/ops-portal-snapshot.html`
