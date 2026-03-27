# ADR 0088: Ephemeral Infrastructure Fixtures

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.95.0
- Implemented In Platform Version: not yet
- Implemented On: 2026-03-23
- Date: 2026-03-22

## Context

Several testing and validation scenarios require real VMs, not mocks:

- **Packer template validation**: the only real test of a Packer template is booting the resulting VM and verifying the provisioner ran correctly
- **Ansible role molecule tests**: molecule's `docker` driver cannot test systemd-dependent roles; a real VM (or LXC container) is required
- **Staging promotion dry-runs**: ADR 0073 defines a staging environment, but currently there is no automated mechanism to provision a staging clone of a service for a specific ADR branch
- **Destructive runbook tests**: testing `break-glass` procedures, certificate rotation, or database failover requires an isolated target that can be destroyed without affecting production

Today, these scenarios either don't get tested (most common), run against production (dangerous), or require manual VM creation in the Proxmox UI (time-consuming, not repeatable).

The platform already has:
- OpenTofu for VM lifecycle (ADR 0085)
- Packer templates for fast VM cloning (ADR 0084)
- A staging VLAN (`vmbr20`, `10.20.10.0/24`) from ADR 0072
- The build server for remote execution (ADR 0082)

What is missing is a simple interface to say "give me a clean VM for 2 hours on the staging network, run these roles against it, then destroy it".

## Decision

We will implement **ephemeral infrastructure fixtures** — on-demand VMs provisioned from Packer templates, used for tests, and destroyed automatically.

### Fixture definition format

Fixtures are declared in `tests/fixtures/`:

```yaml
# tests/fixtures/docker-host-fixture.yml
fixture_id: docker-host
template: lv3-docker-host         # Packer template (ADR 0084)
vmid_range: [910, 979]             # VMID pool for ephemeral VMs
network:
  bridge: vmbr20                   # staging bridge (ADR 0072)
  ip_cidr: 10.20.10.100/24
  gateway: 10.20.10.1
resources:
  cores: 2
  memory_mb: 2048
  disk_gb: 20
lifetime_minutes: 120              # auto-destroy after 2 hours
tags:
  - ephemeral
  - fixture
roles_under_test:
  - lv3.platform.docker_runtime
verify:
  - url: http://10.20.10.100:9000   # Portainer health check
    expected_status: 200
    timeout_seconds: 60
```

### `make fixture-up FIXTURE=<name>`

1. Calls `remote_exec.sh fixture-up docker-host` on the build server
2. On build server: runs `tofu apply` with the fixture module, cloning from the Packer template (< 60 s)
3. VM boots on `vmbr20`; build server waits for SSH readiness (< 30 s)
4. Runs the specified Ansible roles against the fixture VM
5. Runs the `verify` health checks
6. Outputs: fixture VMID, IP, SSH fingerprint, and pass/fail status
7. Records fixture metadata in `receipts/fixtures/<fixture-id>-<timestamp>.json`

### `make fixture-down FIXTURE=<name>`

Destroys the fixture VM via `tofu destroy` and removes its state entry. Can be called manually or triggered by the `lifetime_minutes` expiry timer.

### Lifetime enforcement

ADR 0106 now governs the shared ephemeral VM lifecycle. The repository implementation uses the cluster-aware Windmill entrypoint `ephemeral-vm-reaper`, which reads the governed 910-979 pool, destroys expired VMs, and applies a one-hour grace-period expiry tag to unowned VMs that appear in the ephemeral range.

### Integration with Molecule

Molecule tests for complex systemd-dependent roles use a custom `molecule` driver (`molecule/drivers/proxmox-fixture/`) that calls `make fixture-up` for `create` and `make fixture-down` for `destroy`. This replaces the `docker` driver for roles that require a real init system.

### CI integration (Windmill)

The `pre-merge-integration` Windmill workflow provisions fixtures for every ADR branch that declares `requires_fixture: true` in its workstream doc. This gives ADR branches a live integration test against a real (but isolated, ephemeral) VM before merge.

### VMID pool management

Fixture VMIDs are drawn from the range `910–979`. ADR 0106 reserves this pool for all governed ephemeral VMs and adds explicit owner, purpose, and expiry metadata. A small Python helper ([scripts/vmid_allocator.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/vmid_allocator.py)) scans active Proxmox VMIDs and picks the first free slot in range.

## Consequences

**Positive**
- Ansible roles that require systemd, Docker, or PostgreSQL can be tested in real VMs automatically
- Packer templates are verified by actually booting and probing the resulting VM (previously untested)
- Staging integration tests run on isolated VMs; production is never the test target
- Automatic expiry prevents orphaned VMs from accumulating on the Proxmox host
- Fixture receipts provide a test history: "when did `docker_runtime` role last pass on a fresh VM?"

**Negative / Trade-offs**
- Each fixture consumes ~10–20 GB disk (thin-provisioned clone) during its lifetime; 10 simultaneous fixtures ≈ 200 GB; acceptable on a multi-TB pool
- `tofu apply` + VM boot + Ansible run ≈ 4–6 minutes per fixture; not suitable for sub-minute unit test loops
- OpenTofu and Packer pipeline (ADRs 0084, 0085) must be operational before fixtures can run

## Implementation Notes

- Repository implementation landed in `0.95.0` with the shared [proxmox-fixture module](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/tofu/modules/proxmox-fixture/main.tf), fixture definitions under [tests/fixtures/](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/tests/fixtures), the lifecycle helpers [scripts/fixture_manager.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/fixture_manager.py) and [scripts/vmid_allocator.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/vmid_allocator.py), and the Windmill expiry reaper at [config/windmill/scripts/fixture-expiry-reaper.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/windmill/scripts/fixture-expiry-reaper.py).
- The repository now exposes `make fixture-up`, `make fixture-down`, and `make fixture-list`, plus the delegated Molecule driver under [molecule/drivers/proxmox-fixture/](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/molecule/drivers/proxmox-fixture/).
- ADR 0106 refined the governance in `0.97.0`: the pool moved to `910–979`, repo-managed fixtures now stamp structured owner/purpose/expiry tags, and the reaper path became cluster-aware through [config/windmill/scripts/ephemeral-vm-reaper.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/windmill/scripts/ephemeral-vm-reaper.py).
- Live enablement still depends on ADR 0072's staging bridge being present on the host before fixture VMs can be booted on `vmbr20`, so the platform-version field remains unset.

## Alternatives Considered

- **Vagrant + VirtualBox locally**: runs on the laptop (CPU cost), not on the build server; rejected
- **Docker for all role tests**: cannot test systemd-dependent roles, LVM operations, or multi-NIC networking
- **Keep manual VM creation**: not repeatable, time-consuming, operators skip it

## Related ADRs

- ADR 0072: Staging/production topology (fixtures use `vmbr20` staging network)
- ADR 0082: Remote build execution gateway (fixture provisioning runs on build server)
- ADR 0083: Docker check runner (infra image runs Molecule tests)
- ADR 0084: Packer template pipeline (fixtures clone from these templates)
- ADR 0085: OpenTofu VM lifecycle (fixture module is a thin wrapper around the `proxmox-vm` module)
- ADR 0073: Promotion gate (ADR branches with `requires_fixture: true` get fixture-based integration tests)
