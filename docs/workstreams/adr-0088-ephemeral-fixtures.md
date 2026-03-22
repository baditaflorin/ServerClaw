# Workstream ADR 0088: Ephemeral Infrastructure Fixtures

- ADR: [ADR 0088](../adr/0088-ephemeral-infrastructure-fixtures.md)
- Title: On-demand disposable Proxmox VMs for role testing, Packer validation, and staging integration checks
- Status: ready
- Branch: `codex/adr-0088-ephemeral-fixtures`
- Worktree: `../proxmox_florin_server-ephemeral-fixtures`
- Owner: codex
- Depends On: `adr-0082-remote-build-gateway`, `adr-0084-packer-pipeline`, `adr-0085-opentofu-vm-lifecycle`, `adr-0072-staging-environment`
- Conflicts With: none
- Shared Surfaces: `tofu/`, `tests/`, `Makefile`, Proxmox staging VLAN (`vmbr20`)

## Scope

- create `tests/fixtures/` directory with fixture definition YAML files for three initial fixtures: `docker-host-fixture.yml`, `postgres-host-fixture.yml`, `ops-base-fixture.yml`
- write `tofu/modules/proxmox-fixture/` — thin wrapper around `proxmox-vm` module with `lifetime_minutes`, `vmid_range`, and staging-specific defaults
- write `scripts/vmid_allocator.py` — scans Proxmox for in-use VMIDs and returns next free slot in the fixture range `9100–9199`
- add `make fixture-up FIXTURE=<name>`, `make fixture-down FIXTURE=<name>`, `make fixture-list` targets
- write Windmill workflow `fixture-expiry-reaper` — polls `receipts/fixtures/` every 15 minutes, destroys expired fixtures
- write `molecule/drivers/proxmox-fixture/` — custom Molecule driver that delegates create/destroy to `make fixture-up/down`
- demonstrate the driver with one existing role migrated to use it (e.g., `docker_runtime`)
- write `docs/runbooks/ephemeral-fixtures.md`

## Non-Goals

- Molecule tests for all 40+ roles (each is a separate workstream task)
- LXC fixture support (VMs only)

## Expected Repo Surfaces

- `tests/fixtures/*.yml` (3 fixture definitions)
- `tofu/modules/proxmox-fixture/{main,variables,outputs}.tf`
- `scripts/vmid_allocator.py`
- updated `Makefile` (3 new fixture targets)
- Windmill script `config/windmill/scripts/fixture-expiry-reaper.py`
- `molecule/drivers/proxmox-fixture/` (custom driver)
- `collections/lv3/platform/roles/docker_runtime/molecule/` (demo molecule scenario)
- `receipts/fixtures/.gitkeep`
- `docs/runbooks/ephemeral-fixtures.md`
- `docs/adr/0088-ephemeral-infrastructure-fixtures.md`
- `docs/workstreams/adr-0088-ephemeral-fixtures.md`
- `workstreams.yaml`

## Expected Live Surfaces

- `make fixture-up FIXTURE=docker-host` provisions a VM on `vmbr20` within 5 minutes
- `make fixture-down FIXTURE=docker-host` destroys it and removes the receipt
- Windmill `fixture-expiry-reaper` is scheduled every 15 minutes

## Verification

- `make fixture-up FIXTURE=docker-host` completes and the verify URL (Portainer health) returns HTTP 200
- `make fixture-down FIXTURE=docker-host` completes and the VMID is no longer present in Proxmox
- `make fixture-up` twice concurrently allocates different VMIDs (vmid_allocator.py race-free)
- leave a fixture running past its `lifetime_minutes`; verify the reaper destroys it in the next 15-minute window

## Merge Criteria

- end-to-end fixture lifecycle (up → verify → down) demonstrated and recorded in a receipt
- Molecule `docker_runtime` scenario passes with the `proxmox-fixture` driver
- `fixture-expiry-reaper` Windmill workflow enabled and confirmed to trigger on schedule

## Notes For The Next Assistant

- the expiry reaper must use atomic state: read all receipts, identify expired, destroy one at a time, and write a `reaper-run.json` receipt after each run; never destroy a fixture that has been manually extended (add `extend_minutes` field to fixture YAML)
- `make fixture-list` should show: fixture name, VMID, IP, age, remaining lifetime, and current health check status — all in a single table output
- the `molecule` custom driver is invoked with environment variables: `MOLECULE_FIXTURE_NAME`, `MOLECULE_FIXTURE_IP`; the driver writes these to a `molecule.env` file that Molecule picks up for the test run
