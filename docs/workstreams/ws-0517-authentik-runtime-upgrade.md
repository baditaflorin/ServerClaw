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
evidence. At the time of that merge, production still ran Authentik 2026.8.0
and its public readiness endpoint returned HTTP 200. The previous isolated
restore rehearsal recovered PostgreSQL but did not reach Authentik web
readiness, so this workstream does not claim verified PBS disaster recovery.

The guarded rollout uses a short-lived VM disk snapshot immediately before the
apply. That snapshot is an immediate rollback aid only; retain the PBS restore
finding until a full restore rehearsal reaches Authentik readiness.

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

- Image catalog, scan receipts, and exception merged through PR 261.
- Repository release metadata is being prepared under PR review.
- Production apply and post-upgrade verification are pending.
- Exception expiry: 2026-10-08.
