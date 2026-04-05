# Workstream ws-0331-runtime-pool-live-apply: Guarded Live Apply For The Remaining Runtime Pool Transition

- ADR: [ADR 0319](../adr/0319-runtime-pools-as-the-service-partition-boundary.md), [ADR 0320](../adr/0320-pool-scoped-deployment-surfaces-and-agent-execution-lanes.md), [ADR 0321](../adr/0321-runtime-pool-memory-envelopes-and-reserved-host-headroom.md), [ADR 0322](../adr/0322-memory-pressure-autoscaling-for-elastic-runtime-pools.md), [ADR 0323](../adr/0323-service-mobility-tiers-and-migration-waves-for-runtime-pools.md)
- Title: Bring the remaining runtime pools live from the latest `origin/main`
- Status: live_applied
- Branch: `codex/ws-0331-main-merge`
- Worktree: `.worktrees/ws-0331-exact-main`
- Owner: codex
- Depends On: `ws-0330-runtime-pool-transition-program`
- Conflicts With: none

## Scope

- verify the exact live baseline for `runtime-general-lv3`, `runtime-control-lv3`,
  and the current `docker-runtime-lv3` residual workload
- apply the remaining runtime-pool playbooks from the latest integrated mainline
- keep ADR 0321 honest by rebalancing host-side guest memory if a straight
  additive rollout would violate the 20 GiB floor
- update ADR metadata, workstream state, receipts, release truth, and
  validation evidence only after the live state is verified from the exact-main
  integration replay

## Expected Repo Surfaces

- `workstreams.yaml`
- `docs/workstreams/ws-0331-runtime-pool-live-apply.md`
- `docs/adr/0319-runtime-pools-as-the-service-partition-boundary.md`
- `docs/adr/0320-pool-scoped-deployment-surfaces-and-agent-execution-lanes.md`
- `docs/adr/0321-runtime-pool-memory-envelopes-and-reserved-host-headroom.md`
- `docs/adr/0322-memory-pressure-autoscaling-for-elastic-runtime-pools.md`
- `docs/adr/0323-service-mobility-tiers-and-migration-waves-for-runtime-pools.md`
- `docs/adr/.index.yaml`
- `docs/runbooks/configure-runtime-general-pool.md`
- `docs/runbooks/configure-runtime-control-pool.md`
- `docs/runbooks/runtime-pool-capacity-rebalance.md`
- `docs/runbooks/runtime-pool-memory-governance.md`
- `docs/runbooks/configure-runtime-pool-autoscaling.md`
- `playbooks/runtime-pool-capacity-rebalance.yml`
- `playbooks/services/runtime-pool-capacity-rebalance.yml`
- `playbooks/runtime-general-pool.yml`
- `playbooks/services/runtime-general-pool.yml`
- `playbooks/runtime-control-pool.yml`
- `playbooks/services/runtime-control-pool.yml`
- `collections/ansible_collections/lv3/platform/roles/step_ca_runtime/templates/docker-compose.yml.j2`
- `inventory/hosts.yml`
- `inventory/host_vars/proxmox_florin.yml`
- `inventory/group_vars/platform.yml`
- `config/capacity-model.json`
- `config/runtime-pool-autoscaling.json`
- `build/platform-manifest.json`
- `versions/stack.yaml`
- `README.md`
- `VERSION`
- `changelog.md`
- `docs/release-notes/*.md`
- `tests/test_step_ca_runtime_role.py`
- `receipts/live-applies/`

## Expected Live Surfaces

- Proxmox host `proxmox_florin`
- VM `runtime-general-lv3` at `10.10.10.91`
- VM `runtime-control-lv3` at `10.10.10.92`
- Nomad on `monitoring-lv3`
- residual application workloads on `docker-runtime-lv3`
- private host proxies and public NGINX edge routes backed by the migrated
  services

## Initial Baseline

- `origin/main` baseline commit is `9c58e76c652b9d5e65504d44412aad454207bcb8`
- `runtime-general-lv3` and `runtime-control-lv3` are absent live at workstream
  start
- the `runtime-control` Nomad namespace is absent at workstream start
- `docker-runtime-lv3` still carries control-plane and lightweight support
  services that the repo has already classified for other pools
- host-level available memory is about `22 GiB`, so the remaining pool rollout
  may require a coordinated memory rebalance to satisfy ADR 0321

## Merge Criteria

- the missing runtime pool guests exist live and pass their runbook-level
  verification
- the migrated services answer through their intended private and public routes
- the runtime-pool memory contract is represented truthfully in live guest
  allocations and receipts
- ADR metadata records the final repo and platform versions where live apply
  became true
- the exact-main integration replay passes validation before `origin/main`
  advances

## Progress Notes

### 2026-04-03: Capacity Rebalance And Restic Recovery Baseline

- the governed capacity rebalance is now fully live-applied end to end,
  including the `live-apply-service` post-apply restic trigger
- the committed and verified live memory settings are:
  - `docker-runtime-lv3`: `18 GiB`
  - `docker-build-lv3`: `12 GiB`
  - `coolify-lv3`: `6 GiB`
  - `artifact-cache-lv3`: `4 GiB`
