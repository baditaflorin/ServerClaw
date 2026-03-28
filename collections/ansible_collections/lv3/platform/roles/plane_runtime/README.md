# plane_runtime

Deploys the self-hosted Plane task board on `docker-runtime-lv3` with:

- external PostgreSQL on `postgres-lv3`
- local Valkey, RabbitMQ, and MinIO sidecars
- Proxmox-host Tailscale proxy access for controller automation
- repo-managed bootstrap admin, workspace, project, and API token
- idempotent ADR synchronization into a Plane project
- OpenBao-backed compose runtime secret injection
