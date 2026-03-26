# langfuse_runtime

Deploys the self-hosted Langfuse runtime on `docker-runtime-lv3` with:

- external PostgreSQL on `postgres-lv3`
- local ClickHouse, Redis, and MinIO sidecars
- repo-managed Keycloak OIDC client wiring
- repo-managed bootstrap org, project, API keys, and local bootstrap user
- OpenBao-backed compose runtime secret injection
