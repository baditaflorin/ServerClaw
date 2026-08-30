# ADR 0491 Phase 2 Workstream: GlitchTip Reconciliation and Outline Migration

## Status

In progress as of 2026-08-30 on branch
`codex/authentik-2026-8-flow-ui-fix-20260830`.

## Purpose

Continue the Keycloak-to-Authentik migration without broadening the lockout
blast radius. This workstream closes the incomplete GlitchTip cutover,
reconciles Authentik with its OpenBao-backed target design, validates the
supported Ansible path, and then migrates only Outline.

## Safety boundaries

- Keep Keycloak running and unchanged as the rollback identity provider.
- Change one downstream OIDC client at a time.
- Do not migrate the human operator or require MFA re-enrolment.
- Do not touch `serverclaw-runtime`; it requires cross-repository CI
  coordination.
- Do not begin Keycloak decommissioning or change the canonical
  `identity_provider` selection.
- Never write credentials, bootstrap tokens, or rendered runtime environments
  to Git, receipts, logs, or chat.

## Ordered gates

1. Verify GlitchTip's live `ALLOWED_HOSTS`, login redirect, Authentik discovery,
   callback registration, and a complete test-user login round trip.
2. Capture the out-of-band Authentik provider/application and GlitchTip
   SocialApp configuration in idempotent repository automation.
3. Reconcile Authentik secret delivery with OpenBao and prove the Ansible
   deployment path without changing DNS or edge routing unexpectedly.
4. Create and apply the Outline Authentik provider/application declaration,
   change Outline's OIDC settings, and complete a login round trip.
5. Verify GlitchTip, Outline, Authentik, and Keycloak health; preserve explicit
   per-client rollback instructions and live-apply evidence.

## 2026-08-28 safety audit

The initial live GlitchTip failure was traced to Docker container environment
immutability: the corrected OpenBao-rendered environment existed on disk, but
the application container had only been restarted. A scoped force-recreate
loaded the corrected `ALLOWED_HOSTS`; public health and the allauth configuration
endpoint now return HTTP 200.

GlitchTip uses django-allauth headless mode, so the legacy provider login GET
route intentionally returns 404. The supported browser flow starts with the
headless provider-redirect POST. That flow exposed the next blocker: the
GlitchTip container lacks the internal Authentik hairpin mapping and resolves
the public edge address instead.

Repository and live-state audits also found three foundation stop gates:

- Authentik is live on host port 9010, while canonical edge sources still say
  9000 and the generated platform topology omits the service.
- The common OpenBao helper still authenticates with revoked historical root
  material instead of a scoped, live AppRole.
- The Authentik role would generate replacement secrets instead of safely
  adopting the working legacy environment and datastore.

No broad Authentik or Outline converge is permitted until these gates are
closed. The shared surfaces overlap active multi-deployment workstreams and are
therefore recorded explicitly as shared contracts and conflicts in the
workstream shard.

## 2026-08-28 foundation implementation update

The repository-side foundation gates are now closed:

- Authentik's canonical runtime and edge port is 9010, the generated topology
  agrees with the service registry, and GlitchTip hairpins both its own public
  hostname and Authentik through the edge.
- Sensitive Authentik, GlitchTip, and OpenBao commands require explicit
  identity and topology selectors, a production environment, and an effective
  inventory that matches the tracked deployment snapshot.
- Service runtime secret provisioning no longer consumes historical
  root/unseal material. A bounded breakglass bootstrap creates and verifies the
  narrowly scoped runtime-secret provisioner without restarting OpenBao.
- The Authentik role can adopt the existing four-secret legacy environment,
  verifies immutable rollback copies of both the legacy environment and
  Compose file, and forces recreation when the freshly rendered runtime
  environment changes.
- The Authentik GlitchTip provider/application and GlitchTip SocialApp are
  declarative and idempotent; the old Keycloak client secret remains a separate
  rollback artifact.

The bounded OpenBao bootstrap later completed with non-secret evidence, and
the merged-main Authentik and GlitchTip converges now pass health, provider,
redirect, event-ingestion, and retained-Keycloak checks. The only remaining
GlitchTip gate is the credentialed browser session/logout proof. Outline's
repository preparation is complete below, but its live apply remains gated on
that browser evidence plus merge/CI.

