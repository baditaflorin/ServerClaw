# Provision Guests Runbook

## Purpose

This runbook captures the first-code path for provisioning the initial Proxmox guest set from a Debian 13 cloud template.

## Managed guests

- `110` `nginx-lv3` `10.10.10.10`
- `120` `docker-runtime-lv3` `10.10.10.20`
- `130` `docker-build-lv3` `10.10.10.30`
- `140` `monitoring-lv3` `10.10.10.40`

## Command

```bash
make provision-guests
```

## What the playbook does

1. Downloads the official Debian 13 genericcloud image with a pinned SHA-512 checksum.
2. Creates a reusable Proxmox template VM if it does not already exist.
3. Clones the four initial guests from that template.
4. Applies IPs, CPU, memory, disk size, tags, and cloud-init config.
5. Starts the guests.

## Notes

- This runbook provisions guest shells and baseline packages, not the final application configuration.
- Public ingress forwarding to the NGINX VM is still separate work.
