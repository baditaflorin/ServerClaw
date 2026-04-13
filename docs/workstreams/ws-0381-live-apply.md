# Workstream ws-0381-live-apply: ADR 0381 Live Apply From Latest `origin/main`

- ADR: [ADR 0381](../adr/0381-login-service-contracts-and-session-recovery-automation.md)
- Title: Complete the login-service recovery rollout, validate the auth path end to end, and integrate the verified result onto `main`
- Status: merged
- Implemented In Repo Version: 0.178.127
- Live Applied In Platform Version: 0.178.78
- Implemented On: 2026-04-12
- Live Applied On: 2026-04-12
- Workstream Branch: `codex/ws-0381-origin-main`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/platform_server/.worktrees/ws-0381-origin-main`
- Owner: codex
- Depends On: `adr-0248`, `adr-0376`, `adr-0381`
- Conflicts With: none
- Shared Surfaces: `workstreams.yaml`, `workstreams/archive/2026/ws-0381-live-apply.yaml`, `docs/workstreams/ws-0381-live-apply.md`, `docs/adr/0381-login-service-contracts-and-session-recovery-automation.md`, `docs/adr/implementation-status/adr-0381.md`, `docs/adr/implementation-status/adr-0381.yaml`, `docs/adr/implementation-status/INDEX.yaml`, `docs/adr/.index.yaml`, `docs/adr/index/by-range/0300-0399.yaml`, `docs/adr/index/by-concern/automation.yaml`, `docs/adr/index/by-status/implemented.yaml`, `docs/adr/index/by-status/proposed.yaml`, `docs/runbooks/keycloak-session-invalidation.md`, `docs/runbooks/identity-core-watchdog.md`, `playbooks/templates/compose_macros.j2`, `collections/ansible_collections/lv3/platform/roles/keycloak_runtime/tasks/plane_client.yml`, `config/subdomain-catalog.json`, `config/subdomain-exposure-registry.json`, `scripts/certificate_validator.py`, `scripts/control_plane_lanes.py`, `tests/test_generate_status_docs.py`, `tests/test_keycloak_runtime_role.py`, `tests/test_nginx_edge_publication_role.py`, `tests/test_public_edge_oidc_auth_role.py`, `tests/test_subdomain_exposure_audit.py`, `receipts/live-applies/2026-04-12-adr-0381-login-service-contracts-mainline-live-apply.json`, `receipts/live-applies/evidence/2026-04-12-ws-0381-*`

## Scope

- register `ws-0381` as an active workstream from the latest realistic
  `origin/main` baseline
- reconcile repo truth for ADR 0381, including implementation metadata and
  generated ADR/workstream indexes
- tighten focused regression coverage around stale-session reset, Keycloak
  post-logout URI registration, exact-main Plane OIDC reconciliation, and the
  subdomain exposure audit that gates shared edge publication
- replay the live auth-change converge order and capture branch-local plus
  canonical mainline receipts after the login path is reverified from a clean
  worktree on the latest realistic `origin/main`

## Non-Goals

- changing unrelated release or canonical-truth files before the final verified
  mainline integration step
- reworking broader shared-edge auth architecture outside ADR 0381
- taking ownership of unrelated active workstreams unless a repo gate leaves no
  lower-risk path

## Expected Repo Surfaces

- ADR 0381 metadata updated to reflect the verified implementation state
- runbook guidance updated so operators do not default to manual cookie clearing
- focused auth-contract regression coverage added or refreshed
- workstream registry and ADR index regenerated from the committed shard source

## Expected Live Surfaces

- Keycloak client registration still contains the stale-session recovery return
  URI contract for `ops-portal-oauth`
- shared edge oauth2 callback handling still expires both oauth2-proxy cookies
  and redirects through Keycloak logout
- oauth2-proxy watchdog remains active on `nginx-edge`
- unauthenticated `ops.example.com` and `tasks.example.com` still redirect into
  the shared Keycloak flow after the replay

## Ownership Notes

- This workstream is intentionally scoped to ADR 0381 surfaces plus the minimal
  integration files required once the verified live result is promoted to `main`.
- If the governed live-apply wrapper is blocked by unrelated active-workstream
  registry drift, prefer direct repo-managed converge entrypoints over rewriting
  another agent's workstream unless the final exact-main integration requires
  that fix.

## Verification

- Focused regression coverage passed with:
  `uv run --with pytest python -m pytest tests/test_subdomain_exposure_audit.py tests/test_keycloak_runtime_role.py tests/test_nginx_edge_publication_role.py tests/test_public_edge_oidc_auth_role.py -q`
  (`63 passed`, 2026-04-12).
- The widened ws-0381 repo automation slice also passed with:
  `uv run --with pytest --with pyyaml --with jsonschema python -m pytest tests/test_generate_status_docs.py tests/test_adr_implementation_scanner.py tests/test_live_apply_receipts.py tests/test_validate_service_catalog.py tests/test_validate_service_completeness.py tests/test_uptime_contract.py tests/test_subdomain_exposure_audit.py tests/test_keycloak_runtime_role.py tests/test_nginx_edge_publication_role.py tests/test_public_edge_oidc_auth_role.py -q`
  (`101 passed`, 2026-04-12).
- `make preflight WORKFLOW=converge-keycloak`, `make preflight WORKFLOW=configure-edge-publication`, and `make preflight WORKFLOW=converge-identity-core-watchdog` all passed before the replay.
- Exact-main repo-managed live apply completed in ADR order:
  `make converge-keycloak env=production`,
  `make configure-edge-publication env=production`,
  and `make converge-identity-core-watchdog env=production`.
- The first exact-main `make converge-keycloak env=production` attempt exposed two latest-main regressions before the rerun passed: `playbooks/templates/compose_macros.j2` was missing in the clean worktree, and the Plane OIDC reconciliation path in `collections/ansible_collections/lv3/platform/roles/keycloak_runtime/tasks/plane_client.yml` used a partial raw Keycloak update that returned HTTP 400 until it was restored to the `community.general.keycloak_client` contract.
- The first exact-main `make configure-edge-publication env=production` attempt stopped because the active subdomain catalog still expected `librechat.example.com` while the repo-managed shared edge route remained `chat.example.com`. Restoring `config/subdomain-catalog.json` and regenerating `config/subdomain-exposure-registry.json` cleared that shared-edge drift and the immediate rerun completed successfully.
- The first generated-doc validation attempt on the fresh worktree also exposed a latest-main repo automation bug: `scripts/control_plane_lanes.py` imported `platform.repo` before bootstrapping the repo root onto `sys.path`, which broke `scripts/generate_status_docs.py` with `ModuleNotFoundError` until the CLI import path was corrected and covered by `tests/test_generate_status_docs.py`.
- End-to-end auth verification succeeded:
  `https://ops.example.com/` and `https://tasks.example.com/` both return `302` to `/oauth2/sign_in`, and their sign-in endpoints return `302` to the shared Keycloak authorize flow with `client_id=ops-portal-oauth`.