## 2026-08-29 controller transport correction

The first bounded bootstrap attempt stopped before mutation because the
controller tried the cataloged OpenBao mTLS endpoint directly. That endpoint is
topology provenance and requires a client certificate; the established
controller-local automation path is the OpenBao owner guest's loopback HTTP
listener.

The bootstrap now derives the public jump host, OpenBao owner guest, and
automation port from the explicit identity/topology selectors and creates its
own strict-host-key-checked SSH forward. It does not accept an arbitrary API
override. A live `--check` reached the existing initialized and unsealed
OpenBao instance through this path, authenticated the named break-glass
identity, reported the expected pre-bootstrap policy/AppRole drift, and emitted
no local artifact or receipt. The mutating run remains gated on this correction
merging through CI.

## 2026-08-29 AppRole update compatibility correction

The first post-merge apply established the bounded policies, then stopped on
the first pre-existing service AppRole before writing a controller credential
or success receipt. OpenBao returned HTTP 400 because `local_secret_ids` is a
creation-only AppRole setting and rejects that field on updates even when the
requested value is `false`.

The bootstrap now omits that creation-only field from its create-or-update
payload. New roles retain OpenBao's safe `false` default, every subsequent
read still verifies the field is false, and an existing role with immutable
`true` drift remains a hard failure rather than being silently accepted.
Regression coverage models both mutable repair and unrepairable immutable
drift. The partial reconcile is safe to resume idempotently after this
correction passes review and CI.

The subsequent Authentik adoption preflight stopped before live mutation when
the shared-edge portal generators rejected Authentik's incomplete subdomain
record. Authentik is now declared with `upstream_auth`: it performs its own
authentication and must not be placed behind the edge OIDC policy it provides.
This closes the catalog contract required to regenerate both the operations
and documentation portals before edge publication.

## 2026-08-29 RRSet pagination correction

The first full preserve-mode Authentik converge stopped in the DNS-first play
before runtime mutation. The managed zone contains more records than Hetzner's
default RRSet page size, so the role did not see the existing Authentik A
record and the provider correctly rejected a duplicate create with HTTP 409.

The role now queries the provider by the exact managed record name and type,
both before reconciliation and after a create attempt. Existing records remain
idempotent regardless of zone size while absent records still use the provider
collection create endpoint.

## 2026-08-29 controller-local password preservation correction

The first GlitchTip converge reached PostgreSQL preparation and stopped before
the application cutover. The shared PostgreSQL client role invoked its secret
generator through a controller-working-directory-relative path and did not
declare the existing password file as an idempotence guard.

Password generation is now anchored to the repository containing the active
playbook and uses Ansible's `creates` guard. Existing service passwords are
therefore preserved, while a genuinely absent password can still be generated
once. The root filter plugin also resolves the same repository-local utility
without relying on an invalid fixed parent depth.

## 2026-08-29 GlitchTip secret materialization correction

The next production converge safely recovered Docker bridge networking and
reached the GlitchTip runtime before any application container was created.
It then stopped because the role interpolated generated secret values into a
shell command position. The shell treated each value as an executable name,
leaving zero-byte destination files behind before failing.

GlitchTip runtime and local break-glass secrets are now written atomically
with Ansible's copy primitive only when their destination is absent or empty.
Existing nonempty values remain untouched, generated values retain the
required secret prefix, and both remote and controller-local files are
enforced as mode `0600` without placing secret values in command lines.

## 2026-08-29 mail rotation and supporting service recovery

The shared submission credential exposed during diagnosis was replaced with a
fresh generated value and reconciled to the runtime, controller mirror,
OpenBao service path, compatibility mirror, and rotation metadata. The
corrected Stalwart principal endpoint passed the playbook authentication gate
twice. An independent probe from a separate consumer VM then proved that the
final credential authenticates, the exposed original is rejected, and the
private relay does not advertise STARTTLS. Temporary plaintext snapshots of
the original and intermediate values were destroyed after that proof.

