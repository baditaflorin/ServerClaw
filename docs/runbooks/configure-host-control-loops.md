# Configure Host Control Loops

## Purpose

This runbook converges ADR 0226 on `proxmox-host` by installing the
repository-managed `systemd` service, timer, and path units that form the
canonical host-resident control-loop baseline.

The first live loop is intentionally safe: it records a reconcile heartbeat
under `/var/lib/lv3-host-control-loops/` and proves that the host now has a
reviewable, journal-backed supervisor contract for future server-resident
automation.

## Automation Surface

- make target: `make configure-host-control-loops`
- playbook: `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/playbooks/proxmox-install.yml`
- role: `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/roles/proxmox_host_control_loops/tasks/main.yml`

## Apply

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server
make configure-host-control-loops
```

## What The Workflow Converges

1. Creates the managed control-loop state root at
   `/var/lib/lv3-host-control-loops`.
2. Installs the repo-managed reconcile recorder at
   `/usr/local/libexec/lv3-host-control-loop-reconcile.py`.
3. Renders `lv3-host-control-loop-reconcile.service` with explicit timeout,
   restart, ordering, and hardening settings.
4. Enables `lv3-host-control-loop-reconcile.timer` for periodic execution.
5. Enables `lv3-host-control-loop-reconcile.path` so a local request file can
   trigger the same bounded reconcile service immediately.

## Verification

Seed or refresh the latest status artifact with an explicit one-shot reconcile:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.64.0.1 'sudo systemctl start lv3-host-control-loop-reconcile.service && sudo cat /var/lib/lv3-host-control-loops/status/latest.json'
```

Check that the timer is active and scheduled:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.64.0.1 'sudo systemctl status lv3-host-control-loop-reconcile.timer --no-pager'
```

Check that the path unit is watching for manual trigger files:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.64.0.1 'sudo systemctl status lv3-host-control-loop-reconcile.path --no-pager'
```

Read the latest recorded loop state again without replaying the service:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.64.0.1 'sudo cat /var/lib/lv3-host-control-loops/status/latest.json'
```

Inspect the journal for the last five reconcile runs:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.64.0.1 'sudo journalctl -u lv3-host-control-loop-reconcile.service -n 5 --no-pager'
```

## Manual Trigger

Request an immediate path-triggered reconcile pass:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.64.0.1 "printf '%s\n' '{\"reason\":\"manual-check\"}' | sudo tee /var/lib/lv3-host-control-loops/requests/reconcile.request >/dev/null"
```

Then confirm the request file was consumed and a new journal entry appeared:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.64.0.1 'sudo test ! -e /var/lib/lv3-host-control-loops/requests/reconcile.request && sudo journalctl -u lv3-host-control-loop-reconcile.service -n 1 --no-pager'
```

## Notes

- Host journals have explicit retention in
  `/etc/systemd/journald.conf.d/60-fleet-retention.conf`: 1 GiB persistent,
  256 MiB volatile, 30 days, and one-day journal files. The persistent journal
  also leaves 5 GiB free. These caps operate continuously; they do not depend
  on the emergency low-disk recovery timer. Size caps may expire logs sooner
  than 30 days; central log shipping remains the longer-term query surface.
- To apply only these limits, run the Proxmox playbook with
  `--tags journal-retention`. The role backs up an existing drop-in and restarts
  only `systemd-journald` when the file changes. Verify with
  `systemd-analyze cat-config systemd/journald.conf`,
  `systemctl is-active systemd-journald`, and `journalctl --disk-usage`.
  Roll back by restoring the saved drop-in (or moving the new one aside if
  none existed) and restarting `systemd-journald`; expired logs cannot be
  restored by changing the limits.
- The same helper supports guests through `playbooks/journal-retention.yml`.
  For an explicit SSH alias, pass a one-host inventory and
  `-e journal_retention_hosts=<alias>`. This playbook changes only the journal
  configuration, so it does not replay Proxmox roles on a guest. The shared
  defaults live under `common_journal_retention_*` in the common role.

- The current loop records execution state only; ADR 0225 will later replace
  the placeholder reconcile body with a repo-managed `ansible-pull` path.
- The reconcile service is a bounded `oneshot` unit. Retry comes from the next
  timer tick, a new request file, or an explicit `systemctl start`, not from a
  service-level restart loop.
- Use `systemctl start lv3-host-control-loop-reconcile.service` for an explicit
  one-shot replay when you do not want to go through the path trigger.