- Live edge/runtime verification succeeded:
  `lv3-ops-portal-oauth2-proxy-watchdog.timer` and `lv3-identity-watchdog.timer` are both active;
  `_lv3_ops_portal_proxy_csrf` occurs 16 times in the live edge config on 2026-04-12;
  `@oauth2_stale_session_reset` is present; and no `oauth2/sign_in&client_id` redirect drift remains.
- Certificate validation now works from the worktree via the shared `.local` overlay:
  `make validate-certificates` reported 46 valid domains and one unrelated `vault.example.com` connection reset against `100.64.0.1:443`.
- Exact-main auth verification is recorded in `receipts/live-applies/evidence/2026-04-12-ws-0381-main-auth-verification-r1.txt`, and the canonical mainline receipt is `receipts/live-applies/2026-04-12-adr-0381-login-service-contracts-mainline-live-apply.json`.

## Merge Criteria

- ADR 0381 repo truth is complete and indexed
- focused regression coverage passes
- live auth-change converge sequence succeeds
- end-to-end verification proves the protected login path is healthy again
- final mainline integration records the protected release and canonical-truth
  surfaces truthfully

## Mainline Integration Outcome

- ADR 0381 remains stamped as implemented in repo version `0.178.126`, and this exact-main closeout merged on `main` in repo version `0.178.127` after the live-applied platform verification on version `0.178.78`.
- The exact-main live replay ran against `18dfb4ea01cd6c3787a61eaa5cceff7cfd496543`, the latest realistic mainline revision at apply time. While the closeout was being integrated, `origin/main` advanced to `9afc6d691a9b99e40e8af1cdb2b61005ae8e266c`, so the final merge was rebased onto that newer commit and revalidated without adding further ADR 0381 runtime changes.
- The archived workstream carries canonical-truth metadata for `keycloak`, `public_edge_publication`, `ops_portal`, and `identity_core_watchdog`, allowing the merged registry to advertise the new canonical receipt safely.
- The exact-main replay and follow-on validation repair also cleared five latest-main drifts that would otherwise have blocked truthful live apply or repo automation from a fresh worktree: the missing compose macro loader, the Plane OIDC client reconciliation path, the shared-edge `librechat` versus `chat` catalog mismatch, certificate validation resolving `.local` from worktrees, and the `control_plane_lanes.py` import bootstrap needed by `generate_status_docs.py`.
- The only runtime anomaly that remained after the replay was outside ADR 0381 itself: `vault.example.com` still reset TLS connections against `100.64.0.1:443` during the certificate sweep.