The canonical mail converge then found two pre-existing platform blockers. The
managed DNS zone contains 124 RRsets, so a single 100-entry provider read is
not a complete drift boundary. The role now follows the provider's bounded
pagination metadata, combines every page, and refuses reconciliation unless
the combined count matches `total_entries`.

The monitoring refresh also exposed ADR 0438 path drift: credentials accepted
by MinIO, Grafana, and InfluxDB remained under the raw config-prefix directory,
while current automation derives the POSIX-safe unix-prefix directory. Loki
was recovered by restoring the controller mirror from the accepted legacy
MinIO credential; its systemd service and `/metrics` endpoint both returned
healthy. MinIO and monitoring automation now migrate existing credentials to
the canonical directory before generation or reconciliation, preserving live
authority and leaving the legacy copy available for rollback.

The first merged MinIO replay proved that all five managed credential files
migrated successfully, then stopped at the OpenBao boundary before runtime
mutation. The MinIO playbook still requested its retired `minio/data/root`
path and unprefixed policy. Both entrypoints now use the registered
`services/minio/runtime-env` path and deployment-prefixed service policy while
retaining the bounded `minio-runtime` AppRole.

The monitoring replay then migrated all six local service credentials and
passed Loki readiness, but failed while resolving the desired InfluxDB
organization. The first symptom resembled a stale token; a bounded catalog
probe proved that both local candidates authenticate and expose one organization
under the historical transposed prefix. The role retains the validated token
recovery boundary, then requires either the desired organization or one exact
deployment-approved legacy name. It renames only that organization in place,
preserving its ID, buckets, and authorizations; absent or ambiguous matches stop
without mutation.

The guarded live rename completed and the desired organization resolved under
the preserved ID. The next bucket lookup exposed that the root Influx CLI
default still carried the legacy name and that downstream commands relied on
that implicit context. The role now aligns the root CLI default after a rename
and passes the preserved organization ID explicitly to every bucket and
authorization lookup or creation.

Grafana then passed every datasource and dashboard gate using the preserved
deployment-local datasource UIDs. Alertmanager exposed one final service-identity
drift: the canonical Prometheus unit was healthy while the legacy unit was
restart-looping on the occupied port, and its handler still targeted the retired
generic `lv3-prometheus` name. The exact legacy unit was stopped and disabled
manually at 2026-08-29T05:26Z (canonical readiness remained HTTP 200). The role
now makes that cleanup explicit through a deployment-local allowlist and the
Alertmanager handler targets the canonical service-name variable.

The next canonical mail replay passed the 124-RRset paginated inventory but
found one missing value inside an existing apex TXT RRset. The provider rejected
the old attempt to create a duplicate name/type RRset. The DNS boundary role now
appends a missing value through the rrset `set_records` action while preserving
all existing sibling values and comments; its drift-update path uses the same
full-rrset payload. A no-write Ansible harness verified the reconciled native
payload contains both the existing commented sibling and the missing desired
value before the live repair was submitted.

The first post-mail Keycloak consumer replay stopped at the shared secret
generation helper even though all six remote Keycloak secret files were
nonempty. The helper interpolated generated literal values into shell source;
shell metacharacters could therefore fail parsing before the idempotence guard
was evaluated. Literal secret declarations now use a dedicated value field and
reach the remote shell only through a no-log environment variable, while true
generator commands retain the explicit command path.

The merged-code Keycloak replay then recovered its live PostgreSQL-backed admin
client binding and stayed healthy, but correctly stopped at the SMTP dependency
gate: the running mail container used the selected deployment prefix while the
global `smtp_host` still named the historical `lv3` container. Production SMTP
container DNS now derives from `platform_identity.config_prefix`, with staging
continuing to override the host to Mailpit.

Keycloak then converged fully, including authenticated SMTP and retained
Grafana-to-Keycloak SSO. The Plausible consumer replay stopped before mutation
because it attempted the private OpenBao API from its own VM, where cross-VM
firewall policy correctly blocks that control-plane port. Compose-service
OpenBao API operations now delegate to the OpenBao service's topology owner;
the scoped runtime agent remains on the consumer VM and OpenBao itself is never
restarted or converged by this path.

