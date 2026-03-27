# Configure Backup VM

## Purpose

This runbook captures the first-code path for creating the dedicated backup VM, wiring the Proxmox host to it as a PBS backup target, and optionally configuring the off-site recovery copy required by ADR 0100.

## Model Summary

- create `backup-lv3` as VM `160` on `10.10.10.60`
- run Proxmox Backup Server inside the guest
- store the PBS datastore on a dedicated secondary virtual disk
- point the Proxmox host backup job at that PBS datastore
- optionally back up `backup-lv3` itself to off-site Proxmox storage for total-host-loss recovery

## Command

```bash
ANSIBLE_HOST_KEY_CHECKING=False ansible-playbook -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/inventory/hosts.yml /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/playbooks/backup-vm.yml --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519
```

Or use the Make target:

```bash
make configure-backup-vm
```

## What The Playbook Does

1. Ensures the Proxmox host has the `backup-lv3` guest defined.
2. Attaches a dedicated datastore disk to the backup VM.
3. Installs Proxmox Backup Server inside the guest.
4. Creates the PBS datastore and a dedicated API token for the Proxmox host.
5. Stores the token secret locally outside git.
6. Converges the Proxmox host storage entry `lv3-backup-pbs`.
7. Converges the nightly backup job `backup-lv3-nightly`.
8. Optionally converges the off-site storage entry `lv3-backup-offsite`.
9. Optionally converges the off-site backup job `backup-lv3-offsite` for VM `160`.

## Optional Off-Site Inputs

Set these when enabling the ADR 0100 off-site copy of `backup-lv3`:

```bash
export PROXMOX_DR_OFFSITE_ENABLED=true
export PROXMOX_DR_OFFSITE_SERVER=<storage-box-hostname>
export PROXMOX_DR_OFFSITE_SHARE=<share>
export PROXMOX_DR_OFFSITE_USERNAME=<username>
export PROXMOX_DR_OFFSITE_PASSWORD=<password>
```

## Verification

Verify the VM exists and is running:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.118.189.95 'sudo qm list | grep 160'
```

Verify PBS services and datastore state inside the guest:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.118.189.95 'ssh -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=/dev/null -o ProxyCommand=\"ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.118.189.95 -W %h:%p\" -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 ops@10.10.10.60 \"sudo systemctl is-active proxmox-backup-proxy && sudo proxmox-backup-manager datastore list --output-format json-pretty\"'
```

Verify the Proxmox host backup storage config:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.118.189.95 'sudo pvesh get /storage/lv3-backup-pbs --output-format json-pretty'
```

Verify the backup job:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.118.189.95 'sudo pvesh get /cluster/backup/backup-lv3-nightly --output-format json-pretty'
```

Verify the optional off-site job when enabled:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.118.189.95 'sudo pvesh get /cluster/backup/backup-lv3-offsite --output-format json-pretty'
```

Run one ad hoc backup for validation:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.118.189.95 'sudo vzdump 110 --storage lv3-backup-pbs --mode snapshot --compress zstd --notification-mode notification-system'
```

## Restore-Oriented Check

List the snapshots present in PBS after a backup run:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.118.189.95 'sudo pvesm list lv3-backup-pbs --vmid 110'
```

Restore the latest backup to a spare VMID without starting it:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.118.189.95 'latest=$(sudo pvesm list lv3-backup-pbs --vmid 110 | awk '\''NR==2 {print $1}'\''); sudo qmrestore \"$latest\" 9101 --storage local --unique 1'
```

Cleanup after a drill:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.118.189.95 'sudo qm stop 9101 || true; sudo qm destroy 9101 --destroy-unreferenced-disks 1 --purge 1'
```

## Limitation

Local PBS on `backup-lv3` still shares the same host failure domain as the primary workloads. ADR 0100 closes that gap only when the optional off-site `backup-lv3` copy is configured and verified.

## Lessons Learned

- Keep the backup VM NIC MAC deterministic in inventory. Re-running `qm set --net0` without an explicit MAC can rotate the MAC and leave Debian cloud-init matching the old value, which results in a booted guest with no working network.
- After changing `net0`, `ipconfig0`, or `cicustom`, run `qm cloudinit update <vmid>` before restarting the guest so the attached cloud-init seed actually reflects the new values.
- During early bootstrap, use a Proxmox-side stop/start cycle instead of `qm reboot` if the guest agent is not guaranteed to be available yet.
