# ADR 0282: Mailpit As The SMTP Development Mail Interceptor

- Status: Accepted
- Implementation Status: Not Implemented
- Implemented In Repo Version: N/A
- Implemented In Platform Version: N/A
- Date: 2026-03-29

## Context

The platform runs **Stalwart Mail** (ADR 0130) as the production mail server
for transactional email delivery. Every service that sends email in production
points at Stalwart.

There is no equivalent facility for development and non-production contexts:

- Gitea Actions pipelines that test notification flows send real email or
  skip the test entirely
- Windmill and n8n script authors cannot verify email rendering without
  sending to a real address
- Bootstrap scripts that create initial Keycloak accounts send real
  welcome emails during every `molecule` or staging converge
- Testing the mail-gateway notification profile logic (ADR 0130) requires a
  live SMTP endpoint that captures and exposes the delivered MIME message for
  inspection

The absence of a local SMTP catcher means either real email is sent from
non-production runs (noisy, leaking test data externally) or outbound SMTP is
disabled in test contexts (hiding a class of integration bugs).

Mailpit is a CPU-only, single-binary SMTP interception server. It accepts
SMTP connections on a configurable port, stores messages in memory or a local
database, and exposes them through a web UI and a REST API. It has zero
external dependencies and a ~10 MB binary footprint.

## Decision

We will deploy **Mailpit** as the SMTP development mail interceptor, available
to non-production converge contexts and pipeline test environments.

### Deployment rules

- Mailpit runs as a Docker Compose service on the docker-runtime VM under a
  `dev-tools` stack alongside other development utilities
- It listens on an internal SMTP port on the guest network only; it is not
  exposed at the NGINX edge and has no public subdomain
- The web UI is accessible on the guest network and via the Headscale mesh
  for operator inspection
- Mailpit is stateless by default (in-memory storage); messages are lost on
  restart, which is the desired behaviour for a development interceptor
- No secrets are required; the SMTP port accepts unauthenticated connections
  from the guest network

### Usage contract

- services in Ansible `molecule` and staging converge contexts point their
  SMTP relay at the Mailpit SMTP port instead of Stalwart
- this is enforced by a host variable (`smtp_host: mailpit`) that overrides
  the production default in non-production inventory groups
- Gitea Actions workflows that exercise notification paths include a step that
  reads the Mailpit REST API to assert expected messages were delivered
- the mail-gateway verification playbook (`mail-platform-verify.yml`) uses
  Mailpit as the assertion target in staging runs

### What is not intercepted

- production services always point at Stalwart; Mailpit is never wired into
  a production inventory group

## Consequences

**Positive**

- Non-production runs no longer leak test messages to real email addresses.
- Pipeline jobs can assert on email content (subject, recipient, body, MIME
  structure) through the Mailpit REST API without custom mock layers.
- Developers can visually inspect rendered HTML email in the Mailpit web UI
  without a mail client setup.
- The zero-dependency binary makes it trivial to start and stop alongside
  other dev-tools compose services.

**Negative / Trade-offs**

- Mailpit's in-memory storage means messages are not retained across service
  restarts; long-running pipeline jobs that restart Mailpit mid-test would
  lose earlier messages.
- The SMTP port on the guest network is unauthenticated; this is acceptable
  for a development interceptor inside the trusted guest network but must not
  be exposed externally.

## Boundaries

- Mailpit is a development and test facility only; it must never be configured
  as the SMTP relay in a production inventory group.
- Mailpit does not replace Stalwart for any production transactional or
  operator alert email.
- Mailpit is not used for load testing email volume; it is suited to
  assertion-level message volumes in pipelines.

## Related ADRs

- ADR 0077: Compose secrets injection pattern
- ADR 0130: Mail platform for transactional email
- ADR 0185: Branch-scoped preview environments

## References

- <https://mailpit.axllent.org/docs/>
