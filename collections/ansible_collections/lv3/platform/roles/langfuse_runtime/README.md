# langfuse_runtime

Deploys the self-hosted Langfuse runtime on `docker-runtime` with:

- external PostgreSQL on `postgres`
- local ClickHouse, Redis, and MinIO sidecars
- repo-managed Keycloak OIDC client wiring
- repo-managed bootstrap org, project, API keys, and local bootstrap user
- OpenBao-backed compose runtime secret injection
