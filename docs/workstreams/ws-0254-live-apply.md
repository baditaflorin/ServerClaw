# Workstream ws-0254-live-apply: Live Apply ADR 0254 From Latest `origin/main`

- ADR: [ADR 0254](../adr/0254-serverclaw-as-a-distinct-self-hosted-agent-product-on-lv3.md)
- Title: Deploy the first honest live ServerClaw surface on LV3
- Status: live_applied
- Implemented In Repo Version: 0.177.91
- Live Applied In Platform Version: 0.130.60
- Implemented On: 2026-03-30
- Live Applied On: 2026-03-30 (merged main; first branch-local proof recorded on 2026-03-29)
- Branch: `codex/ws-0254-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.worktrees/ws-0254-live-apply`
- Owner: codex
- Depends On: `adr-0060-open-webui-workbench`, `adr-0097-keycloak`, `adr-0145-local-ollama`, `adr-0148-searxng-web-search`
- Conflicts With: none
- Shared Surfaces: `docs/adr/0254-serverclaw-as-a-distinct-self-hosted-agent-product-on-lv3.md`, `docs/workstreams/ws-0254-live-apply.md`, `docs/runbooks/configure-serverclaw.md`, `playbooks/serverclaw.yml`, `workstreams.yaml`, `inventory/group_vars/all.yml`, `inventory/group_vars/platform.yml`, `inventory/host_vars/proxmox-host.yml`, `config/service-capability-catalog.json`, `config/health-probe-catalog.json`, `config/subdomain-catalog.json`, `config/api-gateway-catalog.json`, `config/dependency-graph.json`, `config/slo-catalog.json`, `config/data-catalog.json`, `config/secret-catalog.json`, `config/image-catalog.json`, `config/service-completeness.json`, `collections/ansible_collections/lv3/platform/roles/open_webui_runtime/`, `collections/ansible_collections/lv3/platform/roles/keycloak_runtime/`, `receipts/live-applies/`

## Scope

- deploy a dedicated public ServerClaw runtime on `coolify`
- brand and configure the runtime as a chat-first ServerClaw surface instead of reusing the private operator `open-webui` entrypoint
- provision a dedicated Keycloak OIDC client for `chat.example.com`
- publish the service through the shared NGINX edge and record live evidence
- add repo-native syntax-check, converge, and validation coverage for the new service

## Non-Goals

- implementing the Matrix, mautrix, Temporal, OpenFGA, Nextcloud, or Qdrant follow-on ADRs in this workstream
- replacing the operator-only Open WebUI deployment on `docker-runtime`
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

- `chat.example.com`
- `coolify:/opt/serverclaw`
- `.local/serverclaw/*`
- `.local/keycloak/serverclaw-client-secret.txt`

## Ownership Notes

- this workstream owns the ServerClaw live-apply automation, its branch-local receipt, and the operational runbook updates for the first public chat surface
- protected release files remained untouched here until the later `ws-0254-main-merge` integration step
- exact-main follow-through moved to `ws-0254-main-merge` after later `origin/main` advances made the earlier canonical-mainline claims unrealistic

## Verification

- `uv run --with pytest --with pyyaml pytest -q tests/test_linux_guest_firewall_role.py tests/test_serverclaw_playbook.py tests/test_coolify_playbook.py tests/test_open_webui_runtime_role.py tests/test_keycloak_runtime_role.py tests/test_nginx_edge_publication_role.py tests/test_openbao_compose_env_helper.py`
- `make syntax-check-serverclaw`
- `make converge-serverclaw`
- public edge, runtime env, login-path, and firewall checks recorded in the live-apply receipts

## Recorded Results

- the refreshed latest-main regression slice returned `38 passed`, and `make syntax-check-serverclaw` passed before the first live replay continued
- the first branch-local replay from source commit `c0576e42f6d4d776fd2d550aaaab1f9b93376cfd` on top of `origin/main` commit `7f1bbe50518fd30a78a2ce5f7ee5f410ba07b0ea` completed successfully with recap `coolify ok=58 changed=0 failed=0 skipped=16`, `docker-runtime ok=66 changed=3 failed=0 skipped=4`, `nginx-edge ok=38 changed=2 failed=0 skipped=8`, and `proxmox-host ok=229 changed=0 failed=0 skipped=111`
- that first proof is preserved in `receipts/live-applies/2026-03-29-adr-0254-serverclaw-distinct-product-surface-live-apply.json`
- the later pre-merge exact-main drift on `origin/main` is still preserved in `receipts/live-applies/2026-03-29-adr-0254-serverclaw-distinct-product-surface-mainline-live-apply.json` so another operator can see exactly why a merged-main replay was required
- after `git push origin HEAD:main` advanced `origin/main` to source commit `72ee92ef77cae2cf73e3c42168b2e193984c05c1`, the exact-main replay `make converge-serverclaw` completed successfully with recap `coolify ok=60 changed=4 failed=0 skipped=14`, `docker-runtime ok=63 changed=0 failed=0 skipped=7`, `nginx-edge ok=39 changed=4 failed=0 skipped=7`, and `proxmox-host ok=241 changed=6 failed=0 skipped=108`
- the merged-main verification proved `/etc/pve/firewall/170.fw` still contains `17:IN ACCEPT -source 10.10.10.10/32 -p tcp -dport 8096`, `nc -vz -w 5 10.10.10.70 8096` from `nginx-edge` succeeds, `curl -sk -D - https://127.0.0.1/ -H 'Host: chat.example.com'` on `nginx-edge` now returns `HTTP/2 200`, `curl http://127.0.0.1:8096/` on `coolify` returns `200`, guest-local sign-in returns `ops@example.com` with `role":"admin"` and a bearer token, `http://chat.example.com/` redirects to `https://chat.example.com/`, and public `https://chat.example.com/` returns `HTTP/2 200`
- the final merged-main proof is recorded in `receipts/live-applies/2026-03-30-adr-0254-serverclaw-distinct-product-surface-mainline-live-apply.json` with supporting evidence in `receipts/live-applies/evidence/2026-03-30-adr-0254-mainline-live-apply.txt`

## Merge Outcome

- the dedicated `chat.example.com` surface remains distinct from the operator-only Open WebUI deployment
- the Proxmox guest firewall, Coolify guest nftables policy, and shared NGINX edge now preserve the `8096` ServerClaw path from the merged exact-main replay
- ADR 0254 metadata, workstream state, release notes, and receipts now record the first clean merged-main receipt instead of the earlier partial latest-main gap
- shared release files and `versions/stack.yaml` were updated only after the merged-main replay and public `chat.example.com` verification were both clean

## Remaining For Merge-To-Main

- none
