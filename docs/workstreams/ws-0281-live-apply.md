# Workstream ws-0281-live-apply: Live Apply ADR 0281 From Latest `origin/main`

- ADR: [ADR 0281](../adr/0281-glitchtip-as-the-sentry-compatible-application-error-tracker.md)
- Title: Replace the partial ad hoc GlitchTip install with a repo-managed Sentry-compatible error tracking service, instrument first-party producers, and verify the live stack end to end
- Status: live_applied
- Included In Repo Version: 0.177.149
- Branch-Local Receipt: `receipts/live-applies/2026-04-03-adr-0281-glitchtip-mainline-live-apply.json`
- Canonical Mainline Receipt: `receipts/live-applies/2026-04-03-adr-0281-glitchtip-mainline-live-apply.json`
- Live Applied In Platform Version: 0.130.93
- Implemented On: 2026-04-03
- Live Applied On: 2026-04-03
- Latest `origin/main` Base Used For The Exact Replay: `0.177.148` at `bdd326164a37f849ca435f5bf32e550f00c5a89b`
- Branch: `codex/ws-0281-mainline-v2`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.worktrees/ws-0281-mainline-v2`
- Owner: codex
- Depends On: `adr-0021-public-subdomain-publication-at-the-nginx-edge`, `adr-0042-postgresql-as-the-shared-relational-database`, `adr-0063-keycloak-sso-for-internal-services`, `adr-0077-compose-secrets-injection-pattern`, `adr-0130-mail-platform-for-transactional-email`, `adr-0191-immutable-guest-replacement`
- Conflicts With: none
- Shared Surfaces: `workstreams.yaml`, `docs/workstreams/ws-0281-live-apply.md`, `docs/adr/0281-glitchtip-as-the-sentry-compatible-application-error-tracker.md`, `docs/runbooks/configure-glitchtip.md`, `receipts/live-applies/`, `playbooks/glitchtip.yml`, `playbooks/services/glitchtip.yml`, `collections/ansible_collections/lv3/platform/roles/glitchtip_runtime/`, `collections/ansible_collections/lv3/platform/roles/glitchtip_postgres/`, `collections/ansible_collections/lv3/platform/roles/keycloak_runtime/`, `collections/ansible_collections/lv3/platform/roles/mail_platform_runtime/`, `inventory/host_vars/proxmox-host.yml`, `inventory/group_vars/platform.yml`, `build/platform-manifest.json`, `config/`, `scripts/`, `tests/`, `Makefile`

## Purpose

Implement ADR 0281 from the latest realistic mainline, prove the repo-managed
GlitchTip publication and Sentry-compatible ingest path live at
`errors.example.com`, and carry that verified result onto protected release truth
without bumping the already-current platform lineage again.

## Outcome

- The authoritative exact-main replay ran from source commit
  `55ccb056fd59e6a69c82709d6f11eb6a6a2bd6dd` on immediate predecessor base
  `ef412b0f061517b64920b7328102e23b89b0774d` / `0.177.147`, and
  `receipts/live-applies/evidence/2026-04-03-ws-0281-converge-glitchtip-r5-0.177.147.txt`
  shows the controller-local quiet-window gate cleared before public
  verification.
- The same replay reconverged PostgreSQL, Docker-runtime recovery, Keycloak,
  the GlitchTip runtime, repo-managed bootstrap, and NGINX publication with
  final recap `docker-runtime : ok=321 changed=0 failed=0`,
  `localhost : ok=30 changed=0 failed=0`, `nginx-edge : ok=46 changed=5
  failed=0`, and `postgres : ok=70 changed=0 failed=0`.
- Fresh public proof in
  `receipts/live-applies/evidence/2026-04-03-adr-0281-current-public-surface-r4-0.177.147.txt`,
  `receipts/live-applies/evidence/2026-04-03-adr-0281-current-public-cert-r4-0.177.147.txt`,
  `receipts/live-applies/evidence/2026-04-03-adr-0281-public-auth-config-r3-0.177.147.json`,
  and
  `receipts/live-applies/evidence/2026-04-03-adr-0281-event-smoke-r4-0.177.147.txt`
  confirms `HTTP/2 200` on the public health endpoint, `CN=errors.example.com`,
  the `LV3 Keycloak` OIDC provider metadata, and live issue creation for event
  `58285bc1956f4a90a19fe3ea393f9f38` / issue `PLATFORM-FINDINGS-B`.
- While that replay was finishing, `origin/main` advanced to
  `bdd326164a37f849ca435f5bf32e550f00c5a89b` / `0.177.148` / `0.130.93` with
  ADR 0309 ops-portal and protected-surface changes only. The branch-local
  delta receipt
  `receipts/live-applies/evidence/2026-04-03-adr-0281-mainline-delta-analysis-r1-0.177.148.txt`
  shows that move did not change GlitchTip-owned live surfaces, so release
  `0.177.149` integrates the verified GlitchTip truth while preserving the
  already-current platform version `0.130.93`.

## Verification

- `receipts/live-applies/evidence/2026-04-03-adr-0281-glitchtip-recovery-tests-r1-0.177.147.txt`
  records the focused recovery slice at `11 passed`.
- `receipts/live-applies/evidence/2026-04-03-adr-0281-targeted-latest-main-tests-r1-0.177.147.txt`
  records the rebased latest-main GlitchTip pytest slice at `42 passed`.
- `receipts/live-applies/evidence/2026-04-03-ws-0281-converge-glitchtip-r5-0.177.147.txt`
  records the governed exact-main replay with the quiet-window gate clearing
  from `2026-04-03T01:10:24Z` to `2026-04-03T01:10:55Z`.
- `receipts/live-applies/evidence/2026-04-03-adr-0281-mainline-release-write-r1-0.177.149.txt`
  records the protected release cut that wrote repository version `0.177.149`.
- The canonical mainline receipt
  `receipts/live-applies/2026-04-03-adr-0281-glitchtip-mainline-live-apply.json`
  now anchors the latest `glitchtip` live-apply truth in `versions/stack.yaml`,
  `README.md`, and the generated release/status surfaces.

## Remaining Work

- none; this workstream is fully live-applied, release-integrated, and ready
  for fast-forward merge to `main`, push to `origin/main`, and worktree
  removal
