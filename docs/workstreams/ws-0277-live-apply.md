# Workstream ws-0277-live-apply: ADR 0277 Live Apply From Latest `origin/main`

- ADR: [ADR 0277](../adr/0277-typesense-as-the-full-text-search-engine-for-internal-structured-data.md)
- Title: private Typesense structured-search service exact-main closeout
- Status: live_applied
- Included In Repo Version: 0.177.124
- Branch-Local Receipt: `receipts/live-applies/2026-03-31-adr-0277-typesense-mainline-live-apply.json`
- Canonical Mainline Receipt: `receipts/live-applies/2026-03-31-adr-0277-typesense-mainline-live-apply.json`
- Live Applied In Platform Version: 0.130.79
- Implemented On: 2026-03-31
- Live Applied On: 2026-03-31
- Branch: `codex/ws-0277-main-closeout-r2`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0277-main-closeout`
- Owner: codex
- Depends On: `adr-0077-compose-runtime-secrets`, `adr-0092-unified-platform-api-gateway`, `adr-0153-distributed-resource-lock-registry`, `adr-0191-immutable-guest-replacement`
- Conflicts With: none
- Shared Surfaces: `workstreams.yaml`, `docs/workstreams/ws-0277-live-apply.md`, `docs/adr/0277-typesense-as-the-full-text-search-engine-for-internal-structured-data.md`, `docs/adr/.index.yaml`, `docs/schema/api-gateway-catalog.schema.json`, `docs/runbooks/configure-typesense.md`, `inventory/host_vars/proxmox_florin.yml`, `inventory/group_vars/platform.yml`, `scripts/generate_platform_vars.py`, `scripts/api_gateway/main.py`, `scripts/api_gateway_catalog.py`, `scripts/restic_config_backup.py`, `platform/health/composite.py`, `Makefile`, `config/service-capability-catalog.json`, `config/health-probe-catalog.json`, `config/image-catalog.json`, `config/service-completeness.json`, `config/service-redundancy-catalog.json`, `config/api-gateway-catalog.json`, `config/dependency-graph.json`, `config/slo-catalog.json`, `config/data-catalog.json`, `config/secret-catalog.json`, `config/controller-local-secrets.json`, `config/command-catalog.json`, `config/workflow-catalog.json`, `config/ansible-execution-scopes.yaml`, `config/grafana/dashboards/typesense.json`, `config/grafana/dashboards/slo-overview.json`, `config/alertmanager/rules/typesense.yml`, `config/prometheus/file_sd/slo_targets.yml`, `config/prometheus/rules/slo_alerts.yml`, `config/prometheus/rules/slo_rules.yml`, `playbooks/typesense.yml`, `playbooks/services/typesense.yml`, `collections/ansible_collections/lv3/platform/playbooks/typesense.yml`, `collections/ansible_collections/lv3/platform/playbooks/services/typesense.yml`, `collections/ansible_collections/lv3/platform/roles/typesense_runtime/**`, `collections/ansible_collections/lv3/platform/roles/api_gateway_runtime/**`, `collections/ansible_collections/lv3/platform/roles/docker_runtime/**`, `collections/ansible_collections/lv3/platform/roles/proxmox_tailscale_proxy/**`, `scripts/typesense_catalog_sync.py`, `README.md`, `RELEASE.md`, `VERSION`, `changelog.md`, `docs/release-notes/`, `build/platform-manifest.json`, `versions/stack.yaml`, `docs/site-generated/architecture/dependency-graph.md`, `docs/diagrams/agent-coordination-map.excalidraw`, `docs/diagrams/service-dependency-graph.excalidraw`, `receipts/ops-portal-snapshot.html`, `receipts/image-scans/`, `receipts/live-applies/`, `tests/`, `tests/test_restic_config_backup.py`

## Scope

- deploy the repo-managed private Typesense runtime on `docker-runtime-lv3`
- publish the private controller path on `http://100.64.0.1:8016`
- populate the repo-managed `platform-services` collection from git-declared
  service metadata
- expose authenticated structured search through
  `https://api.lv3.org/v1/platform/search/structured`
- leave canonical mainline evidence, ADR metadata, and workstream truth in a
  merge-safe state

## Verification

- The rebased regression slice passed with
  `93 passed in 9.32s` across the Typesense runtime, API gateway, Docker
  recovery, platform-vars, and catalog-sync test surfaces.
- `make syntax-check-docker-runtime`, `make syntax-check-typesense`,
  `make syntax-check-api-gateway`, `make syntax-check-restic-config-backup`,
  `make validate-generated-vars`, and `make validate-generated-slo` all passed
  on the rebased mainline candidate.
- `scripts/validate_repo.sh data-models health-probes alert-rules
  agent-standards` passed on the same candidate before the exact-main replay.
- The exact-main closeout also hardened the post-apply Restic hook so
  compose-managed `outline-minio` recovery now uses `docker compose up -d`,
  waits for the MinIO health endpoint, and times out `restic snapshots --json`
  after 60 seconds instead of hanging indefinitely when the shared runtime host
  is still being churned by concurrent live applies. The repo proof for that
  behavior is preserved in
  `receipts/live-applies/evidence/2026-03-31-ws-0277-mainline-restic-backup-r2-0.177.124.txt`
  and
  `receipts/live-applies/evidence/2026-03-31-ws-0277-mainline-targeted-role-and-backup-tests-r3-0.177.124.txt`.
- Branch-local runtime proof already preserved the working Typesense listener,
  controller proxy, collection query, runtime assurance, and authenticated
  API gateway search route in
  `receipts/live-applies/evidence/2026-03-31-ws-0277-typesense-recovery-r26.txt`,
  `receipts/live-applies/evidence/2026-03-31-ws-0277-controller-typesense-proxy-r26.txt`,
  `receipts/live-applies/evidence/2026-03-31-ws-0277-controller-typesense-collection-r26.json`,
  `receipts/live-applies/evidence/2026-03-31-ws-0277-runtime-assurance-r26.txt`,
  and
  `receipts/live-applies/evidence/2026-03-31-ws-0277-public-structured-search-r26.txt`.

## Mainline Completion

- The exact-main closeout reuses the clean integration branch
  `codex/ws-0277-main-closeout-r2` from latest `origin/main` release
  `0.177.123`
  and records the canonical Typesense receipt as
  `receipts/live-applies/2026-03-31-adr-0277-typesense-mainline-live-apply.json`.
- The final closeout advances repository version `0.177.124` and tracked
  platform version `0.130.79`.
- Protected integration surfaces are refreshed on the same clean candidate so
  `origin/main` can accept the fast-forward closeout without another Typesense
  follow-up branch.
