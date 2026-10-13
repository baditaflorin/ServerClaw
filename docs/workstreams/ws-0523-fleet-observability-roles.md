# Workstream ws-0523: Codify the fleet observability and Postgres backup changes

## Goal

On 2026-10-11 and 2026-10-12 the node exporters, the exporter listener arrangement, a guest firewall rule, two advertised
Tailscale routes and the Postgres backup path (vzdump to Proxmox Backup Server, pgBackRest preparation) were set up by hand
on the 0mcp hypervisor and on the 0docker, 0database and 0own fleets. Only the 0mcp guests had infrastructure-as-code. This
workstream puts those changes under version control without triggering a converge: a separate playbook, an inventory that is
only used with an explicit `-i`, and a guard that refuses to run without `--limit`.

## Scope

- `inventory/fleet-observability.yml`: one group per fleet seeded from the SSH aliases, plus role groups for the hosts that
  have something to converge.
- `fleet_node_exporter`: listen addresses, textfile directory ownership, systemd socket proxies, `tailscale serve` forwards,
  and a port-plan check so the exporter and a proxy can never claim the same address and port.
- `fleet_guest_firewall`: the github-mirror nftables file (the 0mcp `nginx` rule stays in PR #299's `network_policy`).
- `fleet_tailscale_node`: advertised routes only, with `tailscale set`.
- `fleet_pg_backup`: the vzdump hook (with the size/duration fix), PBS storage and backup job, prepared pgBackRest
  configuration, PBS user/ACL/prune job.
- `scripts/fleet_observability_render.py`: offline rendering plus a read-only live comparison.

## Out of scope

- The tailnet policy (separate workstream), secrets (token, passphrase), `archive_mode`, the pgBackRest repository choice,
  installing the pgBackRest timer, the `.prom` writers, hosts that pre-date this change.
- Update 2026-10-12: `woodpecker-0exec-build-metrics-proxy.socket` was moved to tailnet `:9103` live, given `FreeBind=true`,
  and is now modelled as managed (see "Build-metrics proxy" in the runbook). The stale `woodpecker-exec-proxy@9100.socket` is
  modelled as disabled. Removing the old `:9100` grant and cluster firewall rule still needs the user's OK.

## Validation

Offline Jinja rendering and `tests/test_fleet_observability_roles.py` (including the vzdump hook run against a stub), and a
read-only live-vs-rendered diff on every modelled host. `ansible-lint`, `yamllint` and `--syntax-check` were not available
locally. See `docs/runbooks/fleet-observability.md`.

## Live state

All changes are already live. After merge, converge host by host with `--check --diff` first.
