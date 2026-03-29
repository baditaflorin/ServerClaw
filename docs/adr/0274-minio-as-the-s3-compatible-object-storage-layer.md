# ADR 0274: MinIO As The S3-Compatible Object Storage Layer

- Status: Accepted
- Implementation Status: Not Implemented
- Implemented In Repo Version: N/A
- Implemented In Platform Version: N/A
- Date: 2026-03-29

## Context

The platform holds several services that either already depend on S3-compatible
blob storage or will require it as they mature:

- Loki uses local filesystem today; long-term chunk retention benefits from an
  object backend
- Langfuse exports traces and datasets as file attachments with no durable
  store behind them
- Gitea LFS attachments are stored on the docker-runtime VM's local disk with
  no retention boundary
- RAG context ingestion has no place to stage raw document uploads before
  extraction
- Windmill workflow outputs and build artifact bundles have no off-VM home
- Nextcloud (ADR 0260) can offload file storage to an S3 backend instead of
  using its own internal chunking store

No S3-compatible endpoint exists today. Services that need blob storage
either write to ephemeral local paths or skip durable persistence entirely.

## Decision

We will deploy **MinIO** in standalone mode on the docker-runtime VM as the
S3-compatible object storage layer for the platform.

### Deployment rules

- MinIO runs as a Docker Compose service in its own stack directory
- TLS termination is handled by the NGINX edge for the public-facing console;
  internal access uses the plain HTTP port on the guest network
- Credentials are injected from OpenBao at service start following the
  standard compose secrets pattern (ADR 0077)
- Bucket policies and lifecycle rules are declared in the Ansible role and
  applied idempotently on every converge

### Bucket ownership rules

- each consumer service owns one or more named buckets declared in the
  platform service catalog
- no service may write to another service's bucket without an explicit
  cross-tenant policy entry
- bucket names follow the pattern `<service-id>-<purpose>` (e.g.
  `loki-chunks`, `langfuse-exports`, `gitea-lfs`)

### Consumers wired at launch

- Loki: `loki-chunks` bucket replaces the local filesystem backend
- Langfuse: `langfuse-exports` bucket for trace exports and dataset attachments
- Gitea LFS: `gitea-lfs` bucket replaces the on-disk LFS store
- RAG ingestion staging: `rag-staging` bucket for raw document uploads pending
  Tika extraction (ADR 0275)

## Consequences

**Positive**

- A single durable blob store removes scattered local-disk persistence from
  the services that need it.
- Loki long-term retention becomes configurable without re-architecting the
  monitoring VM storage layout.
- S3-native consumers such as Nextcloud can offload chunked file storage
  without a new protocol.
- The console UI gives operators a point-in-time view of storage consumption
  by bucket across all services.

**Negative / Trade-offs**

- MinIO in standalone mode is not HA; a failure of the docker-runtime VM also
  loses object access until the VM recovers.
- Bucket governance requires discipline: services that write to local paths
  today need an explicit migration step before they consume the S3 backend.

## Boundaries

- MinIO is the object storage layer only; it does not replace Harbor for
  container image distribution or Proxmox Backup Server for VM-level snapshots.
- Block and filesystem volumes for services that need POSIX semantics remain
  on Docker named volumes; only blob workloads migrate to MinIO.
- Database backups are sent to the Proxmox Backup Server (ADR 0086) and are
  not duplicated into MinIO buckets.

## Related ADRs

- ADR 0077: Compose secrets injection pattern
- ADR 0086: Backup and recovery for stateful services
- ADR 0121: Local search and indexing fabric
- ADR 0146: Langfuse for agent observability
- ADR 0198: Qdrant vector search for semantic platform RAG
- ADR 0260: Nextcloud as the canonical personal data plane for ServerClaw
- ADR 0275: Apache Tika Server for document text extraction in the RAG pipeline

## References

- <https://min.io/docs/minio/container/index.html>
