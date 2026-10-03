# Authentik runtime upgrade to 2026.8.3

## Purpose

Upgrade the production Authentik runtime to the latest stable release reviewed
for this change, while preserving an immediate rollback path and recording the
operator-approved, time-limited security exception.

## Security decision

The operator explicitly accepted both the 3 Critical and 84 High findings in
the fresh Grype scan for seven days, through 2026-10-08. The pinned Linux/AMD64
image is:

`ghcr.io/goauthentik/server:2026.8.3@sha256:09782fe56675bc616a0324468f1698e2d9d83c978bc5e426686fb7563517a442`

The scan reported zero HIGH/CRITICAL findings with a known fix. The immutable
digest and the Syft, Grype, and SBOM receipts are committed in the image
catalog. Re-scan before the exception expires. If no image meets the normal
budget by then, roll back or obtain a new explicit decision; do not silently
extend the exception.

## Repository and production status

PR 261 merged the image pin, recovery-mail route correction, and security
evidence. PR 262 merged repository version 0.179.48 at
`bdef401acf729cd76e529d63314ac4a8cdb12c38`. That exact merged-main release was
applied to production VM192 and verified. The previous isolated restore
rehearsal recovered PostgreSQL but did not reach Authentik web readiness, so
this workstream does not claim verified PBS disaster recovery.

PR 263 merged the Authentik runtime and post-apply evidence at
`7063709d1ac1d9ca693043c63772dd045955e030`. This closeout fixes branch
ownership validation to resolve workstreams from both active and archived
shards, because the generated compatibility registry intentionally omits
archived entries. Regression coverage verifies the archive transition and
continues to reject edits outside the branch's declared surfaces.

The guarded rollout used a short-lived VM disk snapshot immediately before the
apply. After all post-upgrade checks passed, the named snapshot was removed.
Retain the PBS restore finding until a full restore rehearsal reaches Authentik
readiness.

## Rollout and verification

1. Validate release metadata and the Authentik vulnerability-budget gate.
2. Confirm VM192 storage capacity and snapshot state; create a named pre-upgrade
   snapshot immediately before applying.
3. Run the normal production `live-apply-service` target using the selected
   deployment identity and topology. Do not bypass any gate.
4. Verify both server and worker use the approved digest and become healthy;
   confirm the public readiness endpoint and login/recovery-mail behavior.
5. Run representative Gitea and Harbor browser login checks and record the
   remaining Outline, Grafana, GlitchTip, and Chat findings without claiming
   full consumer completion.
6. Keep the rollback snapshot until these checks pass. Then remove it through
   the documented Proxmox snapshot lifecycle and record the live-apply receipt.

## Current state

- Image catalog, scan receipts, and exception merged through PR 261. The
  operator explicitly accepted both **3 Critical and 84 High** findings through
  2026-10-08; the scan reported zero High/Critical findings with a known fix.
- PR 262 merged repository version 0.179.48. Authentik server and worker are
  running `ghcr.io/goauthentik/server:2026.8.3` at digest
  `sha256:09782fe56675bc616a0324468f1698e2d9d83c978bc5e426686fb7563517a442`
  and healthy; `https://id.example.org/-/health/ready/` returned HTTP 200.
- Strict-TLS fresh-browser login checks passed for Gitea and Harbor with the
  non-admin `gitea-e2e` test identity. Authentik recovery mail was accepted and
  independently verified delivered to Gmail; no reset link is recorded here.
- The corrected two Brevo DKIM CNAME records are authoritative and resolve via
  three public resolvers. Brevo reports the domain and DKIM records authenticated;
  SPF, MX, and DMARC were not changed. The follow-up recovery-flow check passed.
- The pre-upgrade VM snapshot was removed after verification. This is not a
  claim of completed PBS disaster-recovery rehearsal. Outline, Grafana,
  GlitchTip, and Chat remain outside this verification scope.
- Outline, Grafana, GlitchTip, and Chat are intentionally deferred, not
  implicitly migrated. If retained, each needs its own integration contract,
  scoped change, and end-to-end test before Keycloak retirement is claimed for
  that consumer.
- Platform version is advanced to 0.178.225 to record this merged-main live
  apply. Re-scan before the exception expires on 2026-10-08; do not extend the
  exception without a new explicit decision.
