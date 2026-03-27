# Workstream ADR 0088: Ephemeral Infrastructure Fixtures

- ADR: [ADR 0088](../adr/0088-ephemeral-infrastructure-fixtures.md)
- Title: On-demand disposable Proxmox VMs for role testing, Packer validation, and staging integration checks
- Status: merged
- Branch: `codex/adr-0088-ephemeral-fixtures`
- Worktree: `.worktrees/adr-0088-ephemeral-fixtures`
- Owner: codex
- Depends On: `adr-0082-remote-build-gateway`, `adr-0084-packer-pipeline`, `adr-0085-opentofu-vm-lifecycle`, `adr-0072-staging-environment`
- Conflicts With: none
- Shared Surfaces: `tofu/`, `tests/`, `Makefile`, Proxmox staging VLAN (`vmbr20`)

ADR 0106 later tightened the lifecycle governance: the active governed ephemeral pool is now `910-979`, not the original `9100-9199` workstream placeholder noted below.

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

- The repository-side implementation is complete on `main`, including the fixture module, lifecycle manager, Make targets, delegated Molecule driver, fixture definitions, and the Windmill expiry reaper.
- Runtime receipts are intentionally ignored under `receipts/fixtures/`; the durable history lives under `.local/fixtures/archive/` so fixture runs do not dirty the git worktree.
- Live rollout is still pending the staging bridge from ADR 0072 on the Proxmox host; once `vmbr20` exists, verify `make fixture-up FIXTURE=docker-host` and then seed the Windmill schedule from `main`.
