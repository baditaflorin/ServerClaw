# Docker Runtime Bridge-Chain Loss

## Purpose

Recognize and recover the shared `docker-runtime` failure mode where the
Docker `DOCKER` or `DOCKER-FORWARD` chains disappear and repo-managed service
replays start destabilizing unrelated workloads.

## When To Use It

Use this runbook when one or more of these appear together on
`docker-runtime`:

- many unrelated containers are exited or restarting at the same time
- a live apply transcript shows `Restart Docker when required bridge chains are
  missing`
- `iptables -t nat -S DOCKER` or `iptables -t filter -S DOCKER-FORWARD` fails
  while `docker.service` is still active
- a service replay starts healthy enough, then unrelated workloads such as
  OpenBao sidecars, backup jobs, or app containers churn immediately after the
  shared Docker runtime preflight runs

## First Checks

Prefer the repo-managed jump path instead of ad hoc SSH wiring:

```bash
ANSIBLE_HOST_KEY_CHECKING=False ansible -i inventory/hosts.yml docker-runtime \
  --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -e proxmox_guest_ssh_connection_mode=proxmox_host_jump \
  -m shell \
  -a 'systemctl is-active docker && iptables -t nat -S DOCKER && iptables -t filter -S DOCKER-FORWARD && docker ps --format "{{.Names}} {{.Status}}"'
```

Also capture the current failed-unit view:

```bash
ANSIBLE_HOST_KEY_CHECKING=False ansible -i inventory/hosts.yml docker-runtime \
  --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -e proxmox_guest_ssh_connection_mode=proxmox_host_jump \
  -m shell \
  -a 'systemctl --failed --no-pager --no-legend || true'
```

If the guest is still reachable, do not immediately rerun multiple live applies.
Each replay can touch the same shared runtime prerequisites again and widen the
blast radius.

## Recovery Steps

1. Confirm whether the issue is scoped to bridge-chain loss on
   `docker-runtime` rather than host-wide Proxmox failure or a full guest
   outage.
2. If `docker.service` is active but the chains are missing, treat the runtime
   as degraded and stop additional service replays until a deliberate recovery
   path is chosen.
3. If most workloads are still up, schedule a maintenance window before any
   Docker daemon restart. A host-wide restart on this guest is disruptive by
   design.
4. Repo-managed replays that pass through `lv3.platform.linux_guest_firewall`
   now attempt one Docker restart automatically if the bridge-chain helper still
   fails after the nftables reload. If that replay already consumed its single
   restart or the guest is broadly degraded before any service converge begins,
   restart Docker once on `docker-runtime`, then re-check the chains and
   container state before touching service-specific playbooks.
5. After the runtime is stable again, rerun only the affected service converges
   from the repo root instead of replaying unrelated services.

Example manual maintenance command on the guest:

```bash
ANSIBLE_HOST_KEY_CHECKING=False ansible -i inventory/hosts.yml docker-runtime \
  --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -e proxmox_guest_ssh_connection_mode=proxmox_host_jump \
  -m shell \
  -a 'sudo systemctl restart docker && sleep 10 && systemctl is-active docker && iptables -t nat -S DOCKER && iptables -t filter -S DOCKER-FORWARD && docker ps --format "{{.Names}} {{.Status}}"'
```

## Observed Example

During the 2026-04-01 Grist exact-main replay:

- `receipts/live-applies/evidence/2026-04-01-ws-0279-grist-mainline-live-apply-r1-0.177.134.txt`
  recorded `lv3.platform.common : Restart Docker when required bridge chains are
  missing` at `2026-04-01T16:21:17Z`
- workstream `ws-0325-service-uptime-investigation` later confirmed that
  `docker-runtime` had many unrelated containers exited or stuck in restart
  loops, while the Proxmox host itself had no matching host-wide systemd
  failure pattern

Treat that chronology as the reference signature for this failure mode.

## After Recovery

- rerun the smallest affected service converge first
- verify `docker ps`, `systemctl --failed`, and the relevant service health
  checks before starting another replay
- document the recovery outcome in the owning workstream or receipt so later
  agents know whether the bridge-chain loss was transient, operator-restarted,
  or still unresolved
