# ADR 0290: Redpanda As The Kafka-Compatible Streaming Platform

- Status: Accepted
- Implementation Status: Live applied
- Implemented In Repo Version: 0.177.114
- Implemented In Platform Version: 0.130.75
- Implemented On: 2026-03-31
- Date: 2026-03-29

## Context

NATS JetStream (ADR 0276) serves the platform as a lightweight event bus for
fire-and-forget notifications and pub/sub messaging. It is well-suited for
that workload. However, a distinct class of streaming workload requires
capabilities that JetStream is not designed to provide:

- **durable, ordered, replayable log streams** where consumers can seek to
  any offset and replay history—e.g. a pipeline that reprocesses all
  documents from the last 7 days after a model change
- **multi-consumer fan-out with independent offsets per consumer group**—
  e.g. a search indexer and an audit logger both consuming the same document
  event stream at their own pace
- **stream-native data transformation** using SQL-like semantics (e.g.
  filtering, joining, windowed aggregation over a topic)
- **the Kafka wire protocol** as a lingua franca so off-the-shelf connectors
  (Debezium, Kafka Connect, Faust, Confluent's Python client) work without
  protocol translation

Redpanda is a CPU-only, open-source streaming platform that implements the
Kafka wire protocol exactly, stores data in a C++ log engine without JVM
overhead, and exposes Kafka, HTTP Proxy, Schema Registry, and Admin API
surfaces that fit the platform's private-only service model without needing a
GUI session.

## Decision

We will deploy **Redpanda** as the Kafka-compatible streaming platform for
durable, replayable log streams. NATS JetStream (ADR 0276) continues to serve
lightweight pub/sub and notification workloads.

### Deployment rules

- Redpanda runs as a Docker Compose service on the docker-runtime VM using
  the official `redpandadata/redpanda` image in single-broker mode
- It is internal-only; no public subdomain is issued
- Redpanda listens on:
  - `9092/tcp` — Kafka wire protocol API (producers and consumers)
  - `9644/tcp` — Redpanda Admin REST API (topic and cluster management)
  - `8103/tcp` — Pandaproxy HTTP REST API (produce and consume via HTTP
    for clients that cannot use the Kafka wire protocol)
  - `8104/tcp` — Schema Registry API (Confluent-compatible, for Avro/Protobuf
    schema management)
- Persistent log data is stored on a named Docker volume on fast local
  storage; recovery currently relies on the governed VM-level backup coverage
  for `docker-runtime-lv3` under ADR 0086, while finer-grained Redpanda
  partition snapshot automation remains a follow-on hardening step
- Secrets (SASL credentials for authenticated topics) are stored in OpenBao
  (ADR 0077) and injected at startup

### Reconciliation and API operation rules

- Topics are declared in the Ansible role and reconciled automatically on
  converge; out-of-band topic creation is treated as drift
- The Ansible role declares the canonical topic list (name, partition count,
  replication factor, retention policy) in `defaults/main.yml`; the converge
  path applies that list idempotently with `rpk topic create --if-not-exists`
  plus explicit retention reconciliation on every run
- Consumer group lag and cluster state may be queried through the Admin API
  and `rpk`; no separate Kafka manager GUI is deployed
- The Schema Registry API (`POST /subjects/{subject}/versions`) is used to
  register and evolve Avro schemas; schema registration is part of the
  producer's deployment pipeline, not a manual step
- Fine-grained Schema Registry authorization is out of scope for the initial
  deployment because Redpanda documents Schema Registry authorization as an
  enterprise feature. The baseline relies on private network reachability and
  HTTP basic authentication instead of subject-level ACL reconciliation.

### Topic naming and governance rules

- topics follow the convention `{domain}.{entity}.{event_type}` in
  snake_case (e.g. `documents.page.extracted`, `iam.user.created`)
- all topics have a retention policy declared in the Ansible role; topics
  without an explicit retention entry default to 7-day byte-bounded
  retention
- dead-letter topics follow the convention `{original_topic}.dlq` and are
  declared alongside their parent topic

## Consequences

**Positive**

- Pipelines that need to replay history (e.g. re-index after a model change)
  seek to an offset and consume forward; no separate data snapshot is
  needed.
- Off-the-shelf Kafka ecosystem tools (Debezium CDC, Kafka Streams, Faust,
  any Kafka client library) work without modification because Redpanda
  speaks the Kafka wire protocol exactly.
- The Admin REST API provides a complete management surface with JSON
  responses for readiness and management checks, while the platform can still
  use `rpk` non-interactively for converge-safe topic reconciliation.
- Redpanda's C++ engine has no JVM warm-up overhead; it is ready to serve
  the Kafka API within seconds of container start.

**Negative / Trade-offs**

- Redpanda in single-broker mode has no replication; a broker failure means
  unacknowledged messages are lost. The deployment is appropriate for the
  homelab risk tolerance but not for production environments with strict
  durability requirements.
- The volume must be on fast storage; placing the log data directory on a
  network-backed or spinning-disk volume will cause producer latency spikes.

## Boundaries

- Redpanda handles durable, replayable log streams; NATS JetStream (ADR 0276)
  continues to handle lightweight pub/sub, request/reply, and notification
  workloads. The two systems are not interchangeable; the workload
  characteristics determine which is used.
- Redpanda does not replace MinIO (ADR 0274) for object storage; large binary
  payloads are stored in MinIO and referenced by key in the Redpanda message.
- Kafka Connect is not deployed; source and sink connector logic is
  implemented as Windmill or n8n workflows that call producer/consumer APIs.
- Multi-broker clustering and Tiered Storage are not in scope for the
  initial deployment.

## Related ADRs

- ADR 0077: Compose secrets injection pattern
- ADR 0086: Backup and recovery for stateful services
- ADR 0274: MinIO as the S3-compatible object storage layer
- ADR 0276: NATS JetStream as the platform event bus

## References

- <https://docs.redpanda.com/current/api/admin-api/>
- <https://docs.redpanda.com/current/api/pandaproxy-rest/>
- <https://docs.redpanda.com/current/api/pandaproxy-schema-registry/>
