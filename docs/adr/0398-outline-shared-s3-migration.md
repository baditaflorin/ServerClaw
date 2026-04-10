# ADR 0398: Outline Shared S3 Migration

- Status: Proposed
- Date: 2026-04-10
- Related ADRs: 0199, 0274, 0373, 0397
- Fixes: wiki.lv3.org not loading (S3 asset access broken)

## Context

Outline (wiki service, ADR 0199) was deployed with an **embedded MinIO sidecar** in its Docker Compose stack. This architecture has caused a critical issue:

**The Problem:**
- Outline hardcodes `AWS_S3_UPLOAD_BUCKET_URL="http://minio:9000"`
- This refers to the internal MinIO service inside Outline's compose network
- The hostname `minio:9000` is only resolvable within the container network
- **Browsers cannot access this URL**, so asset loading fails
- The entire Outline React app fails to render because static assets cannot download

This is a class of problem that affects any embedded S3 service: internal-only hostnames cannot be accessed from outside the container network.

## Decision

Outline will migrate from embedded MinIO to the **shared platform MinIO** (ADR 0274) using the **Managed S3 Bucket Consumer Pattern** (ADR 0397).

### Migration scope

**Remove:**
- Embedded MinIO service from `outline_runtime/docker-compose.yml.j2`
- MinIO directory creation and secret generation from `outline_runtime/tasks/main.yml`
- All `outline_minio_*` variables from `outline_runtime/defaults/main.yml`

**Add to `minio_runtime/defaults/main.yml`:**
- `minio_outline_bucket_name: "outline-documents"`
- `minio_outline_access_key_id: "outline"`
- `minio_outline_secret_key_remote_file`, `secret_key_local_file`
- `minio_outline_policy_document` (read/write to `outline-documents` bucket)

**Update in `outline_runtime`:**
- Reference shared MinIO credentials from controller mirror
- Use public gateway URL: `https://s3.lv3.org` for browser S3 access
- Use internal URL: `http://docker-runtime:9000` for service-to-service API calls

**Add to `public_edge` or nginx role:**
- MinIO API gateway at `s3.lv3.org` → `http://docker-runtime:9000`

### Architecture After Migration

```
Browser                 Public Internet
  │
  ├─ wiki.lv3.org ──────→ NGINX Edge (TLS)
  │                          │
  │                          ├─ proxy → runtime-control (Outline)
  │                          │
  │                    + S3 gateway
  │                          │
  └─ s3.lv3.org ────────────→ MinIO (docker-runtime:9000)

Outline Container      Internal Docker Network
  │
  ├─ PostgreSQL ──────→ postgres-vm
  │
  ├─ Redis ──────────→ local redis sidecar
  │
  └─ S3 requests ────→ MinIO (docker-runtime:9000) [shared instance]
```

## Implementation Plan

### Phase 1: Register Outline with Shared MinIO
**File:** `minio_runtime/defaults/main.yml`
- Add Outline to managed consumers
- Define bucket name, access key, policy document

**Outcome:** When `minio_runtime` converges:
- `outline-documents` bucket created
- Service account `outline` created
- Access policy attached
- Secrets mirrored to controller machine

### Phase 2: Update Outline Role
**Files:**
- `outline_runtime/defaults/main.yml` - Reference shared MinIO vars
- `outline_runtime/docker-compose.yml.j2` - Remove minio service, keep redis
- `outline_runtime/tasks/main.yml` - Remove minio setup tasks
- `outline_runtime/templates/outline.env.j2` - Update S3 env vars

**Changes:**
- Remove embedded MinIO from compose
- Remove MinIO secret generation
- Add dependency on `minio_runtime` convergence
- Update env vars:
  - `AWS_S3_UPLOAD_BUCKET_URL: {{ minio_public_base_url }}` (e.g., `https://s3.lv3.org`)
  - `AWS_SECRET_ACCESS_KEY: {{ minio_outline_secret }}` (from controller mirror)
  - `AWS_ACCESS_KEY_ID: outline` (service account ID)

### Phase 3: Configure Public S3 Gateway
**File:** `public_edge` or `nginx_edge_publication` role
- Add proxy rule for `s3.lv3.org`
- Route to `http://docker-runtime:9000`
- Enable TLS termination

### Phase 4: Verification
**Convergence:**
1. Converge `minio_runtime` → buckets and credentials created
2. Converge `outline_runtime` → uses shared MinIO
3. Access `wiki.lv3.org` → verify page loads and assets download
4. Upload file in Outline → verify S3 storage works

## Consequences

**Positive:**
- Outline S3 access is now external-network accessible via public gateway
- Eliminates embedded MinIO (reduces container count, attack surface)
- Outline gets service-specific credentials (not root)
- S3 configuration is declarative and version-controlled
- Establishes reusable pattern for other services needing S3

**Negative:**
- Outline depends on MinIO uptime (shared failure domain until HA is added)
- Adds dependency on `minio_runtime` convergence ordering
- Requires NGINX S3 gateway configuration (additional DNS, TLS cert)

## Testing Checklist

- [ ] `minio_runtime` converges, creating `outline-documents` bucket
- [ ] Outline service account created with correct policy
- [ ] `outline_runtime` converges without minio sidecar errors
- [ ] `wiki.lv3.org` homepage loads (assets downloadable)
- [ ] File upload in Outline wiki succeeds
- [ ] Downloaded file is accessible via browser S3 access
- [ ] `s3.lv3.org` returns 200 for bucket listing
- [ ] NGINX logs show S3 gateway requests succeeding

## Deployment Notes

**Ordering requirement:**
- `minio_runtime` must converge before `outline_runtime`
- S3 gateway must be deployed before browser S3 access is available

**Rollback path:**
- If issues arise, outline can temporarily use platform MinIO with public gateway disabled
- Emergency workaround: set `AWS_S3_UPLOAD_BUCKET_URL` to private MinIO URL for service-only access

## Related ADRs

- ADR 0077: Compose secrets injection pattern
- ADR 0186: NGINX as reverse proxy and TLS terminator
- ADR 0199: Outline as the living knowledge wiki
- ADR 0274: MinIO as the S3-compatible object storage layer
- ADR 0373: Unified service defaults pattern
- ADR 0397: Managed S3 bucket consumer pattern

## References

- Outline documentation: <https://docs.getoutline.com/s/guide/doc/files-storage-setup-bT8V5XyVJJ>
- MinIO S3 compatibility: <https://min.io/docs/minio/linux/integrations/s3-gateway.html>
