# Network Policy Reference

## Purpose

This document is the reviewed reference view of the canonical `network_policy` data in `inventory/host_vars/proxmox-host.yml`.

Anything not listed here is denied by default between guests.

## Management Sources

- guest SSH management sources: `100.64.0.0/10`, `10.10.10.1/32`
- host service source on `vmbr10`: `10.10.10.1/32`

## Allowed Flows

| Source | Destination | Ports | Reason |
|---|---|---|---|
| management sources | `nginx-edge` | `22` | operator and Ansible SSH |
| management sources | `docker-runtime` | `22` | operator and Ansible SSH |
| management sources | `docker-build` | `22` | operator and Ansible SSH |
| management sources | `monitoring` | `22` | operator and Ansible SSH |
| management sources | `postgres` | `22` | operator and Ansible SSH |
| management sources | `backup` | `22` | operator and Ansible SSH |
| management sources | `artifact-cache` | `22` | operator and Ansible SSH |
| public internet | `nginx-edge` | `80`, `443` | public edge ingress |
| public internet | `docker-runtime` | `25`, `587`, `993` | public mail ingress |
| `nginx-edge` | `docker-runtime` | `3001` | reverse proxy to Uptime Kuma |
| `nginx-edge` | `monitoring` | `3000` | reverse proxy to Grafana |
| any managed guest | `monitoring` | `8086`, `3100` | guest telemetry and log shipping |
| `docker-runtime` | `monitoring` | `4318` | OTLP HTTP trace export |
| Proxmox host | `monitoring` | `8086`, `3100` | host metrics and log shipping |
| Proxmox host | `docker-runtime` | `8000`, `8082`, `8088`, `8200`, `9000`, `9443` | private service proxies for Windmill, NetBox, Open WebUI, OpenBao, step-ca, and Portainer |
| Proxmox host | `postgres` | `5432` | private PostgreSQL TCP proxy |
| `docker-runtime` | `postgres` | `5432` | application databases and OpenBao rotation |
| Proxmox host | `backup` | `8007` | Proxmox Backup Server access |
| Proxmox host | `artifact-cache` | `5001`, `5002`, `5003`, `5004` | private cache-plane verification and host-side checks |
| `docker-build` | `artifact-cache` | `5001`, `5002`, `5003`, `5004` | private artifact-cache mirrors for build and CI consumers |
| `docker-runtime` | `artifact-cache` | `5001`, `5002`, `5003`, `5004` | private artifact-cache mirrors for Windmill workers and shared runtime scans |

## Related Surfaces

- host enforcement: [roles/proxmox_network/tasks/main.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/roles/proxmox_network/tasks/main.yml)
- guest enforcement: [roles/linux_guest_firewall/tasks/main.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/roles/linux_guest_firewall/tasks/main.yml)
