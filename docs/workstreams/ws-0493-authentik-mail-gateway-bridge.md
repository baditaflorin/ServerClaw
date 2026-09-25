# WS-0493: Authentik mail-gateway SMTP bridge

## Goal

Deliver Authentik transactional and recovery email through the platform's
existing managed delivery gateway when direct SMTP egress is unavailable.

## Design

- Authentik remains an SMTP client; no credential or recovery token is copied
  into repository configuration or an HTTP client integration.
- A private SMTP compatibility listener runs alongside the mail gateway on the
  existing internal Docker network. It requires the existing scoped platform
  submission credentials and is not published on the runtime host.
- The listener validates the authenticated sender, extracts only the text and
  HTML alternatives needed for delivery, and submits them through the gateway's
  established Brevo API path.
- A submission succeeds only when Brevo accepts it. Provider failures are
  returned to Authentik as temporary SMTP failures so it can retry safely.
- Stalwart remains the platform mail server for inbound mail, mailbox
  management, and direct-delivery use cases. The bridge is a compatibility
  adapter for consumers that require SMTP while transactional egress is
  gateway-owned.

## Verification

1. The SMTP bridge requires authentication and is reachable only over the
   private mail-platform Docker network.
2. A test message sent through the bridge reaches the gateway provider client
   without exposing recipient, body, token, or credential values in logs.
3. Authentik worker SMTP authentication succeeds against the bridge.
4. A fresh Authentik recovery request is accepted by the provider and the
   public recovery flow remains healthy.

## Live completion

The merged bridge was applied through the governed mail-platform and
Authentik converges. The managed provider credential was validated without
recording it, both gateway processes authenticated successfully, and the
Authentik worker completed a fresh recovery-email task. The bridge recorded
provider acceptance for that delivery. Public Authentik readiness and Outline
OIDC discovery also remained healthy. The governed apply completed its
mandatory backup coverage check with all protected sources covered.
