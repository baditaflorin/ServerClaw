# Workstream ws-0281-live-apply: Live Apply ADR 0281 From Latest `origin/main`

- ADR: [ADR 0281](../adr/0281-glitchtip-as-the-sentry-compatible-application-error-tracker.md)
- Title: Replace the partial ad hoc GlitchTip install with a repo-managed Sentry-compatible error tracking service, instrument first-party producers, and verify the live stack end to end
- Status: ready_for_merge
- Included In Repo Version: 0.177.104
- Branch-Local Receipt: verified latest-main replay evidence `receipts/live-applies/evidence/2026-04-01-ws-0281-converge-glitchtip-r1-0.177.129.txt`, `receipts/live-applies/evidence/2026-04-01-adr-0281-current-public-surface-r2-0.177.129.txt`, `receipts/live-applies/evidence/2026-04-01-adr-0281-public-auth-config-r1-0.177.129.txt`, `receipts/live-applies/evidence/2026-04-01-adr-0281-event-smoke-r2-0.177.129.txt`, and `receipts/live-applies/evidence/2026-04-01-adr-0281-quiet-window-manual-stop-r1-0.177.129.txt`; historical receipt `receipts/live-applies/2026-03-30-adr-0281-glitchtip-live-apply.json`
- Canonical Mainline Receipt: pending final `main` integration on top of `origin/main` `0.177.130`
- Live Applied In Platform Version: first implementation `0.130.69`; latest-main replay reverified against repository version `0.177.129`
- Implemented On: 2026-03-30
- Live Applied On: 2026-03-30
- Latest origin/main Base: `0.177.130` at `fc731170ceec3ea32a910d1980314ef4b150888e`
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

- ADR 0281 is replayed on rebased commit `cfffe8b87529118b3f534bc5a2adfe884bc97052`, which verified the GlitchTip live path on the `0.177.129` `origin/main` snapshot before `origin/main` advanced to `0.177.130` through the release/docs-only commits `c2dc6a07a`, `3d17c116d`, and `fc731170c`.
- The `0.177.129` refresh restored the missing GlitchTip `3005` network-policy exposure on `docker-runtime-lv3`, refreshed `config/subdomain-exposure-registry.json`, and updated `tests/test_keycloak_runtime_role.py` for the current Keycloak client-secret reconciliation surface.
- Fresh latest-main targeted validation passed from this worktree: `114 passed` across the GlitchTip and adjacent hardening surfaces, captured in `receipts/live-applies/evidence/2026-04-01-adr-0281-targeted-latest-main-tests-r2-0.177.129.txt`.
- Latest-main repo validation is green on `0.177.129` through `make syntax-check-glitchtip`, `./scripts/validate_repo.sh workstream-surfaces agent-standards yaml json role-argument-specs data-models`, `./scripts/validate_repo.sh ansible-syntax`, `./scripts/validate_repo.sh ansible-lint`, `scripts/platform_manifest.py --check`, `scripts/generate_slo_rules.py --check`, `scripts/generate_dependency_diagram.py --check`, `scripts/generate_diagrams.py --check`, `./scripts/validate_repo.sh generated-portals`, and `git diff --check`; see `receipts/live-applies/evidence/2026-04-01-adr-0281-repo-contract-refresh-r2-0.177.129.txt`, `receipts/live-applies/evidence/2026-04-01-adr-0281-ansible-lint-r1-0.177.129.txt`, and `receipts/live-applies/evidence/2026-04-01-adr-0281-generated-non-readme-checks-r2-0.177.129.txt`.
- `scripts/canonical_truth.py --check` and `scripts/generate_status_docs.py --check` still fail only because they want to refresh the protected top-level `README.md` and generated status docs; that protected-file integration remains deferred until the final `main` merge step. Evidence is in `receipts/live-applies/evidence/2026-04-01-adr-0281-generated-surfaces-except-canonical-r1-0.177.129.txt`.
- `make converge-glitchtip` replayed successfully through PostgreSQL, Docker runtime recovery, Keycloak reconcile, GlitchTip bootstrap, and NGINX edge publication; the automated quiet-window publication verifier then stalled behind concurrent `ws-0247-clean-main-r1` and `ws-0286-live-apply-r2` ansible runs on the same shared hosts. Evidence is in `receipts/live-applies/evidence/2026-04-01-ws-0281-converge-glitchtip-r1-0.177.129.txt`, `receipts/live-applies/evidence/2026-04-01-adr-0281-quiet-window-waiter-r1-0.177.129.txt`, and `receipts/live-applies/evidence/2026-04-01-adr-0281-quiet-window-manual-stop-r1-0.177.129.txt`.
- Independent post-converge public verification now shows `errors.lv3.org` serving `CN=errors.lv3.org` with `HTTP/2 200` on both `/api/0/internal/health/` and `/_allauth/browser/v1/config`; the auth config advertises `LV3 Keycloak` and `https://sso.lv3.org/realms/lv3/.well-known/openid-configuration`. Evidence is in `receipts/live-applies/evidence/2026-04-01-adr-0281-current-public-surface-r2-0.177.129.txt` and `receipts/live-applies/evidence/2026-04-01-adr-0281-public-auth-config-r1-0.177.129.txt`.
- End-to-end ingestion is also reverified: `scripts/glitchtip_event_smoke.py` succeeded against the live public surface, recording event `dcddc4c934064775b3aad2f01b293aec` and issue `PLATFORM-FINDINGS-7`. Evidence is in `receipts/live-applies/evidence/2026-04-01-adr-0281-event-smoke-r2-0.177.129.txt`.
- The remaining integration gap is now repo-state only: rebase this verified branch onto `origin/main` `0.177.130`, refresh protected generated/release surfaces, and merge/push `main`.

