# Workstream ADR 0074: Platform Operations Portal

- ADR: [ADR 0074](../adr/0074-platform-operations-portal.md)
- Title: Generated static web portal for human navigation of all platform services, VMs, and runbooks
- Status: ready
- Branch: `codex/adr-0074-ops-portal`
- Worktree: `../proxmox_florin_server-ops-portal`
- Owner: codex
- Depends On: `adr-0075-service-capability-catalog`, `adr-0076-subdomain-governance`, `adr-0056-keycloak-sso`, `adr-0021-nginx-edge-publication`
- Conflicts With: none
- Shared Surfaces: `scripts/`, `build/`, NGINX edge config, `Makefile`, `config/service-capability-catalog.json`

## Scope

- write `scripts/generate_ops_portal.py` that reads all catalog inputs and renders a static HTML site to `build/ops-portal/`
- implement the six portal views: Service Map, VM Inventory, DNS Map, Runbook Index, ADR Decision Log, Agent Capability Surface
- integrate live health status from Uptime Kuma API on the Service Map (fetched at generation time, not client-side)
- add NGINX route for `ops.lv3.org` pointing to the static build directory
- add `ops.lv3.org` to `config/subdomain-catalog.json`
- add Keycloak auth gate on the NGINX route (operator role required)
- add `make generate-ops-portal` target
- hook generation into `make generate-status`
- staging instance at `ops.staging.lv3.org` generated from staging catalog inputs

## Non-Goals

- real-time health status updates in the browser (static generation only; health is snapshotted at build time)
- command execution or mutation from the portal (read-only surface)
- custom JavaScript framework or SPA build pipeline — plain HTML + minimal CSS

## Expected Repo Surfaces

- `scripts/generate_ops_portal.py`
- `build/ops-portal/` (gitignored, generated artifact)
- updated NGINX config (`roles/nginx_edge_publication`) for `ops.lv3.org`
- updated `config/subdomain-catalog.json`
- updated `Makefile` (`generate-ops-portal`, `generate-status` hooks)
- `docs/adr/0074-platform-operations-portal.md`
- `docs/workstreams/adr-0074-ops-portal.md`
- `workstreams.yaml`

## Expected Live Surfaces

- `https://ops.lv3.org` serving the generated static portal, auth-gated by Keycloak
- NGINX configuration for `ops.lv3.org` with TLS via Let's Encrypt
- Portal generated and deployed on every merge to main via CI or `make generate-status`

## Verification

- `make generate-ops-portal` completes without error and produces `build/ops-portal/index.html`
- Service Map shows all services from `config/service-capability-catalog.json`
- Runbook Index links resolve to existing files in `docs/runbooks/`
- ADR Decision Log shows all 81+ ADRs with correct status
- `https://ops.lv3.org` returns 401 without Keycloak session, 200 with operator session

## Merge Criteria

- all six portal views are rendered with correct data from catalog inputs
- Keycloak auth gate is enforced (manual verification: unauthenticated request returns 401)
- generation script passes `make validate` (schema-valid HTML, no broken internal links)
- the portal renders correctly on a mobile viewport (operators may access from a phone)

## Notes For The Next Assistant

- start with the Service Map view as it is the highest-value view and exercises all the catalog reading logic
- Uptime Kuma API requires an API key; fetch it from OpenBao at generation time using the agent-identity token, not a hardcoded key
- the build directory is gitignored but must be produced and deployed as part of the CI publish step; consider a `make deploy-ops-portal` target that rsync's to the nginx VM
