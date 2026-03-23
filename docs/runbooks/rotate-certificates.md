# Rotate Certificates

This runbook documents the current manual fallback for certificate rotation until automated lifecycle management is fully implemented.

## Scope

- public edge certificates served by `nginx-lv3`
- internal service certificates issued through step-ca
- controller-side trust material that must stay aligned with rotated certificates

## Procedure

1. Identify the affected hostname or service and the owning ADR or runbook.
2. Confirm whether the certificate is managed by Let’s Encrypt on the public edge or by step-ca internally.
3. Rebuild or reissue the certificate through the repo-managed workflow where one exists.
4. Re-run the relevant convergence workflow so the certificate, key path, and trust bundle stay consistent.
5. Verify the endpoint with an explicit TLS check and the service health probe.
6. Record the rotation event if the change was applied live.

## Related runbooks

- [Configure edge publication](configure-edge-publication.md)
- [Configure step-ca](configure-step-ca.md)
- [Secret rotation and lifecycle](secret-rotation-and-lifecycle.md)
