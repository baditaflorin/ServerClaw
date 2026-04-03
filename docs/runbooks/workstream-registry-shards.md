# Workstream Registry Shards

## Purpose

Use this runbook when creating, editing, validating, or releasing workstream metadata after ADR 0326 split the registry into shard files plus a generated compatibility assembly.

## Canonical Source Layout

- policy and shared metadata: `workstreams/policy.yaml`
- active workstreams: `workstreams/active/<workstream-id>.yaml`
- archived workstreams: `workstreams/archive/<year>/<workstream-id>.yaml`
- generated compatibility artifact for existing readers: `workstreams.yaml`

## Primary Commands

Regenerate the compatibility artifact after editing shard files:

```bash
python3 scripts/workstream_registry.py --write
```

Verify the committed `workstreams.yaml` still matches the shard source:

```bash
python3 scripts/workstream_registry.py --check
```

Inspect the full registry, including archived workstreams:

```bash
python3 scripts/workstream_registry.py --list
```

## Starting A Workstream

1. create or update the shard under `workstreams/active/`
2. update the workstream narrative under `docs/workstreams/`
3. regenerate `workstreams.yaml`
4. run `./scripts/validate_repo.sh agent-standards data-models workstream-surfaces`
5. create the matching git worktree with `scripts/create-workstream.sh <workstream-id>` if you need a fresh checkout

Each active workstream may edit its own shard directly. The compatibility artifact remains shared and generated.

## Releasing A Workstream

When release bookkeeping is complete, the release flow updates `canonical_truth.included_in_repo_version`, moves the shard out of `workstreams/active/` into `workstreams/archive/<year>/`, and regenerates `workstreams.yaml`.

That archive move now happens through the repo-managed canonical-truth path instead of a manual file shuffle.

## Validation

The repo validation contract now checks both of these invariants:

- the shard source layout is internally valid
- `workstreams.yaml` matches the generated compatibility assembly exactly

If `workstreams.yaml` is stale, rerun `python3 scripts/workstream_registry.py --write` and stage the result together with the shard edits.
