# Workstream ws-0294-live-apply: Live Apply ADR 0294 From Latest `origin/main`

- ADR: [ADR 0294](../adr/0294-one-api-as-the-unified-llm-api-proxy-and-router.md)
- Title: Deploy One-API as the unified LLM API proxy and router, then migrate the governed Open WebUI and ServerClaw consumers onto it
- Status: in-progress
- Branch: `codex/ws-0294-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0294-live-apply`
- Owner: codex
- Depends On: `adr-0042`, `adr-0077`, `adr-0095`, `adr-0145`, `adr-0254`
- Conflicts With: none
- Shared Surfaces: `docs/adr/0294`, `docs/workstreams/ws-0294-live-apply.md`, `docs/runbooks/configure-one-api.md`, `docs/runbooks/configure-open-webui.md`, `docs/runbooks/configure-serverclaw.md`, `inventory/group_vars/all.yml`, `inventory/host_vars/proxmox_florin.yml`, `playbooks/one-api.yml`, `playbooks/services/one-api.yml`, `collections/ansible_collections/lv3/platform/roles/one_api_postgres/`, `collections/ansible_collections/lv3/platform/roles/one_api_runtime/`, `scripts/one_api_bootstrap.py`, `config/one-api/`, `config/*catalog*.json`, `Makefile`, `receipts/image-scans/`, `receipts/live-applies/`

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

## Verification Plan

- syntax-check the new and changed playbooks plus the dependent imported
  surfaces
- run focused role and topology tests for the One-API runtime, bootstrap path,
  and consumer migration
- run repository validation gates after the catalog and ADR surfaces are
  updated
- live-apply the One-API workflow from the synchronized worktree
- verify the private controller path, authenticated API gateway path, generated
  consumer env files, and at least one real One-API request routed through the
  Ollama backend

## Result

Pending implementation and live-apply evidence.
