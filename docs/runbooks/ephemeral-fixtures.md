# Ephemeral Fixtures

## Purpose

ADR 0088 adds disposable Proxmox VMs for integration tests, real-role Molecule runs, and short-lived staging checks without polluting the long-lived guest inventory.

## Repo Surfaces

- fixture definitions: [tests/fixtures/](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/tests/fixtures)
- lifecycle manager: [scripts/fixture_manager.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/fixture_manager.py)
- VMID allocator: [scripts/vmid_allocator.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/vmid_allocator.py)
- OpenTofu wrapper module: [tofu/modules/proxmox-fixture/](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/tofu/modules/proxmox-fixture)
- Molecule driver: [molecule/drivers/proxmox-fixture/](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/molecule/drivers/proxmox-fixture)
- Windmill expiry reaper: [config/windmill/scripts/fixture-expiry-reaper.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/windmill/scripts/fixture-expiry-reaper.py)

## Commands

```bash
make fixture-up FIXTURE=docker-host
make fixture-list
make fixture-down FIXTURE=docker-host
```

`fixture-up` will:

1. Read `tests/fixtures/<name>-fixture.yml`
2. Allocate a free VMID from the fixture range
3. Apply the generated OpenTofu runtime in `.local/fixtures/runtime/<receipt-id>/`
4. Wait for SSH through the Proxmox host jump path
5. Converge the declared roles unless `--skip-role-converge` is used
6. Run the declared verification checks unless `--skip-verify` is used
7. Write an active receipt under `receipts/fixtures/<receipt-id>.json`

`fixture-down` destroys the matching active receipt(s), archives the terminal receipt under `.local/fixtures/archive/`, and removes the active receipt from `receipts/fixtures/`.

`fixture-list` prints fixture name, VMID, IP, age, remaining lifetime, and current health.

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
python3 config/windmill/scripts/fixture-expiry-reaper.py
```

It scans the active receipts, destroys expired fixtures one at a time, and writes a `reaper-run-<timestamp>.json` summary receipt.

## Live Rollout Notes

- Repo automation is complete in `0.95.0`, but live use still depends on ADR 0072's staging bridge on `vmbr20`.
- Do not enable the Windmill reaper schedule until `make fixture-up FIXTURE=docker-host` succeeds from `main` against the live host.
