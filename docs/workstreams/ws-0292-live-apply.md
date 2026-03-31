# Workstream ws-0292-live-apply: Live Apply ADR 0292 From Latest `origin/main`

- ADR: [ADR 0292](../adr/0292-lago-as-the-usage-metering-and-billing-api-layer.md)
- Title: Deploy Lago as the repo-managed usage metering and billing API layer, publish `billing.lv3.org`, and verify metered ingestion end to end
- Status: in_progress
- Included In Repo Version: pending latest exact-main replay
- Platform Version Observed During Integration: 0.130.78
- Release Date: pending latest exact-main replay
- Live Applied On: pending latest exact-main replay
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

- `git fetch origin --prune` now resolves the newest realistic `origin/main`
  commit as `14b18869a2ff421ec12596bd199af0adb09a95b8`. The newest observed
  repository version on that baseline is still `0.177.123`, and the platform
  version recorded before the next ADR 0292 replay remains `0.130.78`.
- Focused repository validation for the current replay hardenings passed from
  this worktree:
  `uv run --with pytest --with pyyaml pytest tests/test_docker_runtime_role.py tests/test_api_gateway_runtime_role.py tests/test_lago_runtime_role.py tests/test_lago_playbook.py tests/test_nginx_edge_publication_role.py tests/test_restic_config_backup.py tests/test_restic_config_backup_role.py tests/test_restic_config_backup_windmill.py tests/test_generate_platform_vars.py tests/test_release_manager.py tests/test_live_apply_receipts.py -q`
  returned `125 passed`, `ANSIBLE_HOST_KEY_CHECKING=False ansible-playbook -i inventory/hosts.yml playbooks/lago.yml --syntax-check -e env=production`
  passed, `uv run --with pyyaml python3 scripts/canonical_truth.py --check`
  passed, and `./scripts/validate_repo.sh agent-standards` passed.
- The latest exact-main replay evidence is
  `receipts/live-applies/evidence/2026-03-31-ws-0292-mainline-r24-live-apply-0.177.123-after-host-quiet.txt`.
  That replay proved the repo-local blockers are fixed on the latest mainline
  baseline: Docker post-restart recovery succeeded, Lago started cleanly,
  direct local health and current-usage verification succeeded, API-gateway
  verification degraded correctly from unavailable local Keycloak discovery to
  the legacy platform-context token, and the host SBOM refresh plus governed
  post-verify path completed.
- `r24` is still concurrency-tainted and cannot be promoted to final truth.
  While the replay was in its final public smoke phase, concurrent shared
  applies from other worktrees overwrote the `billing.lv3.org` edge route.
  Direct public probes at `2026-03-31T21:48:06Z` and `2026-03-31T21:50:55Z`
  returned `HTTP/2 308` redirects from `https://billing.lv3.org/api/health`
  to `https://nginx.lv3.org/api/health`, proving the shared NGINX surface had
  diverged after the Lago play repaired it.
- The later `r26` replay (`receipts/live-applies/evidence/2026-03-31-ws-0292-converge-r26-0.177.123-latest-main-after-exposure-audit.txt`)
  repaired the public edge again and reached the final post-publication
  verification phase, but it was invalidated before recap by another shared
  Docker restart on `docker-runtime-lv3`. Public probes at `2026-03-31T22:14Z`
  showed the browser boundary and `/api/health` route were now correct, yet the
  API gateway returned the canonical `INFRA_DEPENDENCY_DOWN` envelope because
  `docker compose -f /opt/lago/docker-compose.yml ps -a` showed the Lago stack
  had exited after `2026-03-31T22:13:47Z`, when `journalctl -u docker`
  recorded a Docker daemon restart on the same host while multiple other shared
  applies were still active.

## Outcome

- This workstream is still active. The remaining gap is a clean latest-main
  verification of the shared `billing.lv3.org` publication plus the final
  public smoke/current-usage checks after both the edge route and the Lago
  containers stop being invalidated by concurrent work on the shared hosts.
- `receipts/live-applies/2026-03-31-adr-0292-lago-mainline-live-apply.json`
  is stale and must be rewritten only after the next successful latest-main
  replay or targeted edge-repair verification path.
- Merge-to-main remaining steps are:
  1. refresh this branch onto the latest realistic `origin/main`
  2. wait for the shared Docker and NGINX hosts to go quiet
  3. replay the latest-main Lago live apply or a shorter targeted edge-repair
     verification path from this branch
  4. verify public ingest and current usage on `billing.lv3.org`
  5. refresh the ADR/workstream/receipt metadata to the successful result
  6. run canonical truth generation, merge to `main`, push `origin/main`, and
     delete this worktree
