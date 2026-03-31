# Workstream ws-0281-live-apply: Live Apply ADR 0281 From Latest `origin/main`

- ADR: [ADR 0281](../adr/0281-glitchtip-as-the-sentry-compatible-application-error-tracker.md)
- Title: Replace the partial ad hoc GlitchTip install with a repo-managed Sentry-compatible error tracking service, instrument first-party producers, and verify the live stack end to end
- Status: in_progress
- Included In Repo Version: 0.177.104
- Branch-Local Receipt: pending fresh `0.177.123` quiet-window replay; latest blocked probes `receipts/live-applies/evidence/2026-03-31-adr-0281-quiet-window-blocked-r5-0.177.123.txt` and `receipts/live-applies/evidence/2026-03-31-adr-0281-quiet-window-waiter-r4-0.177.122.txt`; historical receipt `receipts/live-applies/2026-03-30-adr-0281-glitchtip-live-apply.json`
- Canonical Mainline Receipt: pending final `main` integration
- Live Applied In Platform Version: historical branch-local replay `0.130.69`; latest-main re-verification pending
- Implemented On: 2026-03-30
- Live Applied On: 2026-03-30
- Latest origin/main Base: `0.177.123` at `bd9f92ea90ee07df43caaafcf979701d4a9ccb41`
- Branch: `codex/ws-0281-mainline-v2`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0281-mainline-v2`
- Owner: codex
- Depends On: `adr-0021-public-subdomain-publication-at-the-nginx-edge`, `adr-0042-postgresql-as-the-shared-relational-database`, `adr-0063-keycloak-sso-for-internal-services`, `adr-0077-compose-secrets-injection-pattern`, `adr-0130-mail-platform-for-transactional-email`, `adr-0191-immutable-guest-replacement`
- Conflicts With: none
- Shared Surfaces: `workstreams.yaml`, `docs/workstreams/ws-0281-live-apply.md`, `docs/adr/0281-glitchtip-as-the-sentry-compatible-application-error-tracker.md`, `docs/runbooks/configure-glitchtip.md`, `receipts/live-applies/`, `playbooks/glitchtip.yml`, `playbooks/services/glitchtip.yml`, `collections/ansible_collections/lv3/platform/roles/glitchtip_runtime/`, `collections/ansible_collections/lv3/platform/roles/glitchtip_postgres/`, `collections/ansible_collections/lv3/platform/roles/keycloak_runtime/`, `collections/ansible_collections/lv3/platform/roles/mail_platform_runtime/`, `inventory/host_vars/proxmox_florin.yml`, `inventory/group_vars/platform.yml`, `build/platform-manifest.json`, `config/`, `scripts/`, `tests/`, `Makefile`

## Scope

- introduce a repo-managed GlitchTip service published at `errors.lv3.org`
- move the service onto the shared PostgreSQL, Keycloak, OpenBao, and NGINX platform patterns
- replace the unstable ad hoc runtime on `docker-runtime-lv3` with an automation-owned deployment
- instrument first-party producers so GlitchTip receives real Sentry-compatible events
- verify the branch-local live apply from the latest synchronized `origin/main` and record the evidence

## Non-Goals

- updating `VERSION`, release sections in `changelog.md`, the integrated `README.md` top-level status summary, or `versions/stack.yaml` on this workstream branch
- claiming a broader production-readiness posture beyond the ADR 0281 error-tracking scope
- rewriting unrelated platform services or replacing existing Loki, Tempo, Langfuse, or Grafana responsibilities

## Expected Repo Surfaces

- `playbooks/glitchtip.yml`
- `playbooks/services/glitchtip.yml`
- `build/platform-manifest.json`
- `collections/ansible_collections/lv3/platform/roles/glitchtip_runtime/`
- `collections/ansible_collections/lv3/platform/roles/glitchtip_postgres/`
- `collections/ansible_collections/lv3/platform/roles/docker_runtime/`
- `collections/ansible_collections/lv3/platform/roles/hetzner_dns_record/`
- `collections/ansible_collections/lv3/platform/roles/hetzner_dns_records/`
- `collections/ansible_collections/lv3/platform/roles/keycloak_runtime/`
- `collections/ansible_collections/lv3/platform/roles/mail_platform_runtime/`
- `inventory/host_vars/proxmox_florin.yml`
- `inventory/group_vars/platform.yml`
- `config/`
- `scripts/`
- `tests/`
- `Makefile`
- `docs/adr/0281-glitchtip-as-the-sentry-compatible-application-error-tracker.md`
- `docs/runbooks/configure-glitchtip.md`
- `docs/workstreams/ws-0281-live-apply.md`
- `workstreams.yaml`
- `receipts/live-applies/`

## Expected Live Surfaces

- `docker-runtime-lv3` runs the GlitchTip application and its supporting runtime containers under repo-managed automation
- `postgres-lv3` hosts the `glitchtip` database under the shared PostgreSQL management model
- `errors.lv3.org` is published through the NGINX edge with a valid HTTPS response
- Keycloak OIDC login works for GlitchTip admin access
- first-party producers can send Sentry-compatible events that appear in GlitchTip projects

## Ownership Notes

- this workstream owns the branch-local ADR 0281 implementation, live-apply verification, and receipts
- the current host already contains a partial manual GlitchTip install; replacing or reconciling it must preserve useful state without treating the ad hoc compose files as canonical truth
- protected release files remain deferred until the later main integration step, even if the branch-local live apply completes successfully
- the handoff must state the exact merge-to-main follow-through still required after the live apply is verified

## Latest-Main Replay Status

- ADR 0281 has now been replayed onto the current fetched `origin/main` base `bd9f92ea90ee07df43caaafcf979701d4a9ccb41` (`0.177.123`) with rebased commits `427ec280a`, `915074cb5`, `3acd60ab7`, `e837b66e2`, `dc43c5173`, `bf9bf8c9f`, `03f177ebe`, and `9367ba441`.
- Fresh latest-main targeted validation passed from this worktree: `109 passed` across the replayed and hardening-adjacent pytest surfaces, captured in `receipts/live-applies/evidence/2026-03-31-adr-0281-targeted-latest-main-tests-r5-0.177.123.txt`.
- Latest-main repo validation is green on `0.177.123` through `make syntax-check-glitchtip`, `./scripts/validate_repo.sh workstream-surfaces agent-standards yaml json role-argument-specs data-models`, `./scripts/validate_repo.sh ansible-syntax`, `./scripts/validate_repo.sh ansible-lint`, `scripts/platform_manifest.py --check`, `scripts/generate_slo_rules.py --check`, `scripts/generate_dependency_diagram.py --check`, `scripts/generate_diagrams.py --check`, `./scripts/validate_repo.sh generated-portals`, and `git diff --check`; see `receipts/live-applies/evidence/2026-03-31-adr-0281-repo-validation-summary-r5-0.177.123.txt`, `receipts/live-applies/evidence/2026-03-31-adr-0281-repo-contract-refresh-r3-0.177.123.txt`, `receipts/live-applies/evidence/2026-03-31-adr-0281-ansible-lint-r1-0.177.123.txt`, and `receipts/live-applies/evidence/2026-03-31-adr-0281-generated-non-readme-checks-r5-0.177.123.txt`.
- The `0.177.123` replay needed a generated refresh of `docs/diagrams/agent-coordination-map.excalidraw` after `scripts/generate_diagrams.py --check` reported stale generated output; the refreshed map now records `304` parallel branches instead of `303`.
- `config/subdomain-exposure-registry.json` remains refreshed from `scripts/subdomain_exposure_audit.py --write-registry`, and the branch-local contract checks now pass again after this latest `0.177.123` truth refresh through `make syntax-check-glitchtip`, `./scripts/validate_repo.sh workstream-surfaces agent-standards yaml json role-argument-specs data-models`, `./scripts/validate_repo.sh ansible-syntax`, and `git diff --check`; see `receipts/live-applies/evidence/2026-03-31-adr-0281-repo-contract-refresh-r3-0.177.123.txt`.
- `scripts/canonical_truth.py --check` and `scripts/generate_status_docs.py --check` still fail only because they want to refresh the protected top-level `README.md` and generated status docs; that protected-file integration remains intentionally deferred until this workstream finishes the latest-main live apply. Evidence is in `receipts/live-applies/evidence/2026-03-31-adr-0281-generated-surfaces-except-canonical-r5-0.177.123.txt`.
- A fresh quiet-window probe on `0.177.123` is still blocked by concurrent live applies touching the same shared hosts. `receipts/live-applies/evidence/2026-03-31-adr-0281-quiet-window-blocked-r5-0.177.123.txt` captures blocked checks against `postgres-lv3`, `docker-runtime-lv3`, and `nginx-lv3` with 5 conflicting controller-local `ansible-playbook` processes, while `receipts/live-applies/evidence/2026-03-31-adr-0281-quiet-window-waiter-r4-0.177.122.txt` records that a 15-minute waiter never found a quiet controller window.
- Read-only public-surface observation still shows shared-edge drift: `errors.lv3.org` resolves to `65.108.75.123`, but the edge is serving `CN=nginx.lv3.org` and returning `308` redirects to `https://nginx.lv3.org/...` for both the GlitchTip health and auth endpoints. Evidence is in `receipts/live-applies/evidence/2026-03-31-adr-0281-current-public-surface-r5-0.177.123.txt`.
- Because the shared hosts are not quiet and the public edge is presently drifted, the latest-main GlitchTip live apply has not yet been rerun safely from this worktree.