- the Proxmox host now reports roughly `75 GiB` available memory after the
  replayed rebalance verification, preserving ADR 0321 headroom for
  `runtime-general-lv3` and `runtime-control-lv3`
- the restic self-heal path needed one additional repo fix before the wrapper
  could pass cleanly:
  - `playbooks/restic-config-backup.yml` now enables
    `linux_guest_firewall_recover_missing_docker_bridge_chains: true`
  - the restic live-apply trigger successfully rehydrated
    `/run/lv3-systemd-credentials/restic-config-backup/runtime-config.json`
    after the rebalance reboot and finished the backup trigger successfully
- live-apply evidence for the rebalance attempts is recorded under
  `receipts/live-applies/evidence/2026-04-03-ws-0331-runtime-pool-capacity-rebalance-live-apply-r*.txt`
- the next owned step remains the exact-main live apply for
  `runtime-general-lv3`, followed by `runtime-control-lv3`

### 2026-04-04: Exact-Main Runtime-Control Correction Loop

- the latest realistic exact-main baseline for the runtime-control replay was
  `origin/main@20a66bbf0` with repository version `0.178.3` and platform
  version `0.130.98`
- the first exact-main runtime-control replays exposed two separate failure
  modes:
  - a transient SSH reconnect race after guest-firewall evaluation on
    `runtime-control-lv3`
  - a stale live Proxmox per-guest firewall on `postgres-lv3` that still
    blocked `10.10.10.92 -> 10.10.10.50:5432` even though the repo inventory
    already declared that allowance
- the stale PostgreSQL firewall rule was corrected by replaying
  `lv3.platform.proxmox_network` directly from exact main, which restored the
  missing `IN ACCEPT -source 10.10.10.92/32 -p tcp -dport 5432` entry in
  `/etc/pve/firewall/150.fw`; see
  `receipts/live-applies/evidence/2026-04-04-ws-0331-proxmox-network-replay-r1.txt`
- the repo-side replay contract is now hardened too:
  `linux_guest_firewall` only resets the SSH transport when the rendered
  nftables policy actually changes, with focused coverage preserved in
  `receipts/live-applies/evidence/2026-04-04-ws-0331-targeted-tests-r1.txt`
- exact-main replay evidence for the runtime-control apply attempts is preserved
  under
  `receipts/live-applies/evidence/2026-04-04-ws-0331-runtime-control-mainline-live-apply-r*.txt`
- final live-apply verification, ADR metadata closeout, and protected-surface
  release integration remain pending the last successful exact-main recap

### 2026-04-05: Exact-Main Runtime-Pool Closeout

- the latest realistic mainline baseline fetched immediately before final
  integration was `origin/main@630f663bd4b35214ef866df0772acef48a6ac6fe` with
  repository version `0.178.5` and platform version `0.130.99`
- the final runtime-control correction loop closed two branch-local regressions
  that only appeared against the latest exact-main state:
  - Windmill seeding was still targeting the stale `ntfy/platform` resource
    path instead of `f/lv3/ntfy_platform`
  - the mail-platform runtime treated the expected `created|...` compose state
    as a hard failure during startup validation
- replay `r25` failed on the stale Windmill resource path, replay `r27` failed
  on the mail-platform `created|...` false negative, replay `r26` was
  terminated as a duplicate while the corrected replay was already running, and
  replay `r28` became the authoritative successful exact-main live apply
- `receipts/live-applies/evidence/2026-04-05-ws-0331-runtime-control-mainline-live-apply-r28.txt`
  captured the green recap that kept `runtime-control-lv3`, `postgres-lv3`,
  `proxmox_florin`, and the remaining production guests at zero failures while
  retiring the legacy control-plane copies from `docker-runtime-lv3`
- the first post-apply verification sweep in
  `receipts/live-applies/evidence/2026-04-05-ws-0331-runtime-pool-post-verify-r1.txt`
  exposed that `configure-runtime-control-pool.md` was still checking the
  OpenBao private proxy with a bare `curl --cacert ...` request even though the
  proxy intentionally requires a client certificate
- `receipts/live-applies/evidence/2026-04-05-ws-0331-runtime-pool-post-verify-r2.txt`
  is the authoritative final sweep: it records the corrected runtime-general
  and runtime-control substrate, route, Nomad namespace, public-route,
  host-private-proxy, OpenBao mTLS, healthy `step-ca`, legacy retirement, and
  capacity-governance verification set
- `receipts/live-applies/evidence/2026-04-05-ws-0331-step-ca-healthcheck-live-apply-r1.txt`
  captured the bounded `step-ca` replay that replaced the inherited image
  healthcheck with the repo-managed HTTPS probe after the runtime was otherwise
  healthy
- the governed post-apply restic trigger completed successfully and refreshed
  both `receipts/restic-backups/20260405T101939Z.json` and
  `receipts/restic-snapshots-latest.json`; the later bounded `step-ca` replay
  then refreshed `receipts/restic-backups/20260405T103625Z.json` as well
- ADR 0321 and ADR 0323 are now live-applied at platform version `0.130.100`;
  ADR 0322 remains repo-implemented only because this closeout did not roll out
  a live Nomad Autoscaler controller or emit any scale-action receipts
- the integrated mainline closeout for this workstream stamps repository
  version `0.178.6` and platform version `0.130.100`
