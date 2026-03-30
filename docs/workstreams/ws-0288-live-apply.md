# Workstream ws-0288-live-apply: ADR 0288 Live Apply From Latest `origin/main`

- ADR: [ADR 0288](../adr/0288-flagsmith-as-the-feature-flag-and-remote-configuration-service.md)
- Title: deploy Flagsmith as the repo-managed feature flag and remote configuration control plane
- Status: live_applied
- Included In Repo Version: 0.177.109
- Branch-Local Receipt: `receipts/live-applies/2026-03-30-adr-0288-flagsmith-live-apply.json`
- Canonical Mainline Receipt: `receipts/live-applies/2026-03-30-adr-0288-flagsmith-mainline-live-apply.json`
- Live Applied In Platform Version: 0.130.71
- Implemented On: 2026-03-30
- Live Applied On: 2026-03-30
- Branch: `codex/ws-0288-live-apply-r2`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0288-live-apply-r2`
- Owner: codex
- Depends On: `adr-0021`, `adr-0023`, `adr-0042`, `adr-0077`, `adr-0086`
- Conflicts With: none

## Scope

- add the repo-managed Flagsmith runtime, PostgreSQL setup, edge publication, secret mirrors, image pinning, health probes, and workflow metadata
- live-apply the service from an isolated latest-main worktree and verify local and public behaviour end to end
- carry the verified change through exact-main integration once the workstream branch is fully validated

## Shared Surfaces

- `workstreams.yaml`
- `docs/workstreams/ws-0288-live-apply.md`
- `docs/adr/0288-flagsmith-as-the-feature-flag-and-remote-configuration-service.md`
- `docs/runbooks/configure-flagsmith.md`
- `inventory/host_vars/proxmox_florin.yml`
- `inventory/group_vars/platform.yml`
- `scripts/generate_platform_vars.py`
- `Makefile`
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
- `config/certificate-catalog.json`
- `config/workflow-catalog.json`
- `config/command-catalog.json`
- `config/ansible-execution-scopes.yaml`
- `config/ansible-role-idempotency.yml`
- `config/prometheus/file_sd/https_tls_targets.yml`
- `config/prometheus/rules/https_tls_alerts.yml`
- `playbooks/flagsmith.yml`
- `playbooks/services/flagsmith.yml`
- `collections/ansible_collections/lv3/platform/playbooks/flagsmith.yml`
- `collections/ansible_collections/lv3/platform/playbooks/services/flagsmith.yml`
- `collections/ansible_collections/lv3/platform/roles/flagsmith_postgres/`
- `collections/ansible_collections/lv3/platform/roles/flagsmith_runtime/`
- `scripts/flagsmith_seed.py`
- `tests/test_flagsmith_playbook.py`
- `tests/test_flagsmith_runtime_role.py`
- `tests/test_flagsmith_seed.py`
- `receipts/image-scans/2026-03-30-flagsmith-runtime.json`
- `receipts/live-applies/`

## Verification

- The branch-local converge carried ADR 0288 from the latest available
  `origin/main` lineage at repo version `0.177.108` and made the service true
  on platform version `0.130.71`, recorded in
  `receipts/live-applies/2026-03-30-adr-0288-flagsmith-live-apply.json`.
- The focused repository regression slice passed with `72 passed in 3.58s`
  across the Flagsmith runtime, seed, playbook, platform-vars, DNS, edge
  publication, and subdomain validation surfaces, using
  `uv run --with pytest --with pyyaml --with jsonschema python -m pytest -q tests/test_flagsmith_seed.py tests/test_flagsmith_runtime_role.py tests/test_flagsmith_playbook.py tests/test_generate_platform_vars.py tests/test_hetzner_dns_record_role.py tests/test_nginx_edge_publication_role.py tests/test_subdomain_catalog.py`.
- `make syntax-check-flagsmith` passed on the repaired worktree before the live
  replay.
- The branch-local repository validation bundle passed after the workstream
  manifest was updated to include `tests/test_flagsmith_seed.py`:
  `git diff --check`,
  `uv run --with pyyaml --with jsonschema python scripts/live_apply_receipts.py --validate`,
  `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate`,
  and `./scripts/validate_repo.sh agent-standards workstream-surfaces health-probes`.
  The final ownership replay intentionally scoped `LV3_VALIDATION_CHANGED_FILES_JSON`
  to the ADR 0288 surfaces so two unrelated dirty files already present in the
  shared worktree did not masquerade as this workstream's edits.
- The generic wrapper path
  `ALLOW_IN_PLACE_MUTATION=true HETZNER_DNS_API_TOKEN=... make live-apply-service service=flagsmith env=production`
  exercised the repository automation and correctly stopped at
  `check-canonical-truth` because the protected shared `README.md` publication
  gate still belongs to the exact-main integration step. That expected
  workstream-branch stop is preserved in
  `receipts/live-applies/evidence/2026-03-30-ws-0288-live-apply-service-flagsmith.txt`.
- The focused runtime replay on the settled branch completed successfully in
  `receipts/live-applies/evidence/2026-03-30-ws-0288-flagsmith-runtime-focused-r13.txt`
  with final recap
  `docker-runtime-lv3 : ok=73 changed=0 unreachable=0 failed=0 skipped=29 rescued=0 ignored=0`.
- The governed production replay
  `HETZNER_DNS_API_TOKEN=... make converge-flagsmith env=production` succeeded
  in
  `receipts/live-applies/evidence/2026-03-30-ws-0288-converge-flagsmith-r2.txt`
  with final recaps `docker-runtime-lv3 : ok=171 changed=2 unreachable=0 failed=0 skipped=36 rescued=0 ignored=0`,
  `localhost : ok=23 changed=0 unreachable=0 failed=0 skipped=3 rescued=0 ignored=0`,
  `nginx-lv3 : ok=40 changed=5 unreachable=0 failed=0 skipped=6 rescued=0 ignored=0`,
  and `postgres-lv3 : ok=51 changed=0 unreachable=0 failed=0 skipped=21 rescued=0 ignored=0`.
- Public verification succeeded after the governed replay:
  `curl -fsS https://flags.lv3.org/health` returned the Flagsmith system status
  page, `curl -I https://flags.lv3.org/` and
  `curl -I https://flags.lv3.org/api/v1/projects/` both redirected to the
  shared oauth2-proxy sign-in flow, and a guest-local
  `curl -fsS http://127.0.0.1:8017/health` on `docker-runtime-lv3` returned the
  same status page.
