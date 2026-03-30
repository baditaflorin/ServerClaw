# ADR 0256: Mautrix Bridges For External Chat Channel Adapters

- Status: Accepted
- Implementation Status: Live-applied on the workstream branch; exact-main replay pending
- Implemented In Repo Version: N/A
- Implemented In Platform Version: N/A
- Implemented On: 2026-03-30
- Date: 2026-03-28

## Context

Once Matrix is the canonical conversation hub, ServerClaw still needs practical
ways to reach the networks people actually use. Re-implementing adapters inside
the assistant runtime would make the product core depend on:

- proprietary network payloads
- network-specific auth quirks
- custom event translation per chat provider

Matrix already has a mature application-service bridge model. The missing
decision is which bridge family ServerClaw should standardize on.

## Decision

We will use **mautrix** bridges as the default external chat-channel adapters
for ServerClaw.

### Adapter rule

- external networks terminate into a mautrix bridge
- the bridge maps network-specific events into Matrix rooms and user identities
- the ServerClaw runtime consumes the normalized Matrix stream, not the
  proprietary network directly

### Rollout rule

- start with the most mature bridges such as Telegram, WhatsApp, and Discord
- add additional networks only after the bridge quality, auth model, and
  moderation implications are reviewed

## Consequences

**Positive**

- Channel support grows by adding adapters rather than rewriting the assistant
  core.
- Matrix remains the one internal conversation model even when multiple user
  networks are active.
- Bridge health, secrets, and permissions can be governed as separate runtime
  surfaces.

**Negative / Trade-offs**

- Each bridge carries its own operational and compliance risk.
- Some networks will always be less stable because their upstream APIs are
  closed or hostile to automation.

## Boundaries

- This ADR does not promise support for every chat network.
- Bridges are adapters, not the source of truth for identity, memory, or
  policy.
- Unsupported or high-risk networks may remain intentionally out of scope.

## Related ADRs

- ADR 0206: Ports and adapters for external integrations
- ADR 0255: Matrix Synapse as the canonical ServerClaw conversation hub

## References

- <https://docs.mau.fi/>
- <https://spec.matrix.org/latest/application-service-api/>
