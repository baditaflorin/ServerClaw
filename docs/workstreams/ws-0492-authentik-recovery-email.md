# WS-0492: Authentik recovery email

## Goal

Provide a governed, self-service password-recovery path for the platform
operator without disclosing or transporting an existing password.

## Design

- Authentik receives its global SMTP configuration from the existing,
  authenticated internal platform relay. The password stays in the runtime
  secret path and is never written into the flow blueprint or repository.
- The Authentik worker joins the mail platform's external Docker network and
  resolves the relay through its service DNS name. This avoids a host-port
  hairpin connection that can open TCP without presenting the SMTP banner.
- A local Authentik blueprint owns a recovery flow, binds it to the active
  brand, and exposes the recovery link from the default authentication
  identification stage.
- The recovery email is a short-lived, rate-limited link. It returns the user
  to Authentik to choose a new password; no password is sent over email.
- The initial flow verifies control of the configured email address. Operators
  should enrol a second factor after recovery; Keycloak MFA material was not
  migrated into Authentik.

## Verification

1. Rendered Authentik configuration contains the SMTP settings but no exposed
   secret values.
2. The live API reports the recovery flow on both the active brand and default
   login identification stage.
3. Authentik accepts the recovery-email action for the platform operator and
   the mail relay accepts delivery.
4. A clean browser session shows the recovery option and follows a received
   recovery link to the password prompt.

## Current status

The recovery flow, worker-to-relay network attachment, login-stage
correction, and governed recovery-email payload are live. A fresh VM backup
preceded the apply attempts; the live recovery contract, identity
reconciliation, worker SMTP authentication, public readiness, and Outline
OIDC discovery checks pass. Authentik accepted the operator reset-email
request with HTTP 204. The local operator identity file is owner-readable only
before the governed client consumes it; no password or recovery link is stored
in the repository or receipt.
