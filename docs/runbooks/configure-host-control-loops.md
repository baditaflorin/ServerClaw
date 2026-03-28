# Configure Host Control Loops

## Purpose

This runbook converges ADR 0226 on `proxmox_florin` by installing the
repository-managed `systemd` service, timer, and path units that form the
canonical host-resident control-loop baseline.

The first live loop is intentionally safe: it records a reconcile heartbeat
under `/var/lib/lv3-host-control-loops/` and proves that the host now has a
reviewable, journal-backed supervisor contract for future server-resident
automation.

## Automation Surface

- make target: `make configure-host-control-loops`
- playbook: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/playbooks/site.yml`
- role: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/proxmox_host_control_loops/tasks/main.yml`

## Apply

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server
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

Check that the timer is active and scheduled:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.64.0.1 'sudo systemctl status lv3-host-control-loop-reconcile.timer --no-pager'
```

Check that the path unit is watching for manual trigger files:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.64.0.1 'sudo systemctl status lv3-host-control-loop-reconcile.path --no-pager'
```

Read the latest recorded loop state:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.64.0.1 'sudo cat /var/lib/lv3-host-control-loops/status/latest.json'
```

Inspect the journal for the last five reconcile runs:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.64.0.1 'sudo journalctl -u lv3-host-control-loop-reconcile.service -n 5 --no-pager'
```

## Manual Trigger

Request an immediate path-triggered reconcile pass:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.64.0.1 "printf '%s\n' '{\"reason\":\"manual-check\"}' | sudo tee /var/lib/lv3-host-control-loops/requests/reconcile.request >/dev/null"
```

Then confirm the request file was consumed and a new journal entry appeared:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.64.0.1 'sudo test ! -e /var/lib/lv3-host-control-loops/requests/reconcile.request && sudo journalctl -u lv3-host-control-loop-reconcile.service -n 1 --no-pager'
```

## Notes

- The current loop records execution state only; ADR 0225 will later replace
  the placeholder reconcile body with a repo-managed `ansible-pull` path.
- Use `systemctl start lv3-host-control-loop-reconcile.service` for an explicit
  one-shot replay when you do not want to go through the path trigger.
