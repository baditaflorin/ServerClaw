# Authentik consumer sign-in E2E audit

- ADR: 0491
- Title: Audit and repair live Authentik consumer sign-in paths end to end
- Status: blocked pending security-gate remediation
- Branch: `codex/authentik-live-closeout-20260926`
- Worktree: `.worktrees/authentik-live-closeout-20260926`
- Owner: Codex
- Depends on: `adr-0491-authentik-keycloak-sunset-2026-08-30`, `ws-0510-gitea-authentik-oidc-e2e`

## Scope

Reconcile the active Authentik client catalog against deployed consumers, then
test reported browser flows—including Gitea, Harbor, Outline, Grafana,
GlitchTip, Repo Intake, Chat, and Ops Portal—with fresh sessions. Fix reproducible IaC,
application, proxy, or logout defects and record non-secret live evidence.

## Non-goals

- Do not remove rollback archives or cold Keycloak data as part of this audit.
- Do not widen a test identity into an administrator or grant access to
  operational capabilities merely to make an authentication test pass.
- Do not treat an HTTP 200/302 response as proof of a completed OIDC session.
- Do not claim unrelated service health from an authentication-only test.

## Expected live surfaces

Authentik on `runtime-control`; native OIDC consumers and shared-edge protected
apps on their declared runtime hosts; the public NGINX edge. Existing reported
URLs are checked against live response and authenticated browser state.

## Ownership notes

Runtime/client configuration changes share `adr-0491-authentik-migration-v1`.
The new browser harness and its unit tests are exclusive to this workstream.
All client secrets and test passwords remain in the ignored deployment-local
overlay. The existing `gitea-e2e` identity is non-admin and limited to
`gitea-users` plus the read-only `grafana-viewers` group; it is not a member of
`grafana-admins` or any platform-admin group. Any broader test access must be
explicitly least-privileged.

## Findings and current change

- The reported GlitchTip login loop reproduces in a fresh browser profile. The
  Authentik credential step succeeds, but the GlitchTip callback redirects to
  `/login/finalize` with the safe allauth error code `signup_closed`; its
  authenticated-session endpoint then returns 401.
- The deployed GlitchTip runtime disables local registration and organization
  creation, and does not enable social-provider JIT registration. The change
  enables first-login provisioning only through the managed social provider;
  local registration and organization creation stay disabled, and JIT users
  do not receive project access until explicitly added to the organization.
- Added `scripts/glitchtip_authentik_e2e.py` to test a fresh-browser callback
  and the final allauth authenticated session without logging query values.
  Before the runtime change is applied, it exits with the sanitized
  `signup_closed` result as expected.
- Focused regression tests and `make syntax-check-glitchtip` pass. The
  post-merge browser check still returns `signup_closed`; applying the merged
  runtime fix is blocked by the docker-runtime vulnerability budget (host
  warnings exceed budget and both GlitchTip image scans are stale).
- The Grafana browser report also reproduces with the current non-admin test
  identity. Grafana's callback reaches userinfo, then its server log rejects
  the identity because it is not in either configured allowed group. The
  existing boundary is correct; the test identity was granted only the
  `grafana-viewers` group. The fresh browser now reaches an authenticated
  Grafana session, but `/api/user` reports no organization role, so the Viewer
  assertion still fails. Applying the managed Grafana configuration is blocked
  by the monitoring host's three warning findings against a budget of two.
- Repository completeness validation also found that Grafana lacked its own
  managed dashboard and readiness alert. Added both against the existing
  `service="grafana",probe_kind="readiness"` probe contract; this makes the
  missing monitoring surface visible without weakening service validation.
- Harbor's fresh-browser Authentik flow succeeds with `gitea-e2e`. The strict-TLS
  Firefox check reaches Harbor's current-user API and confirms
  `sysadmin_flag: false`; the identity is not granted `harbor-admins`.
- Added `scripts/harbor_authentik_e2e.py` as repeatable coverage for Harbor's
  rendered Authentik sign-in option, callback, and non-admin session. Its
  bounded wait accounts for Harbor's SPA rendering the OIDC link after initial
  page load, and diagnostics never print callback query values.
- Outline login succeeds and `/api/auth.info` returns 200 in a fresh strict-TLS
  browser session. Timed screenshots show Authentik's brief loading state
  followed by the complete “You've logged out of Outline” card in about 100 ms;
  no manual refresh is needed. The default provider invalidation flow and its
  empty stage list are expected; no override is warranted. Provider logout
  leaves the central Authentik session active, so re-entry may be silent.
