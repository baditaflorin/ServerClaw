# Health Probe Contracts Runbook

## Purpose

This runbook defines the canonical liveness and readiness contract for every currently-managed service on the LV3 platform.

The machine-readable source of truth is [config/health-probe-catalog.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/health-probe-catalog.json). Role-owned services must also import `tasks/verify.yml` from their `tasks/main.yml`.

## Contract Fields

Each service contract declares:

- `liveness`: the lightest useful probe that proves the process answers on its intended listener or control surface
- `readiness`: a deeper probe that proves the service can handle real platform traffic or a repo-managed bootstrap path
- `timeout_seconds`, `retries`, `delay_seconds`: the convergence wait budget used by the role verify task
- `uptime_kuma`: whether the service is mirrored into [config/uptime-kuma/monitors.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/uptime-kuma/monitors.json)

Services without dedicated service roles today still need catalog entries. At the moment, `proxmox_ui` and `docker_build` are catalog-only surfaces because they do not have standalone service roles.

## Current Contracts

| Service | Owner | Liveness | Readiness | Uptime Kuma |
| --- | --- | --- | --- | --- |
| `nginx_edge` | `nginx-lv3` | `systemctl is-active nginx` | HTTPS `GET /` with `Host: nginx.lv3.org` | yes |
| `grafana` | `monitoring-lv3` | `GET http://127.0.0.1:3000/api/health` | LV3 dashboard and datasource API lookups | yes |
| `proxmox_ui` | `proxmox_florin` | TCP `10.10.10.1:8006` | `GET /api2/json/version` | yes |
| `docker_runtime` | `docker-runtime-lv3` | `systemctl is-active docker` | `docker info` | no |
| `docker_build` | `docker-build-lv3` | TCP `10.10.10.30:22` | SSH reachability | yes |
| `uptime_kuma` | `docker-runtime-lv3` | running `uptime-kuma` container | local HTTP UI returns 200 | yes |
| `mail_platform` | `docker-runtime-lv3` | `GET /healthz` on the private gateway | authenticated gateway plus Stalwart catalog checks | yes |
| `step_ca` | `docker-runtime-lv3` | TCP `127.0.0.1:9000` | issue and verify a short-lived test certificate | yes |
| `windmill` | `docker-runtime-lv3` | `GET /api/version` | seeded `windmill_healthcheck` job returns the expected payload | yes |
| `netbox` | `docker-runtime-lv3` | `GET /login/` | bootstrap API token can read `/api/users/users/` | yes |
| `open_webui` | `docker-runtime-lv3` | `GET /` | repo-managed admin sign-in succeeds | yes |
| `openbao` | `docker-runtime-lv3` | `GET /v1/sys/seal-status` | `GET /v1/sys/health` returns active node status | no |
| `ntopng` | `proxmox_florin` | local HTTP root returns `200` or `302` | authenticated interface inventory and traffic counters return data | no |
| `portainer` | `docker-runtime-lv3` | TCP `127.0.0.1:9443` | Portainer API exposes the managed local endpoint | yes |
| `postgres` | `postgres-lv3` | TCP `127.0.0.1:5432` | `psql -Atqc 'SELECT 1'` | yes |
| `backup_pbs` | `backup-lv3` | TCP `127.0.0.1:8007` | `proxmox-backup-manager datastore list` includes the managed datastore | yes |

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

## Notes

- Uptime Kuma is complementary, not authoritative. The role verify task is the convergence gate.
- Authenticated readiness probes keep using repo-managed local artifacts; the catalog documents the contract, not the secret material.
- If a service changes listener, auth path, or readiness semantics, update the role verify task, the catalog, and the Uptime Kuma monitor entry in the same change.