- The correction loop evidence from
  `receipts/live-applies/evidence/2026-03-30-ws-0288-flagsmith-featurestate-debug-r7.txt`,
  `receipts/live-applies/evidence/2026-03-30-ws-0288-flagsmith-seed-debug-r8.txt`,
  and the sequential `receipts/live-applies/evidence/2026-03-30-ws-0288-flagsmith-runtime-focused-r*.txt`
  files captures the sparse feature-state PATCH response shape, typed nested
  feature values, and the Docker bridge-chain/runtime recovery work that had
  to land before the replay settled.
- During the correction loop a manual Hetzner DNS API create was used to add
  the `flags.lv3.org` A record, but the settled repository converge now treats
  the canonical record as managed and drift-free, with both DNS tasks skipped
  because no change is required.
- The exact-main integration lane then carried ADR 0288 onto the shared
  `origin/main` baseline after it had already settled at
  `0.177.109 / 0.130.72`, replayed the committed `0.177.109` source, and
  published the canonical receipt
  `receipts/live-applies/2026-03-30-adr-0288-flagsmith-mainline-live-apply.json`.

## Mainline Closeout

- The branch-local receipt remains the first-live audit trail for ADR 0288 on
  platform version `0.130.71`.
- The protected release and canonical-truth surfaces are now carried by
  `ws-0288-main-merge`, whose canonical receipt is
  `receipts/live-applies/2026-03-30-adr-0288-flagsmith-mainline-live-apply.json`.
- The exact-main integration lane preserves the already-merged
  `0.177.109 / 0.130.72` baseline while carrying ADR 0288's canonical
  mainline receipt and preserving this workstream's branch-local evidence as
  audit history.
