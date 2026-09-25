# WS-0495: Authentik direct SMTP recovery delivery

## Goal

Restore operator password-recovery email after the external transactional
provider accepted submissions but later rejected the unverified sender.

## Decision

Use the mail platform's private authenticated Stalwart submission listener.
The Authentik worker already joins the required Docker network and a delivery
check produced a `delivery.delivered` mail-platform event without a rejection.
This keeps SMTP credentials and recovery links private while avoiding sender
validation that the restricted transactional-provider API key cannot manage.

## Verification

1. The Authentik worker resolves and authenticates to the internal Stalwart
   listener over the private Docker network.
2. A recovery delivery generates a mail-platform `delivery.delivered` event
   and no corresponding message-rejection event.
3. Public Authentik readiness and the Outline OIDC discovery document remain
   available after the apply.

## Live status

The governed default was merged in PR #218. The live recovery email stage is
persisted with the same direct Stalwart submission route, and the Authentik
worker resolves, connects to, and authenticates to that route successfully.
The temporary server-side network attachment used only for SMTP testing was
removed; the declared worker-only attachment remains.

The full Ansible converge remains intentionally gated on a separate refresh of
stale generated DNS/SSO artifacts. That broader data-model repair is outside
this recovery workstream. It does not prevent the live recovery stage from
using the verified direct route.