The merged delegation correction proved every provisioner-authorized API gate,
then the one-shot Plausible agent timed out before application mutation. API
delegation and agent delivery are separate network paths: each service's
persistent agent must reach the OpenBao automation listener after future
restarts, not only during Ansible execution. The runtime-control firewall now
admits only the `docker-runtime` guest to TCP 8201 for that purpose, matching
the existing source-specific grants for `docker-build` and `runtime-comms`.
No public listener, broad guest range, OpenBao configuration, restart, or
unseal operation is part of this correction.

The first main-branch firewall apply installed only the VM 192 policy change,
then correctly detected that the runtime-control nftables reload had removed
Docker's NAT and forwarding chains. The role's bounded recovery restarted the
Docker daemon, restored both chains, and completed successfully. OpenBao's
image and configuration hash remained unchanged, and its watcher restored the
existing initialized store to an unsealed state; no OpenBao converge ran.

That hardened replay also removed an untracked edge exception: Authentik stayed
healthy locally, but its public readiness timed out because the canonical
runtime-control policy did not grant the `nginx` guest TCP 9010. The policy now
adds that single port to the existing edge-source rule, matching Authentik's
registered upstream and preserving default-deny access for every other guest.

## 2026-08-29 durable agent delivery and Plausible password recovery

The merged firewall policy passed a no-change replay with no nftables reload or
Docker restart. A subsequent Plausible converge completed the one-shot OpenBao
Agent render from `docker-runtime` in about one second, proving that persistent
agents no longer depend on a controller-owned SSH tunnel.

The resulting full-stack recreation exposed separate persisted PostgreSQL
state: the desired password was present in the root-only Compose secret and
rendered application URL, but the existing database role still rejected it on
the service network. Local socket trust had hidden that drift. The Plausible
role now starts and health-checks its database first, probes the desired
credential through the service hostname, changes the persisted role only when
that probe fails, and repeats the network-authentication proof before starting
the application. The secret is read inside the database container and passed
to `psql` on standard input; it never appears in process arguments or task
output.

The merged-main replay proved that database reconciliation is idempotent, then
stopped at the bootstrap contract because the selected deployment identity did
not match the single historical Plausible user that already owned all managed
sites. Creating a second user inside the same transaction could never satisfy
the owner-access assertion, so the transaction rolled back on every replay.
When exactly one historical user exists and the desired bootstrap identity is
absent, the bootstrap now adopts that user in place by reconciling its email,
name, verification flag, and password. Existing team and site ownership stays
attached to the same user ID. Empty instances still create the desired user;
multi-user instances stop as ambiguous instead of silently transferring an
identity.

The live adoption completed and every direct bootstrap fact then verified
true. The final Ansible assertion still stopped because it referenced retired
role-local health register names even though the shared health helper now
publishes `common_verify_health_response` and
`common_verify_extra_response`. The Plausible assertion now consumes those
actual helper outputs, so HTTP readiness is checked instead of failing on an
undefined variable.

## 2026-08-29 Dify consumer pre-validation repair

The canonical Dify replay safely created its dedicated PostgreSQL database and
then stopped before runtime mutation during role argument validation. Dify's
first task derives conventional paths from the service registry, but Ansible
validates the argument contract before that task can run. The role now mirrors
the registry-derived site, data, secret, Compose, local-artifact, port, and
OpenBao defaults at role-default precedence. The first task still derives the
same values and preserves higher-precedence deployment overrides.

That repair allowed the Dify stack to start and pass its local health and
bootstrap-safe setup checks. The subsequent SSO bootstrap stopped before
mutation because the Dify role referenced client variables owned only by the
Keycloak role, whose defaults are not imported into a Dify play. Dify now
reads its canonical client ID from the service registry, its existing client
secret from the shared controller-local Keycloak artifact directory, and its
issuer from the global identity contract.

