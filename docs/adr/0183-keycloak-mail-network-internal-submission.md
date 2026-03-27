# ADR 0183: Keycloak Uses Shared-Mail-Network Internal Submission

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: 2026-03-27
- Date: 2026-03-27

## Context

Keycloak password-reset and required-action mail originally used the Docker-runtime host address `10.10.10.20:1587` with STARTTLS disabled.

Live testing on 2026-03-27 showed that this host-published path is unreliable from inside the Keycloak container namespace:

- the relay accepted and authenticated from the Docker runtime host namespace
- the Keycloak container could open sockets to host-published submission ports but frequently received no SMTP greeting
- switching Keycloak to the public hostname `mail.lv3.org:587` avoided the private hairpin path but still failed because the container resolved `mail.lv3.org` to the public IP `65.108.75.123`, which is another same-host hairpin
- after Keycloak joined the `mail-platform_default` Docker network, it could reach the Stalwart container directly by internal DNS name
- STARTTLS on that direct Docker-hostname path failed certificate validation because the certificate is not issued for `lv3-mail-stalwart`

The durable working path is the internal Stalwart submission listener on the shared Docker network, not any host-published address.

## Decision

Keycloak will:

- join the external Docker network `mail-platform_default`
- use the internal Stalwart hostname `lv3-mail-stalwart`
- send through port `1587`
- keep STARTTLS disabled on that listener

This routes reset mail directly from the Keycloak container to the Stalwart container and avoids both host-port hairpin failures and internal-hostname certificate mismatch.

## Consequences

**Positive**

- Password-reset mail no longer depends on Docker host port publishing from another container network.
- Keycloak uses a repo-managed path that was proven live with an end-to-end reset test.
- The private `1587` listener remains aligned with its original purpose: authenticated plaintext submission for trusted internal consumers.

**Negative / Trade-offs**

- Keycloak now depends on the presence of the external Docker network created by the mail-platform compose project.
- The SMTP host is an internal container DNS name, so this path is specific to the Docker runtime topology and not suitable for non-container clients.

## Boundaries

- This ADR changes the Keycloak SMTP transport path and runtime network attachment only.
- It does not change public client submission on TCP `587`.
- It does not change the Stalwart public certificate strategy.

## Related ADRs

- ADR 0041: Mail platform runtime
- ADR 0056: Keycloak for operator and agent SSO
