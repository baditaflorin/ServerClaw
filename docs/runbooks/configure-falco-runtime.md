# Configure Falco Runtime

## Purpose

This runbook converges ADR 0300 by enabling repo-managed Falco syscall
monitoring on the selected production guests and routing WARNING+ findings
through the private Falco event bridge on `docker-runtime`.

It delivers:

- a private Falco event bridge on `docker-runtime` listening on the
  managed internal port `18084`
- the matching `ntfy` auth grant for `platform-security-critical` before the
  bridge starts emitting CRITICAL findings
- Falco `modern_ebpf` systemd services on `docker-runtime`,
  `docker-build`, `monitoring`, and `postgres`
- Loki journal relabels so Falco events land under `job="falco"`
- WARNING+ event fan-out to NATS subject `platform.security.falco`
- CRITICAL push notifications on ntfy topic `platform-security-critical`
- legacy mutation-audit JSONL entries with `surface="falco"`
- WARNING+ event delivery through the managed NATS JetStream bus on
  `runtime-control`, reached from the controller and the bridge via the
  repo-managed internal runtime-control target instead of a loopback-only
  assumption

## Entrypoints

- syntax check: `make syntax-check-falco`
- verify NATS streams: `make check-nats-streams`
- repair NATS streams when missing: `make apply-nats-streams`
- converge: `make converge-falco`

## Managed Artifacts

- bridge service directory: `/opt/lv3/falco-event-bridge`
- bridge environment file: `/opt/lv3/falco-event-bridge/falco-event-bridge.env`
- bridge systemd unit: `/etc/systemd/system/lv3-falco-event-bridge.service`
- Falco journald override: `/etc/systemd/system/falco-modern-bpf.service.d/lv3-journald.conf`
- Falco override config: `/etc/falco/config.d/lv3-runtime.yaml`
- Falco rules: `/etc/falco/rules.d/50-lv3-platform-overrides.yaml`
- mutation audit sink: `/var/log/platform/mutation-audit.jsonl`

## Verification

1. `make syntax-check-falco`
2. `make check-nats-streams`
3. If the platform event streams are missing or drifted, run `make apply-nats-streams` and then rerun `make check-nats-streams`.
4. `ANSIBLE_HOST_KEY_CHECKING=False ansible -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/inventory/hosts.yml docker-runtime -m shell -a 'systemctl is-active lv3-falco-event-bridge falco-modern-bpf && curl -fsS http://127.0.0.1:18084/healthz' --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -e proxmox_guest_ssh_connection_mode=proxmox_host_jump`
5. `ANSIBLE_HOST_KEY_CHECKING=False ansible -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/inventory/hosts.yml docker-runtime:docker-build:monitoring:postgres -m shell -a 'systemctl is-active falco-modern-bpf && falco --version' --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -e proxmox_guest_ssh_connection_mode=proxmox_host_jump`
6. Trigger the repo-managed smoke marker on each host and confirm one `platform.security.falco` envelope plus one `surface="falco"` audit entry per host, plus CRITICAL delivery into ntfy topic `platform-security-critical`.

## Notes

- The bridge is intentionally private and stays on `docker-runtime`; other
  guests only post Falco HTTP events over the internal guest network.
- The bridge publishes into the NATS JetStream runtime on
  `runtime-control`; controller-side verification helpers now prefer that
  governed target and only fall back to `docker-runtime` when the runtime
  control lane is unavailable.
- The rollout uses one repo-managed ntfy credential already shared with the
  private Alertmanager topic; ntfy grants that same identity publish rights to
  `platform-security-critical`, so `make converge-falco` also replays
  `ntfy_runtime` on `docker-runtime`.
- The ntfy topic uses a hyphenated slug rather than a dotted subject name
  because the live ntfy publish endpoint rejects dotted topic paths with
  `404 page not found`.
- The upstream `falco-modern-bpf.service` unit ships with `StandardOutput=null`;
  the repo-managed journald drop-in flips Falco back to `StandardOutput=journal`
  and `StandardError=journal` so runtime matches remain queryable through Loki.
- Falco rules and suppressions stay version controlled; do not hand-edit
  `/etc/falco` on the guests.
