# Ephemeral Fixtures

## Purpose

ADR 0088 adds disposable Proxmox VMs for integration tests, real-role Molecule runs, and short-lived staging checks without polluting the long-lived guest inventory.

## Repo Surfaces

- fixture definitions: [tests/fixtures/](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/tests/fixtures)
- lifecycle manager: [scripts/fixture_manager.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/fixture_manager.py)
- governed pool seed: [config/capacity-model.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/capacity-model.json)
- lease and warm-pool catalog: [config/ephemeral-capacity-pools.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/ephemeral-capacity-pools.json)
- VMID allocator: [scripts/vmid_allocator.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/vmid_allocator.py)
- OpenTofu wrapper module: [tofu/modules/proxmox-fixture/](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/tofu/modules/proxmox-fixture)
- Molecule driver: [molecule/drivers/proxmox-fixture/](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/molecule/drivers/proxmox-fixture)
- Windmill expiry reaper: [config/windmill/scripts/ephemeral-vm-reaper.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/windmill/scripts/ephemeral-vm-reaper.py)
- VMID range guard: [scripts/validate_ephemeral_vmid.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/validate_ephemeral_vmid.py)

## Commands

```bash
make fixture-up FIXTURE=docker-host PURPOSE=adr-0186-smoke OWNER=codex LEASE_PURPOSE=preview LIFETIME_HOURS=1 EPHEMERAL_POLICY=integration-test
python3 scripts/fixture_manager.py create ops-base --purpose adr-0187-seed-check --policy integration-test --seed-class tiny
TF_VAR_proxmox_endpoint=https://127.0.0.1:18006/api2/json LV3_PROXMOX_API_INSECURE=true LV3_PROXMOX_HOST_ADDR=100.64.0.1 python3 scripts/fixture_manager.py create seed-staging-smoke --purpose adr-0187-seed-check --policy integration-test --seed-class tiny
make fixture-list
make fixture-pool-status
make fixture-pool-reconcile
make fixture-down VMID=910

uvx --with pyyaml python scripts/validate_ephemeral_vmid.py --validate

lv3 fixture create docker-host --purpose adr-0186-smoke --lease-purpose preview --owner codex --lifetime-hours 1 --policy integration-test --dry-run
lv3 fixture destroy --vmid 910 --dry-run
```

`fixture-up` will:

1. Read `tests/fixtures/<name>-fixture.yml`
2. Resolve the ADR 0186 pool policy, including the allowed lease purpose, local address allocation, protected capacity class, and declared spillover domain
3. Reuse a prewarmed stopped member when one is available, otherwise allocate a free VMID from the governed `910-979` range and build a cold member
4. Stamp owner, lease purpose, detailed purpose, policy, expiry, and pool metadata tags onto the VM configuration
5. Apply the generated OpenTofu runtime in `.local/fixtures/runtime/<receipt-id>/` only for cold or refill members
6. Wait for SSH through the Proxmox host jump path
7. Converge the declared roles unless `--skip-role-converge` is used
8. Stage the requested ADR 0187 seed snapshot under `/var/lib/lv3-seed-data/<receipt-id>/` when `--seed-class` is set
9. Run the declared verification checks unless `--skip-verify` is used
10. Write an active lease receipt under `receipts/fixtures/<receipt-id>.json`

`fixture-pool-reconcile` will:

1. Read [config/ephemeral-capacity-pools.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/ephemeral-capacity-pools.json)
2. Check the declared warm target per pool
3. Create any missing warm members as repo-managed stopped fixtures with dedicated pool-local addresses
4. Return an explicit spillover decision if local capacity is exhausted instead of silently consuming standby reservations

`fixture-pool-status` prints the current warm count, active lease count, local ceilings, and spillover target for each pool.

`fixture-down` destroys the matching active receipt when one exists, and can also destroy a governed ephemeral VM directly by `VMID` when only the Proxmox-side VM remains.

`fixture-list` prints fixture name, VMID, owner, purpose, IP, remaining lifetime, and current health. When Proxmox access is available it reads the cluster state for the governed ephemeral range instead of only reading local receipts.

When the local controller cannot reach the Proxmox API endpoint directly but can still SSH to the private management address, establish an SSH tunnel such as `ssh -N -L 18006:127.0.0.1:8006 ops@100.64.0.1` and run fixture commands with:

```bash
TF_VAR_proxmox_endpoint=https://127.0.0.1:18006/api2/json
LV3_PROXMOX_API_INSECURE=true
LV3_PROXMOX_HOST_ADDR=100.64.0.1
```

