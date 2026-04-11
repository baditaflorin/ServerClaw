# Workstream: ADR 0346 — Centralized Port Registry

- ADR: [0346](../adr/0346-centralized-port-registry.md)
- Branch: `claude/modest-northcutt`
- Status: live_applied
- Owner: claude

## Summary

Eliminates hardcoded platform port numbers from role defaults. Establishes
`platform_port_assignments` as the single source of truth, adds
`_host_proxy_port` collision detection to the generator, and fixes the Gitea
ROOT_URL bug that broke Keycloak SSO login.

## Changes

- `scripts/generate_platform_vars.py`: gitea public URL fix, keycloak in
  build_service_urls, PORT_KEYS dedup, collision detection
- `inventory/host_vars/proxmox-host.yml`: keycloak_internal_http_port added,
  keycloak topology uses port assignment template
- 12 role defaults + 1 playbook migrated to registry references