The next merged-main replay proved the runtime and OpenBao paths idempotent,
then exposed two older bootstrap assumptions. The controller helper used the
OAuth-protected public hostname instead of the private runtime API, and the
persisted initialization password exceeded Dify 1.13's 30-character API
limit. The role now repairs only an over-limit initialization secret, renders
that bounded value through the existing OpenBao path, initializes the admin
before login, and reaches the API through a transient loopback-only SSH
forward via the declared jump host. Command failures are checked before JSON
change parsing, so import, transport, and API errors retain their real cause.

The live bootstrap then completed, but the shared post-verify catalog still
contained the default deployment's Docker runtime address. On the selected
deployment that retired address is unreachable while the selected inventory
host reports a finished setup. Dify now overlays only its three post-verify
URLs from the active host's `ansible_host` and the canonical registry port;
the default catalog remains generic for other deployments.

## 2026-08-29 GlitchTip frontend rollback-provider repair

The merged-main GlitchTip replay passed health, Authentik headless redirect,
real client-secret validation, and event ingestion. The mandatory clean-browser
gate then found that the login page exposed only email/password. GlitchTip's
frontend depends on `/api/settings/`, and that endpoint resolves every stored
SocialApp before returning any provider. A retained Keycloak rollback row still
pointed at a retired misspelled issuer, so its discovery failure returned HTTP
500 and hid the otherwise healthy Authentik button.

The runtime bootstrap now reconciles both the selected Authentik SocialApp and
the retained Keycloak rollback SocialApp from separate provider-specific secret
files. The publication gate additionally requires frontend settings to return
HTTP 200 and expose both providers with resolved authorization URLs. Keycloak
remains deployed and usable for scoped rollback; the selected provider remains
Authentik.

## 2026-08-29 GlitchTip browser redirect repair

The merged rollback-provider repair still stopped in a real browser before the
authorization request left GlitchTip. Its same-origin headless form POST
returned a redirect to Authentik, but the shared edge's `form-action 'self'`
policy applied across that redirect and the browser canceled it. Headless HTTP
smokes could not detect that browser-only enforcement boundary.

The edge now gives only the GlitchTip hostname a narrow `form-action` allowlist
containing itself, Authentik, and retained Keycloak. Every other CSP directive
and every other hostname remains unchanged. The exact merged-main replay passed
both provider assertions, the headless Authentik redirect, and real event
ingestion. A clean Chrome session then reached Authentik's authentication flow,
proving the CSP failure is closed; credentialed session and logout evidence is
recorded separately at the final browser gate.

## 2026-08-29 Outline Authentik cutover preparation

Before changing Outline's selected provider, the preserved Keycloak
`outline.automation` flow minted the missing durable Outline API token. All 12
repo-managed collections and landing pages synchronized and verified through
that token. The cutover therefore does not require migrating the human operator
or creating an unmanaged Authentik automation user.

Repository truth now declares a dedicated Authentik provider/application for
Outline, selects its provider-scoped issuer and confidential client in the
runtime environment, retains the Keycloak client and secret as a separate
rollback boundary, and verifies discovery plus the live `/auth/oidc` redirect
before document synchronization. The `converge-outline` entrypoint also
requires explicit identity and topology selectors before controller preflight.
The Authentik and Outline syntax checks, catalog validators, deployment-selector
preflight, integration contracts, and focused regression suite pass. Live
application remains gated on PR merge and exact-main replay.

## 2026-08-29 Outline API-token permission correction

The final controller pre-apply audit found the newly minted durable Outline
API token readable beyond its owner (`0644`). Its exact local file was
immediately restricted to `0600`; no token value was printed or copied. The
bootstrap writer now creates the token with exclusive `0600` permissions,
refuses symlink/non-regular/empty collisions, and normalizes a valid existing
token to `0600`. The Outline publication role independently requires a regular
owner-only token before using it. Regression coverage verifies both first
creation and existing-token normalization.

## 2026-08-30 Authentik browser-flow compatibility repair

A credentialed GlitchTip browser login proved the Authentik password step, but
the Authentik flow UI then failed before redirecting back to the relying party.
The 2026.5.6 frontend expected a camel-case current-brand flow flag that its
server response supplied in the documented snake-case form. Authentik 2026.8.0
contains the upstream current-brand flag-schema repair and has no additional
upgrade requirements.