`fixture_manager.py` and `vmid_allocator.py` now honor that tunneled endpoint for controller-side API calls, and the Docker OpenTofu fallback automatically rewrites loopback endpoints to `host.docker.internal` inside the container runtime.

## Runtime State

- Active receipts: `receipts/fixtures/*.json`
- Reaper receipts: `.local/fixtures/reaper-runs/reaper-run-*.json`
- Ignored local state and history: `.local/fixtures/`

The tracked repository keeps only [receipts/fixtures/.gitkeep](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/receipts/fixtures/.gitkeep) plus [receipts/fixtures/.gitignore](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/receipts/fixtures/.gitignore) so fixture runs do not dirty the git tree.

The warm-pool reconciler writes branch-local and worker-local runtime evidence under `.local/fixtures/` so prewarming and refill activity stays auditable without polluting tracked truth.

## Molecule

The delegated driver is defined under [molecule/drivers/proxmox-fixture/create.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/molecule/drivers/proxmox-fixture/create.yml) and [molecule/drivers/proxmox-fixture/destroy.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/molecule/drivers/proxmox-fixture/destroy.yml).

The demo scenario lives under [collections/ansible_collections/lv3/platform/roles/docker_runtime/molecule/default/molecule.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/collections/ansible_collections/lv3/platform/roles/docker_runtime/molecule/default/molecule.yml).

The driver writes:

- `molecule.env` with the fixture name, IP, and receipt id
- `inventory.json` with the delegated inventory for later Molecule steps

## Expiry Reaper

Run the reaper manually with:

```bash
python3 config/windmill/scripts/ephemeral-vm-reaper.py
```

It scans the governed `910-979` pool, destroys expired ephemeral VMs, adds a one-hour grace expiry tag to unowned VMs found in that range, and writes a `reaper-run-<timestamp>.json` summary receipt under `.local/fixtures/reaper-runs/`.

The live Windmill worker path uses the mounted repo checkout at `/srv/proxmox_florin_server`. The reaper now prefers a repo-local Proxmox API token payload mirrored to `/srv/proxmox_florin_server/.local/proxmox-api/lv3-automation-primary.json` because the sandboxed Windmill job environment does not reliably inherit the runtime env contract during `run_wait_result` execution.

## Warm Pools

ADR 0186 adds lease-based warm pools for `ops-base`, `docker-host`, and `postgres-host`.

- The canonical declaration lives in [config/ephemeral-capacity-pools.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/ephemeral-capacity-pools.json).
- Each pool owns its warm count, refill target, local address set, maximum concurrent leases, protected capacity class, and auxiliary spillover domain.
- Warm members are created as normal governed fixtures, verified once, then stopped and tagged as `prewarmed`.
- Lease handoff updates the same receipt with the real owner, lease purpose, detailed purpose, and expiry. Returned fixtures are destroyed rather than put back into the pool so no mutated state leaks into the next consumer.
- Spillover is intentionally explicit. When the local ceilings or pool-local addresses are exhausted, the reconciler and lease path report the auxiliary-domain target instead of borrowing standby or recovery reservations.

## Live Rollout Notes

- Repository automation shipped in repo version `0.97.0`; the first verified production live apply completed on `2026-03-26` in platform version `0.130.20`.
- Windmill schedule `f/lv3/ephemeral_vm_reaper_every_30m` is now enabled on `docker-runtime-lv3`.
- Manual API verification from the controller returned `{"expired_vmids":[],"retagged_vmids":[],"skipped_vmids":[],"warned_vmids":[]}` and the latest integrated mainline verification wrote `/srv/proxmox_florin_server/.local/fixtures/reaper-runs/reaper-run-20260326T170554Z.json`.
- The 2026-03-26 live path required committed runtime changes in the Windmill role plus two host-side operating details that are now documented here: mirroring the Proxmox token payload into the mounted worker checkout and keeping `/srv/proxmox_florin_server/.local/fixtures/reaper-runs/` writable for worker-generated reaper receipts.
- ADR 0186 adds the worker script `f/lv3/ephemeral_pool_reconciler` plus schedule `f/lv3/ephemeral_pool_reconciler_every_15m`; the branch-local live replay details are recorded in the ADR, workstream, and receipt after verification completes.
- The 2026-03-28 ADR 0186 live verification confirmed that controller-side fixture checks should prefer `management_tailscale_ipv4` for the Proxmox jump host and `TF_VAR_proxmox_endpoint=https://100.64.0.1:8006/api2/json` for direct Proxmox API access, because the public host path was slower and less reliable for fixture SSH handoff during the replay.
