# ADR 0047: Short-Lived Credentials And Internal mTLS

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-22

## Context

Long-lived SSH keys, API tokens, and shared passwords age badly in an agentic environment. They are hard to rotate, easy to copy, and difficult to scope cleanly.

The platform already has private networking, but private networking alone does not replace credential discipline.

## Decision

We will prefer short-lived credentials and mutual TLS for new internal access paths.

Default expectations:

- human interactive SSH certificates: hours, not days
- agent SSH or API credentials: as short as the workflow can tolerate
- service-to-service certificates: automatically renewed and time-bounded
- long-lived static secrets: exception path only, with an explicit reason

Issuer boundaries:

- `step-ca` is the default issuer for SSH and internal X.509 certificates
- OpenBao is the default authority for API tokens, wrapped secrets, and cryptographic material

Internal APIs that cross trust boundaries should prefer:

1. HTTPS
2. server authentication
3. client authentication when the caller is another service or agent
4. narrow authorization after authentication

## Consequences

- Credential theft becomes less useful because stolen material expires quickly.
- Internal services can stop relying on broad, reusable bearer tokens where mTLS is a better fit.
- The platform needs renewal paths, certificate distribution, and failure monitoring as first-class operations.