The runtime now takes its exact image reference from the managed image catalog,
pins the 2026.8.0 Linux/AMD64 digest, and sets the documented public base URL
for both server and worker. The existing legacy media mount remains unchanged:
the release does not require a data-layout migration, so changing it would add
unnecessary risk to this narrow authentication repair.

The candidate has the same eight unfixed upstream Debian-base critical findings
as the live image, no high/critical finding with an available fix, and materially
fewer high and medium findings. The catalog records a bounded exception through
2026-09-13 with compensating controls and a required upstream re-scan. Fresh
runtime-control host evidence and the scoped Authentik vulnerability gate pass.
The repair PR, CI, and a fresh browser authorization-code session are now
complete. Keycloak remains the retained rollback provider throughout.

## 2026-08-30 Woodpecker pull-request trigger correction

The repair PR initially remained pending because the Woodpecker server excluded
the workflow before scheduling any step. The root workflow used the list form
that is appropriate for a step-level `when`, where list entries are
alternatives. Workflow-level conditions are conjunctive, so the mutually
exclusive event entries prevented every webhook from creating a runnable
workflow.

The root filter now uses one event list. The GitHub integration excluded the
workflow when a branch clause was added, so the branch restriction belongs only
on the secret-validation step. The ordinary validation step therefore runs for
pull requests and branch pushes, while secrets remain unavailable to
pull-request events and non-main pushes. A focused contract test prevents this
CI gate from regressing before the live Authentik application.

## 2026-08-30 Woodpecker agent scheduling recovery

After the workflow filter began creating pipelines, the selected Docker agent
was healthy and label-compatible but administratively paused. The scheduler had
no other `lv3=true` worker, so both the branch and pull-request workflows
remained pending without a test failure. With no task running on that worker,
its scheduling flag was temporarily enabled solely to execute this PR's CI
gate. The prior paused state was restored after both resulting pipeline
outcomes were captured successfully.

## 2026-08-30 Outline compatible-secret recovery

The first governed Outline replay stopped at its local health gate before any
public publication change. The runtime correctly rejected a non-hex
application encryption key that had been generated at the newer unix-prefix
path by the generic secret helper. The established deployment still retained
the original, valid 32-byte hexadecimal key under the deployment's historical
config-prefix path, and the existing database contained live documents and
provider state.

The recovery therefore preserves the historical compatible key instead of
silently replacing it. The runtime role now accepts only a 64-character
lowercase hexadecimal canonical key, restores the valid config-prefix
counterpart when necessary, and generates a new `openssl rand -hex 32` value
only when neither path has a key. An invalid canonical key without a compatible
recovery source is a deliberate fail-closed error, preventing an accidental
encryption-key rotation and loss of access to existing encrypted fields.

## 2026-08-30 Phase 2 completion

The scoped Phase 2 migration is complete. Authentik 2026.8.0 server and worker
health, public readiness, the scoped edge-header audit, GlitchTip's OIDC smoke,
and Outline's managed-collection verification all passed. A newly initiated
operator browser session completed the Authentik authorization-code flow and
reached the protected Outline workspace with no browser-console errors.

No other relying party changed in this workstream. Keycloak discovery remains
healthy and Keycloak is retained as the documented per-client rollback broker.
The later client migration, MFA re-enrolment, and Keycloak retirement decisions
remain explicitly outside this completed scope.

The completion is recorded in the repository's Unreleased changelog until the
repository-wide release gate permits the next version cut. This workstream does
not claim a platform-version bump without a subsequent merged-main replay.

## Rollback model

For each client, preserve the prior Keycloak client settings before mutation.
If the Authentik callback or token exchange fails, restore only that client's
Keycloak configuration, restart only that service, and re-run its login smoke
test. Authentik remains parallel and Keycloak is not removed in this phase.

## Handoff source

The local operational handoff is
`sessions/2026-08-28-authentik-phase2-handoff.md`. It is intentionally outside
the committed workstream because it contains deployment-specific details; the
generic decisions and repeatable procedures belong in ADR 0491 and the service
runbooks.
