# Fork-shape fixture inventories — ADR 0444

Three synthetic identity overlays covering the deployment-shape matrix the
pre-push gate exercises (item 12 of ADR 0444). Each file mirrors the schema of
`.local/identity.yml` (the gitignored per-deployment overlay), but uses
publishable values so the fixtures can live in-repo.

| File | Purpose | Anchors a deployment with… |
|------|---------|----------------------------|
| `lv3-shape.yml`        | Current production shape          | DNS-label-only prefix (`lv3`) — exercises the path where `config_prefix == sql_prefix == pve_prefix == unix_prefix`. |
| `0fork-shape.yml`      | Fork shape (digit-prefixed label) | `0fork` first label — exercises the path where SQL/Unix flavors must strip a leading digit (`fork`) but PVE/config keep the full label. |
| `synthetic-shape.yml`  | Third unrelated identity          | `testfork.invalid` — catches lv3/0fork coincidences that look generic but are not, and proves a third deployment can be added without code changes. |

## Contract

Each fixture MUST:

1. Set `platform_domain`, `platform_operator_email`, `platform_operator_name`.
2. Produce a non-empty result for every `platform_identity.*` flavor
   (`config_prefix`, `sql_prefix`, `pve_prefix`, `unix_prefix`, `dns_label`).
3. Avoid collisions: no two fixtures may resolve to the same `sql_prefix` or
   `unix_prefix`. Collisions defeat the purpose of running the matrix because a
   role passing on lv3 by accident also passes on the fork.
4. Use only publishable values. No real operator emails, no `.local/`-style
   secrets. These files are committed and replicated to the public mirror.

## Usage

The fixtures are consumed by:

- `scripts/converge_dry_run.py` (item 10) — runs `ansible-playbook --check
  --diff` for changed roles against each fixture in turn.
- `tests/test_fixture_inventories.py` — smoke test that each fixture renders
  the `platform_identity` filter without error and produces the expected
  unique prefixes.

The fixtures intentionally do NOT include real topology (host IPs, VM
counts). Topology lives in `inventory/host_vars/proxmox-host.yml` and is
overlaid per-deployment via ADR 0430 / ADR 0440. Item 5 of ADR 0444 will add
a parallel set of `host_vars/*-shape.yml` fixtures once `inventory/hosts.yml`
is parameterized from `deployment-model.yaml`.

## Adding a fixture

1. Pick a publishable domain whose first DNS label is unique vs. existing
   fixtures across all five flavors.
2. Copy `synthetic-shape.yml` and edit the four scalars at the top.
3. Add an entry to the table above.
4. Update `tests/test_fixture_inventories.py::EXPECTED_FIXTURES`.
5. Update `scripts/converge_dry_run.py::FIXTURE_INVENTORIES` once that script
   exists.
