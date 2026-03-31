# Workstream ws-0292-live-apply: Live Apply ADR 0292 From Latest `origin/main`

- ADR: [ADR 0292](../adr/0292-lago-as-the-usage-metering-and-billing-api-layer.md)
- Title: Deploy Lago as the repo-managed usage metering and billing API layer, publish `billing.lv3.org`, and verify metered ingestion end to end
- Status: live_applied
- Included In Repo Version: 0.177.118
- Platform Version Observed During Integration: 0.130.77
- Release Date: 2026-03-31
- Live Applied On: 2026-03-31
- Branch: `codex/ws-0292-main-integration-r1`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0292-live-apply-r2`
- Owner: codex
- Depends On: `adr-0021-public-subdomain-publication`, `adr-0042-postgresql-as-the-shared-relational-database`, `adr-0063-keycloak-sso-for-internal-services`, `adr-0077-compose-secret-injection-pattern`, `adr-0086-backup-and-recovery`, `adr-0276-nats-jetstream-as-the-platform-event-bus`
- Conflicts With: none
- Shared Surfaces: `workstreams.yaml`, `Makefile`, `README.md`, `RELEASE.md`, `VERSION`, `changelog.md`, `docs/adr/0292`, `docs/workstreams/ws-0292-live-apply.md`, `docs/runbooks/configure-lago.md`, `docs/release-notes/README.md`, `docs/release-notes/*.md`, `docs/diagrams/agent-coordination-map.excalidraw`, `docs/diagrams/service-dependency-graph.excalidraw`, `docs/site-generated/architecture/dependency-graph.md`, `build/platform-manifest.json`, `versions/stack.yaml`, `inventory/host_vars/proxmox_florin.yml`, `inventory/group_vars/platform.yml`, `playbooks/lago.yml`, `playbooks/services/lago.yml`, `collections/ansible_collections/lv3/platform/playbooks/lago.yml`, `collections/ansible_collections/lv3/platform/playbooks/services/lago.yml`, `roles/lago_postgres/`, `roles/lago_runtime/`, `roles/api_gateway_runtime/`, `roles/nginx_edge_publication/`, `collections/ansible_collections/lv3/platform/roles/common/tasks/docker_bridge_chains.yml`, `collections/ansible_collections/lv3/platform/roles/docker_runtime/defaults/main.yml`, `collections/ansible_collections/lv3/platform/roles/docker_runtime/tasks/main.yml`, `scripts/api_gateway/main.py`, `scripts/generate_platform_vars.py`, `config/*catalog*.json`, `config/ansible-execution-scopes.yaml`, `config/ansible-role-idempotency.yml`, `config/prometheus/file_sd/https_tls_targets.yml`, `config/prometheus/rules/https_tls_alerts.yml`, `config/uptime-kuma/monitors.json`, `receipts/image-scans/`, `receipts/live-applies/`, `receipts/live-applies/evidence/`, `receipts/ops-portal-snapshot.html`, `tests/`

## Purpose

Carry the verified ADR 0292 Lago deployment onto the latest realistic
`origin/main` baseline, replay the governed service live apply from that
integrated tree, and record the first merged repository and platform versions
where `billing.lv3.org` is live with public event ingest, protected browser
access, current-usage verification, and the restored post-apply backup path.

## Shared Surfaces

- `workstreams.yaml`
- `docs/workstreams/ws-0292-live-apply.md`
- `docs/adr/0292-lago-as-the-usage-metering-and-billing-api-layer.md`
- `docs/runbooks/configure-lago.md`
- `Makefile`
- `README.md`
- `RELEASE.md`
- `VERSION`
- `changelog.md`
- `docs/release-notes/README.md`
- `docs/release-notes/*.md`
- `versions/stack.yaml`
- `build/platform-manifest.json`
- `docs/diagrams/service-dependency-graph.excalidraw`
- `docs/site-generated/architecture/dependency-graph.md`
- `collections/ansible_collections/lv3/platform/playbooks/lago.yml`
- `collections/ansible_collections/lv3/platform/roles/lago_runtime/`
- `collections/ansible_collections/lv3/platform/roles/api_gateway_runtime/`
- `receipts/live-applies/2026-03-31-adr-0292-lago-mainline-live-apply.json`
- `receipts/live-applies/evidence/2026-03-31-ws-0292-*`

## Verification

- `git fetch origin --prune` confirmed the newest realistic `origin/main`
  commit as `5c7e07235f7b0da1f756148e145397f0ac6ceb10`, carrying repository
  version `0.177.117` and platform version `0.130.76` before the final ADR
  0292 integration pass.
- The authoritative exact-main replay completed from merged commit
  `11d8bbb4ea1835b7c2c4995749381432d93c7d51` via
  `make live-apply-service service=lago env=production`, reaching
  `PLAY RECAP` with `docker-runtime-lv3 ok=437 changed=152 failed=0`,
  `nginx-lv3 ok=45 changed=4 failed=0`, `postgres-lv3 ok=60 changed=4 failed=0`,
  and `localhost ok=18 changed=0 failed=0`.
- The merged-main verification path proved the public billing contract end to
  end: the protected `billing.lv3.org` browser surface stayed in place, the
  public smoke event reached Lago through the API-gateway adapter after retry,
  and the seeded current-usage query for the smoke customer/subscription pair
  succeeded from the same replay.
- The governed post-apply Restic trigger now succeeds on the merged tree via
  `uv run --with pyyaml python scripts/trigger_restic_live_apply.py ...`,
  returning JSON status `ok`, `returncode: 0`, `governed_sources: 5`,
  `protected: 4`, `uncovered: 0`, and `inactive_sources: ["falco_overrides"]`.
- Integrated repository validation also passed from this worktree:
  `99 passed` across the focused Lago, API-gateway, Docker-runtime, NGINX edge,
  platform-vars, and API slices, plus `make syntax-check-lago`,
  `make syntax-check-api-gateway`, `./scripts/validate_repo.sh agent-standards
  health-probes`, and `make pre-push-gate`.

## Outcome

- Repository version `0.177.118` is the first integrated mainline version that
  records ADR 0292 as implemented.
- Platform version `0.130.77` is the first verified mainline platform version
  that records Lago as live at `billing.lv3.org`.
- `receipts/live-applies/2026-03-31-adr-0292-lago-mainline-live-apply.json` is
  the canonical mainline live-apply receipt for this ADR.
- The earlier branch-local concurrency divergence is retained as evidence only;
  the merged-main `r15` replay is the durable source of truth and no additional
  merge-to-main follow-up remains.
