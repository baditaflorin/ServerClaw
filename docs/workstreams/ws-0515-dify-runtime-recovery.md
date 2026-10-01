# WS-0515: Recover Dify runtime health

## Status

`in_progress` — PR #256 merged the Dify Docker-DNS and ephemeral Squid `/run`
fix, and PR #257 merged refreshed image and host-security evidence. Live
inspection on 2026-09-28 still found a Dify 502, unhealthy NGINX, and the SSRF
proxy restarting, so the repo-managed fix has not yet been applied to
production. A pre-deploy converge stopped before Compose because it ran with a
generic placeholder identity rather than the selected 0mcp overlay; it exposed
a role gap where absent host-side secret files could be regenerated and
mirrored over a valid OpenBao runtime secret set. The current branch adds a
fail-closed seed/check step before secret mirroring. The controller-side Dify
runtime-secret mirrors are not authoritative for a live apply until reconciled
with the current runtime env. The separate controller-side admin password is
preserved only as a fallback when its host copy is missing. No Dify Compose
recreation has been completed yet.

## Scope and decision

Make Dify service discovery resilient to Docker IP changes by configuring the
NGINX Docker DNS resolver and variable-based upstreams for API, web, and plugin
daemon traffic. Give the Squid SSRF proxy an ephemeral `/run` so its PID file
cannot survive container recreation. Keep the change in the Ansible role and
apply it only through the documented `make converge-dify` workflow.

Dify already uses Authentik OIDC through the shared edge. Its gateway-hosted
`/v1/dify-tools` provider is implemented by the API Gateway itself; Dify's UI
and app API are not valid generic OIDC-JWT upstreams. The completeness model
will therefore represent API-gateway applicability explicitly instead of
adding a misleading route or extending an expired suppression. The canonical
service definition lives in `catalog/services/dify/service.yaml`; regenerate
aggregate catalogs with `scripts/service_definition_catalog.py --write`.

## Verification

- Render and validate the Dify Compose and NGINX templates.
- Test the Squid entrypoint and `/run` behavior in an isolated container.
- Run Dify runtime-role and service-completeness regression tests.
- Validate Dify's Authentik client, dashboard, SLO, data entry, and alerts.
- Push the branch through the normal Woodpecker PR/push gates, merge via PR,
  then run the governed Dify converge from fresh `main`.
- Verify the private listener and public `https://agents.example.com/healthz`
  return success after converge, and record the running image/container and
  rollback reference in a live-apply receipt.
- Reconcile only missing host-side Dify secrets from the root-only rendered
  runtime env. Existing host files that disagree must stop the converge before
  any secret can be mirrored back into OpenBao.
- Preserve the controller-side Dify admin password when its host-side copy is
  missing; it is not represented in the runtime env.
- Preserve the existing Dify tools API key separately: it is shared with the
  API Gateway and is not rendered into Dify's runtime env. If its host-side
  source is missing, stop instead of generating a replacement.

## Security evidence and open upgrade

On 2026-09-28, all eight pinned Dify runtime images were scanned from their
currently deployed digests using the repository-pinned Syft and Grype tools.
Seven images have critical findings without fixes available for those pinned
digests and are covered by narrowly scoped exceptions through 2026-10-05; the
SSRF proxy has no critical findings. The Dify API image also contains LiteLLM
1.82.6, affected by [GHSA-r75f-5x8p-qvmc](https://github.com/advisories/GHSA-r75f-5x8p-qvmc),
which is fixed in LiteLLM 1.83.7. These exceptions are a short availability
bridge, not an acceptable long-term image posture. Upgrade Dify from 1.13.3 to
a supported release, back up PostgreSQL, Qdrant, and file storage, validate all
required migrations, then re-scan and smoke-test before the exception expires.

The same date's host scan found three `docker-runtime` Lynis warnings: Debian
deb822 security-mirror detection, a time-recency warning despite NTP being
synchronized, and Huly MongoDB authorization disabled on a network with no
published host ports. The host exception also expires 2026-10-05 and requires a
fresh scan plus a decision on MongoDB authentication or a documented isolation
control.

The local changed-service gate passes for this evidence change:
`python3 scripts/validate_service_completeness.py --changed --validate`.
The broader inventory still has legacy completeness debt; it is not being
waived or changed by this branch.

The pre-push lane catalog now classifies image-scan, SBOM, CVE, and host
security-report receipts as evidence surfaces. This prevents newly added
security evidence from being treated as unknown files and unnecessarily
expanding every receipt-only change into every infrastructure lane.

## Credential recovery safety

The failed controller-side attempt rewrote several ignored `.local/dify` mirror
files, but no production Compose update was reached. Treat those mirrors as
untrusted until a successful runtime-env reconciliation rewrites them. One
Redis health diagnostic also exposed a credential in captured output; rotate
the affected credential through the governed secret-rotation path after the
stack is stable. Do not include secret values in workstream files, receipts, or
logs.

## Live findings

The production NGINX error log targets the former API address while Docker's
embedded DNS resolves `api` to the current container. The Squid logs report a
fresh instance PID file at `/run/squid.pid`; `/run` is not mounted separately
and therefore remains in the container's writable layer. These observations
match the failure modes the role changes are designed to prevent.

Only the Dify NGINX container publishes the private listener; the Dify API,
web, SSRF, plugin daemon, Redis, PostgreSQL, Qdrant, and sandbox containers do
not publish host ports. Unauthenticated console setup requests redirect to the
SSO sign-in path. The live NGINX health and public Dify path remain unverified
after the code change until the governed apply is run.
