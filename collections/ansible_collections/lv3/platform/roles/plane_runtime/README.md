# plane_runtime

Deploys the self-hosted Plane task board on `docker-runtime` with:

- external PostgreSQL on `postgres`
- local Valkey, RabbitMQ, and MinIO sidecars
- Proxmox-host Tailscale proxy access for controller automation
- repo-managed bootstrap admin, workspace, project, and API token
- idempotent ADR synchronization into a Plane project
- OpenBao-backed compose runtime secret injection
