# Workstream Registry Shards

## Purpose

Use this runbook when creating, editing, validating, or releasing workstream metadata after ADR 0326 split the registry into shard files plus a generated compatibility assembly.

## Canonical Source Layout

- policy and shared metadata: `workstreams/policy.yaml`
- active workstreams: `workstreams/active/<workstream-id>.yaml`
- archived workstreams: `workstreams/archive/<year>/<workstream-id>.yaml`
- generated compatibility artifact for existing readers: `workstreams.yaml`

## Path Rules

- committed `worktree_path` and `doc` values must stay repository-relative and must not escape the repo with `..`
- the default portable worktree convention is `.worktrees/<workstream-id>`
- local operators may create a worktree elsewhere for their own session, but committed metadata should normalize back to the in-repo portable path

## Status Guidance

- if a workstream is merge-ready but waiting on an external publication window or shared validation infrastructure, keep `status: ready_for_merge` and record the specific blocker under `blockers:` instead of downgrading the release-candidate status

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

Keep the committed metadata fork-first and repository-relative:

- `worktree_path` should stay under `.worktrees/` or another repo-local path
- `doc` should point at the canonical in-repo document under `docs/`
- do not commit `../...`, `/absolute/...`, or another worktree's nested `.../docs/...` path

Each active workstream may edit its own shard directly. The compatibility artifact remains shared and generated.

## Releasing A Workstream

When release bookkeeping is complete, the release flow updates `canonical_truth.included_in_repo_version`, moves the shard out of `workstreams/active/` into `workstreams/archive/<year>/`, and regenerates `workstreams.yaml`.

That archive move now happens through the repo-managed canonical-truth path instead of a manual file shuffle.

## Validation

The repo validation contract now checks both of these invariants:

- the shard source layout is internally valid
- `workstreams.yaml` matches the generated compatibility assembly exactly

If `workstreams.yaml` is stale, rerun `python3 scripts/workstream_registry.py --write` and stage the result together with the shard edits.
