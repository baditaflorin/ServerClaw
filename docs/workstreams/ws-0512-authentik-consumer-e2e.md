# Authentik consumer sign-in E2E audit

- ADR: 0491
- Title: Audit and repair live Authentik consumer sign-in paths end to end
- Status: in progress; production applies remain security-gated
- Branch: `codex/authentik-e2e-continue-after-harbor-fix-20261013`
- Worktree: `.worktrees/authentik-e2e-closeout-20261013`
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

## Current live status — 2026-10-12

This section supersedes earlier per-service diagnoses below where they differ.
Fresh strict-TLS browser checks currently pass for Gitea and Harbor using the
non-admin test identity. Repo Intake and Ops Portal return the expected
non-admin authorization denial. Grafana's strict-TLS login, non-admin Viewer
role, 48-dashboard search, provider-scoped logout, and post-logout re-login now
pass fresh browser checks. The merged fix was applied from `origin/main` and
recorded in the live-apply receipt. LibreChat's firewall and Authentik browser
path now pass a fresh end-to-end check. Outline and GlitchTip still need their
separately governed fixes and browser retests. Do not claim
overall Authentik completion or complete Keycloak retirement yet.

- **Authentik runtime:** a read-only live check confirms both server and worker
  run pinned `2026.8.3` digest `09782fe56675bc616a0324468f1698e2d9d83c978bc5e426686fb7563517a442`;
  public readiness returns HTTP 200. The current five-host security report is
  host-only, so it does not refresh the image scan. A fresh scan of the exact
  digest was archived on 2026-10-13 with Grype 0.111.0 and the latest available
  vulnerability database. It reports 4 Critical, 96 High, 102 Medium, 29 Low,
  86 Unknown, and zero blocking findings with a known fix; the catalog points
  to this receipt and remains `blocked`. The tracked 2026-10-11 Grype 0.110.0
  receipt reported 6 Critical/99 High and is retained as historical evidence;
  the separate operator-reported Oct 12 receipt remains absent. The old
  exception's 3/84 justification does not match the latest scan and expired
  2026-10-08. The runtime image gate rejects a new apply until the findings
  and policy decision are reconciled. Do not renew the exception implicitly.
  As of 2026-10-13, upstream still identifies 2026.8.3 as latest stable; no
  newer stable tag was found.
- **Keycloak sunset:** no Keycloak container is running on `docker-runtime` or
  `runtime-control`; Gitea's live auth-source list contains only Authentik, and
  active service/client/integration/subdomain declarations contain no
  Keycloak-named object. Remaining source references are guarded retirement
  logic for old Gitea, GlitchTip, Nomad, and Windmill assets. Cold rollback and
  archival references remain intentionally preserved.
- **LibreChat account-tool contract:** the canonical agent-tool registry and
  generator already target Authentik, but the checked-in generated account and
  combined OpenAPI specs still described Keycloak. This branch regenerates
  those artifacts and adds a parity test so they cannot silently drift again.
  The live advertised tool schema still needs a post-merge publication check.
- **Grafana:** the server-side OIDC route was corrected to resolve Authentik
  through the private edge with strict TLS. The managed Authentik
  `grafana-groups` scope mapping is present and the provider metadata
  reconciles idempotently. Grafana requests `openid profile email
  grafana-groups`; the mapping exposes only the two Grafana authorization
  groups under the `groups` claim. A fresh strict-TLS browser session now
  authenticates the non-admin test identity as Viewer, and dashboard search
  returns 48 dashboards. Logout originally sent Grafana's ID-token hint to the
  shared Ops Portal provider's end-session endpoint and Authentik returned
  HTTP 400. PR #288 points Grafana to its own provider endpoint; the merged
  mainline apply and fresh browser test now pass. Authentik displays its normal
  provider-invalidation confirmation, Grafana's `/api/user` returns HTTP 401
  after logout, and reauthentication returns the test identity as Viewer.
  Do not grant admin access. The Monitoring host's private-edge DNS pin is
  merged/applied, and fresh 2026-10-11 Lynis evidence places it within budget.
  The browser verifier checks identity and server-admin status at `/api/user`,
  then reads workspace membership roles from `/api/user/orgs`; Grafana does
  not expose the workspace role in the user-profile response. PR #297 merged
  this verifier-only change at `648cf810c5037fa2f3e2e8a5d6a8683547fa2bc5`;
  both Woodpecker push and PR checks passed, and it did not change live Grafana
  or Authentik configuration.
- **Outline:** a fresh browser reaches the app, but the realtime Engine.IO
  WebSocket handshake still fails because the live `SERVICES` setting omits
  `websockets`. The managed runtime template includes that service. Fresh
  2026-10-11 scans of the pinned image and latest official candidate still
  found unresolved critical vulnerabilities. Two source-build attempts reached
  dependency installation but were killed by the builder host's global OOM
  killer. Inventory declares a 12 GiB VM maximum, but the running guest reports
  an 8 GiB balloon allocation with no swap; the Proxmox host is under memory
  pressure. The Dockerfile now caps Node's heap at 3 GiB and Yarn network
  concurrency at four. The candidate has not yet been rebuilt or scanned, so
  the governed apply remains blocked.
- **GlitchTip:** Authentik accepts the credentials, then first-login
  provisioning is rejected with the safe `signup_closed` error. The managed
  social-provider JIT change is present; local public registration and
  organization creation remain disabled. Fresh 2026-10-11 scans of the pinned
  image and latest official candidate still found unresolved critical
  vulnerabilities; the new source-built candidate is not yet built or scanned,
  so the governed apply remains blocked.
- **LibreChat:** PR #294 merged the managed, narrowly scoped nftables SNAT
  needed for the observed `172.16.1.0/24` container-to-private-edge TCP/443
  path. Its scoped Coolify apply and strict-TLS browser E2E now pass; direct
  discovery from inside the container returns HTTP 200 with the expected
  Authentik issuer, and the fresh Firefox session completed the callback and
  authenticated app session as non-admin `gitea-e2e`. Monitoring-to-Coolify
  node-exporter metrics remained reachable (HTTP 200 on TCP/9100). The
  firewall-only apply did not redeploy LibreChat or restart Docker. The exact
  backup/config hashes, apply recap, and E2E evidence are in the live-apply
  receipt. A separate pinned-image scan at
  `receipts/image-scans/2026-10-11-librechat-runtime.json` reports 20 Critical,
  239 High, 286 Medium, and 54 Low findings, with no fix available for
  HIGH/CRITICAL findings. The previous exception was not renewed, so the
  runtime-image deployment remains security-gated. Host hardening warnings and
  stale backup-host coverage are tracked separately; they did not prevent this
  narrowly scoped firewall policy apply.
- **Keycloak:** no running Keycloak container was found on the checked runtime
  hosts, and the active Authentik catalog has no Keycloak-named consumer.
  Cold rollback archives and residual DNS/config references have not been
  exhaustively retired; those are distinct from removing a live runtime.

### Runtime-image security remediation — 2026-10-12

This branch adds pinned source recipes and a strict remote-build path for
Outline, GlitchTip, and MinIO, plus a shared Redis-compatible Valkey catalog pin
for GlitchTip, Outline, Langfuse, and Paperless. The exact Valkey linux/amd64
digest `sha256:187679e3bd4036959631e3f03983ab2ba503ab21e6fd0454d508e909db2ee989`
was scanned with Syft 1.42.4 and Grype 0.111.0: 0 Critical, 13 High, and zero
fixable High/Critical findings. Its SBOM, CVE receipt, and catalog summary are
tracked in the image-scan receipts and the expired shared-Redis exception is
removed.

