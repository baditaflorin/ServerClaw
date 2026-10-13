# MinIO Object Storage

## Purpose

This runbook converges and verifies the shared MinIO object-storage layer introduced by ADR 0274.

The managed runtime lives on `docker-runtime`, publishes the S3-compatible API at `https://minio.example.com`, keeps the console behind the authenticated edge route at `https://minio-console.example.com`, and provisions the launch buckets and credentials for:

- Langfuse: `langfuse-exports`
- Gitea LFS: `gitea-lfs`
- Loki chunks: `loki-chunks`
- Platform-context staging: `rag-staging`

## Commands

Syntax-check the dedicated workflow:

```bash
cd "$(git rev-parse --show-toplevel)"
make syntax-check-minio
```

Converge the shared runtime, DNS, and edge publication:

```bash
cd "$(git rev-parse --show-toplevel)"
make converge-minio
```

Or use the full service live-apply path:

```bash
cd "$(git rev-parse --show-toplevel)"
ALLOW_IN_PLACE_MUTATION=true make live-apply-service service=minio env=production
```

## Controller-Local Secrets

The managed MinIO workflow mirrors these secrets outside git:

- `.local/minio/root-password.txt`
- `.local/langfuse/minio-secret-key.txt`
- `.local/gitea/minio-secret-key.txt`
- `.local/monitoring/loki-minio-secret-key.txt`
- `.local/platform-context/minio-secret-key.txt`

If any of these files are missing in a fresh worktree, rerun `make converge-minio` before replaying the dependent consumer service.

## Verification

Verify the public API health endpoint:

```bash
curl -fsS https://minio.example.com/minio/health/live
```

Verify the console stays behind oauth2-proxy:

```bash
curl -I https://minio-console.example.com/
```

Expected result:

- `302 Found`
- `Location` includes `/oauth2/`

Verify the MinIO container and local listeners on `docker-runtime`:

```bash
ssh <minio-host> 'docker compose --file /opt/minio/docker-compose.yml ps && curl -fsS http://127.0.0.1:9010/minio/health/live && curl -fsS http://127.0.0.1:9010/minio/health/ready >/dev/null'
```

Verify the managed buckets, the Langfuse default CORS behavior, and the `rag-staging` lifecycle rule:

```bash
make converge-minio
```

Verify the mirrored controller-local secrets exist:

```bash
test -s .local/minio/root-password.txt
test -s .local/langfuse/minio-secret-key.txt
test -s .local/gitea/minio-secret-key.txt
test -s .local/monitoring/loki-minio-secret-key.txt
test -s .local/platform-context/minio-secret-key.txt
```

## Operating Notes

- The MinIO API is public for S3-compatible clients, but the console is operator-facing only and must remain behind the authenticated edge route.
- The runtime is intentionally standalone on `docker-runtime`; recovery depends on the VM and its repo-managed data path rather than a multi-node MinIO cluster.
- Consumer buckets stay private by default. Cross-service access requires an explicit bucket policy change in the role, not an ad hoc console edit.
- When ADR 0438 changes a deployment from a raw config-prefix secret directory
  to its POSIX-safe unix-prefix directory, the role treats the existing remote
  credential as authoritative. It copies that value to the canonical path
  before consulting a controller mirror or generating a new value; it does not
  rotate MinIO users merely because their directory name changed.
- MinIO's S3-compatible `PutBucketCors` API is not used here. The role verifies the required Langfuse browser-origin behavior with a presigned-download smoke probe because MinIO documents default CORS handling instead of bucket-local CORS mutation.
- If `make live-apply-service service=minio env=production` fails after the
  Docker-runtime recovery path has restarted shared services, check
  `docker-runtime` disk headroom and recover the guest with
  [docker-runtime-disk-pressure.md](docker-runtime-disk-pressure.md)
  before replaying the managed workflow.

## Non-root runtime migration

The patched MinIO image runs as UID/GID `10001:10001`. On the first converge
with that runtime identity, the role stops only the MinIO service, recursively
changes ownership under the configured MinIO data directory, records a
UID/GID-specific marker, and then starts MinIO as the unprivileged user. The
object contents are not copied or deleted. This one-time pass causes a MinIO
maintenance interruption; allow it to finish before retrying other consumers.

If the ownership pass fails, the role restores the Compose user to root,
restarts MinIO, and fails the converge rather than claiming the security change
landed. After a successful migration, root-run rollback images can still read
the volume; a future non-root image must use the same UID/GID or perform a
separately reviewed ownership migration.
