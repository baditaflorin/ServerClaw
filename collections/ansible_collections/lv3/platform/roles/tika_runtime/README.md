# tika_runtime

## Purpose

Converge the private Apache Tika Server runtime on `docker-runtime-lv3` so the
RAG and document-ingestion pipelines can extract clean text and metadata from
binary documents before embedding.

## Use Case

Run this role during Tika deployment, upgrade, or recovery when the canonical
document-extraction service on the private guest network must match repo truth.

## Inputs

- `tika_runtime_site_dir`: runtime directory that stores the Compose stack
- `tika_runtime_compose_file`: rendered Compose file path
- `tika_runtime_image`: digest-pinned Apache Tika image reference
- `tika_runtime_container_name`: deterministic container name
- `tika_runtime_port`: guest-network listener port
- `tika_runtime_base_url`: canonical internal base URL used for verification
- `tika_runtime_java_opts`: bounded JVM heap and startup options

## Outputs

- `/opt/tika/docker-compose.yml` on `docker-runtime-lv3`
- a running `tika` container listening on the internal guest network
- verified `/version`, `/tika`, and `/meta` behavior on the live runtime

## Idempotency

Fully idempotent. Re-running the role re-renders the Compose file, refreshes the
image, and reconciles the container to the declared configuration.

## Dependencies

- ADR 0198: Qdrant vector search for semantic platform RAG
- ADR 0263: ServerClaw memory substrate
- ADR 0274: MinIO staging bucket for document provenance
- ADR 0275: Apache Tika extraction service decision
- Role: `docker_runtime` - ensures Docker is available on the guest
- Role: `linux_guest_firewall` - enforces the private network boundary