## Verification

- `uv run --with pytest python -m pytest -q`
- `uv run --with pyyaml python scripts/workflow_catalog.py --validate`
- `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate`
- `uv run --with pyyaml python scripts/generate_adr_index.py --write`
- `./scripts/validate_repo.sh agent-standards`
- `make live-apply-service service=glitchtip env=production`
- branch-local SSH, HTTP, and API checks proving publication, health, OIDC, and event ingestion end to end

## Branch-Local Results

- `receipts/live-applies/evidence/2026-04-01-ws-0281-converge-glitchtip-r1-0.177.129.txt`
  captures the governed latest-main replay through PostgreSQL, Docker runtime,
  Keycloak recovery, GlitchTip bootstrap, and NGINX edge publication. The
  automated quiet-window publication verifier never cleared because unrelated
  concurrent workstreams kept touching `docker-runtime-lv3` and `nginx-lv3`, so
  the waiting verifier was manually stopped after independent public
  verification succeeded; see
  `receipts/live-applies/evidence/2026-04-01-adr-0281-quiet-window-manual-stop-r1-0.177.129.txt`.
- Fresh public verification preserved in
  `receipts/live-applies/evidence/2026-04-01-adr-0281-current-public-surface-r2-0.177.129.txt`
  and
  `receipts/live-applies/evidence/2026-04-01-adr-0281-public-auth-config-r1-0.177.129.txt`
  confirmed `errors.lv3.org` resolves to `65.108.75.123`, serves
  `CN=errors.lv3.org`, returns `HTTP/2 200` on the public health and auth
  endpoints, and advertises the repo-managed Keycloak OIDC provider.
- Fresh end-to-end ingestion verification preserved in
  `receipts/live-applies/evidence/2026-04-01-adr-0281-event-smoke-r2-0.177.129.txt`
  confirmed the live public DSN path creates issue `PLATFORM-FINDINGS-7` for
  event `dcddc4c934064775b3aad2f01b293aec`.
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

- The latest-main replay, recovery hardening, and repo-validation refresh are now integrated in this worktree on top of the verified `0.177.129` snapshot, with fresh receipts for targeted tests, repo validation, the governed converge, public auth and health, and end-to-end event ingestion.
- The live service is no longer blocked: `errors.lv3.org` is healthy, serves the dedicated certificate, exposes the repo-managed Keycloak OIDC provider, and accepts live Sentry-compatible events. The only blocked automation was the controller-local quiet-window verifier, which was waiting on unrelated concurrent workstreams rather than GlitchTip state.
- Merge to `main` now depends on repo-state integration only: rebase this verified branch onto `origin/main` `0.177.130`, refresh the protected generated/release surfaces (`VERSION`, `changelog.md`, `README.md`, `versions/stack.yaml`, release notes, and canonical receipts), and then push the final integrated `main`.

## Merge Criteria

- the repo owns the GlitchTip runtime, database wiring, publication, OIDC client, and secret injection path
- at least one first-party producer is instrumented and verified against the live GlitchTip service
- ADR 0281 metadata, runbook guidance, workstream notes, and live-apply receipts clearly describe what is true on the branch and what remains for merge to `main`
