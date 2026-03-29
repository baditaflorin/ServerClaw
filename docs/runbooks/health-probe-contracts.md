# Health Probe Contracts Runbook

## Purpose

This runbook defines the canonical startup, liveness, and readiness probe contract for every currently-managed service on the LV3 platform, plus how those probes interact with declared degraded modes.

The machine-readable source of truth is [config/health-probe-catalog.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/health-probe-catalog.json). Role-owned services must also import `tasks/verify.yml` from their `tasks/main.yml`.

## Contract Fields

Each service contract declares:

- `startup` when initialization needs an explicit completion proof before the service should be treated as failed
- `liveness`: the lightest useful probe that proves the process answers on its intended listener or control surface
- `readiness`: a deeper probe that proves the service can handle real platform traffic or a repo-managed bootstrap path
- `readiness.docker_publication`: an optional Docker-host publication contract that proves the expected bridge networks, host-side bind addresses, and port programming exist before readiness is trusted
- `timeout_seconds`, `retries`, `delay_seconds`: the convergence wait budget used by the role verify task
- `uptime_kuma`: whether the service is mirrored into the generated [config/uptime-kuma/monitors.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/uptime-kuma/monitors.json)

Degraded-state rules remain service-level metadata in [config/service-capability-catalog.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/service-capability-catalog.json) under `degradation_modes`. If a service has no declared degraded modes, broken readiness is treated as a failure rather than an acceptable partial state.

Services without dedicated service roles today still need catalog entries. At the moment, `proxmox_ui` and `docker_build` are catalog-only surfaces because they do not have standalone service roles.

## Current Contracts

| Service | Owner | Startup | Liveness | Readiness | Uptime Kuma |
| --- | --- | --- | --- | --- | --- |
| `nginx_edge` | `nginx-lv3` | implicit from liveness/readiness | `systemctl is-active nginx` | HTTPS `GET /` with `Host: nginx.lv3.org` | yes |
| `grafana` | `monitoring-lv3` | implicit from liveness/readiness | `GET http://127.0.0.1:3000/api/health` | LV3 dashboard and datasource API lookups | yes |
| `proxmox_ui` | `proxmox_florin` | implicit from liveness/readiness | TCP `10.10.10.1:8006` | `GET /api2/json/version` | yes |
| `docker_runtime` | `docker-runtime-lv3` | implicit from liveness/readiness | `systemctl is-active docker` | `docker info` | no |
| `docker_build` | `docker-build-lv3` | implicit from liveness/readiness | TCP `10.10.10.30:22` | SSH reachability | yes |
| `uptime_kuma` | `docker-runtime-lv3` | implicit from liveness/readiness | running `uptime-kuma` container | local HTTP UI returns 200 | yes |
| `mail_platform` | `docker-runtime-lv3` | implicit from liveness/readiness | `GET /healthz` on the private gateway | authenticated gateway plus Stalwart catalog checks | yes |
| `step_ca` | `docker-runtime-lv3` | implicit from liveness/readiness | TCP `127.0.0.1:9000` | issue and verify a short-lived test certificate | yes |
| `windmill` | `docker-runtime-lv3` | implicit from liveness/readiness | `GET /api/version` | seeded `windmill_healthcheck` job returns the expected payload | yes |
| `netbox` | `docker-runtime-lv3` | API token bootstrap path | `GET /login/` | bootstrap API token can read `/api/users/users/` | yes |
| `open_webui` | `docker-runtime-lv3` | admin sign-in succeeds locally | `GET /` | repo-managed admin sign-in succeeds | yes |
| `openbao` | `docker-runtime-lv3` | active-node health endpoint | `GET /v1/sys/seal-status` | `GET /v1/sys/health` returns active node status | no |
| `ntopng` | `proxmox_florin` | implicit from liveness/readiness | local HTTP root returns `200` or `302` | authenticated interface inventory and traffic counters return data | no |
| `portainer` | `docker-runtime-lv3` | implicit from liveness/readiness | TCP `127.0.0.1:9443` | Portainer API exposes the managed local endpoint | yes |
| `postgres` | `postgres-lv3` | implicit from liveness/readiness | TCP `127.0.0.1:5432` | `psql -Atqc 'SELECT 1'` | yes |
| `backup_pbs` | `backup-lv3` | implicit from liveness/readiness | TCP `127.0.0.1:8007` | `proxmox-backup-manager datastore list` includes the managed datastore | yes |

## Operator Checks

Validate the catalog shape:

```bash
python3 -c "import json; json.load(open('config/health-probe-catalog.json'))"
```

Validate the full repository gate, including verify-task presence and catalog or Uptime Kuma alignment:

```bash
make validate
```

Run just the dedicated probe-contract checks:

```bash
make validate-health-probes
make validate-data-models
```

## Docker Publication Extension

ADR 0270 adds an optional `docker_publication` sub-contract beneath `readiness`
for Docker-hosted services whose private or edge publication path must be
proven separately from the application response itself.

The current catalog uses this extension for:

- `coolify`
- `dify`
- `gitea`
- `harbor`
- `homepage`
- `keycloak`
- `langfuse`
- `openbao`
- `outline`
- `step_ca`
- `vaultwarden`

When present, the shared post-verify path and the observation loop both run the
repo-managed helper at
`/usr/local/bin/lv3-docker-publication-assurance`. The helper derives expected
host bindings from the probe contract, verifies declared Docker networks and
iptables publication primitives, and can repair missing Docker publication
state before the readiness probe runs.

## Notes

- Uptime Kuma is complementary, not authoritative. The role verify task is the convergence gate.
- Authenticated readiness probes keep using repo-managed local artifacts; the catalog documents the contract, not the secret material.
- If a service changes listener, auth path, startup behavior, or readiness semantics, update the role verify task, the catalog, and regenerate the Uptime Kuma monitor artifact in the same change.
- `startup` is optional. Use it when startup completion needs its own proof; otherwise the platform derives the service state from liveness, readiness, and any active degraded modes.
- The dedicated contract workflow now lives in `docs/runbooks/service-uptime-contracts.md`.