## Verification

- `uv run --with pytest python -m pytest -q`
- `uv run --with pyyaml python scripts/workflow_catalog.py --validate`
- `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate`
- `uv run --with pyyaml python scripts/generate_adr_index.py --write`
- `./scripts/validate_repo.sh agent-standards`
- `make live-apply-service service=glitchtip env=production`
- branch-local SSH, HTTP, and API checks proving publication, health, OIDC, and event ingestion end to end

## Branch-Local Results

- `receipts/live-applies/2026-03-30-adr-0281-glitchtip-live-apply.json`
  records the synchronized branch-local replay from committed source
  `229fd0933019701297b96259aef6a9b6beecfdcd` on repository version
  `0.177.104` and live platform version `0.130.69`.
- `make converge-glitchtip` completed successfully from the rebased latest-main
  tree with final recap `docker-runtime-lv3 : ok=261 changed=5 failed=0
  skipped=60`, `postgres-lv3 : ok=51 changed=0 failed=0 skipped=14`,
  `nginx-lv3 : ok=40 changed=5 failed=0 skipped=6`, and `localhost : ok=27
  changed=0 failed=0 skipped=5`, preserved in
  `receipts/live-applies/evidence/2026-03-30-ws-0281-converge-glitchtip-final6.txt`.
- Fresh public verification preserved in
  `receipts/live-applies/evidence/2026-03-30-ws-0281-glitchtip-public-verification.txt`
  confirmed `errors.lv3.org` resolves to `65.108.75.123`, the shared edge now
  renders dedicated `server_name errors.lv3.org` blocks, the public health
  endpoint returns `{"healthy": {}, "problems": []}`, the GlitchTip auth
  config advertises the repo-managed Keycloak OIDC provider, and an end-to-end
  smoke event landed in the `platform-findings` project.