The service-completeness gate also exposed expired metadata gaps on affected
services. GlitchTip explicitly does not require an API-gateway route because
its Sentry-compatible APIs use native credentials; its browser login remains
Authentik-backed. Langfuse now has readiness/liveness dashboard and alert
rules. Those checks no longer depend on expired suppressions.

The MinIO candidate now declares UID/GID `10001:10001`. Its managed runtime
performs a single, marker-guarded ownership conversion of the persistent data
tree before switching users; failure restores the root-run Compose identity and
fails closed. The one-time service interruption and rollback behavior are
documented in the MinIO runbook.

### Runtime-image continuation — 2026-10-13

Operator notes reported that the exact pinned Authentik digest was rescanned on
2026-10-12 at 6 Critical/99 High, with zero fixable Critical/High findings;
that specific scan artifact is still absent. A fresh scan of the tracked SBOM
was archived on 2026-10-13 using Grype 0.111.0 and the latest available
database, built at 2026-10-13T06:35Z. The current receipt reports 4 Critical,
96 High, 102 Medium, 29 Low, 86 Unknown, and zero blocking findings with a
known fix. `config/image-catalog.json` points to this scan, while the image
remains blocked because Critical findings are present and the prior exception
expired. The scanner's current four Critical matches are Python 3.14.7
(`CVE-2026-19445`), AnyIO 4.14.1
(`GHSA-82r6-8w77-94w6`), PyJWT 2.13.0 (`GHSA-ffc3-869f-jxw9`), Debian
libxml2 (`CVE-2026-6653`). Python 3.14.8 includes the
Python security fix; AnyIO 4.14.2 and PyJWT 2.14.0 are the published fixed
versions ([Python 3.14.8](https://www.python.org/downloads/release/python-3148/),
[AnyIO advisory](https://github.com/advisories/ghsa-82r6-8w77-94w6),
[PyJWT advisory](https://github.com/advisories/GHSA-ffc3-869f-jxw9)). Debian's
tracker still marks the Trixie libxml2 package vulnerable and notes no DSA;
do not cross-grade from unstable just to clear the scanner
([Debian tracker](https://security-tracker.debian.org/tracker/CVE-2026-6653)).
The two GnuTLS findings present in the earlier scan remain in the raw receipt,
but Grype 0.111.0 classifies them as negligible rather than Critical; they are
not counted among the current four Critical findings. Debian's tracker still
marks the exact Trixie package as vulnerable and lists no fixed Trixie version
([Debian CVE-2026-95210 tracker](https://security-tracker.debian.org/tracker/CVE-2026-95210),
[Debian CVE-2026-88647 tracker](https://security-tracker.debian.org/tracker/CVE-2026-88647)).
The previous exception covered 3 Critical/84 High and expired 2026-10-08; it
does not authorize the reported newer scan, and no exception was renewed.

The currently pinned stable 2026.8.3 source still carries those vulnerable
Python and application dependency versions. Upstream `main`, which identifies
itself as the 2026.11.0 release candidate, has moved to the fixed
`fips-python:3.14.8` base, AnyIO 4.14.2, and PyJWT 2.15.1
([container Dockerfile](https://github.com/goauthentik/authentik/blob/main/lifecycle/container/Dockerfile),
[dependency lock](https://github.com/goauthentik/authentik/blob/main/uv.lock),
[project dependencies](https://github.com/goauthentik/authentik/blob/main/pyproject.toml)).
That is useful evidence for the next stable release, not a production candidate:
no resulting immutable image has been scanned, and the two GnuTLS findings and
the Debian libxml2 finding still require a current-image scan and security
decision. Keep the deployed digest pinned until an approved stable candidate
passes the image budget.

Two Outline source-build attempts were killed by the host OOM killer during
dependency installation. This branch lowers Node's heap cap to 3 GiB and Yarn
network concurrency to four, with focused regression coverage, but the change
is not yet validated by a complete image build. A read-only capacity check at
2026-10-12 22:01 UTC showed the configured builder guest with 2.9 GiB available,
no swap, elevated five-minute memory PSI, and concurrent CI/build containers.
Its Proxmox parent had 4.2 GiB available and 3.9/4.0 GiB swap used. No further
heavy image build was started, and no candidate was published or deployed.
Recheck builder/host headroom before the next attempt; then build and scan
Outline, GlitchTip, and MinIO candidates at their exact Harbor digests before
any governed apply.

The ServerClaw strict sanitization audit now has no Critical or Warning gaps;
exact generic DNS resolver addresses are recognized as non-deployment public
services, and regression coverage ensures a deployment address remains
Critical. The publisher dry-run passed its leak check. This is only a preflight:
the private branch still needs the PR merge, followed by the mainline
publication run.

The Harbor project/robot reconciliation and source recipes are code only at
this checkpoint. Outline, GlitchTip, and MinIO candidates have not yet been
scanned at their resulting digests, and no runtime image was deployed. Do not
mark those image gates cleared until each pushed immutable digest has a passing
scan; do not deploy until the merged catalog and exact receipt are in place.

### Patched-image push regression — 2026-10-13

The first retry reached the final Outline image export on the configured
remote BuildKit host, but Harbor rejected the push with HTTP 401 during the
registry blob check. Inspection found that `build_remote.sh` logged in using a
temporary Docker config, then invoked Buildx without selecting that config.
The login and push therefore used different credential stores. The build
script now exports the temporary `DOCKER_CONFIG` for the lifetime of the
remote build, and a focused test guards that Buildx sees the same isolated
Harbor login config. The patched-image test module passes (11 tests), shell
syntax validation passes, and `git diff --check` is clean.

A fresh read-only check of the configured build guest first showed 4.4 GiB
available RAM, 2.7 GiB swap in use, a load average around 25, and elevated
memory and I/O pressure. A later sample worsened to 3.4 GiB available, 3.3
GiB swap in use, load average 48.5, and 10-second PSI of 9% memory-some / 4.5%
memory-full and 19% I/O-some / 6.4% I/O-full. The Proxmox parent had 13 GiB
available RAM and zero memory or I/O PSI; active Go format/build/test jobs were
visible on the guest. No second image build was started. Recheck sustained
builder headroom before retrying. Harbor granted the publisher a scoped push
token and accepted the beginning of an empty upload, but the Buildx retry
remains the definitive proof of the repaired auth handoff. No complete
candidate digest was pushed, scanned, pinned in the catalog, or deployed; the
GlitchTip signup setting has not been changed live.

### Risk-status and repository-truth correction — 2026-10-13

The Authentik catalog entry no longer retains the expired October 8 exception:
it is explicitly `blocked` with no active risk approval. The image-catalog
validator now permits this honest state only when a Critical finding exists;
the vulnerability-budget regression confirmed that the entry remained denied
at the then-current 6 Critical / 99 High. The later Grype 0.111.0 scan below
reports 4 Critical / 96 High and remains denied. Focused coverage for the touched image policy, budget,
Authentik role, patched-image, publication-audit, and generated
status/release-note surfaces passes (62 tests).

The same validation pass found the canonical platform version disagreed with
its release track: `versions/stack.yaml` said `0.179.51` while the release
track remained `0.179.50` and the 0.179.51 release notes explicitly state that
there was no live platform-version bump. The top-level platform version is
corrected to `0.179.50`, and the generated README now matches. Repository data
model validation and generated-README validation pass.

A full local repository test run was attempted before these final metadata and
policy corrections. It returned 3,963 passed, 190 failed, 17 collection/setup
errors, and 26 skipped; the failure set spans unrelated existing service and
generated-catalog tests, including fixture-manager setup expecting a removed
module attribute. This is not a green repository-wide run. Reconcile that set
against the actual Woodpecker gate before merging; do not interpret the focused
suite as a full-suite pass.

### Private registry route for the image builder — 2026-10-12

The first candidate build stopped at Harbor login before cloning or building:
the private builder resolved the public registry hostname to the public IP,
where TCP/443 is refused from the builder network. The same TLS hostname and
certificate work through the private NGINX edge. Both the builder host and its
BuildKit container had the public resolution, so a host-only resolver fix would
have left image pushes broken. The build-server role now manages a narrow
registry-host-to-private-edge mapping in `/etc/hosts` and passes the same
mapping into the BuildKit container. Public DNS and the TLS hostname remain
unchanged. This IaC change must pass CI and merge before its live converge;
image candidates remain unbuilt and undeployed until then.

The first governed live converge used the documented Proxmox jump route and
reached `docker-build`, but stopped after the Docker runtime role: the
`artifact_cache_runtime` role requires `site_dir` and `compose_file` during
Ansible's pre-task argument validation, while those values were only derived
inside the role's first task. Its defaults now expose those registry-derived
values before validation, with a regression test covering every required role
input. The converge restarted Docker and then failed before the build-server
role. Follow-up checks show Docker active, the host and BuildKit resolver both
using the private edge, and the Harbor TLS ping returning HTTP 200. The
managed BuildKit systemd unit is absent, however, and buildx still cannot
bootstrap because two unmanaged BuildKit containers share the socket and cache
mounts. The build-server role now offers an opt-in handoff that requires exact
container names and explicit idle confirmation, validates the expected image
and persistent mounts, and stops only those named containers without deleting
cache data. The focused role tests and syntax validation pass; merge this fix,
then rerun the governed converge and prove the managed builder bootstraps
before building or scanning candidates. Partial-apply evidence is recorded at
`receipts/live-applies/ws-0512-authentik-builder-route-partial-20261012-apply-receipt.yaml`.
No image candidate has been pushed or deployed.

The clean builder snapshot also exposed two validation-context gaps. Receipt
validation now accepts historical evidence references only when the recorded
source commit is unavailable in the immutable snapshot and differs from the
snapshot commit; references for the current snapshot still must exist. The
service-completeness gate can scope a changed generated completeness catalog
to the changed canonical service bundles when the snapshot has no Git merge
Without Git metadata, it can scope changed generated service-scoped catalogs to
changed canonical service bundles only when a valid snapshot source commit is
present. Canonical or global catalog changes and unresolvable service paths
still fail closed to repository-wide validation.

Ansible validation searches its verified dependency cache before the source
collection directory. This prevents partial Python cache files under a stale
third-party collection path from shadowing the installed collection, without
changing the repository-owned `lv3.platform` collection. Local ignored
collection installs are excluded from builder snapshots so their upstream
test fixtures cannot be mistaken for tracked repository secrets.

- **Scoped security evidence:** receipt
  `receipts/security-reports/20261011T082609Z.json` contains fresh Lynis
  results for 12 reachable production hosts (all selected hosts except
  `backup`) and no image scans. It is host-hardening evidence, not a complete
  fleet image-security pass. Coolify's two verified false positives remain
  suppressed only for Coolify; the required reboot and internal MongoDB
  authorization warnings remain visible, and its hardening index is 65.
  The container image gate uses its separate image-catalog scan receipt.

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
- The earlier Grafana browser assertion incorrectly expected `orgRole` in
  `/api/user`; Grafana exposes organization membership through
  `/api/user/orgs`. The corrected verifier checks the authenticated username
  and server-admin flag separately from membership roles, and rejects any
  elevated membership for the Viewer test identity. On 2026-10-11, a fresh
  strict-TLS Firefox run passed as `gitea-e2e`: one Viewer membership,
  non-admin, authenticated session. No Grafana or Authentik configuration
  changed during this verifier-only run.
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
  authentication both pass. One recovery-email request returned HTTP 204. A
  metadata-only Gmail search on 2026-10-13 found a platform-password-reset
  message in Inbox dated 2026-10-11. The message body and one-time link were not
  accessed; delivery is confirmed, but reset completion and link validity are
  not.
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
  by Authentik; at that time mailbox delivery was unverified because Gmail
  required reauthentication.
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

## Live verification checkpoint — 2026-10-01

- The selected `0mcp` deployment preflight passed. Authentik's public ready
  endpoint returned HTTP 200; `/opt/authentik/.env` metadata is a non-empty,
  root-owned, regular mode-0600 file, and the local OpenBao provisioner
  artifact/receipt plus Authentik token and test-password files passed
  mode-0600 metadata checks. No secret contents were displayed.
- Read-only identity and OAuth reconciliation both report zero drift. The live
  catalog contains 22 applications/providers and no Keycloak-named object.
  Runtime checks found no active Keycloak container on the former VM120 or
  VM192 hosts; the tracked active service/integration/Authentik declarations
  likewise contain no Keycloak consumer. Existing cold rollback archives were
  not removed.
- Fresh strict-TLS browser OIDC checks pass for Gitea and Harbor using the
  existing non-admin `gitea-e2e` identity. Its Authentik test password remains
  only in the ignored local credential file. Ops Portal and Repository Intake
  return the expected 403 at the shared proxy callback with no server errors.
- Outline still fails the authenticated realtime WebSocket handshake. Grafana
  did not establish an authenticated browser session. GlitchTip still returns
  `signup_closed`. Chat now loads its LibreChat login page (HTTP 200, not the
  previously reported 502), but the Authentik callback returns HTTP 500 and
  does not establish an app session. Its live issuer, client ID, callback,
  social-registration policy, and client-secret equality check match the
  managed configuration; the existing non-admin Mongo user is OpenID-linked.
  A stale OpenID subject is a plausible migration cause, but the subject
  comparison was not completed and no account record was changed.
- The managed operator identity (`akadmin`) and groups reconcile without drift.
  One fresh-browser attempt using the ignored local bootstrap-password file
  recorded `login_failed`; that file is not a confirmed current operator
  credential. A later reset request used the dedicated recovery flow; see the
  recovery follow-up below.
- Before the operator decision, the catalog pinned 2026.8.0; its 2026-08-30
  receipt reported 8 critical and 58 high findings, was 32 days old, and had
  an exception that expired on 2026-09-13.
- On 2026-10-01, the governed image-upgrade workflow resolved stable 2026.8.3
  to `ghcr.io/goauthentik/server:2026.8.3@sha256:09782fe56675bc616a0324468f1698e2d9d83c978bc5e426686fb7563517a442`
  and rescanned it with pinned Syft 1.41.2 and Grype 0.110.0: 3 critical, 84
  high, 94 medium, 29 low, 79 unknown, and zero HIGH/CRITICAL findings with a
  known fix. The earlier 3/74 candidate count was from Trivy, not the current
  Grype budget evidence.
- The operator explicitly accepted both the 3 critical and 84 high findings
  for seven days. The branch catalog now records a digest-pinned exception
  through 2026-10-08 with a re-scan/remediation plan; the Authentik budget gate
  passes using that exception. Do not extend it silently.
- This is not yet a production deployment: VM192 still runs 2026.8.0 and
  public readiness returns HTTP 200. The latest PBS backup is from 2026-09-29;
  PBS has only about 6.3 MiB free, and its restore rehearsal did not reach
  Authentik web readiness. A short-lived VM snapshot is the available
  immediate rollback option; capture it before applying 2026.8.3 and remove it
  only after the post-deploy checks pass.
- A temporary, NIC-detached restore of
  `backup-lv3:backup/vm/192/2026-09-29T00:18:41Z` restored 137,438,953,472 bytes
  in 89.10 seconds and booted under guest-agent control. The restored Postgres
  container accepted connections, but the Authentik web container exited 255
  and local readiness returned HTTP 400. The temporary VM was stopped and
  destroyed; production VM192 remained running. This is partial
  disk/database-recovery evidence, not a passing Authentik service restore.
  PBS had only 6,484 KiB available, so no new backup was attempted.
- Current unauthenticated reachability checks return HTTP 200 for Authentik,
  Outline, Gitea, Harbor, Grafana, GlitchTip, and Chat; Ops Portal and
  Repository Intake return 302 to the shared login path. These status checks
  are not counted as authenticated-session proof.
- A fresh browser visit confirmed the dedicated `platform-operator-recovery`
  page renders and accepts the account identifier. After one explicitly
  requested reset submission, Authentik displayed its generic "Check your
  Inbox" confirmation. Gmail is currently signed in; a focused `in:anywhere`
  search for recent Authentik/reset mail returned no matching message. This is
  evidence that the flow accepted the request, not proof of delivery.
- A code audit found a concrete SMTP contract mismatch: Authentik defaults
  pointed to Stalwart's `1587` listener, while the mail-platform runbook
  requires the private provider-backed `mail-gateway-smtp:1588` bridge for
  transactional mail. The Authentik defaults and regression test now match
  that contract, but this correction has not been applied to production or
  delivery-tested; treat it as a likely cause, not yet a confirmed fix.
- A read-only Resend domain-list request using the newly supplied credential
  returned an empty list, so no verified Resend sender was confirmed. No email
  was sent and the credential was not persisted; the existing mail gateway is
  still the supported Authentik delivery path.

The workstream remains blocked on an Authentik image that meets the enforced
security budget, a fully successful application-level restore rehearsal, and a
current least-privilege operator credential. After those gates are resolved,
repair and rerun the Grafana, Outline, GlitchTip, and Chat browser paths before
claiming completion.

## Live verification checkpoint — 2026-10-11

- A Tailscale daemon restart temporarily removed `tailscale0`; all 19 declared
  Proxmox TCP proxy socket units stopped and did not re-arm. Restoring those
  sockets recovered the private listeners without changing service containers,
  proxy targets, or public exposure.
- The Gitea login page now returns HTTP 200 through the PVE-hosted private
  proxy, and Authentik readiness returns HTTP 200. This verifies upstream
  reachability, not a completed browser OIDC session.
- The current Mac cannot reach the PVE proxy address because the hosted
  Tailscale ACL drops that direct peer/port flow. Separately,
  `git.example.org` presents a strict-TLS certificate whose SAN names only
  `achizitii.example.com`; the browser E2E therefore fails before OIDC. Gitea is
  declared private-only, so no public NGINX route or TLS downgrade was made.
- The Proxmox Tailscale proxy role now wants sockets from both
  `sockets.target` and `tailscaled.service`, starts listeners based on socket
  state, and asserts the socket remains active. Focused regression coverage
  checks this recovery contract. The updated role has not yet been applied to
  production; the manual socket recovery is recorded in the accompanying
  sanitized live-apply receipt.
- No Authentik identities, application/provider objects, consumer credentials,
  Keycloak archives, or service containers were changed during this recovery.

### Gitea browser-route correction — 2026-10-11

The earlier conclusion that no managed NGINX route was appropriate was too
strong. Direct, proxy-bypassed inspection showed that the browser hostname
reaches the private NGINX VM through the Proxmox subnet-router path, but its
request fell through to an unrelated default vhost and certificate. The
Tailscale ACL was not the browser-path failure; it only blocks a separate
direct Mac-to-host-proxy flow.

The source work now declares a distinct private HTTPS edge route for Gitea,
allowlisted to the private ingress address, while keeping the raw controller
TCP proxy separate. Private routes do not trigger public per-host ACME
issuance: the edge must already have a shared certificate covering the
hostname, and the converge checks that coverage with OpenSSL before rendering.
The private HTTP and HTTPS vhosts deny other source addresses, and the
ACME-challenge exception is omitted from those private vhosts. The route is now
applied and verified as recorded in the dated live-apply receipt below.

- The 2026-10-11 fresh edge host scan reports hardening index 64 and three
  warnings. Direct host inspection confirmed the Debian `trixie-security`
  deb822 source and active nftables input/forward drop-policy chains, so
  `PKGS-7388` and `FIRE-4512` are now host-scoped detector suppressions for
  `nginx` only. The genuine `KRNL-5830` pending-reboot warning remains visible.
  The broad security scan could not reach the declared backup target, so it did
  not publish a misleading all-host receipt; NGINX was rescanned separately.
  The narrow route apply passed the NGINX service gate and its documented
  in-place exception.

The PR gate also exposed two repository-contract defects and one mis-scoped
completeness check. Changes to individual subdomain rows now select only their
owning service, while reservation/structure changes still fail closed to the
global audit. The NGINX edge appliance explicitly does not require an API
gateway registration, application dashboard, app data catalog, or per-app
alert rule; its health is represented by the existing edge SLO and centralized
host monitoring. The HTTPS/TLS workflow now references the generator rather
than an ignored generated alert file that is not present in fresh Git snapshots.
Regression tests cover service scoping and these non-app applicability rules.

### Gitea production edge apply and browser proof — 2026-10-11

The first converge was invoked without the explicit deployment selectors. It
failed closed at the existing-certificate coverage guard before rendering or
reloading NGINX. The deployment's ignored local identity profile also contained
stale host-name/interface metadata; those facts were corrected from live
Proxmox inspection, and the generated inventory was rebuilt with the explicit
identity and topology overlays.

The corrected governed public-edge converge completed with 133 tasks OK, 5
changed, 0 failed, and 53 skipped. NGINX configuration validation and service
activity passed. The Gitea HTTPS route and Authentik readiness both returned
HTTP 200, with TLS verification enabled. A new temporary Firefox profile
completed the Authentik OIDC callback into Gitea using `gitea-e2e`; the account
was confirmed non-admin. No Tailscale ACL was widened and no Gitea public
exposure was added. A governed Restic run then protected all five configured
sources with zero uncovered sources; its latest snapshot summary is recorded
separately and does not claim that an uncommitted source revision was backed up.

This proves the Gitea browser sign-in path, not overall Authentik completion.
Outline realtime, Grafana role assignment, GlitchTip first-login provisioning,
Chat's OIDC callback, the current operator credential/recovery path, and an
application-level Authentik restore remain unresolved or unverified. The
Keycloak runtime is absent from the checked live hosts and active application
catalog, but cold rollback archives and residual discovery references have not
been exhaustively retired.

### Security and restore closeout evidence — 2026-10-11

- The live Authentik server and worker still use the exact catalog-pinned
  `2026.8.3` linux/amd64 digest. A fresh Syft/Grype scan of that digest reports
  6 Critical, 99 High, 102 Medium, 29 Low, 81 Unknown, and zero HIGH/CRITICAL
  findings with a known fix. The refreshed receipt is
  `receipts/image-scans/2026-10-11-authentik-runtime.json`. The enforced budget
  remains 0 Critical / 40 High; the prior operator decision covered 3 Critical
  / 84 High and its seven-day exception expired on 2026-10-08. No new
  exception was inferred or renewed. The official upstream release page still
  identifies 2026.8.3 as the latest stable release; see
  [Authentik releases](https://github.com/goauthentik/authentik/releases).
- The public Authentik readiness endpoint returned HTTP 200 with TLS
  verification enabled during this checkpoint. This is availability evidence,
  not an authenticated operator session.
- Proxmox reports the PBS storage endpoint active and the latest VM192 backup
  available at `2026-10-11T00:24:38Z`. The tracked backup guest (VMID 160 at
  its declared address) is absent from the single-node Proxmox cluster and its
  SSH/PBS ports are unreachable, so the stale backup-host security scan could
  not be refreshed against that inventory target. The live PBS endpoint is a
  separate Tailscale peer and does not expose SSH from the Proxmox host.
- The application restore rehearsal was deliberately not booted. Live
  inspection shows `vmbr20` is the production guest network, not the isolated
  staging segment assumed by the generic restore procedure. VM192 also has
  several auto-starting service stacks and 12 GiB configured RAM, while the
  Proxmox host had only about 7.9 GiB available. VMID 903 was free and no
  clone was created. A successful Authentik restore still requires a genuinely
  isolated restore path and capacity admission; filesystem or PBS snapshot
  presence alone is not app-level recovery proof.
- The generic restore runbook now has an explicit fail-closed safety gate.
  The runner also refuses fixtures without explicit isolation, with a default
  gateway, or overlapping managed guest addresses; it verifies that the
  selected bridge is unaddressed and has no attached ports, refuses occupied
  target VMIDs, claims ownership only after a successful restore, and requires
  an exact per-run Proxmox tag before deleting the guest. Failed or ambiguous
  cleanup is preserved in the verification result instead of deleting an
  unverified VM.
  The current three generic fixtures are explicitly marked non-isolated, so
  the live command stops before restoring anything. A separate
  bridge/capacity path and deployment-specific service-bind behavior still
  need implementation and verification. No production service, account,
  network route, or backup was changed during this check.

### LibreChat firewall apply and Authentik browser proof — 2026-10-11

PR #294 merged the managed, narrowly scoped SNAT policy for the observed
LibreChat bridge (`172.16.1.0/24`) to the private edge on TCP/443. The canonical
guest-network-policy converge targeted Coolify only and completed with 30 OK,
2 changed, 0 unreachable, and 0 failed. The old file was retained in a verified
root-owned mode-0600 backup; its SHA-256 and the post-apply SHA-256, plus the
exact invocation evidence, are in the live-apply receipt. The Docker service
PID and 11 container IDs did not change, confirming the apply did not restart
Docker or recreate application containers.

The firewall syntax check passed. From inside the LibreChat container, strict-
TLS OIDC discovery returned HTTP 200 with the expected Authentik issuer. A
fresh temporary Firefox profile then completed Authentik OIDC authentication
and the application callback (`authenticated_session=true`, callback HTTP
302, `status=ok`) using the existing non-admin test identity. A request from
the monitoring guest to Coolify's node-exporter `/metrics` endpoint also
returned HTTP 200, confirming the monitoring scrape path survived the narrowed
forwarding rule. No image redeploy or security-budget exception was made.

The remaining blockers are still distinct: Outline and GlitchTip image/runtime
applies are denied by unresolved critical findings; Authentik's runtime image
budget is currently exceeded; the operator recovery credential is not yet
verified; and the application-level restore rehearsal has not passed. The
Keycloak container remains absent from checked runtime hosts and the active
Authentik catalog, but cold rollback archives and residual discovery references
are intentionally not described as fully retired.

### Operator recovery account selection — 2026-10-11

The read-only recovery contract check passes. A reset request failed closed
before sending because two active Authentik internal identities share the
configured operator email. Inspection confirmed that the managed bootstrap
administrator is the intended superuser; the second matching account is
non-admin. No account, credential, group, or email address was changed. The
recovery helper now selects by both the configured email and the managed
bootstrap username, then verifies active and administrator status. Its focused
tests pass (6/6), including duplicate-email selection and non-admin rejection.
After merge, issue one reset request and verify inbox delivery without storing
or surfacing the short-lived link. The Authentik image budget remains expired;
this helper correction and recovery request do not change or redeploy its image.

The first push attempt also exposed an incomplete ownership manifest for the
new recovery helper and a workflow-catalog validation assumption: a generated,
gitignored Uptime Kuma catalog was absent from the remote validation snapshot,
which has no Git metadata. The workstream now declares both new recovery files,
and workflow implementation references accept only generated paths explicitly
declared by the existing bootstrap manifest. A regression test covers both a
manifested generated path and an undeclared missing path in a no-Git snapshot.

### Patched runtime Harbor bootstrap — 2026-10-12

The private `patched-runtime` Harbor project was created by the managed
converge with the required private, auto-scan, and no-system-allowlist metadata.
The converge then stopped before creating its scoped robots because Harbor's
per-key metadata endpoint rejected the role's request body; its
`reuse_sys_cve_allowlist` setting also requires a CSRF context on that endpoint.
Read-only checks confirmed Harbor stayed healthy and the project metadata
already matches policy. The role now merges the desired metadata with any
existing metadata, updates the project through Harbor's project update API only
when values differ, and verifies the read-back. Focused Harbor role tests and
playbook syntax pass. The corrected converge, robot provisioning, patched image
builds/scans, catalog review, and consumer rollout are still pending.

### Builder and artifact-cache recovery — 2026-10-12

PR #306 is merged; Woodpecker push pipeline 632 and PR pipeline 633 both
completed successfully. The temporarily authorized shared
`docker-runtime-lv3-woodpecker-agent` was stopped after the checks completed;
there were no active `wp_*` job containers when it was paused.

The builder/cache investigation initially found the immediate live blocker:
Docker was active on the dedicated artifact-cache guest, but it had no running
containers or listeners on ports 5001–5004. Read-only probes from monitoring
and docker-build timed out. That initial state was repaired by the governed
builder replay; the exact monitoring route was then restored separately.

The builder converge had previously stopped after eight changes at artifact
cache argument validation. The current branch supplies the values early enough
for Ansible role-argument validation, preserves the legacy BuildKit cache
mounts during managed handoff, and adds the missing artifact-cache service
definition instead of weakening service-completeness validation. Dependency
graph node-only edits are now scoped to their owning service; edge edits still
fall back to full validation. Focused completeness tests (34/34), Authentik and
artifact-cache completeness, the generated service catalog, and the full
`data-models` validation pass. The sanitized-publication audit still reports
two pre-existing critical public-IP coverage gaps and must be repaired before
publishing the private repository to ServerClaw.

Rebasing on PR #309 exposed a lifecycle-model mismatch: edge publication can
be retiring while the service remains active in the private runtime, as the
edge-publication runbook explicitly intends for never-deployed backends. The
environment validator now allows only the `active` service / `retiring`
subdomain combination; other status mismatches remain rejected. Service
catalog aggregates and the generated dependency diagram were refreshed from
their canonical sources. That refresh also selected the managed status-page
endpoint for completeness validation; its profile now reflects that it is an
Uptime Kuma endpoint rather than a standalone Compose service, without changing
runtime deployment state.

PR #320 is merged. Its identity guard and systemd-aware BuildKit handoff passed
CI, but the first identity-aware live apply exposed one more lifecycle race:
stopping a systemd unit whose Docker command uses `--rm` removes its legacy
container, while the following task relied on the pre-stop inspection and tried
to stop that now-absent container. The apply receipt is partial. The canonical
managed service and container were restored and are active; the non-canonical
unit is inactive and disabled, both legacy containers are absent, the persistent
cache path remains present, and `buildctl debug workers` reports an amd64
worker. No cache contents were deleted.

The follow-up change reinspects named containers after the unit stop and only
stops those still running, while treating only the exact Docker
"No such container" race as benign. Focused role/runtime tests (23 passed),
Ansible lint, playbook syntax validation, and live-apply preflight pass. This
fix must merge before the governed replay; because the legacy containers have
already been retired, that replay should omit the legacy-container override and
verify the canonical service, managed Buildx bootstrap, and a small build
canary. Then record the completed receipt and continue with the cache-plane
port checks and approved patched-image build/scan workflow. Do not deploy a
candidate image until its scan and consumer tests pass.

Manifest regeneration exposed that free-text receipt matching could attribute
common terms such as “container” and “docker-build” to many unrelated services.
Live-apply receipts now support explicit `service_ids`; this builder receipt
scopes its date evidence to `artifact_cache` and `docker_build`, and the
regenerated platform manifest updates only those two services.

PR #321 merged as repository/platform version `0.179.50`. The governed builder
replay completed with `ok=157 changed=1 failed=0`; the canonical service is
active/enabled, the legacy unit is disabled, the persistent cache path remains
present, and the old containers are absent. The remote `mcp-cache` Buildx
builder bootstrapped, and a local-only OCI amd64 canary built and was removed.
All four artifact-cache `/v2/` endpoints responded from both docker-build and
docker-runtime. The detailed record is
`receipts/live-applies/ws-0512-authentik-builder-managed-replay-20261012.json`.

The first monitoring-VM probe still timed out on cache port 5001 and
node-exporter port 9100. PR #322's canonical policy now declares both monitoring
checks while keeping ports 5002–5004 restricted to approved build/runtime
consumers. A scoped check-mode render showed that a full Proxmox network-role
replay would write a self-referential uplink/bridge configuration from the
current identity override; the fail-fast guard blocked that unsafe whole-host
apply and no Proxmox host network configuration was changed.

The live firewall recovery was then applied safely to VM 180 only. The
generated PVE VM firewall policy added monitoring-source TCP/5001 (retaining
the existing TCP/9100 rule); its prior file is retained on the Proxmox host
for rollback. The guest-only nftables converge added monitoring TCP/9100 and
removed only unrestricted forwarding accepts, retaining the four cache-port
allowlist. All four cache containers remain running with host networking and
the Docker bridge has no attached containers. From the actual monitoring
Blackbox Exporter, the catalog module now reports `probe_success 1`, HTTP 200
for `/v2/` and `/metrics`, and TCP ports 5002–5004 remain blocked. Both
docker-build and docker-runtime still reach all four cache ports. The
non-secret evidence is in
`receipts/live-applies/ws-0512-artifact-cache-monitoring-20261012.json`.
PR #323 is merged, and the artifact-cache SLO is live on monitoring VM 140.
Prometheus reports the `artifact-cache-availability` target healthy with
`probe_success=1`; after the first recording-rule evaluation,
`slo:artifact_cache_availability:success_ratio_5m` returned `1`. The three
artifact-cache burn/budget alerts are loaded, healthy, and inactive, and the
Grafana SLO overview dashboard imported and verified.

The optional Alertmanager triage Jinja control lines are YAML-comment-prefixed
so full-repository YAML lint can parse the template. Rendered YAML was compared
with triage both disabled and enabled and remains semantically unchanged.

The scoped `live-apply-service service=grafana` run used the documented ADR
0191 reversible in-place exception. Its SLO-specific tasks passed, but the
broader monitoring role ended with `ok=267 changed=19 unreachable=0 failed=1`
when the controller-local ntfy notification-password file was absent. No
password was fabricated or copied. This receipt records the SLO as live while
keeping the remaining Alertmanager converge explicitly incomplete:
`receipts/live-applies/ws-0512-artifact-cache-prometheus-slo-20261012.json`.

### Keycloak SSO DNS retirement — 2026-10-13

The source audit found no active Keycloak DNS declaration in the current
inventory, DNS catalog, or service topology. Historical and compatibility
references remain in migration/retirement code and cold rollback archives, so
this one-record change is not a claim that every historical Keycloak artifact
has been erased. The first read-only credential context lacked the `example.org`
zone. A metadata-only Fleet Secrets inventory then identified the canonical
`hcloud_token_fleet_core` record and its owning project. A short-lived,
single-use service key read that record through the approved consumer API; the
key was revoked immediately, and the token was never printed or stored locally.

The Hetzner Cloud API inventory showed that `sso.example.org` had exactly one
unprotected RRSet, `sso/A -> 203.0.113.1`; no `sso` AAAA or CNAME set existed.
The separate `id.example.org` A record was retained. Before removal, strict TLS
validation for `https://sso.example.org/` failed because the edge certificate did
not cover the hostname, and an unauthenticated diagnostic GET returned HTTP
403. The canonical Cloud API DELETE returned HTTP 201 and a subsequent GET of
that exact RRSet returned 404. No other DNS names or record types were changed.
See the live-apply receipt
`receipts/live-applies/ws-0512-authentik-keycloak-sso-dns-retirement-20261013.yaml`.
After the prior 60-second TTL elapsed, Cloudflare (`1.1.1.1`), Google
(`8.8.8.8`), and Quad9 (`9.9.9.9`) each returned `NOERROR` with no A answer for
`sso.example.org`, so the retirement is propagated at those resolvers.

### ServerClaw publication CI repair — 2026-10-13

Private PR #334 merged as `6d6b876a5`; it recorded the current security and
runtime gates but did not complete the public snapshot publication. The
private source repair PR #337 later merged as `3f64c9b7b`, correcting the
sanitized templates, image receipt reference, and workstream ownership found
by the first public CI run. The
sanitized ServerClaw PR #69 initially failed both required Woodpecker checks:
its generic Gitea catalog omitted the private-edge declaration, the firewall
renderer test depended on private deployment addresses, and the generic host
template did not consume `LV3_PROXMOX_HOST_ADDR`. The source-side corrections
and a generic reserved-address SNAT fixture are committed on
`codex/serverclaw-template-ci-20261013`. The exact mirror Woodpecker test sets
passed locally (229, 31, and 7 tests); additional image-policy, vulnerability,
sanitization, firewall, and subdomain checks also pass. The protected private
pre-push gate then exposed two bookkeeping errors: undeclared ownership of the
new template/fixture paths and a missing 2026-10-12 Authentik scan summary
receipt. Ownership is now declared. The catalog continues to mark Authentik
blocked and points to the last tracked same-digest receipt from 2026-10-11;
the reported 2026-10-12 scan remains unarchived. Re-run the protected gate,
merge the private source PR, regenerate the sanitized snapshot, and get green
checks on PR #69 before calling publication done. The follow-up sections below
record the completed source and public snapshot gates.

The refreshed public runs then narrowed the remaining failure to one omitted
generic firewall rule: the sanitized Proxmox host template lacked the existing
monitoring-to-Coolify TCP/9100 node-exporter flow. The test proved the mismatch
against the sanitized template (the private inventory already contains the
rule). This follow-up adds the same narrowly scoped, non-forwarded rule to the
generic template. Local mirror suites pass again (229, 31, and 7 tests), the
focused firewall/image-policy set passes (59 tests), the strict sanitization
audit has zero Critical/Warnings, and the fresh-main publisher dry-run reports
no leaks. A subsequent public run exposed three additional monitoring-to-
node-exporter rules omitted from the same Tier A template (nginx,
docker-build, and runtime-control). The private inventory already contains
those policies. This follow-up restores their generic equivalents in the
canonical publication template and adds a regression assertion so future
snapshots retain all three. The template corrections were merged in private
source PR #339 and included in the published snapshot.

The refreshed public runs then exposed a separate inherited-CI mismatch: the
publisher intentionally removes `config/tailscale/` and its private policy
manifest, but the public snapshot still runs the source repository's offline
Tailscale policy check. The check now skips only when the default policy and
private publication manifest are both absent, which identifies the sanitized
snapshot shape; a missing policy remains fatal in private source. Regression
tests cover both cases. This source repair and the refreshed public PR checks
passed the private protected gate and both private Woodpecker checks. The fresh
sanitized snapshot from source commit `f31c276c8d` passed the publication leak
check and both public Woodpecker checks. ServerClaw PR #69 merged as
`01e12293dc28f8da0cc30f9653774b2f28a439f2`. This closes the snapshot CI gap;
it does not deploy Authentik or change the remaining live-service blockers.

### Live continuation — 2026-10-13

The active 0mcp deployment selector was verified from its ignored local
identity/topology overlays. The Outline and GlitchTip deployment-selection
preflights initially stopped because `inventory/group_vars/platform.yml` was
stale for that selected deployment. Regenerating the canonical generated file
made both preflights pass. The focused Outline, GlitchTip, admin-gate, and
restore-verification tests pass (42 tests).

Fresh strict-TLS consumer browser runs reproduce the remaining live defects:
Outline completes Authentik login but fails its Engine.IO WebSocket handshake;
the running Outline container omits the managed `websockets` service from its
`SERVICES` value. GlitchTip returns `signup_closed` after Authentik login; local
registration remains disabled and the running container lacks the managed
social-app registration setting. Neither consumer was changed because its
current image remains security-gated.

A fresh scan of the exact deployed Authentik digest is recorded in
`receipts/image-scans/2026-10-13-authentik-runtime.json` and
`receipts/cve/09782fe56675-20261013T121937Z.grype.json`: 4 Critical, 96 High,
102 Medium, 29 Low, 86 Unknown, with zero blocking findings that have a known
fix. The image remains blocked; the old exception was not renewed. The
configured builder and its Proxmox parent currently have limited available
memory and near-full swap, so no patched-image build was started.

Read-only Proxmox checks still find VMID 160 absent, while PBS storage is
active; the declared guest route is unreachable. No restore VM or network
bridge was created. At the time of this checkpoint the DNS retirement was
still pending; the later one-record change is recorded below.
The requested operator credential reset was applied directly through the
authenticated Authentik user API (HTTP 204) after the recovery-link attempt
stalled before its password-entry stage. The credential remains only in ignored
deployment-local storage. A fresh Firefox profile trusted the internal CA,
kept TLS validation enabled, and successfully reached `/if/admin/` as `akadmin`.
The username/password were sent to the configured operator mailbox. Gmail
metadata shows a SENT-labeled message with the same sender and recipient; it is
not Inbox-labeled because this was self-addressed. This confirms administrator
access; it does not confirm the self-service recovery-link flow.
The change is recorded in
`receipts/live-applies/ws-0512-authentik-operator-admin-access-20261013.yaml`.

The example.org zone was subsequently verified through the canonical Hetzner
Cloud API. Only the orphaned `sso/A -> 203.0.113.1` RRSet was removed;
`id/A` was preserved. The deletion returned HTTP 201, its exact post-delete
GET returned 404, and Cloudflare, Google, and Quad9 returned no A answer after
the 60-second TTL. The one-use Fleet Secrets writer/service keys were revoked
immediately after use; the canonical DNS token was never printed or stored
locally. See
`receipts/live-applies/ws-0512-authentik-keycloak-sso-dns-retirement-20261013.yaml`.

### Runtime-comms security gate refresh and Neko edge audit — 2026-10-13

The Neko live-apply gate initially rejected the host at four Lynis warnings.
Read-only checks then confirmed a current Debian `trixie-security` source,
active nftables input and forward chains with drop policies, and synchronized
systemd time. The warning for legacy iptables and the legacy-format security
repository detector are now host-scoped suppressions with fresh evidence; a
scoped Lynis refresh at
`receipts/security-reports/20261013T083129Z.json` leaves one warning: a pending
reboot. `vulnerability_budget.py --service neko` now approves the host budget.
The pending reboot remains visible and was not performed under the current
Proxmox memory/swap pressure.

The live strict-TLS `browser.example.org/oauth2/start?rd=%2F` route returns HTTP
302 to `id.example.org` through the shared `ops-portal-oauth` client; NGINX syntax
is valid. The exact live Neko site file contains four `Keycloak` mentions,
all in comments and none in active directives. Its existing email-to-browser
map has one route and runtime-comms has one running Neko container. The current
managed playbook template is Authentik-backed, but the selected inventory has
no top-level `neko_instances` input (the only canonical nested value is empty).
A check-mode attempt to render the template therefore fails closed with
`neko_instances` undefined. The `edge-publication` tag also selects no
Neko-specific tasks in the current wrapper. No live Neko mapping was changed:
re-rendering from the empty source would remove the one existing user route.
The SSO redirect is verified as Authentik-backed, but those residual comments
and the undeclared user-to-container mapping remain an IaC reconciliation gap.

The governed apply's standard configuration-backup hook completed: all five
governed sources were protected with zero uncovered or inactive sources in
`receipts/restic-backups/20261013T083620Z.json`. This backup does not imply that
the Neko site template was applied.

### API Gateway and Typesense authenticated E2E — 2026-10-13

Typesense had no existing container, image, persistent volume, or index on the
declared `docker-runtime` VM. The pinned Typesense 29.0 image was restored and
its health endpoint returned HTTP 200. A playbook ownership bug was found before
the gateway was deployed: the Typesense playbook also invoked the API Gateway
role on `docker-runtime`, despite the gateway being assigned to `runtime-control`.
The playbook now converges Typesense only; a regression test prevents a second
gateway from being created on the wrong VM.

The separate governed API Gateway apply on `runtime-control` completed with
zero failed or unreachable tasks. Its verification used the managed
Authentik machine client: the discovery issuer matched, the client-credentials
grant returned a bearer token, anonymous `/v1/health` was rejected with the
canonical 401 error, and the authenticated platform-services and runtime-
assurance endpoints returned 200. The protected structured-search endpoint
returned Typesense-backed results. Independent read-only probes confirmed
Typesense HTTP 200, 78 documents in `platform-services`, and public gateway
`/healthz` HTTP 200. The post-apply Restic hook protected all five governed
sources with no uncovered or inactive sources.

The first gateway apply exposed a newline at the end of the controller-local
Typesense API-key file; `urllib` rejected it as an invalid header before making
the collection request. The catalog-sync client now strips surrounding file
whitespace and has a regression test. The retry completed successfully. The
temporary controller-to-Typesense SSH tunnel was closed and its listener
verified absent. The local ignored Restic receipt records the apply snapshot;
the tracked latest-snapshot receipt is updated by the managed hook.
The committed live-apply evidence is recorded in
`receipts/live-applies/ws-0512-authentik-api-gateway-typesense-20261013-apply-receipt.yaml`.

This closes the API Gateway/Typesense portion only. Outline and GlitchTip remain
blocked behind unresolved runtime-image security and build-capacity gates;
restore rehearsal, Neko IaC mapping, and full Keycloak retirement also remain
open as recorded above.

### Fresh consumer retest and builder capacity — 2026-10-13

Repeated the six browser checks in new temporary Firefox profiles with strict
TLS validation enabled. Gitea and Harbor completed Authentik login as the
non-admin test identity. Grafana completed login with organization role
`Viewer` and no server-admin privilege. LibreChat completed its Authentik
callback and authenticated session. Outline still fails the Engine.IO
WebSocket handshake; GlitchTip still rejects first-login provisioning with
`signup_closed`. These results confirm the four passing consumers remain
healthy, but do not close the two application-specific defects.

The configured remote image builder is reachable through its strict-host-key
bastion route. A read-only capacity check reports 5.0 GiB guest memory
available, 2.3/4.0 GiB swap used, and 47 GiB free disk. Its Proxmox parent has
4.5 GiB available and 4.0/4.0 GiB swap used. Because prior source builds were
killed by the host OOM killer and the parent remains nearly out of memory, no
new image build was started. A separate Buildx pool was not repurposed for this
repository; it is not configured here as an approved image-build worker. No
production runtime or configuration was changed during these
retests.

The first direct scan-refresh attempt also found that
`config/sbom-scanner.json` still pointed at the staging cache address. The
production builder's read-only probes returned HTTP 200 from all four current
cache mirrors, confirming the production route declared by the topology. The
scanner default now matches that route, and its unit fixtures use a generic
cache hostname; a regression test covers the controller-local proxy override.
Because this controller has no direct private-cache route, the refresh used a
temporary strict-host-key SSH forward for the one required registry port. The
local listener was closed after the scan. No public-registry fallback was used.

Grype 0.111.0 and the latest available vulnerability database rescanned the
exact pinned digests. Outline reports 23 Critical / 303 High, GlitchTip 23
Critical / 235 High, and MinIO 38 Critical / 201 High; all three report zero
blocking findings with a known fix. The raw SBOM/CVE evidence is recorded under
`receipts/sbom/` and `receipts/cve/`. The three catalog summary receipts are:

- `receipts/image-scans/2026-10-13-outline-runtime.json`
- `receipts/image-scans/2026-10-13-glitchtip-runtime.json`
- `receipts/image-scans/2026-10-13-minio-runtime.json`

The catalog now points at those exact scan summaries, marks all three images
`blocked`, and removes their expired exceptions. The scan-only refresh path now
records blocked evidence without changing image pins or implicitly renewing an
exception. No image apply or NATS/ntfy alert was run.

The next safe closure step is to obtain adequate capacity on the configured
builder (or explicitly configure and govern a repository-specific alternative),
build and scan the exact Outline and GlitchTip candidates, and only then apply
their already-managed runtime settings and repeat these browser checks. The
current pinned images remain explicitly blocked. The Authentik image gate,
restore rehearsal, Neko source mapping, and residual Keycloak retirement audit
remain separate open gates.

### Repository release-bookkeeping gate — 2026-10-13

The first remote pre-push run passed all policy lanes except `generated-docs`:
three valid post-0.179.51 changelog entries from already-merged mainline commits
had no workstream metadata, so the canonical generator considered them stale.
Rather than delete those notes, this branch adds merged-but-unreleased
workstream records `ws-0525` through `ws-0527`, regenerates the changelog and
merged-workstream status ledger, and keeps them tracked until the next version
cut. The canonical-truth, generated-doc, workstream-surface, and agent-standard
checks now pass locally. This bookkeeping repair does not change `VERSION`,
`versions/stack.yaml`, or live services.

### Post-merge Harbor fix and current build route — 2026-10-13

PR #363 merged to private `main` at `6982c649f6c285f9ca072b5dc7f230b242a3b2f1`.
Both Woodpecker checks passed; the repository pre-push gate also passed after
its permitted local fallback retried Ansible lint/syntax when Ansible Galaxy
returned HTTP 502. The merge fixed the isolated Harbor-auth handoff used by
Buildx. The first corrected retry then exposed a second interaction: the fresh
Docker config also hid the selected remote Buildx instance and fell back to the
Docker-default builder. I interrupted that attempt after Buildx history showed
an error at 1m51s; it produced no completed candidate digest, scan, catalog
update, or live apply. A read-only probe confirmed that copying only the
original `buildx/` metadata into the isolated auth config preserves the
selected `example-cache` remote builder without copying its unrelated registry
credentials. The continuation branch now does that, with regression coverage;
one final build and scan is still needed to prove both auth and cache selection
end to end.

The current clean ServerClaw publication dry-run used that exact private-main
source, passed the sanitization coverage and leak checks, and regenerated the
public derived artifacts. Protected-branch publication PR #74 is open; its
Woodpecker push and PR checks are pending because the shared `repo=*` agent is
stopped. No direct push to public `main` was made.

Read-only Proxmox evidence shows VMID 130 (`docker-build-lv3`) is running with
about 8.1 GiB of its 12 GiB maximum allocated and high CPU use. Its current
Proxmox config reports 20 cores and an 8 GiB balloon minimum, while the
committed inventory declares 12 cores and the managed guest role sets balloon
to zero. This drift was observed but not changed. The parent host has roughly
12 GiB available and no memory or I/O PSI; the guest's SSH route through the
strict bastion timed out during the SSH banner exchange. Earlier in the same
session the guest reported all swap in use and severe I/O pressure. Do not
retry image builds or alter guest hardware until guest access and sustained
capacity recover; reconcile the observed hardware drift through the governed
Proxmox path rather than an ad-hoc VM change.

Next: complete the protected public PR after its checks pass; regain a stable
read-only SSH/capacity sample from the configured builder; then retry and scan
Outline, GlitchTip, and the MinIO dependency candidate at immutable Harbor
digests. Only apply consumer runtime settings after each applicable image gate
passes, then rerun the fresh browser E2E checks. Restore rehearsal, Neko IaC
mapping, the Authentik image gate, and residual Keycloak retirement remain
separate outstanding gates.

### CI webhook filter repair — 2026-10-13

After PR #364 and ServerClaw PR #74 were pushed, the Woodpecker server recorded
`when filters filtered out all steps` for webhooks from both repositories.
GitHub therefore kept their push and pull-request status contexts pending; the
already-running build agent had no job to execute. The workflow-level event
gate was moved onto the primary validation step as a documented step-level
event list, and a regression test now guards that shape. No agent was left
running on the runtime VM. The new push/PR events still need to prove that the
server creates and completes pipelines before either PR is merged.
