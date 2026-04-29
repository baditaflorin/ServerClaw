# ADR 0462: Topology Pre-Commit Schema Hook

- Status: Accepted
- Implementation Status: Implemented (`scripts/validate_topology_schema.py` + `validate-topology-schema` hook in `.pre-commit-config.yaml`)
- Date: 2026-04-29
- Concern: shift-left, schema-drift, converge-time-failure
- Tags: pre-commit, topology, schema, deployment-v1
- Implements: improvement #1 from the 2026-04-29 reliability review
- Depends on: ADR 0440, ADR 0457

---

## Context

The 2026-04-28 ops.0fork.com recovery surfaced a class of bug we have no shift-left signal for. `.local/deployments/0fork/topology.yml` was committed with bare `{name, vmid, ipv4}` entries and no `role` field. The deployment loader (`scripts/generate_platform_vars.py:411`) treats `role` as required and fails at converge time, ~30 minutes deep into a multi-VM run, with `host_vars.proxmox_guests[0].role must be a non-empty string`. ws-0448 patched the loader to default `role` to `name`, but that hides the original schema violation rather than catching it.

Today's static signals on topology files:

- The committed `inventory/host_vars/proxmox-host.yml` is reviewed by humans on PRs.
- `scripts/deployment.py validate` checks per-deployment topology against the committed schema, but the operator has to remember to run it.
- The pre-push gate runs `validate_repository_data_models.py`, which checks platform consistency but not the per-deployment topology shape.

## Decision

Add a pre-commit hook that runs `scripts/validate_topology_schema.py` against any committed topology file. The script:

1. Loads `config/contracts/deployment-v1/topology.schema.json` (the same schema `scripts/deployment.py` uses).
2. Filters input paths to those that "look like" topology (have a top-level `proxmox_guests` key) — pre-commit can hand it any file matching the glob, and `inventory/host_vars/proxmox-host.yml` is the only committed topology today, but the heuristic future-proofs against new topology paths.
3. Validates each surviving file with `jsonschema.Draft202012Validator`. Falls back to a minimal required-keys check when `jsonschema` is not installed (so pre-commit works on a fresh checkout).
4. Returns exit 1 on any violation with one stderr line per error in `<path>:<jsonpath>: <message>` format.

Hook entry in `.pre-commit-config.yaml`:

```yaml
- id: validate-topology-schema
  name: ADR 0462 — validate proxmox_guests topology against deployment-v1 schema
  entry: bash -c 'uv run --quiet --with pyyaml --with jsonschema python3 scripts/validate_topology_schema.py "$@" --quiet' --
  language: system
  pass_filenames: true
  files: ^(inventory/host_vars/proxmox-host\.yml)$
```

The hook fires on changes to the committed canonical topology. `.local/` paths are gitignored so pre-commit never sees them; operators who want to validate per-deployment overlays can run the script directly:

```bash
python3 scripts/validate_topology_schema.py
# (no args = walks committed proxmox-host.yml + .local/deployments/*/topology.yml)
```

### Why pre-commit and not pre-push

Pre-commit gives the author the error before the commit hash is created. The 2026-04-28 incident's commit was already on a branch and pushed before the runtime loader rejected it. Pushing a known-bad commit is wasted work. Pre-push catches it later but pre-commit catches it earlier.

### Why a custom script and not `pre-commit-hooks`'s `check-jsonschema`

`pre-commit-hooks` doesn't ship a generic JSON Schema validator that hits a relative repo path. Vendoring the validator in-tree keeps the schema and the validator co-located, and the script is also reusable as a CI step or operator one-liner.

## Consequences

- A committed topology that doesn't match the schema is rejected at `git commit` time with a clear `<path>:<jsonpath>` error.
- The runtime loader's `role` auto-fill (ws-0448) becomes belt-and-suspenders rather than the only signal.
- New deployment overlays that operators write under `.local/deployments/<slug>/topology.yml` are not pre-commit-validated (they're gitignored), but `python3 scripts/validate_topology_schema.py` is now the operator-facing validation entry point.

## References

- [ADR 0440 — Per-Deployment Identity & Artifact Isolation](0440-per-deployment-identity-and-artifact-isolation.md)
- [ADR 0457 — Host-Pinning via deployment_owner](0457-host-pinning-deployment-owner.md) — adds `deployment_owner` field to the topology schema; this hook validates the new field's shape.
- `config/contracts/deployment-v1/topology.schema.json` — the schema the hook validates against.
