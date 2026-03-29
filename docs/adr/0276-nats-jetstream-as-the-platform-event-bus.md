# ADR 0276: NATS JetStream As The Platform Event Bus

- Status: Accepted
- Implementation Status: Not Implemented
- Implemented In Repo Version: N/A
- Implemented In Platform Version: N/A
- Date: 2026-03-29

## Context

The platform has several workflow and integration layers:

- Windmill executes scheduled and triggered workflows
- n8n connects external services and wires integration flows
- Temporal (ADR 0258) will provide durable session orchestration

None of these provide a lightweight, durable publish-subscribe bus for
service-to-service events within the platform itself. When one service needs
to signal another, the options today are:

- a direct HTTP call (tight coupling, no durability, no replay)
- writing a record to PostgreSQL and polling (latent, noisy, schema coupling)
- creating a Windmill or n8n trigger (heavyweight for internal signalling)

Several patterns that are already partially implemented would benefit from a
proper event bus:

- RAG ingestion events when new documents are staged to MinIO (ADR 0274)
- Mutation audit events from the mutation ledger (ADR 0115)
- Secret rotation completion events consumed by dependent services
- ServerClaw session lifecycle events shared between orchestration layers

NATS with JetStream is a CPU-only, single-binary event streaming server with
sub-millisecond latency, durable log-based consumers, and a footprint under
30 MB of RAM at idle.

## Decision

We will deploy **NATS with JetStream enabled** as the platform event bus.

### Deployment rules

- NATS runs as a Docker Compose service on the docker-runtime VM
- A single standalone NATS server is sufficient; clustering is deferred until
  the host topology supports it
- TLS client credentials are issued by Step-CA for any service that connects
  to NATS
- The management UI (NATS Surveyor or natsboard) is internal-only; no public
  subdomain is issued

### Stream and subject conventions

- stream names follow the pattern `<domain>.<entity>` (e.g. `platform.mutation`,
  `rag.document`, `secret.rotation`)
- producers publish to fully-qualified subjects; consumers use durable named
  subscriptions
- all JetStream streams declare an explicit retention policy and max-age limit
  in the Ansible role

### Producer ownership rule

- each subject has exactly one authoritative producer; fan-in is not
  permitted without an explicit broker subject
- producers must not rely on NATS for durable state; NATS carries events and
  signals, not records of truth

### Consumers at launch

- RAG ingestion pipeline: subscribe to `rag.document.staged` to trigger
  Tika extraction (ADR 0275)
- Mutation ledger: publish `platform.mutation.recorded` after each committed
  entry (ADR 0115)
- Secret rotation: publish `secret.rotation.completed` after a successful
  rotation cycle so dependent services can reload credentials

## Consequences

**Positive**

- Internal service coordination moves from polling or tight HTTP coupling to
  durable, decoupled events.
- NATS JetStream retains messages until acknowledged, so a transient consumer
  failure does not drop events.
- The single binary with no external dependencies is trivial to operate,
  monitor, and restart.
- Windmill and n8n can subscribe to NATS subjects as an event trigger source
  without becoming the coupling point themselves.

**Negative / Trade-offs**

- Adding a bus introduces a new reliability dependency; a NATS failure blocks
  every service that depends on event delivery.
- Producers must be disciplined about not using NATS as a database; event
  replay covers transient outages, not long-term data recovery.

## Boundaries

- NATS replaces polling and direct HTTP for internal platform events only; it
  does not replace n8n for external integration flows.
- NATS is not a job queue; Windmill and Temporal continue to own durable task
  execution.
- NATS does not replace the mutation audit PostgreSQL record; it carries the
  signal that a mutation occurred, not the mutation content.

## Related ADRs

- ADR 0115: Mutation audit ledger
- ADR 0151: n8n as the external app connector fabric
- ADR 0206: Ports and adapters for external integrations
- ADR 0258: Temporal as the durable ServerClaw session orchestrator
- ADR 0274: MinIO as the S3-compatible object storage layer
- ADR 0275: Apache Tika Server for document text extraction in the RAG pipeline

## References

- <https://docs.nats.io/nats-concepts/jetstream>
