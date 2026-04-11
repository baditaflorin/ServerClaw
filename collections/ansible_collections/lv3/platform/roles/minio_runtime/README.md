# MinIO Runtime

Converges the shared standalone MinIO runtime on `docker-runtime`.

This role:

- installs the pinned `mc` client used for bucket, policy, lifecycle, and presigned smoke verification
- injects the MinIO root password through the standard OpenBao compose env path
- provisions the launch buckets and per-consumer access keys for Langfuse, Gitea LFS, Loki, and RAG staging
- verifies local health, bucket reachability, Langfuse default CORS behavior, and the `rag-staging` lifecycle rule
