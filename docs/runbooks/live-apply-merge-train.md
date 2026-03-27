# Live Apply Merge Train

This runbook documents ADR 0182: the merge-train gate that batches ready workstreams, builds a rollback bundle before mutation begins, and reverts the integration set when an apply step fails.

## Inputs

- workstream registry: `workstreams.yaml`
- merge-train operator entrypoint: `scripts/live_apply_merge_train.py`
- Make targets:
  - `make live-apply-train-status`
  - `make live-apply-train-queue WORKSTREAMS="adr-a adr-b"`
  - `make live-apply-train-plan`
  - `make live-apply-train-bundle`
  - `make live-apply-train-run`
  - `make live-apply-train-rollback BUNDLE=receipts/rollback-bundles/<bundle>.json`

## Required Workstream Metadata

Each train-eligible workstream must declare `live_apply` metadata in `workstreams.yaml`:

- `docs.adrs`: ADR documents that justify the change
- `docs.runbooks`: runbooks updated with the operator path
- `ownership.surfaces`: declared surface ownership or shared-contract scope
- `validation_checks`: commands that must pass before queue admission or planning
- `apply_plan.waves`: the steps that perform the live mutation
- `rollback_bundle`: strategy plus executable rollback steps

If `ownership.surfaces` is omitted, the merge train falls back to the workstream's `shared_surfaces` list as its serialization boundary.

## Queue A Train

1. Confirm the workstream branch exists locally or on `origin`.
2. Confirm `ready_to_merge: true` is set for the selected workstream.
3. Queue it:

```bash
make live-apply-train-queue WORKSTREAMS="adr-0182-live-apply-merge-train"
```

4. Inspect the current queue and planned waves:

```bash
make live-apply-train-status
make live-apply-train-plan
```

The plan serializes workstreams that declare the same owned or shared surface group and keeps disjoint workstreams in the same wave.

## Create The Rollback Bundle

Build the bundle before the train is run:

```bash
make live-apply-train-bundle
```

The bundle records:

- the pre-apply `HEAD`
- the selected workstreams and wave plan
- snapshots for any `file_restore` rollback steps
- a generated `git_revert_merges` step that is filled in with the actual merge commits during execution

Set `LV3_ROLLBACK_BUNDLE_DIR` if the artifacts should be written outside the repo checkout.

## Run The Train

```bash
make live-apply-train-run
```

Execution order:

1. validate queued workstreams
2. create the rollback bundle
3. merge each queued branch into the current integration branch with `--no-ff`
4. run each workstream's `apply_plan` in wave order
5. mark the queue entries `applied` if every step succeeds

## Failed Apply And Rollback

If an apply step fails, the train:

1. executes any declarative rollback steps such as `file_restore` or `shell`
2. reverts merge commits in reverse order using the generated rollback step
3. marks the queue entries `failed`
4. records the rollback outcome in the bundle metadata

Manual rollback steps of kind `runbook` are preserved in the bundle and reported as `manual_required`.

To rerun a bundle explicitly:

```bash
make live-apply-train-rollback BUNDLE=receipts/rollback-bundles/<bundle>.json
```
