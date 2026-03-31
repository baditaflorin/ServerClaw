# MinIO Object Storage

## Purpose

This runbook converges and verifies the shared MinIO object-storage layer introduced by ADR 0274.

The managed runtime lives on `docker-runtime-lv3`, publishes the S3-compatible API at `https://minio.lv3.org`, keeps the console behind the authenticated edge route at `https://minio-console.lv3.org`, and provisions the launch buckets and credentials for:

- Langfuse: `langfuse-exports`
- Gitea LFS: `gitea-lfs`
- Loki chunks: `loki-chunks`
- Platform-context staging: `rag-staging`

## Commands

Syntax-check the dedicated workflow:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server
make syntax-check-minio
```

Converge the shared runtime, DNS, and edge publication:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server
make converge-minio
```

Or use the full service live-apply path:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server
ALLOW_IN_PLACE_MUTATION=true make live-apply-service service=minio env=production
```

## Controller-Local Secrets

The managed MinIO workflow mirrors these secrets outside git:

- `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/minio/root-password.txt`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/langfuse/minio-secret-key.txt`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/gitea/minio-secret-key.txt`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/monitoring/loki-minio-secret-key.txt`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/platform-context/minio-secret-key.txt`

If any of these files are missing in a fresh worktree, rerun `make converge-minio` before replaying the dependent consumer service.

## Verification

Verify the public API health endpoint:

```bash
curl -fsS https://minio.lv3.org/minio/health/live
```

Verify the console stays behind oauth2-proxy:

```bash
curl -I https://minio-console.lv3.org/
```

Expected result:

- `302 Found`
- `Location` includes `/oauth2/`

Verify the MinIO container and local listeners on `docker-runtime-lv3`:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.64.0.1 ops@10.10.10.20 'docker compose --file /opt/minio/docker-compose.yml ps && curl -fsS http://127.0.0.1:9010/minio/health/live && curl -fsS http://127.0.0.1:9010/minio/health/ready >/dev/null'
```

Verify the managed buckets, the Langfuse default CORS behavior, and the `rag-staging` lifecycle rule:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.64.0.1 ops@10.10.10.20 'tmp=$(mktemp) && trap "rm -f \"$tmp\"" EXIT && printf "lv3-langfuse-cors-smoke\n" > "$tmp" && sudo mc --config-dir /opt/minio/mc cp "$tmp" local/langfuse-exports/__lv3-langfuse-cors-smoke.txt >/dev/null && url=$(sudo mc --config-dir /opt/minio/mc share download --json --expire 5m local/langfuse-exports/__lv3-langfuse-cors-smoke.txt | python3 -c '"'"'import json,sys; lines=[line for line in sys.stdin.read().splitlines() if line.strip()]; data=json.loads(lines[-1]); print(data.get("share") or data.get("url") or data.get("shareURL") or "")'"'"') && curl -sS -D - -o /dev/null -H "Origin: https://langfuse.lv3.org" "$url" | grep -i "access-control-allow-origin" && sudo mc --config-dir /opt/minio/mc ls local/langfuse-exports && sudo mc --config-dir /opt/minio/mc ls local/gitea-lfs && sudo mc --config-dir /opt/minio/mc ls local/loki-chunks && sudo mc --config-dir /opt/minio/mc ls local/rag-staging && sudo mc --config-dir /opt/minio/mc ilm rule list --json local/rag-staging && sudo mc --config-dir /opt/minio/mc rm --force local/langfuse-exports/__lv3-langfuse-cors-smoke.txt >/dev/null'
```

Verify the mirrored controller-local secrets exist:

```bash
test -s /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/minio/root-password.txt
test -s /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/langfuse/minio-secret-key.txt
test -s /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/gitea/minio-secret-key.txt
test -s /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/monitoring/loki-minio-secret-key.txt
test -s /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/platform-context/minio-secret-key.txt
```

## Operating Notes

- The MinIO API is public for S3-compatible clients, but the console is operator-facing only and must remain behind the authenticated edge route.
- The runtime is intentionally standalone on `docker-runtime-lv3`; recovery depends on the VM and its repo-managed data path rather than a multi-node MinIO cluster.
- Consumer buckets stay private by default. Cross-service access requires an explicit bucket policy change in the role, not an ad hoc console edit.
- MinIO's S3-compatible `PutBucketCors` API is not used here. The role verifies the required Langfuse browser-origin behavior with a presigned-download smoke probe because MinIO documents default CORS handling instead of bucket-local CORS mutation.
- If `make live-apply-service service=minio env=production` fails after the
  Docker-runtime recovery path has restarted shared services, check
  `docker-runtime-lv3` disk headroom and recover the guest with
  [docker-runtime-disk-pressure.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0274-mainline-refresh-v6/docs/runbooks/docker-runtime-disk-pressure.md)
  before replaying the managed workflow.
