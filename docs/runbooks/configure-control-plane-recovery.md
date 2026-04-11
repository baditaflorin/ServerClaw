# Configure Control-Plane Recovery

## Purpose

This runbook converges the repository-managed backup, restore-drill, and break-glass support path for the control-plane components on `docker-runtime`.

## Covered State

The workflow treats the following as first-class control-plane recovery scope:

- `step-ca` runtime files and private password material
- OpenBao configuration plus a managed Raft snapshot
- Windmill database state and runtime bootstrap secrets
- mail-platform runtime files and API credentials
- controller-local recovery references mirrored into the backup store

## Command

```bash
ANSIBLE_HOST_KEY_CHECKING=False ansible-playbook -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/inventory/hosts.yml /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/playbooks/control-plane-recovery.yml --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -e proxmox_guest_ssh_connection_mode=proxmox_host_jump
```

Or use the Make target:

```bash
make converge-control-plane-recovery
```

## What The Playbook Does

1. Updates the Proxmox-side `backup` guest firewall so `docker-runtime` can push the archived bundles over SSH.
2. Configures `backup` as the control-plane recovery store.
3. Installs a dedicated non-human SSH landing user for runtime archive delivery.
4. Configures `docker-runtime` to export scheduled control-plane backups.
5. Creates a scoped OpenBao AppRole plus agent-managed systemd credentials used only for managed Raft snapshots and the Windmill backup database DSN.
6. Builds a controller-local recovery bundle and mirrors it into `backup`.
7. Enables a scheduled restore drill on `backup`.
8. After the restore drill passes, builds a git-backed witness bundle from the repo checkout and publishes one immutable off-host generation.
9. Runs one immediate backup, one immediate restore drill, and one witness verification pass.

## Scheduled Policy

- runtime backup timer: `*-*-* 01,07,13,19:15:00`
- restore drill timer: `*-*-* 05:45:00`

The current cadence is intentionally faster than typical VM-only backup policy because short-lived secrets and internal certificates change more often than guest disks.

The backup push path depends on `backup` accepting SSH from `docker-runtime` on `10.10.10.20/32`. The workflow now manages that Proxmox guest-firewall allowance explicitly.

## Verification

Check the backup timer on `docker-runtime`:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -o ProxyCommand="ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.118.189.95 -W %h:%p" ops@10.10.10.20 'sudo systemctl status lv3-control-plane-backup.timer --no-pager'
```

Check the OpenBao Agent credential delivery unit on `docker-runtime`:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -o ProxyCommand="ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.118.189.95 -W %h:%p" ops@10.10.10.20 'sudo systemctl status lv3-control-plane-backup-openbao-agent.service --no-pager'
```

Confirm the host-native credential source files exist and the legacy token artifact is gone:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -o ProxyCommand="ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.118.189.95 -W %h:%p" ops@10.10.10.20 'sudo ls -l /run/lv3-systemd-credentials/control-plane-backup && sudo test ! -e /etc/lv3/control-plane-recovery/openbao-backup-token.json'
```

Check the restore-drill timer on `backup`:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -o ProxyCommand="ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.118.189.95 -W %h:%p" ops@10.10.10.60 'sudo systemctl status lv3-control-plane-restore-drill.timer --no-pager'
```

Inspect the latest runtime backup landing zone:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -o ProxyCommand="ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.118.189.95 -W %h:%p" ops@10.10.10.60 'ls -lah /srv/control-plane-recovery/runtime/docker-runtime/latest'
```

Inspect the restore-drill result:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -o ProxyCommand="ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.118.189.95 -W %h:%p" ops@10.10.10.60 'sudo cat /srv/control-plane-recovery/drills/last-restore-drill.json'
```

Inspect the controller recovery bundle:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -o ProxyCommand="ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.118.189.95 -W %h:%p" ops@10.10.10.60 'ls -lah /srv/control-plane-recovery/controller'
```

Inspect the latest off-host witness receipt written during the live apply:

```bash
ls -1 /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/receipts/witness-replication | tail -n 1
```

Verify the latest off-host witness generation directly:

```bash
LV3_CONTROL_METADATA_WITNESS_ARCHIVE_ROOT=/path/to/off-host/archive python3 /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/scripts/control_metadata_witness.py verify --archive-root "$LV3_CONTROL_METADATA_WITNESS_ARCHIVE_ROOT"
```

## Off-Host Witness Inputs

Set these controller-side environment variables before `make converge-control-plane-recovery` when ADR 0181 witness replication is enabled:

- `LV3_CONTROL_METADATA_WITNESS_ARCHIVE_ROOT`: mounted off-host path that stores immutable witness generations and the `latest` pointer
- `LV3_CONTROL_METADATA_WITNESS_GIT_REMOTE`: git remote used as the first witness target, default `origin`
- `LV3_CONTROL_METADATA_WITNESS_GIT_REMOTE_REF`: optional exact remote ref that must match local `HEAD`; defaults to the current upstream branch or `refs/heads/<current-branch>`

## Break-Glass Notes

- The controller bundle includes repo-managed recovery references needed to reconnect to the live control plane.
- The root break-glass SSH private key remains an external dependency and is intentionally not copied into the archived bundle.
- Treat `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519` as a separately preserved recovery secret.
- The durable AppRole bootstrap files under `/etc/lv3/control-plane-recovery/openbao-agent/` are intentionally narrow, low-privilege bootstrap material for the host-local OpenBao Agent and should remain root-only (`0600`).

## Restore Orientation

Use the archived component files in `backup` as the source of truth for service-specific recovery:

- `step-ca.tar.zst` for CA runtime files and passwords
- `openbao-config.tar.zst` plus `openbao-raft.snap` for OpenBao
- `windmill-db.dump` plus `windmill-files.tar.zst` for Windmill
- `mail-platform.tar.zst` for Stalwart and gateway state
- `controller-recovery-bundle.tar.zst` plus `control-plane-recovery-manifest.json` for controller-local references

The automated restore drill validates archive integrity and key file presence, but it does not yet recreate the full services on an isolated host.

## Limitation

This workflow now covers one repo-managed off-host witness archive, but it still depends on the configured remote git provider and archive mount existing outside the Proxmox host. It is not a substitute for a second recovery site.
