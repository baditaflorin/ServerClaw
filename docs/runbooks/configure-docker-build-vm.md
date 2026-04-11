# Configure Docker Build VM

## Purpose

`docker-build` is the private build worker used for heavier repository validation, controlled image builds, and supporting telemetry that should not run on the public edge or the main runtime VM.

## Inventory

- VMID: `130`
- Hostname: `docker-build`
- Internal IP: `10.10.10.30`
- Primary access path: `ops` over the Proxmox jump path

## Repository Surfaces

- guest definition and topology: `versions/stack.yaml`
- monitoring and telemetry integration: `docs/runbooks/monitoring-stack.md`
- tailscale and operator access: `docs/runbooks/configure-tailscale-access.md`
- image policy inputs: `config/image-catalog.json`

## Validation

Confirm the guest is reachable:

```bash
ansible -i inventory/hosts.yml docker-build -m command -a 'hostname' \
  -e proxmox_guest_ssh_connection_mode=proxmox_host_jump
```

Confirm the VM is represented in the current platform status:

```bash
rg -n "docker-build|10.10.10.30" versions/stack.yaml README.md
```

Confirm monitoring surfaces exist for the VM:

```bash
rg -n "docker-build" docs/runbooks/monitoring-stack.md versions/stack.yaml
```

## Notes

- Treat this VM as an internal build and validation surface, not as a public application runtime.
- When build-base images change, update `config/image-catalog.json` and rerun the repository validation gate from `main`.