- `make converge-mail-platform` and `make converge-windmill` were replayed
  after the GlitchTip bootstrap to refresh producer consumers, with successful
  evidence in
  `receipts/live-applies/evidence/2026-03-30-ws-0281-converge-mail-platform.txt`
  and
  `receipts/live-applies/evidence/2026-03-30-ws-0281-converge-windmill.txt`.
- Fresh producer checks preserved in
  `receipts/live-applies/evidence/2026-03-30-ws-0281-mail-gateway-sentry-env.txt`
  and
  `receipts/live-applies/evidence/2026-03-30-ws-0281-windmill-runtime-evidence.txt`
  confirmed the reconverged `lv3-mail-gateway` runtime exports
  `SENTRY_DSN=https://<redacted>@errors.lv3.org/1`,
  `SENTRY_ENVIRONMENT=production`, and `SENTRY_RELEASE=0.177.56`, while the
  Windmill runtime still exposes its expected `LV3_GRAPH_DSN` env and the
  branch-local `windmill-jobs.dsn` artifact exists under the shared controller
  secret root.
- The rebased branch validation bundle also passed: targeted pytest returned
  `70 passed`, `make syntax-check-glitchtip` passed, and
  `./scripts/validate_repo.sh agent-standards`,
  `./scripts/validate_repo.sh ansible-idempotency`,
  `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate`,
  and `uv run --with pyyaml python scripts/live_apply_receipts.py --validate`
  all completed successfully from this latest-main worktree.
- The first DNS replay happened during the Hetzner legacy DNS brownout window,
  so the `errors` A record was bridged manually before the new retry handling
  landed. The final synchronized replay now observes the canonical `errors ->
  65.108.75.123` state without further manual mutation.
- During branch-local verification, the public edge had drifted back to the
  default `nginx.lv3.org` redirect because a later shared-edge replay no
  longer carried the GlitchTip publication surface. Rerunning the governed
  GlitchTip workflow from this latest-main worktree restored the dedicated edge
  blocks and revalidated the public auth and smoke path.

## Outcome

- The latest-main replay, recovery hardening, and repo-validation refresh are now integrated in this worktree on top of `0.177.123`, with fresh receipts for targeted tests, repo validation, protected-surface blockers, quiet-window contention, and current public-surface drift.
- The live rerun remains blocked by external concurrent controller activity and current shared-edge drift, so this workstream is not yet ready for final protected-surface integration onto `main`.
- Merge to `main` must wait for a fresh quiet window, a successful latest-main `make converge-glitchtip`, renewed public health/auth/smoke verification, and then the protected-file updates (`VERSION`, `changelog.md`, `README.md`, `versions/stack.yaml`, ADR metadata, and canonical mainline receipt).

## Merge Criteria

- the repo owns the GlitchTip runtime, database wiring, publication, OIDC client, and secret injection path
- at least one first-party producer is instrumented and verified against the live GlitchTip service
- ADR 0281 metadata, runbook guidance, workstream notes, and live-apply receipts clearly describe what is true on the branch and what remains for merge to `main`
