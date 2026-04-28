# proxmox-fixture Molecule driver — STUB

This is a stub implementation of the `proxmox-fixture` Molecule driver
referenced by `roles/docker_runtime/molecule/default/molecule.yml` and
the future scaffold ws-0446 phase 4 will produce.

## Status

**STUB.** The driver does not actually provision a Proxmox guest. The
`create.yml` / `destroy.yml` playbooks declare the expected shape so
Molecule loads the scenario and the workstream that references this
path stops failing the traceability validator (ADR 0455 phase 7.3).

## Expected eventual behaviour

`create.yml` should:

1. Read `MOLECULE_FIXTURE_NAME` from the environment (e.g. `docker-host`).
2. Provision a Proxmox guest matching the named fixture under
   `tests/fixtures/inventories/`.
3. Wait for SSH on the management IP.
4. Write `{{ lookup('env', 'MOLECULE_EPHEMERAL_DIRECTORY') }}/inventory.json`
   so the converge play can target it.

`destroy.yml` should:

1. Stop and destroy the guest provisioned by `create.yml`.
2. Tolerate "guest already gone" without erroring.

## Why a stub now

The full implementation depends on:

- A Proxmox API client role (not yet available)
- `proxmox-fixture` driver inclusion in the Molecule scenario contract
- A decision on the bridge between `tests/fixtures/inventories/` and
  Proxmox guest specs

Phase 7 of the postmortem-driven self-healing roadmap (ADR 0455) lands
the stub now to **unblock the substrate** that the doctor's
`blocked_substrate` signal flagged. The full implementation is tracked
in ws-0446 phase 4.

## Activating

To use the stub in a Molecule scenario, set in `molecule.yml`:

```yaml
driver:
  name: delegated
provisioner:
  name: ansible
  playbooks:
    create: "{{ lookup('env', 'MOLECULE_PROJECT_DIRECTORY') }}/molecule/drivers/proxmox-fixture/create.yml"
    destroy: "{{ lookup('env', 'MOLECULE_PROJECT_DIRECTORY') }}/molecule/drivers/proxmox-fixture/destroy.yml"
```

The stubs will run, do nothing destructive, and let the converge play
proceed against `localhost`.
