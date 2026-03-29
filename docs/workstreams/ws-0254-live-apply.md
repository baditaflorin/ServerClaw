# Workstream WS-0254: Live Apply ADR 0254 ServerClaw

- ADR: [ADR 0254](../adr/0254-serverclaw-as-a-distinct-self-hosted-agent-product-on-lv3.md)
- Title: Deploy the first honest live ServerClaw surface on LV3
- Status: in-progress
- Implemented In Repo Version: N/A
- Implemented In Platform Version: N/A
- Implemented On: N/A
- Branch: `codex/ws-0254-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0254-live-apply`
- Owner: codex
- Depends On: `adr-0060-open-webui-workbench`, `adr-0097-keycloak`,
  `adr-0145-local-ollama`, `adr-0148-searxng-web-search`
- Conflicts With: none
- Shared Surfaces: `docs/adr/0254-serverclaw-as-a-distinct-self-hosted-agent-product-on-lv3.md`,
  `docs/workstreams/ws-0254-live-apply.md`, `docs/runbooks/configure-serverclaw.md`,
  `playbooks/serverclaw.yml`, `workstreams.yaml`, `inventory/group_vars/all.yml`,
  `inventory/group_vars/platform.yml`, `inventory/host_vars/proxmox_florin.yml`,
  `config/service-capability-catalog.json`, `config/health-probe-catalog.json`,
  `config/subdomain-catalog.json`, `config/api-gateway-catalog.json`,
  `config/dependency-graph.json`, `config/slo-catalog.json`,
  `config/data-catalog.json`, `config/secret-catalog.json`,
  `config/image-catalog.json`, `config/service-completeness.json`,
  `collections/ansible_collections/lv3/platform/roles/open_webui_runtime/`,
  `collections/ansible_collections/lv3/platform/roles/keycloak_runtime/`,
  `receipts/live-applies/`

## Scope

- deploy a dedicated public ServerClaw runtime on `coolify-lv3`
- brand and configure the runtime as a chat-first ServerClaw surface instead of
  reusing the private operator `open-webui` entrypoint
- provision a dedicated Keycloak OIDC client for `chat.lv3.org`
- publish the service through the shared NGINX edge and record live evidence
- add repo-native syntax-check, converge, and validation coverage for the new
  service

## Non-Goals

- implementing the Matrix, mautrix, Temporal, OpenFGA, Nextcloud, or Qdrant
  follow-on ADRs in this workstream
- replacing the operator-only Open WebUI deployment on `docker-runtime-lv3`
- claiming the broader ServerClaw architecture bundle is fully complete

## Expected Repo Surfaces

- `playbooks/serverclaw.yml`
- `docs/runbooks/configure-serverclaw.md`
- `docs/workstreams/ws-0254-live-apply.md`
- `config/*` service catalogs for `serverclaw`
- `collections/ansible_collections/lv3/platform/roles/open_webui_runtime/`
- `collections/ansible_collections/lv3/platform/roles/keycloak_runtime/`
- `receipts/live-applies/*serverclaw*`

## Expected Live Surfaces

- `chat.lv3.org`
- `coolify-lv3:/opt/serverclaw`
- `.local/serverclaw/*`
- `.local/keycloak/serverclaw-client-secret.txt`

## Verification

- `make syntax-check-serverclaw`
- `make validate`
- `make converge-serverclaw`
- public edge, runtime env, and login-path checks recorded in the live-apply
  receipt

## Notes For The Next Assistant

- keep ADR 0254 honest: this workstream implements the first distinct product
  surface, not the full 0255-0263 bundle
- `serverclaw` runs on `coolify-lv3`, so the current live apply renders its
  runtime env directly and leaves the shared OpenBao sidecar disabled there;
  the managed OpenBao automation listener is still host-local to
  `docker-runtime-lv3`
- the shared post-verify `health-probe-catalog.json` checks for `open_webui`
  and `serverclaw` now stay on non-auth local HTTP surfaces; the admin
  sign-in assertion remains in the role-level Open WebUI verification tasks
- the shared `nginx_edge_publication` replay for this workstream must opt out
  of unrelated generated static-site syncs (`docs-portal`, `changelog-portal`)
  so a fresh separate worktree can publish `chat.lv3.org` without prebuilding
  other portals
- if shared integration files wait until merge-to-main, record the exact follow-on
  deltas in the receipt and this document
