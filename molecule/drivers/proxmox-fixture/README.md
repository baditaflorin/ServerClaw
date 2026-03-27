# Proxmox Fixture Driver

This delegated Molecule driver provisions a repo-managed ADR 0088 fixture through `scripts/fixture_manager.py`.

Required environment:

- `MOLECULE_FIXTURE_NAME`

Optional environment:

- `MOLECULE_FIXTURE_SKIP_VERIFY=1`
- `MOLECULE_FIXTURE_RECEIPT`

`create.yml` writes a `molecule.env` file with:

- `MOLECULE_FIXTURE_NAME`
- `MOLECULE_FIXTURE_IP`
- `MOLECULE_FIXTURE_RECEIPT`
