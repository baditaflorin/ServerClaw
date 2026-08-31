# ADR 0491 Authentik Phase 3–4: client migration and Keycloak retirement

## Goal

Finish the approved Authentik migration by moving every active authentication
path away from Keycloak, validating the replacement end to end, and retiring
the Keycloak runtime only after a reversible backup and clean dependency audit.

## Scope

- The shared edge `oauth2-proxy` client that protects every `auth_proxy: true`
  service.
- Native OIDC consumers: Gitea, Grafana, Harbor, API gateway, Plane, and
  Semaphore where deployed.
- Named operator and platform-admin Authentik identities, platform groups, and
  operator browser verification.
- The ServerClaw runtime client after its consuming runtime is verified.
- Keycloak runtime, edge route, health probes, dependency contracts, and
  obsolete automation after every client has passed verification.

## Explicit exclusions

- Never-deployed historical Keycloak clients are not recreated. Their secrets
  are retained only as cold rollback evidence until the retention window ends.
- Password hashes and a physical MFA device are not copied between identity
  providers. The current operator credential is used only through the ignored
  local credential path, and the new provider exposes the supported MFA
  enrollment flow for the operator to complete on a trusted device.

## Guardrails

1. Authentik remains the only provider changed first; each consumer is
   converged and verified before its Keycloak configuration is removed.
2. Every confidential secret is created or reconciled in `.local/` and never
   rendered into committed files or command output.
3. A Keycloak data and configuration backup is captured before shutdown and is
   recorded in the live-apply receipt without including credential material.
4. Keycloak is not stopped until repository checks, public health checks,
   confidential-client smoke tests, and a credentialed operator browser flow
   all pass against Authentik.

## Migration order

1. Reconcile Authentik clients, groups, and operator identities.
2. Move service-to-service bearer-token validation and native clients.
3. Move the shared edge proxy and verify each protected public surface.
4. Validate ServerClaw runtime integration and all remaining client metadata.
5. Archive then decommission Keycloak; run the no-Keycloak dependency audit.

## Completion record

The production cutover completed on 2026-08-31. Authentik client and identity
reconciliation completed without creating duplicate objects; the shared edge,
native OIDC consumers, and API bearer-token validation now use Authentik.
Credentialed operator and protected-surface checks passed, as did Grafana and
GlitchTip-specific OAuth/OIDC smoke checks.

The former Keycloak compose definitions were archived on both runtime hosts
before the stacks were stopped. The archive and runtime data were deliberately
retained for the governed rollback window; no active container, edge route,
health probe, or dependency contract remains. The detailed, non-secret live
evidence is recorded in
`receipts/live-applies/adr-0491-authentik-keycloak-sunset-2026-08-30-apply-receipt.json`.

Repository integration is prepared for version `0.179.46`; the platform version
remains unchanged until the merged automation has been converged from `main`.
