# Converge Proxmox host firewall policy

## Purpose

Apply only the Proxmox security role's firewall-policy tasks. This keeps
firewall configuration changes separate from the role's unrelated SSH, TFA,
ACME, and Proxmox-user management.

## Preconditions

- The selected deployment identity and topology overlays are explicit.
- `PLATFORM_INVENTORY_OVERLAY` names that deployment's SSH connection overlay;
  it must select the right Proxmox hostname, SSH port, and operator identity.
- The preflight credentials for `install-proxmox` are available.
- The proposed firewall policy has been checked against the currently live
  cluster and host firewall files, including any existing manual exceptions.

## Commands

Check the narrow task selection without applying changes:

```bash
PLATFORM_IDENTITY_OVERLAY=.local/deployments/<deployment>/identity.yml \
PLATFORM_TOPOLOGY_OVERLAY=.local/deployments/<deployment>/topology.yml \
PLATFORM_INVENTORY_OVERLAY=.local/deployments/<deployment>/ansible-connection.yml \
BOOTSTRAP_OVERLAY_ENV=production \
make converge-proxmox-firewall-policy env=production EXTRA_ARGS='--check --diff'
```

Apply after the check is reviewed:

```bash
PLATFORM_IDENTITY_OVERLAY=.local/deployments/<deployment>/identity.yml \
PLATFORM_TOPOLOGY_OVERLAY=.local/deployments/<deployment>/topology.yml \
PLATFORM_INVENTORY_OVERLAY=.local/deployments/<deployment>/ansible-connection.yml \
BOOTSTRAP_OVERLAY_ENV=production \
make converge-proxmox-firewall-policy env=production
```

The target runs `proxmox-install.yml` with only `proxmox_firewall_policy`
tasks selected and a hard limit to `proxmox-host`. It includes the existing
compile, restart, and host-input-chain recovery guard. It does not run other
Proxmox security tasks.

## Verification

- Confirm the `proxmox_firewall_policy` rule appears in the correct live
  `cluster.fw` or `host.fw` file.
- Confirm `pve-firewall` is active and has compiled the expected source/port
  rules.
- Test the intended connection from the specific source peer, and verify
  unrelated existing host rules remain present.
- Record live changes in a workstream apply receipt.
