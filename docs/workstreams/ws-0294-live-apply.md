# Workstream ws-0294-live-apply: Live Apply ADR 0294 From Latest `origin/main`

- ADR: [ADR 0294](../adr/0294-one-api-as-the-unified-llm-api-proxy-and-router.md)
- Title: Deploy One-API as the unified LLM API proxy and router, then migrate the governed Open WebUI and ServerClaw consumers onto it
- Status: live_applied
- Included In Repo Version: 0.177.135
- Branch-Local Receipt: `receipts/live-applies/2026-03-31-adr-0294-one-api-live-apply.json`
- Canonical Mainline Receipt: `receipts/live-applies/2026-04-01-adr-0294-one-api-mainline-live-apply.json`
- Platform Version Observed During Integration: 0.130.84
- Live Applied In Platform Version: 0.130.85
- Release Date: 2026-04-01
- Implemented On: 2026-04-01
- Live Applied On: 2026-04-01
- Branch: `codex/ws-0294-main-integration`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0294-main-integration`
- Owner: codex
- Depends On: `adr-0042`, `adr-0077`, `adr-0095`, `adr-0145`, `adr-0254`
- Conflicts With: none
- Shared Surfaces: `docs/adr/0294`, `docs/workstreams/ws-0294-live-apply.md`, `docs/runbooks/configure-one-api.md`, `docs/runbooks/configure-open-webui.md`, `docs/runbooks/configure-serverclaw.md`, `docs/runbooks/configure-ollama.md`, `inventory/group_vars/all.yml`, `inventory/group_vars/postgres_guests.yml`, `inventory/host_vars/proxmox_florin.yml`, `playbooks/one-api.yml`, `playbooks/services/one-api.yml`, `collections/ansible_collections/lv3/platform/roles/common/`, `collections/ansible_collections/lv3/platform/roles/docker_runtime/`, `collections/ansible_collections/lv3/platform/roles/linux_guest_firewall/`, `collections/ansible_collections/lv3/platform/roles/ollama_runtime/`, `collections/ansible_collections/lv3/platform/roles/one_api_postgres/`, `collections/ansible_collections/lv3/platform/roles/one_api_runtime/`, `collections/ansible_collections/lv3/platform/roles/postgres_vm/`, `scripts/one_api_bootstrap.py`, `config/one-api/`, `config/*catalog*.json`, `Makefile`, `tests/test_docker_runtime_role.py`, `tests/test_linux_guest_firewall_role.py`, `tests/test_ollama_runtime_role.py`, `tests/test_one_api_runtime_role.py`, `tests/test_postgres_vm_access_policy.py`, `tests/test_postgres_vm_role.py`, `receipts/image-scans/`, `receipts/live-applies/`

## Purpose

Implement ADR 0294 by adding a repo-managed One-API service on
`docker-runtime-lv3`, wiring its PostgreSQL and OpenBao-backed secret
dependencies, publishing its private operator and agent access paths, and
migrating the governed Open WebUI and ServerClaw runtimes from direct Ollama
connectivity onto the unified OpenAI-compatible proxy contract.

## Scope

- add the One-API runtime, bootstrap automation, service catalogs, topology,
  image pin, and verification coverage
- make the One-API controller path available through the Proxmox Tailscale
  proxy and the authenticated API gateway
- switch Open WebUI and ServerClaw to repo-managed provider env files generated
  from One-API consumer tokens
- capture live-apply evidence, validation output, and any exact remaining
  merge-to-main work on protected integration surfaces

## Non-Goals

- changing shared release surfaces on this workstream branch unless this branch
  becomes the final merge-to-`main` integration step
- broadening the proxy to external commercial model providers that are not part
  of the current Ollama-first ADR scope
- claiming native One-API Prometheus metrics that the upstream runtime does not
  actually expose

## Initial Findings

- upstream One-API `v0.6.10` exposes the expected admin, channel, token, and
  OpenAI-compatible APIs, but it does not ship a native Prometheus `/metrics`
  endpoint
- the bootstrap automation therefore has to rely on the real admin API, not on
  undocumented assumptions
- during pre-apply reconnaissance on 2026-03-30, `ollama`, `open-webui`, and
  `openfga` were found stopped on `docker-runtime-lv3`, so this workstream must
  recover the dependent LLM lane as part of truthful end-to-end verification

## Verification

- The exact-main targeted pytest bundle passed on repository version `0.177.134` with `174 passed in 14.59s` across the One-API, Open WebUI, OpenBao, Ollama, Docker runtime, guest firewall, PostgreSQL, log shipping, RAG, and vulnerability-budget lanes.
- `./scripts/validate_repo.sh all` passed on the synchronized tree after the final `grist_runtime` idempotency ledger update and the Docker runtime assertion hardening landed.
- `make converge-one-api env=production` completed successfully from the exact-main tree with final recap `docker-runtime-lv3 : ok=223 changed=4 failed=0`, `localhost : ok=3 changed=0 failed=0`, `postgres-lv3 : ok=73 changed=5 failed=0`, and `proxmox_florin : ok=41 changed=4 failed=0`.
- The controller-side bootstrap verification reported `verification_passed: true`, kept both generated provider env files present, exposed the governed chat and embedding aliases, and returned chat probe excerpt `READY`.
- `make converge-open-webui env=production` completed successfully with final recap `docker-runtime-lv3 : ok=151 changed=2 failed=0` and `proxmox_florin : ok=41 changed=4 failed=0`, including the admin sign-in verification path.
- The first exact-main `make converge-serverclaw env=production` replay surfaced `docker-runtime-lv3` disk exhaustion during `apt-get update`; after the documented `docker image prune -af` plus `docker builder prune -af` recovery and a clean `apt-get update`, the second replay passed with final recap `coolify-lv3 : ok=87 changed=4 failed=0`, `docker-runtime-lv3 : ok=89 changed=0 failed=0`, `nginx-lv3 : ok=45 changed=4 failed=0`, and `proxmox_florin : ok=360 changed=0 failed=0`.
- `make converge-rag-context env=production` completed successfully with final recap `docker-runtime-lv3 : ok=182 changed=21 failed=0` and `proxmox_florin : ok=41 changed=4 failed=0`, including the cited platform-context query and the ServerClaw memory round-trip through semantic plus keyword recall.
- Post-replay verification confirmed the consumer paths still answered correctly: the Open WebUI head probe returned `HTTP 200`, the ServerClaw public edge at `https://chat.lv3.org` returned `HTTP/2 200` with the expected hardening headers, Open WebUI now renders `OPENAI_API_BASE_URL=http://host.docker.internal:8101/v1` with `ENABLE_OLLAMA_API=False`, and ServerClaw now renders `OPENAI_API_BASE_URL=http://10.10.10.20:8101/v1` with the same governed default model contract.

## Live Apply Outcome

- ADR 0294 is now live from the exact-main integration branch on platform version `0.130.85`: One-API is the unified private OpenAI-compatible proxy, Ollama remains the backend inference engine, Open WebUI and ServerClaw now consume repo-managed One-API provider contracts, and the operator-only host proxy on `http://100.64.0.1:8018` is verified.
- The settled branch also hardens the supporting recovery paths that surfaced during truthful live replay: Docker bridge recovery now waits for SSH after daemon restarts, PostgreSQL converges the correct `pgaudit` package and verifies `shared_preload_libraries`, the guest firewall and PostgreSQL access policy admit the governed Docker bridge CIDRs, and the Ollama startup path clears stale partial blobs before in-container model pulls.
- The One-API playbook now converges `ollama_runtime` before `one_api_runtime`, which turned the previously flaky bootstrap into a reproducible end-to-end workflow instead of assuming a healthy backend model lane out of band.
- The canonical 2026-04-01 replay also records the only manual operator intervention required during the exact-main window: temporary Docker image and builder cache cleanup on `docker-runtime-lv3` to restore enough free space for the shared apt metadata refresh that the ServerClaw replay inherited from current main.

## Live Evidence

- Branch-local receipt: `receipts/live-applies/2026-03-31-adr-0294-one-api-live-apply.json`
- Canonical mainline receipt: `receipts/live-applies/2026-04-01-adr-0294-one-api-mainline-live-apply.json`
- Targeted pytest output: `receipts/live-applies/evidence/2026-04-01-ws-0294-main-integration-targeted-pytest-r4-0.177.134.txt`
- Repository validation output: `receipts/live-applies/evidence/2026-04-01-ws-0294-main-integration-validate-repo-all-r6-0.177.134.txt`
- One-API converge replay: `receipts/live-applies/evidence/2026-04-01-ws-0294-mainline-converge-one-api-r1-0.177.134.txt`
- Open WebUI converge replay: `receipts/live-applies/evidence/2026-04-01-ws-0294-mainline-converge-open-webui-r1-0.177.134.txt`
- ServerClaw converge replay and disk-pressure recovery: `receipts/live-applies/evidence/2026-04-01-ws-0294-mainline-converge-serverclaw-r1-0.177.134.txt`, `receipts/live-applies/evidence/2026-04-01-ws-0294-docker-runtime-space-recovery-r1-0.177.134.txt`, and `receipts/live-applies/evidence/2026-04-01-ws-0294-mainline-converge-serverclaw-r2-0.177.134.txt`
- Bootstrap verification report: `receipts/live-applies/evidence/2026-04-01-ws-0294-bootstrap-report-r2-0.177.134.json`
- One-API status proof: `receipts/live-applies/evidence/2026-04-01-ws-0294-one-api-status-r1-0.177.134.json`
- Runtime env verification: `receipts/live-applies/evidence/2026-04-01-ws-0294-open-webui-runtime-env-r1-0.177.134.txt` and `receipts/live-applies/evidence/2026-04-01-ws-0294-serverclaw-runtime-env-r1-0.177.134.txt`
- Endpoint verification: `receipts/live-applies/evidence/2026-04-01-ws-0294-open-webui-head-r1-0.177.134.txt` and `receipts/live-applies/evidence/2026-04-01-ws-0294-serverclaw-head-r1-0.177.134.txt`

## Merge-To-Main Notes

- The exact-main integration step completed from `origin/main` commit `b7dde631d290474de3200886846217e688e0c16e`; the remaining work on this branch is only the protected release cut, final merge to `main`, and push to `origin/main`.
- Raw provider-env captures were intentionally not retained in the committed evidence set because they contained live consumer tokens; the bootstrap report plus the downstream runtime env verification files are the canonical non-secret proofs for the generated provider contracts.