- Realtime failure reproduces: the browser's `/realtime/?EIO=4&transport=websocket`
  handshake receives an NGINX 502, and the NGINX error log says the Outline
  upstream closed the connection before returning headers. The live Outline
  runtime omits `websockets` from `SERVICES=web,worker,collaboration`. The pinned
  Outline 1.6.1 source attaches the `/realtime` Socket.IO handler only when the
  `websockets` service starts. Added the missing service to both managed env
  templates, a role regression assertion, and
  `scripts/outline_authentik_e2e.py` to test login, authenticated WebSocket,
  session-clearing logout, and SSO re-entry. A fresh-browser check after merge
  still fails the realtime WebSocket handshake. The governed Outline apply was
  rejected because the runtime security receipt/image scans are stale and
  critical findings remain; no gate was bypassed.
- Repo Intake and Ops Portal do not currently return 502s on the fresh browser
  path. Both are intentionally restricted to the platform-admin group. The
  `gitea-e2e` account correctly receives a 403 from the shared
  `ops-portal-oauth` callback on both hosts; this is an authorization denial,
  not a callback-host mix-up. Added
  `scripts/authentik_admin_gate_e2e.py` to verify that exact boundary and fail
  on any 5xx response without elevating the test identity.
- The live recovery API check found drift: the platform-operator email stage
  had local SMTP settings while the managed blueprint declares global SMTP.
  The `authentik-recovery-flow` lane was run through the documented bastion
  port override, and the blueprint was explicitly applied. A repeat narrow
  converge then passed with no changes; the recovery contract and worker SMTP
  authentication both pass. One recovery-email request returned HTTP 204. The
  Gmail connector currently requires reauthentication, so inbox delivery could
  not be independently confirmed.
- Repository-wide validation exposed a stale platform-manifest release date:
  the parser ignored the release notes' existing `- Date:` metadata and
  substituted today's date. Fixed the parser with a regression test and
  refreshed the generated artifact. The repository data-model and stage-smoke
  validators pass; the final push gate remains the authority for the full
  branch.
- The selected deployment's generated platform facts and topology snapshot
  must be checked with the same explicit identity and topology selectors used
  by the guarded converge. The generator and repository data-model validator
  now honor exported `PLATFORM_IDENTITY_OVERLAY` and
  `PLATFORM_TOPOLOGY_OVERLAY` values, so local validation compares like with
  like rather than mixing a selected deployment with committed defaults.

## Live verification checkpoint — 2026-09-26

- The Authentik provider/application reconciliation reported zero drift for
  Outline, GlitchTip, Gitea, Grafana, and Harbor.
- The dedicated `gitea-e2e` identity now has only `gitea-users` and the
  read-only `grafana-viewers` groups. Fresh Firefox OIDC checks pass for Gitea
  and Harbor with TLS validation enabled and no admin privileges.
- Grafana reaches `/api/user` as `gitea-e2e`, but `orgRole` is null and the
  Viewer-role E2E fails. Its governed apply was rejected: the monitoring host
  has findings `KRNL-5830`, `PKGS-7388`, and `PKGS-7392` (three warnings; budget
  two). No production changes were made by that rejected apply.
- Outline's realtime WebSocket handshake still fails. Its governed apply was
  rejected because the runtime security receipt/image scans are stale and
  critical findings remain. GlitchTip's fresh browser still returns
  `signup_closed`; its apply was rejected because the docker-runtime host
  exceeds its warning budget and its two image scans are 180 days old. No gate
  or exception was bypassed.
- The final narrow Authentik Ansible run completed with 14 tasks OK, zero
  changes, and zero failures. The user-requested recovery email was accepted
  by Authentik, but delivery to the mailbox remains unverified because the
  connected Gmail app requires reauthentication.
- Code PR #244 is merged. This status/receipt PR and required ServerClaw
  publication remain to be completed after this checkpoint.

## Verification

1. Compare the live Authentik application/provider catalog with the checked-in
   OAuth client manifest and currently deployed services.
2. For each active reported consumer, test the fresh browser redirect to
   Authentik, credential submission, callback, final application session, and
   logout/re-entry behavior as applicable.
3. Run focused unit tests, repository validation, and Woodpecker push/PR gates.
4. Apply affected consumer configuration through documented converges. Apply
   only `--tags authentik-recovery-flow` for the recovery-stage drift; do not
   use the full Authentik runtime role until the recorded OpenBao adoption
   prerequisites are satisfied.
5. Verify the resulting live sessions and recovery-email delivery, then record
   a receipt that contains no credentials, tokens, email bodies, or OAuth state.

## Merge criteria

All reported authentication paths have an explicit passing result or a
documented, intentional authorization denial; any discovered defects have a
regression test; repository gates pass; live changes have a sanitized receipt;
and the changes are merged through pull request.
