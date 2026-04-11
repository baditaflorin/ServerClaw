# ADR 0024: Docker Guest Security Baseline

- Status: Accepted
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-22

## Context

ADR 0023 defines how the Docker runtime VM gets a supported Docker Engine baseline, but installing Docker is not the same thing as hardening a Docker guest for production use.

Docker has special networking behavior that can bypass naive host firewall expectations, and the current platform still needs an explicit guest-level security contract for:

- published container ports
- package update cadence
- operator access to the Docker socket
- separation between runtime and build guest exceptions

Without that contract, security behavior stays implicit and will drift per host or per compose file.

## Decision

We will handle Docker guest hardening as its own workstream, separate from package installation and separate from workload deployment.

The Docker guest security baseline will require:

1. No remote Docker API listener by default.
   - Docker remains locally managed through the Unix socket
2. Host-level port controls use Docker-aware filtering.
   - when host firewall policy is needed for published ports, rules must be expressed through the Docker-supported path such as `DOCKER-USER`
   - the repository must not rely on `ufw`-style assumptions that Docker can bypass
3. Security updates are automated on Docker guests.
   - Debian security updates and the reboot policy for Docker guests must be codified
4. Privileged local access stays explicit.
   - Docker group membership is granted only to named operator identities that actually need it
5. Runtime and build guests can diverge intentionally.
   - stricter ingress rules may apply to `docker-runtime`
   - more permissive interactive tooling may apply to `docker-build`

## Consequences

- Docker-specific firewall behavior stops being an undocumented trap.
- Guest hardening can evolve without colliding with the Docker package baseline or compose deployment work.
- Runtime and build hosts can be hardened differently without losing the shared high-level policy.

## Sources

- <https://docs.docker.com/engine/install/debian/>
- <https://docs.docker.com/engine/network/packet-filtering-firewalls/>
