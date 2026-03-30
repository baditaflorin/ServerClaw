# Configure Falco Runtime

## Purpose

This runbook converges ADR 0300 by enabling repo-managed Falco syscall
monitoring on the selected production guests and routing WARNING+ findings
through the private Falco event bridge on `docker-runtime-lv3`.

It delivers:

- a private Falco event bridge on `docker-runtime-lv3` listening on the
  managed internal port `18084`
- Falco `modern_ebpf` systemd services on `docker-runtime-lv3`,
  `docker-build-lv3`, `monitoring-lv3`, and `postgres-lv3`
- Loki journal relabels so Falco events land under `job="falco"`
- WARNING+ event fan-out to NATS subject `platform.security.falco`
- CRITICAL push notifications on ntfy topic `platform.security.critical`
- legacy mutation-audit JSONL entries with `surface="falco"`

## Entrypoints

- syntax check: `make syntax-check-falco`
- converge: `make converge-falco`

## Managed Artifacts

- bridge service directory: `/opt/lv3/falco-event-bridge`
- bridge environment file: `/opt/lv3/falco-event-bridge/falco-event-bridge.env`
- bridge systemd unit: `/etc/systemd/system/lv3-falco-event-bridge.service`
- Falco override config: `/etc/falco/config.d/lv3-runtime.yaml`
- Falco rules: `/etc/falco/rules.d/50-lv3-platform-overrides.yaml`
- mutation audit sink: `/var/log/platform/mutation-audit.jsonl`

## Verification

1. `make syntax-check-falco`
2. `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.64.0.1 ops@10.10.10.20 'systemctl is-active lv3-falco-event-bridge falco-modern-bpf && curl -fsS http://127.0.0.1:18084/healthz'`
3. `for host in 10.10.10.20 10.10.10.30 10.10.10.40 10.10.10.50; do ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.64.0.1 ops@$host 'systemctl is-active falco-modern-bpf && falco --version'; done`
4. Trigger the repo-managed smoke marker on each host and confirm one `platform.security.falco` envelope plus one `surface="falco"` audit entry per host.

## Notes

- The bridge is intentionally private and stays on `docker-runtime-lv3`; other
  guests only post Falco HTTP events over the internal guest network.
- The rollout uses one repo-managed ntfy credential already shared with the
  private Alertmanager topic; ntfy grants that same identity publish rights to
  `platform.security.critical`.
- Falco rules and suppressions stay version controlled; do not hand-edit
  `/etc/falco` on the guests.
