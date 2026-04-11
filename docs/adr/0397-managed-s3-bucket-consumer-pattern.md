# ADR 0397: Managed S3 Bucket Consumer Pattern

- Status: Proposed
- Date: 2026-04-10
- Related ADRs: 0077, 0274, 0373

## Context

ADR 0274 established MinIO as the shared S3-compatible object storage layer for the platform, with buckets for Langfuse, Gitea, Loki, and RAG context.

Currently, each service that needs S3 access is handled as a special case:
- Some services embed their own MinIO (Outline)
- Some services are registered in `minio_runtime/defaults/main.yml` under `minio_managed_consumers_resolved`
- There is no consistent, declarative pattern for adding new S3 consumers

**The problem:** Services that need S3 access must:
1. Hardcode MinIO endpoints (often internal-only URLs like `http://minio:9000`)
2. Generate their own credentials or use root MinIO credentials
3. Lack a programmatic way to request buckets, access keys, and policies
4. Are tightly coupled to the MinIO implementation details

This creates scaling problems as more services need S3 access and couples services to MinIO internals rather than the platform's S3 contract.

## Decision

We will establish a **Managed S3 Bucket Consumer Pattern** that allows any service to declaratively request:
- One or more named S3 buckets
- Service-specific access credentials (not root)
- Bucket-level policies (read/write/delete permissions)
- Lifecycle rules (optional, for data retention)

### Pattern Overview

**1. Service declares its S3 needs** in `minio_runtime/defaults/main.yml`:

```yaml
# minio_runtime/defaults/main.yml
minio_<service>_bucket_name: "<service>-<purpose>"
minio_<service>_access_key_id: "<service>"
minio_<service>_secret_key_remote_file: "{{ minio_secret_dir }}/<service>-secret.txt"
minio_<service>_secret_key_local_file: "{{ minio_local_artifact_dir }}/<service>-secret.txt"
minio_<service>_policy_name: "<service>-bucket-policy"
minio_<service>_policy_document: |
  {
    "Version": "2012-10-17",
    "Statement": [
      {
        "Effect": "Allow",
        "Principal": {"AWS": "arn:aws:iam::minio:user/<service>"},
        "Action": ["s3:GetObject", "s3:PutObject"],
        "Resource": "arn:aws:s3:::<service>-<purpose>/*"
      }
    ]
  }
```

**2. `minio_runtime` automatically provisions:**
- Bucket creation via `mc mb --ignore-existing`
- Service account user creation
- Policy attachment
- Credential generation and mirroring to controller machine

**3. Service configures S3 access:**
- Reads credentials from controller mirror or OpenBao injection
- Uses the **public MinIO gateway URL** (e.g., `https://s3.example.com`) for browser access
- Uses the **internal MinIO URL** (e.g., `http://docker-runtime:9000`) for service-to-service access

### Naming conventions

- Bucket names: `<service-id>-<purpose>` (e.g., `outline-documents`, `gitea-lfs`)
- Access key IDs: `<service-id>` (e.g., `outline`, `gitea`)
- Policy names: `<service-id>-bucket-policy` (e.g., `outline-bucket-policy`)
- Secret key files (remote): `{{ minio_secret_dir }}/<service-id>-secret.txt`
- Secret key files (local): `{{ minio_local_artifact_dir }}/<service-id>-secret.txt`

### Integration with ADR 0373 (Service Defaults)

Services that use this pattern should also declare their S3 configuration in their own role defaults for referential integrity:

```yaml
# outline_runtime/defaults/main.yml
outline_s3_bucket_name: "{{ minio_outline_bucket_name }}"
outline_s3_access_key_id: "{{ minio_outline_access_key_id }}"
outline_s3_secret_key_local_file: "{{ minio_outline_secret_key_local_file }}"
outline_s3_public_url: "{{ minio_public_base_url }}"  # e.g., https://s3.example.com
outline_s3_internal_url: "{{ minio_private_api_url }}"  # e.g., http://docker-runtime:9000
```

## Implementation Steps

### For `minio_runtime` role:
1. Add service to `minio_managed_consumers_resolved` (already done in existing pattern)
2. Service consumer automatically provisioned when `minio_runtime` converges
3. No special logic needed—existing bucket creation via `mc mb` applies

### For service roles (e.g., `outline_runtime`):
1. Declare S3 needs by referencing `minio_*` variables
2. Remove embedded S3/MinIO services
3. Use credential files from controller mirror or OpenBao injection
4. Configure app to use public MinIO gateway URL for browser access
5. Configure app to use internal MinIO URL for service-to-service API calls

### For public access (browser downloads):
1. NGINX edge exposes MinIO API at public gateway URL (e.g., `s3.example.com`)
2. Routes to internal MinIO at `docker-runtime:9000`
3. TLS termination at edge (ADR 0186)

## Consequences

**Positive:**
- Single declarative pattern for all S3 consumers
- No more embedded MinIO or hardcoded internal URLs in services
- Services get their own credentials (least-privilege principle)
- Policies are version-controlled and auditable
- Scaling pattern for adding new services with S3 needs
- Lifecycle rules become configurable (data retention, archival, deletion)

**Negative:**
- Services no longer control their own S3 implementation
- Dependency on MinIO uptime (single point of failure until HA is added)
- Requires coordination: service role must reference minio_runtime variables

## Boundaries

- This pattern applies only to S3-compatible object storage via MinIO
- Database backups continue to use Proxmox Backup Server (ADR 0086)
- Volume storage for POSIX-needing services remains on Docker named volumes
- Container image distribution remains through Harbor

## Related ADRs

- ADR 0077: Compose secrets injection pattern
- ADR 0186: NGINX as reverse proxy and TLS terminator
- ADR 0274: MinIO as the S3-compatible object storage layer
- ADR 0373: Unified service defaults pattern

## References

- MinIO Client docs: <https://min.io/docs/minio/linux/reference/minio-mc.html>
- MinIO bucket policies: <https://min.io/docs/minio/linux/administration/identity-access-management/policy-based-access-control.html>
