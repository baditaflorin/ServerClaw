# Workstream ws-0288-main-merge

- ADR: [ADR 0288](../adr/0288-flagsmith-as-the-feature-flag-and-remote-configuration-service.md)
- Title: Integrate ADR 0288 Flagsmith exact-main replay onto `origin/main`
- Status: merged
- Included In Repo Version: 0.177.109
- Platform Version Observed During Integration: 0.130.72
- Release Date: 2026-03-30
- Live Applied On: 2026-03-30
- Branch: `codex/ws-0288-main-merge`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0288-main-candidate`
- Owner: codex
- Depends On: `ws-0288-live-apply`

## Purpose

Carry the verified ADR 0288 Flagsmith workstream onto the newest available
`origin/main`, refresh the protected release and canonical-truth surfaces from
that synchronized baseline, rerun the exact-main live replay from committed
source, and publish the canonical mainline receipt that preserves the settled
`0.177.109 / 0.130.72` release and platform baseline.

## Shared Surfaces

- `workstreams.yaml`
- `docs/workstreams/ws-0288-main-merge.md`
- `docs/workstreams/ws-0288-live-apply.md`
- `docs/adr/0288-flagsmith-as-the-feature-flag-and-remote-configuration-service.md`
- `docs/adr/.index.yaml`
- `docs/runbooks/configure-flagsmith.md`
- `inventory/host_vars/proxmox_florin.yml`
- `inventory/group_vars/platform.yml`
- `scripts/generate_platform_vars.py`
- `Makefile`
- `collections/ansible_collections/lv3/platform/roles/hetzner_dns_record/tasks/main.yml`
- `collections/ansible_collections/lv3/platform/roles/nginx_edge_publication/defaults/main.yml`
- `config/service-capability-catalog.json`
- `config/health-probe-catalog.json`
- `config/image-catalog.json`
- `config/secret-catalog.json`
- `config/controller-local-secrets.json`
- `config/data-catalog.json`
- `config/service-completeness.json`
- `config/service-redundancy-catalog.json`
- `config/dependency-graph.json`
- `config/subdomain-catalog.json`
- `config/subdomain-exposure-registry.json`
- `config/certificate-catalog.json`
- `config/workflow-catalog.json`
- `config/command-catalog.json`
- `config/ansible-execution-scopes.yaml`
- `config/ansible-role-idempotency.yml`
- `config/uptime-kuma/monitors.json`
- `config/prometheus/file_sd/https_tls_targets.yml`
- `config/prometheus/rules/https_tls_alerts.yml`
- `playbooks/flagsmith.yml`
- `playbooks/services/flagsmith.yml`
- `collections/ansible_collections/lv3/platform/playbooks/flagsmith.yml`
- `collections/ansible_collections/lv3/platform/playbooks/services/flagsmith.yml`
- `collections/ansible_collections/lv3/platform/roles/flagsmith_postgres/**`
- `collections/ansible_collections/lv3/platform/roles/flagsmith_runtime/**`
- `scripts/flagsmith_seed.py`
- `tests/test_flagsmith_playbook.py`
- `tests/test_flagsmith_runtime_role.py`
- `tests/test_flagsmith_seed.py`
- `tests/test_generate_platform_vars.py`
- `tests/test_hetzner_dns_record_role.py`
- `tests/test_nginx_edge_publication_role.py`
- `tests/test_subdomain_catalog.py`
- `README.md`
- `RELEASE.md`
- `VERSION`
- `changelog.md`
- `docs/release-notes/README.md`
- `docs/release-notes/*.md`
- `versions/stack.yaml`
- `build/platform-manifest.json`
- `docs/site-generated/architecture/dependency-graph.md`
- `docs/diagrams/agent-coordination-map.excalidraw`
- `docs/diagrams/service-dependency-graph.excalidraw`
- `receipts/image-scans/2026-03-30-flagsmith-runtime.json`
- `receipts/image-scans/2026-03-30-flagsmith-runtime.trivy.json`
- `receipts/live-applies/2026-03-30-adr-0288-flagsmith-live-apply.json`
- `receipts/live-applies/2026-03-30-adr-0288-flagsmith-mainline-live-apply.json`
- `receipts/live-applies/evidence/2026-03-30-ws-0288-mainline-*`

## Verification

- `git fetch origin --prune` confirmed the exact-main baseline before release
  work and replay.
- The focused Flagsmith compatibility slice passed on the exact-main branch:
  `uv run --with pytest --with pyyaml --with jsonschema python -m pytest -q tests/test_flagsmith_seed.py tests/test_flagsmith_runtime_role.py tests/test_flagsmith_playbook.py tests/test_generate_platform_vars.py tests/test_hetzner_dns_record_role.py tests/test_nginx_edge_publication_role.py tests/test_subdomain_catalog.py`
  returned `72 passed` in
  `receipts/live-applies/evidence/2026-03-30-ws-0288-mainline-r1-targeted-checks.txt`.
- `make syntax-check-flagsmith` passed on the synchronized tree, recorded in
  `receipts/live-applies/evidence/2026-03-30-ws-0288-mainline-r1-syntax-checks.txt`.
- The earlier exact-main candidate preserved release-preparation provenance in
  `receipts/live-applies/evidence/2026-03-30-ws-0288-mainline-r2-release-dry-run.txt`
  and `receipts/live-applies/evidence/2026-03-30-ws-0288-mainline-r1-release-write.txt`;
  after `origin/main` later absorbed ADR 0293, the rebased merge retained
  those receipts as history while preserving the already-published
  `0.177.109 / 0.130.72` baseline.
- The authoritative exact-main replay from committed source
  `0b32e585bbf2f0445f9eddd153923f93c221dba2` passed via
  `ALLOW_IN_PLACE_MUTATION=true HETZNER_DNS_API_TOKEN=... make live-apply-service service=flagsmith env=production`,
  recorded in
  `receipts/live-applies/evidence/2026-03-30-ws-0288-mainline-r2-live-apply-service-0.177.109.txt`,
  with final recaps
  `docker-runtime-lv3 : ok=171 changed=3 unreachable=0 failed=0 skipped=36 rescued=0 ignored=0`,
  `localhost : ok=23 changed=0 unreachable=0 failed=0 skipped=3 rescued=0 ignored=0`,
  `nginx-lv3 : ok=40 changed=5 unreachable=0 failed=0 skipped=6 rescued=0 ignored=0`,
  and `postgres-lv3 : ok=51 changed=0 unreachable=0 failed=0 skipped=21 rescued=0 ignored=0`;
  the public health probe retried once before settling.
- Public and guest-local runtime proofs were captured in
  `receipts/live-applies/evidence/2026-03-30-ws-0288-mainline-r2-public-health-0.177.109.html`,
  `receipts/live-applies/evidence/2026-03-30-ws-0288-mainline-r2-public-ui-headers-0.177.109.txt`,
  `receipts/live-applies/evidence/2026-03-30-ws-0288-mainline-r2-public-api-headers-0.177.109.txt`,
  `receipts/live-applies/evidence/2026-03-30-ws-0288-mainline-r2-host-state-0.177.109.txt`,
  `receipts/live-applies/evidence/2026-03-30-ws-0288-mainline-r2-guest-health-0.177.109.html`,
  and
  `receipts/live-applies/evidence/2026-03-30-ws-0288-mainline-r2-guest-runtime-state-0.177.109.txt`.
- `git diff --check`, `scripts/live_apply_receipts.py --validate`,
  `scripts/validate_repository_data_models.py --validate`, and
  `./scripts/validate_repo.sh agent-standards workstream-surfaces health-probes`
  passed on the exact-main branch and were recorded under the
  `2026-03-30-ws-0288-mainline-r3-*` evidence set.
- `make remote-validate` on the shared exact-main worktree correctly exposed
  the remaining merge-candidate gaps: the generated
  `config/prometheus/file_sd/https_tls_targets.yml` and
  `docs/site-generated/architecture/dependency-graph.md` artifacts still need a
  clean refresh, and the remote snapshot also inherited an unrelated dirty
  `receipts/ops-portal-snapshot.html` from the shared worktree. The final gate
  reruns therefore move to a clean exact-main candidate worktree before
  `main` is updated.
- After moving the active workstream to the clean candidate worktree and
  refreshing `config/prometheus/file_sd/https_tls_targets.yml`,
  `config/prometheus/rules/https_tls_alerts.yml`, and
  `docs/site-generated/architecture/dependency-graph.md`, the exact-main
  automation bundle all passed: `git diff --check`,
  `uv run --with pyyaml --with jsonschema python scripts/live_apply_receipts.py --validate`,
  `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate`,
  `./scripts/validate_repo.sh agent-standards workstream-surfaces health-probes`,
  `make remote-validate`, and `make pre-push-gate`, preserved in the
  `2026-03-30-ws-0288-mainline-r4-*` evidence set.
- `receipts/live-applies/2026-03-30-adr-0288-flagsmith-mainline-live-apply.json`
  records the canonical exact-main receipt from committed source
  `0b32e585bbf2f0445f9eddd153923f93c221dba2`, while the earlier branch-local
  receipt remains preserved as first-live audit history on platform version
  `0.130.71`.

## Outcome

- Release `0.177.109` now carries ADR 0288 on top of the settled shared
  mainline baseline of `0.177.109 / 0.130.72`.
- The authoritative committed replay from
  `0b32e585bbf2f0445f9eddd153923f93c221dba2` refreshed the repo-managed
  Flagsmith runtime plus the authenticated public `flags.lv3.org` edge route
  on the live server, and the integrated canonical truth preserves that
  verified release and platform baseline while adding the Flagsmith mainline
  receipt.
- `receipts/live-applies/2026-03-30-adr-0288-flagsmith-mainline-live-apply.json`
  is the canonical mainline receipt for ADR 0288; the earlier branch-local
  receipt on `0.130.71` remains part of the audit trail.
