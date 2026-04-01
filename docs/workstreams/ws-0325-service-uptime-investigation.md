# Workstream ws-0325-service-uptime-investigation: Runtime Service Uptime Investigation

- ADR: [ADR 0319](../adr/0319-runtime-pools-as-the-service-partition-boundary.md)
- Title: Investigate why multiple live services are failing to remain healthy across the platform runtime pools
- Status: merged
- Branch: `codex/ws-0325-service-uptime-investigation`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0325-service-uptime-investigation`
- Owner: codex
- Depends On: `ADR 0123`, `ADR 0196`, `ADR 0319`
- Conflicts With: none
- Shared Surfaces: `workstreams.yaml`, `docs/workstreams/ws-0325-service-uptime-investigation.md`

## Scope

- collect failing-service evidence from the Proxmox host and affected guests using the repo-managed access paths
- determine whether the instability is caused by resource pressure, restart loops, dependency failures, or runtime drift
- capture the root cause and any bounded repo or operational follow-up needed so another agent can continue cleanly

## Non-Goals

- claiming a platform-wide fix before the failing-service pattern is reproduced and explained
- editing protected integration files unless this investigation later becomes a dedicated mainline integration step
- making opportunistic live changes that are not documented in the same workstream

## Expected Repo Surfaces

- `workstreams.yaml`
- `docs/workstreams/ws-0325-service-uptime-investigation.md`
- `docs/adr/0329-shared-docker-runtime-bridge-chain-checks-must-fail-safe-before-daemon-restart.md`
- `docs/adr/.index.yaml`
- `docs/runbooks/docker-runtime-bridge-chain-loss.md`
- `roles/common/tasks/docker_bridge_chains.yml`
- `collections/ansible_collections/lv3/platform/roles/common/tasks/docker_bridge_chains.yml`
- `tests/test_common_docker_bridge_chains_helper.py`
- `tests/test_docker_runtime_role.py`

## Expected Live Surfaces

- Proxmox host `systemd` health and recent journal failures
- affected guest service or container health reached through the governed jump path

## Verification

- `scripts/validate_repo.sh agent-standards`

## Findings

- The Proxmox host itself was stable during the investigation: `systemctl --failed`
  on `proxmox_florin` was empty and there was no matching host-wide OOM or
  reboot pattern.
- The service churn localized to `docker-runtime-lv3`, where many unrelated
  containers were exited or restarting while `dockerd` had restarted more
  recently than `containerd`.
- The most direct repo-managed trigger was preserved in
  `receipts/live-applies/evidence/2026-04-01-ws-0279-grist-mainline-live-apply-r1-0.177.134.txt`,
  which shows `lv3.platform.common : Restart Docker when required bridge chains
  are missing` at `2026-04-01T16:21:17Z` during the Grist exact-main live apply.
- The same chronology shows the shared `linux_guest_firewall` and
  `docker_runtime` prerequisites touching nftables and Docker bridge-chain
  checks on `docker-runtime-lv3` immediately before that restart.
- Secondary failures were present but not the primary uptime cause:
  `lv3-control-plane-backup.service` hit a `503`, `lv3-netbox-housekeeping.service`
  was missing `/run/lv3-secrets/netbox/runtime.env`, and
  `lv3-control-plane-restore-drill.service` on `backup-lv3` could not write
  `last-restore-drill.json` because of a permission error.

## Results

- Hardened the shared `common.docker_bridge_chains` helper so it now waits for
  bounded automatic chain recovery and fails safe instead of restarting
  `docker.service`.
- Added ADR 0329 to record the shared-runtime blast-radius rule behind that
  change.
- Added a dedicated runbook for bridge-chain loss on `docker-runtime-lv3` so a
  future operator can confirm the degraded state and choose a deliberate
  maintenance restart only when justified.

## Remaining Risks

- Many service-specific roles on `docker-runtime-lv3` still contain explicit
  Docker restart rescue paths. This workstream removes the shared preflight
  restart that was proven on 2026-04-01, but it does not yet eliminate every
  repo-managed daemon restart path on the shared runtime guest.
