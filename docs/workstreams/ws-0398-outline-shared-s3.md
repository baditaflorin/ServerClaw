# Workstream 0398: Outline Shared S3 Migration

## Overview

Migrate Outline (wiki.example.com) from an embedded MinIO sidecar to the shared platform MinIO instance. This fixes the broken asset loading issue where `http://minio:9000` (internal-only hostname) is unreachable from browsers.

Implements the **Managed S3 Bucket Consumer Pattern** (ADR 0397) to establish a reusable, declarative pattern for all services needing S3 access.

## Why This Matters

**Current Problem:**
- wiki.example.com doesn't load because S3 assets are unreachable
- Outline hardcodes internal MinIO URL: `http://minio:9000`
- This hostname only exists inside Outline's container network
- Browsers cannot access it, breaking asset loading

**Impact:**
- All wiki functionality broken until S3 is accessible from browser
- Establishes pattern for other services (Nextcloud, Coolify, etc.) needing S3

## Architecture Change

### Before (Broken)
```
Outline Container
├── MinIO (embedded)
│   └── outline bucket
├── Redis
└── Outline app
    └── Hardcoded: AWS_S3_UPLOAD_BUCKET_URL=http://minio:9000 ❌
```

### After (Working)
```
Shared Platform MinIO (docker-runtime:9000)
├── outline-documents bucket
├── langfuse-exports bucket
├── gitea-lfs bucket
└── ...

Outline Container (runtime-control)
├── Redis
└── Outline app
    └── AWS_S3_UPLOAD_BUCKET_URL=https://s3.example.com ✅

NGINX Edge
└── s3.example.com → proxy to docker-runtime:9000 ✅
```

## Implementation Phases

### Phase 1: Register Outline with MinIO ✅
**Status:** In Progress

**What:** Add Outline to `minio_runtime/defaults/main.yml` as a managed consumer

**Changes:**
```yaml
minio_outline_bucket_name: outline-documents
minio_outline_access_key_id: outline
minio_outline_secret_key_remote_file: "{{ minio_secret_dir }}/outline-secret.txt"
minio_outline_secret_key_local_file: "{{ minio_local_artifact_dir }}/outline-secret.txt"
minio_outline_policy_name: outline-bucket-policy
minio_outline_policy_document: |
  {
    "Version": "2012-10-17",
    "Statement": [
      {
        "Effect": "Allow",
        "Principal": {"AWS": "arn:aws:iam::minio:user/outline"},
        "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
        "Resource": "arn:aws:s3:::outline-documents/*"
      }
    ]
  }
```

**Verification:**
- `minio_runtime` converges
- `outline-documents` bucket created
- Service account `outline` created with policy attached
- Secrets mirrored to controller machine

### Phase 2: Update Outline Role ✅
**Status:** Not Started

**What:** Remove embedded MinIO, reference shared MinIO

**Files changed:**
1. `outline_runtime/defaults/main.yml`
   - Remove: `outline_minio_*` variables
   - Add: References to `minio_*` variables

2. `outline_runtime/docker-compose.yml.j2`
   - Remove: `minio:` service definition
   - Keep: `redis:` and `outline:` services

3. `outline_runtime/tasks/main.yml`
   - Remove: MinIO directory setup (lines 64-67)
   - Remove: MinIO secret generation (lines 86-88)
   - Remove: MinIO data directory path references

4. `outline_runtime/templates/outline.env.j2`
   - Change: `AWS_S3_UPLOAD_BUCKET_URL=http://minio:9000` → `https://s3.example.com`
   - Change: `AWS_ACCESS_KEY_ID=minio` → `outline`
   - Change: `AWS_SECRET_ACCESS_KEY` → Read from controller mirror

**Verification:**
- `outline_runtime` converges without minio errors
- No minio container in `docker ps`
- Outline env vars point to shared MinIO

### Phase 3: Configure S3 Gateway ✅
**Status:** Not Started

**What:** Add public NGINX route for `s3.example.com`

**Where:** `public_edge` or `nginx_edge_publication` role

**Config:**
```nginx
server {
    listen 443 ssl http2;
    server_name s3.example.com;

    location / {
        proxy_pass http://docker-runtime:9000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

**Verification:**
- `curl https://s3.example.com/` returns 200
- NGINX logs show requests being routed to docker-runtime

### Phase 4: Test & Verify ✅
**Status:** Not Started

**Convergence order:**
1. `minio_runtime` converges → buckets created
2. `outline_runtime` converges → uses shared MinIO
3. Access wiki.example.com → verify page loads

**Testing checklist:**
- [ ] wiki.example.com homepage loads completely
- [ ] Static assets (JS, CSS) download successfully
- [ ] File upload in Outline succeeds
- [ ] Uploaded file is stored in shared MinIO bucket
- [ ] Downloaded file is accessible via `s3.example.com`
- [ ] No minio container running on runtime-control

## Critical Decisions

1. **Public URL:** Use `https://s3.example.com` (not internal `http://docker-runtime:9000`)
   - Enables browser downloads
   - Requires TLS certificate for s3.example.com
   - NGINX handles routing and TLS termination

2. **Credentials:** Service account `outline`, not root `minio`
   - Least-privilege principle
   - Bucket-scoped policy prevents cross-tenant access

3. **Bucket naming:** `outline-documents` (not just `outline`)
   - Follows ADR 0397 pattern: `<service-id>-<purpose>`
   - Allows for multiple buckets if needed later

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| MinIO downtime | Outline can't access S3 | Deploy MinIO HA (future ADR) |
| S3 gateway unavailable | Browsers can't download files | NGINX is highly available |
| Credential rotation needed | Service interrupted | Automated secret rotation in OpenBao |
| Policy too restrictive | Outline functions broken | Use wildcard policy initially, refine later |

## Files Requiring Review/Approval

1. `docs/adr/0397-managed-s3-bucket-consumer-pattern.md` - Pattern definition
2. `docs/adr/0398-outline-shared-s3-migration.md` - Outline-specific implementation
3. `docs/workstreams/ws-0398-outline-shared-s3.md` - This document

## Deployment Checklist

- [ ] ADRs 0397-0398 merged to main
- [ ] Phase 1: minio_runtime defaults updated and tested
- [ ] Phase 2: outline_runtime updated and tested
- [ ] Phase 3: NGINX S3 gateway deployed
- [ ] Phase 4: wiki.example.com fully functional
- [ ] Convergence: minio_runtime → outline_runtime → verify
- [ ] Version bump and changelog entry
- [ ] Live-apply: Outline to production
- [ ] Incident log: Document resolution

## Success Criteria

✅ wiki.example.com loads completely with all assets
✅ File upload/download works in wiki
✅ S3 bucket is shared with other services (pattern proven)
✅ No embedded MinIO containers running
✅ Zero downtime migration (shadow convergence method)

## References

- ADR 0199: Outline as the living knowledge wiki
- ADR 0274: MinIO as the S3-compatible object storage layer
- ADR 0373: Unified service defaults pattern
- ADR 0397: Managed S3 bucket consumer pattern
- ADR 0398: Outline shared S3 migration
