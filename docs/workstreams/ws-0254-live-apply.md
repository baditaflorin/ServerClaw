# Workstream ws-0254-live-apply: Live Apply ADR 0254 From Latest `origin/main`

- ADR: [ADR 0254](../adr/0254-serverclaw-as-a-distinct-self-hosted-agent-product-on-lv3.md)
- Title: Deploy the first honest live ServerClaw surface on LV3
- Status: live_applied
- Implemented In Repo Version: 0.177.84
- Live Applied In Platform Version: 0.130.58
- Implemented On: 2026-03-29
- Live Applied On: 2026-03-29
- Branch: `codex/ws-0254-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0254-live-apply`
- Owner: codex
- Depends On: `adr-0060-open-webui-workbench`, `adr-0097-keycloak`, `adr-0145-local-ollama`, `adr-0148-searxng-web-search`
- Conflicts With: none
- Shared Surfaces: `docs/adr/0254-serverclaw-as-a-distinct-self-hosted-agent-product-on-lv3.md`, `docs/workstreams/ws-0254-live-apply.md`, `docs/runbooks/configure-serverclaw.md`, `playbooks/serverclaw.yml`, `workstreams.yaml`, `inventory/group_vars/all.yml`, `inventory/group_vars/platform.yml`, `inventory/host_vars/proxmox_florin.yml`, `config/service-capability-catalog.json`, `config/health-probe-catalog.json`, `config/subdomain-catalog.json`, `config/api-gateway-catalog.json`, `config/dependency-graph.json`, `config/slo-catalog.json`, `config/data-catalog.json`, `config/secret-catalog.json`, `config/image-catalog.json`, `config/service-completeness.json`, `collections/ansible_collections/lv3/platform/roles/open_webui_runtime/`, `collections/ansible_collections/lv3/platform/roles/keycloak_runtime/`, `receipts/live-applies/`

## Scope

- deploy a dedicated public ServerClaw runtime on `coolify-lv3`
- brand and configure the runtime as a chat-first ServerClaw surface instead of reusing the private operator `open-webui` entrypoint
- provision a dedicated Keycloak OIDC client for `chat.lv3.org`
- publish the service through the shared NGINX edge and record live evidence
- add repo-native syntax-check, converge, and validation coverage for the new service

## Non-Goals

- implementing the Matrix, mautrix, Temporal, OpenFGA, Nextcloud, or Qdrant follow-on ADRs in this workstream
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

## Ownership Notes

- this workstream owns the ServerClaw live-apply automation, its branch-local receipt, and the operational runbook updates for the first public chat surface
- protected release files remained untouched here until the later `ws-0254-main-merge` integration step
- the exact-main follow-through now records both the branch-local receipt and the canonical mainline receipt for the same ADR

## Verification

- `uv run --with pytest --with pyyaml pytest -q tests/test_linux_guest_firewall_role.py tests/test_serverclaw_playbook.py tests/test_coolify_playbook.py tests/test_open_webui_runtime_role.py tests/test_keycloak_runtime_role.py tests/test_nginx_edge_publication_role.py tests/test_openbao_compose_env_helper.py`
- `make syntax-check-serverclaw`
- `make converge-serverclaw`
- public edge, runtime env, login-path, and firewall checks recorded in the live-apply receipts

## Branch-Local Results

- the refreshed latest-main regression slice returned `38 passed`, and `make syntax-check-serverclaw` passed before the live replay continued
- the branch-local latest-main replay from source commit `c0576e42f6d4d776fd2d550aaaab1f9b93376cfd` on top of `origin/main` commit `7f1bbe50518fd30a78a2ce5f7ee5f410ba07b0ea` completed successfully with recap `coolify-lv3 ok=58 changed=0 failed=0 skipped=16`, `docker-runtime-lv3 ok=66 changed=3 failed=0 skipped=4`, `nginx-lv3 ok=38 changed=2 failed=0 skipped=8`, and `proxmox_florin ok=229 changed=0 failed=0 skipped=111`
- the branch-local verification proved `pve-manager/9.1.6/71482d1833ded40a` remained active, `/etc/pve/firewall/170.fw` still contained the `8096` ingress rule for `10.10.10.10/32`, `nc -vz -w 5 10.10.10.70 8096` from `nginx-lv3` succeeded, `curl -sv --max-time 5 http://10.10.10.70:8096/ -o /dev/null` returned `HTTP/1.1 200 OK`, guest-local sign-in on `coolify-lv3` returned `ops@lv3.org` with `role":"admin"`, and public `chat.lv3.org` checks returned `HTTP/1.1 308` on HTTP plus `HTTP/2 200` on HTTPS
- that first live proof is preserved in `receipts/live-applies/2026-03-29-adr-0254-serverclaw-distinct-product-surface-live-apply.json`
- after `origin/main` advanced to `8871117b40466b7907a33992f44ca7d83a3e9409`, the protected integration step cut repository version `0.177.84` and replayed `make converge-serverclaw` again from source commit `54622948a39fa6632058b63536204188e5040753`
- the synchronized exact-main replay completed with recap `coolify-lv3 ok=58 changed=0 failed=0 skipped=16`, `docker-runtime-lv3 ok=63 changed=0 failed=0 skipped=7`, `nginx-lv3 ok=38 changed=2 failed=0 skipped=8`, and `proxmox_florin ok=229 changed=0 failed=0 skipped=111`, making platform version `0.130.58` the first canonical integrated platform version for ADR 0254

## Merge Criteria

- the dedicated `chat.lv3.org` surface remains distinct from the operator-only Open WebUI deployment
- the Proxmox guest firewall, Coolify guest nftables policy, and shared NGINX edge all preserve the `8096` ServerClaw path from the merged exact-main replay
- ADR 0254 metadata, workstream state, and receipts all record both the branch-local proof and the canonical mainline receipt without overstating the rest of the 0255-0263 architecture bundle

## Exact-Main Outcome

- repository version `0.177.84` is the first integrated repo release that carries ADR 0254
- platform version `0.130.58` is the first integrated platform version that records the synchronized latest-main replay and verification for ADR 0254
- the canonical mainline proof now lives in `receipts/live-applies/2026-03-29-adr-0254-serverclaw-distinct-product-surface-mainline-live-apply.json`, while the earlier branch-local receipt remains preserved as the first latest-main candidate replay
