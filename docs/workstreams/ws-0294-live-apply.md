# Workstream ws-0294-live-apply: Live Apply ADR 0294 From Latest `origin/main`

- ADR: [ADR 0294](../adr/0294-one-api-as-the-unified-llm-api-proxy-and-router.md)
- Title: Deploy One-API as the unified LLM API proxy and router, then migrate the governed Open WebUI and ServerClaw consumers onto it
- Status: ready_for_merge
- Included In Repo Version: not yet
- Branch-Local Receipt: `receipts/live-applies/2026-03-31-adr-0294-one-api-live-apply.json`
- Canonical Mainline Receipt: pending exact-main replay
- Live Applied In Platform Version: 0.130.74
- Implemented On: 2026-03-31
- Live Applied On: 2026-03-31
- Branch: `codex/ws-0294-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0294-live-apply`
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

- Focused branch validation passed from the live-apply worktree: `uv run --with pytest --with pyyaml pytest -q tests/test_one_api_runtime_role.py tests/test_docker_runtime_role.py tests/test_linux_guest_firewall_role.py tests/test_ollama_runtime_role.py tests/test_postgres_vm_role.py tests/test_postgres_vm_access_policy.py` returned `37 passed in 2.46s`, and `make syntax-check-one-api` passed.
- `make converge-one-api` completed successfully from the settled worktree with final recap `docker-runtime-lv3 : ok=192 changed=2 failed=0`, `localhost : ok=3 failed=0`, `postgres-lv3 : ok=58 changed=5 failed=0`, and `proxmox_florin : ok=41 changed=4 failed=0`.
- The controller-side bootstrap verification reported `verification_passed: true`, reconciled the managed root profile as `root / LV3 Platform Root`, exposed the governed model set `gpt-4.1-mini`, `gpt-4o-mini`, and `text-embedding-3-small`, returned chat probe excerpt `READY`, and kept both downstream provider env files present.
- The generated provider env contracts now point consumers at One-API: Open WebUI uses `http://host.docker.internal:8101/v1`, and ServerClaw uses `http://10.10.10.20:8101/v1`.
- `make converge-open-webui` completed successfully with final recap `docker-runtime-lv3 : ok=125 changed=6 failed=0` and `proxmox_florin : ok=41 changed=4 failed=0`, including the admin sign-in verification path.
- `make converge-serverclaw` completed successfully with final recap `coolify-lv3 : ok=79 changed=5 failed=0`, `docker-runtime-lv3 : ok=81 changed=2 failed=0`, `nginx-lv3 : ok=45 changed=4 failed=0`, and `proxmox_florin : ok=272 changed=3 failed=0`.

## Live Apply Outcome

- ADR 0294 is now live from this isolated worktree on platform version `0.130.74`: One-API is the unified private OpenAI-compatible proxy, Ollama remains the backend inference engine, Open WebUI and ServerClaw now consume repo-managed One-API provider contracts, and the operator-only host proxy on `http://100.64.0.1:8018` is verified.
- The settled branch also hardens the supporting recovery paths that surfaced during truthful live replay: Docker bridge recovery now waits for SSH after daemon restarts, PostgreSQL converges the correct `pgaudit` package and verifies `shared_preload_libraries`, the guest firewall and PostgreSQL access policy admit the governed Docker bridge CIDRs, and the Ollama startup path clears stale partial blobs before in-container model pulls.
- The One-API playbook now converges `ollama_runtime` before `one_api_runtime`, which turned the previously flaky bootstrap into a reproducible end-to-end workflow instead of assuming a healthy backend model lane out of band.

## Live Evidence

- Branch-local receipt: `receipts/live-applies/2026-03-31-adr-0294-one-api-live-apply.json`
- Bootstrap report: `receipts/live-applies/evidence/2026-03-31-ws-0294-bootstrap-report-r1.json`
- Bootstrap summary: `receipts/live-applies/evidence/2026-03-31-ws-0294-bootstrap-summary-r1.txt`
- Provider env base URLs: `receipts/live-applies/evidence/2026-03-31-ws-0294-provider-env-base-urls-r2.txt`
- Focused pytest output: `receipts/live-applies/evidence/2026-03-31-ws-0294-targeted-pytest-r1.txt`
- Syntax-check output: `receipts/live-applies/evidence/2026-03-31-ws-0294-syntax-check-one-api-r2.txt`

## Merge-To-Main Notes

- Remaining for the exact-main integration step: fetch and rebase onto the latest `origin/main`, rerun the relevant validation and live replay paths from that synchronized tree, then update the protected surfaces `VERSION`, `changelog.md`, `RELEASE.md`, `docs/release-notes/`, `README.md`, `versions/stack.yaml`, and `build/platform-manifest.json` together with the canonical mainline receipt.
