# Disaster Recovery

## Purpose

This runbook is the operator path for ADR 0100.

The recovery anchor is `backup` (VM `160`). Recover that VM first from off-site storage, then use PBS on `backup` to restore the remaining platform VMs.

## Targets

- platform RTO: `< 4h`
- platform RPO: `< 24h`
- readiness report: `make dr-status`
- backup coverage evidence: `make backup-coverage-ledger`
- release-readiness view: `lv3 release status`

## Preconditions

- Hetzner reinstall access exists
- the break-glass references in [break-glass.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/docs/runbooks/break-glass.md) are available
- the off-site Proxmox storage target for VM `160` is reachable
- the off-host witness archive for ADR 0181 is reachable

## Tier 0: Rebuild The Host

Verify the latest off-host witness bundle first:

```bash
LV3_CONTROL_METADATA_WITNESS_ARCHIVE_ROOT=/path/to/off-host/archive python3 /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/scripts/control_metadata_witness.py verify --archive-root "$LV3_CONTROL_METADATA_WITNESS_ARCHIVE_ROOT"
```

Reinstall Debian 13 and restore Proxmox VE first.

Verify Proxmox is up:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.118.189.95 'sudo pvesh get /version --output-format json-pretty'
```

## Tier 1: Restore `backup`

List the latest off-site backup for VM `160`:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.118.189.95 'sudo pvesm list lv3-backup-offsite --vmid 160'
```

Restore `backup` from the latest off-site backup:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.118.189.95 'latest=$(sudo pvesm list lv3-backup-offsite --vmid 160 | awk '\''NR==2 {print $1}'\''); sudo qmrestore "$latest" 160 --storage local --unique 0'
```

Verify PBS is back:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ProxyCommand="ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.118.189.95 -W %h:%p" ops@10.10.10.60 'sudo proxmox-backup-manager datastore list --output-format json'
```

## Tier 2: Restore Stateful Data Services

Restore `postgres`:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.118.189.95 'latest=$(sudo pvesm list lv3-backup-pbs --vmid 150 | awk '\''NR==2 {print $1}'\''); sudo qmrestore "$latest" 150 --storage local --unique 0'
```

Restore `docker-runtime`:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.118.189.95 'latest=$(sudo pvesm list lv3-backup-pbs --vmid 120 | awk '\''NR==2 {print $1}'\''); sudo qmrestore "$latest" 120 --storage local --unique 0'
```

Verify `step-ca` and OpenBao:

```bash
curl -skf https://100.118.189.95:9443/health
curl -skf https://100.118.189.95:8200/v1/sys/health
```

## Tier 3: Restore Edge And Observability

Restore `monitoring`:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.118.189.95 'latest=$(sudo pvesm list lv3-backup-pbs --vmid 140 | awk '\''NR==2 {print $1}'\''); sudo qmrestore "$latest" 140 --storage local --unique 0'
```

Restore `nginx-edge`:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.118.189.95 'latest=$(sudo pvesm list lv3-backup-pbs --vmid 110 | awk '\''NR==2 {print $1}'\''); sudo qmrestore "$latest" 110 --storage local --unique 0'
```

Verify public-edge services:

```bash
curl -skf https://grafana.example.com/api/health
curl -skf https://sso.example.com/health/ready
```

## Tier 4: Restore Build Infrastructure

Restore `docker-build`:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.118.189.95 'latest=$(sudo pvesm list lv3-backup-pbs --vmid 130 | awk '\''NR==2 {print $1}'\''); sudo qmrestore "$latest" 130 --storage local --unique 0'
```

## Tier 5: Verification

Show the repo-managed DR posture:

```bash
make dr-status
```

Refresh the ADR 0271 coverage ledger if the recovery exercise changed backup
coverage on the live host:

```bash
make backup-coverage-ledger
```

Show release-readiness including the DR review criterion:

```bash
lv3 release status
```

Render the structured runbook plan:

```bash
python3 /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/scripts/disaster_recovery_runbook.py
```

## Off-Site Storage Configuration

The off-site copy for `backup` is optional in the playbook and is enabled only when the following environment variables are present:

- `PROXMOX_DR_OFFSITE_ENABLED=true`
- `PROXMOX_DR_OFFSITE_SERVER=<storage-box-hostname>`
- `PROXMOX_DR_OFFSITE_SHARE=<share>`
- `PROXMOX_DR_OFFSITE_USERNAME=<username>`
- `PROXMOX_DR_OFFSITE_PASSWORD=<password>`

When these are set, `make configure-backup-vm` also converges:

- Proxmox storage `lv3-backup-offsite`
- Proxmox backup job `backup-offsite`

## Current Gap

As of the ADR 0271 rollout, the backup coverage ledger makes the remaining
host-loss gap explicit instead of leaving it in prose: `backup` stays
`uncovered` until `lv3-backup-offsite` exists live and carries fresh VM `160`
evidence. ADR 0181 witness publication is already live, so the remaining DR gap
is specifically the optional second copy of `backup`, which still depends
on the `PROXMOX_DR_OFFSITE_*` credentials when a separate off-site backup target
is desired.
