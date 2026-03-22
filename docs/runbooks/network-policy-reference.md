# Network Policy Reference

## Purpose

This document is the reviewed reference view of the canonical `network_policy` data in `inventory/host_vars/proxmox_florin.yml`.

Anything not listed here is denied by default between guests.

## Management Sources

- guest SSH management sources: `100.64.0.0/10`, `10.10.10.1/32`
- host service source on `vmbr10`: `10.10.10.1/32`

## Allowed Flows

| Source | Destination | Ports | Reason |
|---|---|---|---|
| management sources | `nginx-lv3` | `22` | operator and Ansible SSH |
| management sources | `docker-runtime-lv3` | `22` | operator and Ansible SSH |
| management sources | `docker-build-lv3` | `22` | operator and Ansible SSH |
| management sources | `monitoring-lv3` | `22` | operator and Ansible SSH |
| management sources | `postgres-lv3` | `22` | operator and Ansible SSH |
| management sources | `backup-lv3` | `22` | operator and Ansible SSH |
| public internet | `nginx-lv3` | `80`, `443` | public edge ingress |
| public internet | `docker-runtime-lv3` | `25`, `587`, `993` | public mail ingress |
| `nginx-lv3` | `docker-runtime-lv3` | `3001` | reverse proxy to Uptime Kuma |
| `nginx-lv3` | `monitoring-lv3` | `3000` | reverse proxy to Grafana |
| any managed guest | `monitoring-lv3` | `8086`, `3100` | guest telemetry and log shipping |
| `docker-runtime-lv3` | `monitoring-lv3` | `4318` | OTLP HTTP trace export |
| Proxmox host | `monitoring-lv3` | `8086`, `3100` | host metrics and log shipping |
| Proxmox host | `docker-runtime-lv3` | `8000`, `8082`, `8088`, `8200`, `9000`, `9443` | private service proxies for Windmill, NetBox, Open WebUI, OpenBao, step-ca, and Portainer |
| Proxmox host | `postgres-lv3` | `5432` | private PostgreSQL TCP proxy |
| `docker-runtime-lv3` | `postgres-lv3` | `5432` | application databases and OpenBao rotation |
| Proxmox host | `backup-lv3` | `8007` | Proxmox Backup Server access |

## Related Surfaces

- host enforcement: [roles/proxmox_network/tasks/main.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server-guest-network-policy/roles/proxmox_network/tasks/main.yml)
- guest enforcement: [roles/linux_guest_firewall/tasks/main.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server-guest-network-policy/roles/linux_guest_firewall/tasks/main.yml)
