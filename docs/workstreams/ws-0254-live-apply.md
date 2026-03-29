# Workstream ws-0254-live-apply: Live Apply ADR 0254 From Latest `origin/main`

- ADR: [ADR 0254](../adr/0254-serverclaw-as-a-distinct-self-hosted-agent-product-on-lv3.md)
- Title: Deploy the first honest live ServerClaw surface on LV3
- Status: implemented
- Implemented In Repo Version: not yet
- Live Applied In Platform Version: branch-local proof only on 2026-03-29; exact-main mainline replay not yet recorded
- Implemented On: 2026-03-29
- Live Applied On: 2026-03-29 (branch-local)
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
- exact-main follow-through moved to `ws-0254-main-merge` after later `origin/main` advances made the earlier canonical-mainline claims unrealistic

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
- after `origin/main` advanced further to commit `bae420263872e079fdc34f7f755a6984a3cd5949` with repository version `0.177.87` and platform version `0.130.59`, verification showed current `main` still does not carry the ADR 0254 topology, playbook, runbook, guest-firewall rule, or public-edge publication contract
- the latest March 29, 2026 checks therefore show a mixed state: `proxmox_florin` still exposes the host firewall lane, `coolify-lv3` still serves `http://127.0.0.1:8096/` and accepts bootstrap admin sign-in, but the guest nftables allowlist has drifted back to `{ 80, 443, 8000 }` for `10.10.10.10`, `nginx-lv3` times out on `10.10.10.70:8096`, and public `https://chat.lv3.org/` redirects to `https://nginx.lv3.org/`
- the latest exact-main candidate evidence is preserved in `receipts/live-applies/2026-03-29-adr-0254-serverclaw-distinct-product-surface-mainline-live-apply.json` as a partial pre-merge record, not as final merged-main truth

## Merge Criteria

- the dedicated `chat.lv3.org` surface remains distinct from the operator-only Open WebUI deployment
- the Proxmox guest firewall, Coolify guest nftables policy, and shared NGINX edge all preserve the `8096` ServerClaw path from the merged exact-main replay
- ADR 0254 metadata, workstream state, and receipts record the current partial latest-main state without claiming a merged-main receipt until it is true
- the final merge step replays `make converge-serverclaw` from merged `main`, verifies `chat.lv3.org` returns the app instead of the generic `nginx.lv3.org` redirect, and only then updates shared release files plus `versions/stack.yaml`

## Remaining For Merge-To-Main

- merge `codex/ws-0254-main-merge` onto the latest `origin/main`
- cut the next patch release from merged `main`
- replay `make converge-serverclaw` from that merged `main` checkout so server-resident reconciliation and repo truth agree
- update ADR 0254 metadata, protected release files, `versions/stack.yaml`, and the mainline receipt only after `chat.lv3.org` and the internal `10.10.10.70:8096` lane are both healthy from merged `main`
