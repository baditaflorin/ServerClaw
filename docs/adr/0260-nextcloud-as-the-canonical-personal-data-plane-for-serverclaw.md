# ADR 0260: Nextcloud As The Canonical Personal Data Plane For ServerClaw

- Status: Accepted
- Implementation Status: Not Implemented
- Implemented In Repo Version: N/A
- Implemented In Platform Version: N/A
- Date: 2026-03-28

## Context

ServerClaw needs a durable, user-owned place for personal data such as:

- files and attachments
- calendars
- contacts
- tasks and notes
- agent-generated drafts that should stay under user control

Storing those artifacts only inside vendor connectors or only inside assistant
runtime databases would make portability, privacy, and user ownership weaker.

## Decision

We will use **Nextcloud** as the canonical personal data plane for ServerClaw.

### Data-plane rule

- files and attachments should prefer WebDAV-backed storage in Nextcloud
- calendars and tasks should prefer CalDAV-backed storage
- contacts should prefer CardDAV-backed storage
- user-facing drafts, notes, or assistant-produced documents should prefer
  user-owned Nextcloud locations when durable retention is desired

### Integration rule

- ServerClaw reaches Nextcloud through standard protocols and typed ports
- n8n may sync external systems into or out of Nextcloud where that reduces
  vendor lock-in

## Consequences

**Positive**

- Users get a self-hosted personal-data home instead of a pile of connector-side
  fragments.
- Standard protocols reduce coupling between the assistant runtime and one
  product-specific API shape.
- Personal data can be retained, exported, and governed separately from traces
  or control-plane metadata.

**Negative / Trade-offs**

- Nextcloud adds another important stateful service to secure and recover.
- Some external services will still need direct connectors when their data does
  not map cleanly into files, DAV objects, or notes.

## Boundaries

- Nextcloud is not the canonical store for build artifacts, release bundles, or
  repo source code.
- This ADR does not require every personal datum to be mirrored into Nextcloud,
  but it makes Nextcloud the default durable home when the product controls the
  storage choice.

## Related ADRs

- ADR 0206: Ports and adapters for external integrations
- ADR 0259: n8n as the external app connector fabric for ServerClaw

## References

- <https://docs.nextcloud.com/server/latest/admin_manual/>
