# Workstream ws-0292-live-apply: Live Apply ADR 0292 From Latest `origin/main`

- ADR: [ADR 0292](../adr/0292-lago-as-the-usage-metering-and-billing-api-layer.md)
- Title: Deploy Lago as the repo-managed usage metering and billing API layer, publish `billing.lv3.org`, and verify metered ingestion end to end
- Status: merged
- Included In Repo Version: 0.177.128
- Canonical Mainline Receipt: `receipts/live-applies/2026-04-01-adr-0292-lago-mainline-live-apply.json`
- Platform Version Observed During Integration: 0.130.80
- Live Applied In Platform Version: 0.130.81
- Release Date: 2026-04-01
- Implemented On: 2026-03-31
- Live Applied On: 2026-04-01
- Branch: `codex/ws-0292-main-integration-r1`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0292-live-apply-r2`
- Owner: codex
- Depends On: `adr-0021-public-subdomain-publication`, `adr-0042-postgresql-as-the-shared-relational-database`, `adr-0063-keycloak-sso-for-internal-services`, `adr-0077-compose-secret-injection-pattern`, `adr-0086-backup-and-recovery`, `adr-0276-nats-jetstream-as-the-platform-event-bus`
- Conflicts With: none
- Shared Surfaces: `workstreams.yaml`, `Makefile`, `README.md`, `RELEASE.md`, `VERSION`, `changelog.md`, `docs/adr/0292`, `docs/workstreams/ws-0292-live-apply.md`, `docs/runbooks/configure-lago.md`, `docs/release-notes/README.md`, `docs/release-notes/*.md`, `docs/diagrams/agent-coordination-map.excalidraw`, `docs/diagrams/service-dependency-graph.excalidraw`, `docs/site-generated/architecture/dependency-graph.md`, `build/platform-manifest.json`, `versions/stack.yaml`, `inventory/host_vars/proxmox_florin.yml`, `inventory/group_vars/platform.yml`, `playbooks/lago.yml`, `playbooks/services/lago.yml`, `collections/ansible_collections/lv3/platform/playbooks/api-gateway.yml`, `collections/ansible_collections/lv3/platform/playbooks/lago.yml`, `collections/ansible_collections/lv3/platform/playbooks/services/lago.yml`, `roles/lago_postgres/`, `roles/lago_runtime/`, `roles/api_gateway_runtime/`, `roles/nginx_edge_publication/`, `collections/ansible_collections/lv3/platform/roles/common/tasks/docker_bridge_chains.yml`, `collections/ansible_collections/lv3/platform/roles/docker_runtime/defaults/main.yml`, `collections/ansible_collections/lv3/platform/roles/docker_runtime/tasks/main.yml`, `scripts/api_gateway/main.py`, `scripts/generate_platform_vars.py`, `config/*catalog*.json`, `config/ansible-execution-scopes.yaml`, `config/ansible-role-idempotency.yml`, `config/prometheus/file_sd/https_tls_targets.yml`, `config/prometheus/rules/https_tls_alerts.yml`, `config/uptime-kuma/monitors.json`, `receipts/image-scans/`, `receipts/live-applies/`, `receipts/live-applies/evidence/`, `receipts/ops-portal-snapshot.html`, `receipts/sbom/**`, `tests/`

## Scope

- refresh the ADR 0292 Lago stack onto the latest realistic `origin/main`
  baseline before final integration
- replay the governed repo-managed converge from that refreshed tree
- verify the protected browser surface, gateway-mediated public smoke event
  ingestion, and seeded current-usage aggregation end to end
- record the canonical receipt, evidence bundle, and merge-safe workstream
  state for the successful 2026-04-01 replay

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
- `collections/ansible_collections/lv3/platform/playbooks/api-gateway.yml`
- `collections/ansible_collections/lv3/platform/playbooks/lago.yml`
- `collections/ansible_collections/lv3/platform/roles/lago_runtime/`
- `collections/ansible_collections/lv3/platform/roles/api_gateway_runtime/`
- `receipts/live-applies/2026-03-31-adr-0292-lago-mainline-live-apply.json`
- `receipts/sbom/host-docker-runtime-lv3-2026-04-01.cdx.json`
- `receipts/live-applies/evidence/2026-03-31-ws-0292-*`

## Verification

- `git fetch origin --prune` first resolved the refreshed replay baseline as
  `741241bf8739a093bc396900cd6f0ce6056a192b` (`Merge gitea/main history`), so
  the successful Lago replay ran on repository version `0.177.126` and
  platform version `0.130.80` before release promotion. Later the same day
  `origin/main` advanced again to `ef62d910cd1c873e09200ce48b20c5ad4bf0f1c1`
  (`[mainline] Merge ws-0315 gitea followups`); that newer mainline was merged
  into this promotion branch without requiring a second Lago replay because the
  ws-0315 changes were repo-only Gitea automation follow-ups.
- Focused repository validation on the refreshed tree passed before the final
  replay: `uv run --with pytest --with pyyaml --with-requirements requirements/api-gateway.txt pytest tests/test_api_gateway.py tests/test_api_gateway_runtime_role.py tests/test_docker_runtime_role.py tests/test_generate_platform_vars.py tests/test_lago_playbook.py tests/test_lago_runtime_role.py tests/test_nginx_edge_publication_role.py tests/test_restic_config_backup.py tests/test_restic_config_backup_role.py -q`
  returned `134 passed in 13.76s`.
- Repo automation and repository-model checks on the refreshed tree also
  passed: `make syntax-check-lago`, `./scripts/validate_repo.sh agent-standards`,
  and `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate`.
- The final protected-surface validation also passed before merge:
  `uvx --from pyyaml python scripts/canonical_truth.py --write`,
  `make generate-status`,
  `uv run --with jsonschema python scripts/generate_dependency_diagram.py --write`,
  `uv run --with pyyaml --with jsonschema python scripts/platform_manifest.py --write`,
  and `make pre-push-gate` on the final latest-main merge tip rooted at
  `ef62d910cd1c873e09200ce48b20c5ad4bf0f1c1`. The durable proof is
  `receipts/live-applies/evidence/2026-04-01-ws-0292-main-pre-push-gate-r7.txt`.
- The successful latest-main replay evidence is
  `receipts/live-applies/evidence/2026-04-01-ws-0292-mainline-r31-converge-0.177.126.txt`.
  `make converge-lago env=production` completed with clean recap
  `docker-runtime-lv3 ok=447 changed=150 failed=0`,
  `nginx-lv3 ok=45 changed=4 failed=0`,
  `postgres-lv3 ok=74 changed=0 failed=0`,
  `localhost ok=18 changed=0 failed=0`.
- Public proof before and after the replay is captured in
  `receipts/live-applies/evidence/2026-04-01-ws-0292-main-pre-apply-public-baseline-r2-0.177.126.txt`
  and
  `receipts/live-applies/evidence/2026-04-01-ws-0292-main-post-apply-public-verification-r1-0.177.126.txt`.
  Before the replay, both `/` and `/api/health` were misrouted through
  `nginx.lv3.org` as `HTTP/2 308` redirects. After the replay, `/` returned
  the expected shared oauth2 sign-in redirect and `/api/health` returned the
  expected canonical `401` gateway rejection for anonymous callers.
- The converged playbook also re-verified the public smoke event path through
  the API-gateway billing adapter and confirmed current usage reflects the
  fresh public smoke transaction on the same run.

## Results

- ADR 0292 is now re-verified from the latest realistic `origin/main` lineage
  with a clean 2026-04-01 replay on top of the refreshed mainline tree and a
  final closeout rebased onto `ef62d910cd1c873e09200ce48b20c5ad4bf0f1c1`.
- The historical 2026-03-31 concurrency-tainted evidence remains in the branch
  as audit context, but the April 1 `r31` replay supersedes it as the durable
  latest-main proof for `billing.lv3.org`.
- The final integration step promotes this replay into repository version
  `0.177.128` and platform version `0.130.81`, with
  `receipts/live-applies/2026-04-01-adr-0292-lago-mainline-live-apply.json`
  as the canonical receipt.
