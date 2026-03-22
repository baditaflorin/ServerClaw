# ADR 0047: Short-Lived Credentials And Internal mTLS

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.49.0
- Implemented In Platform Version: 0.25.0
- Implemented On: 2026-03-22
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

## Implementation Notes

- Short-lived human SSH certificates are now issued by `step-ca` and accepted on the Proxmox host and managed guests, with controller-side verification using an eight-hour `ops` certificate through the Tailscale host path and the Proxmox jump path.
- OpenBao AppRole artifacts now use short-lived secret IDs that are refreshed on each converge and after end-to-end verification, reducing reuse of long-lived machine bootstrap credentials.
- The external OpenBao API now presents a `step-ca`-issued server certificate on `https://100.118.189.95:8200` and requires client certificates signed by the same CA, while retaining a loopback-only HTTP listener on `127.0.0.1:8201` for managed bootstrap and verification traffic.
- Operator procedures are documented in [docs/runbooks/configure-step-ca.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/configure-step-ca.md) and [docs/runbooks/configure-openbao.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/configure-openbao.md).
