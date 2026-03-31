# ADR 0255: Matrix Synapse As The Canonical ServerClaw Conversation Hub

- Status: Accepted
- Implementation Status: Live on production from main
- Implemented In Repo Version: 0.177.85
- Implemented In Platform Version: 0.130.58
- Implemented On: 2026-03-29
- Date: 2026-03-28

## Context

OpenClaw-style assistants are messaging-first. The current repository already
has Mattermost for operator collaboration, but Mattermost alone is not a
general-purpose chat hub for:

- direct assistant conversations
- room-based multi-user interaction
- normalized events across multiple external chat networks
- durable bridge adapters with one shared identity and audit model

Building custom bot logic for every network directly into the assistant core
would create a fragile adapter sprawl.

## Decision

We will use **Matrix Synapse** as the canonical conversation hub for
ServerClaw.

### Role of Matrix

- Matrix is the normalized message transport seen by the ServerClaw runtime.
- one-to-one conversations, rooms, and assistant threads map into Matrix
  rooms or direct-message spaces
- external networks are translated into Matrix events before the assistant
  runtime consumes them
- operator backchannels and user-facing assistant channels can share the same
  transport model while remaining identity-separated

### Product boundary

- Mattermost remains an operator collaboration product.
- Matrix becomes the canonical user-and-agent conversation backbone.

## Consequences

**Positive**

- ServerClaw gets an open, self-hosted, multi-client conversation layer.
- Future channel adapters can terminate into one normalized event model.
- Conversation history and room identity become easier to reason about than a
  collection of network-specific bot payloads.

**Negative / Trade-offs**

- Matrix introduces another stateful service that must be secured, recovered,
  and monitored.
- Operators must govern federation, media retention, and bridge isolation
  carefully.

## Boundaries

- This ADR chooses the canonical conversation hub, not every end-user client.
- This ADR does not require Matrix federation to the public internet.
- Matrix is the message backbone; it is not the place where assistant policy or
  business logic should live.

## Related ADRs

- ADR 0056: Keycloak for operator and agent SSO
- ADR 0206: Ports and adapters for external integrations
- ADR 0254: ServerClaw as a distinct self-hosted agent product on LV3

## References

- <https://matrix-org.github.io/synapse/latest/>
- <https://spec.matrix.org/latest/application-service-api/>
