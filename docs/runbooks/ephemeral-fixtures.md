# Ephemeral Fixtures

## Purpose

ADR 0088 adds disposable Proxmox VMs for integration tests, real-role Molecule runs, and short-lived staging checks without polluting the long-lived guest inventory.

## Repo Surfaces

- fixture definitions: [tests/fixtures/](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/tests/fixtures)
- lifecycle manager: [scripts/fixture_manager.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/fixture_manager.py)
- governed pool seed: [config/capacity-model.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/capacity-model.json)
- VMID allocator: [scripts/vmid_allocator.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/vmid_allocator.py)
- OpenTofu wrapper module: [tofu/modules/proxmox-fixture/](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/tofu/modules/proxmox-fixture)
- Molecule driver: [molecule/drivers/proxmox-fixture/](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/molecule/drivers/proxmox-fixture)
- Windmill expiry reaper: [config/windmill/scripts/ephemeral-vm-reaper.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/windmill/scripts/ephemeral-vm-reaper.py)
- VMID range guard: [scripts/validate_ephemeral_vmid.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/validate_ephemeral_vmid.py)

## Commands

```bash
make fixture-up FIXTURE=docker-host PURPOSE=adr-0106-test OWNER=codex LIFETIME_HOURS=1 EPHEMERAL_POLICY=integration-test
make fixture-list
make fixture-down VMID=910

uvx --with pyyaml python scripts/validate_ephemeral_vmid.py --validate

lv3 fixture create docker-host --purpose adr-0106-test --owner codex --lifetime-hours 1 --policy integration-test --dry-run
lv3 fixture destroy --vmid 910 --dry-run
```

`fixture-up` will:

1. Read `tests/fixtures/<name>-fixture.yml`
2. Enforce the ADR 0106 capacity budget for the governed ephemeral pool
3. Allocate a free VMID from the governed `910-979` range
4. Stamp owner, purpose, policy, and expiry tags onto the VM configuration
5. Apply the generated OpenTofu runtime in `.local/fixtures/runtime/<receipt-id>/`
6. Wait for SSH through the Proxmox host jump path
7. Converge the declared roles unless `--skip-role-converge` is used
8. Run the declared verification checks unless `--skip-verify` is used
9. Write an active receipt under `receipts/fixtures/<receipt-id>.json`

`fixture-down` destroys the matching active receipt when one exists, and can also destroy a governed ephemeral VM directly by `VMID` when only the Proxmox-side VM remains.

`fixture-list` prints fixture name, VMID, owner, purpose, IP, remaining lifetime, and current health. When Proxmox access is available it reads the cluster state for the governed ephemeral range instead of only reading local receipts.

## Runtime State

- Active receipts: `receipts/fixtures/*.json`
- Reaper receipts: `receipts/fixtures/reaper-run-*.json`
- Ignored local state and history: `.local/fixtures/`

The tracked repository keeps only [receipts/fixtures/.gitkeep](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/receipts/fixtures/.gitkeep) plus [receipts/fixtures/.gitignore](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/receipts/fixtures/.gitignore) so fixture runs do not dirty the git tree.

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

It scans the governed `910-979` pool, destroys expired ephemeral VMs, adds a one-hour grace expiry tag to unowned VMs found in that range, and writes a `reaper-run-<timestamp>.json` summary receipt.

The live Windmill worker path uses the mounted repo checkout at `/srv/proxmox_florin_server`. The reaper now prefers a repo-local Proxmox API token payload mirrored to `/srv/proxmox_florin_server/.local/proxmox-api/lv3-automation-primary.json` because the sandboxed Windmill job environment does not reliably inherit the runtime env contract during `run_wait_result` execution.

## Live Rollout Notes

- Repository automation shipped in repo version `0.97.0`; the first verified production live apply completed on `2026-03-26` in platform version `0.130.20`.
- Windmill schedule `f/lv3/ephemeral_vm_reaper_every_30m` is now enabled on `docker-runtime-lv3`.
- Manual API verification from the controller returned `{"expired_vmids":[],"retagged_vmids":[],"skipped_vmids":[],"warned_vmids":[]}` and wrote `/srv/proxmox_florin_server/receipts/fixtures/reaper-run-20260326T143309Z.json`.
- The 2026-03-26 live path required committed runtime changes in the Windmill role plus two host-side operating details that are now documented here: mirroring the Proxmox token payload into the mounted worker checkout and keeping `receipts/fixtures/` writable for worker-generated reaper receipts.
