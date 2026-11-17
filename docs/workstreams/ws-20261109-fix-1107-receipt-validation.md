# WS-20261109: the three 2026-11-07 live-apply receipts pass the receipt validator again

## Status

In review (branch `claude/fix-1107-receipt-validation`, ADR 0036). Receipt metadata only: no host is changed by it, nothing is applied, and no script, catalog, schema or CI file is edited. The pre-push gate result is in the pull request description.

## Goal

`scripts/live_apply_receipts.py --validate` has failed on `origin/main` since PR 686 (2026-11-07). The pre-push gate lane `schema-validation` runs it through `./scripts/validate_repo.sh data-models`; the gate run for a docs-only branch cut from main on 2026-11-09 ended 25 of 26 on exactly this and the hook refused the push. This change makes the receipt set valid again.

## What was wrong

The gate printed one error: `2026-11-07-log-shipping-labels-live-apply.json: workflow_id 'adr-0250-log-shipping-label-repair-and-main-replay' is not in workflow-catalog.json`. That is only the first of three, because the validator raises on the first bad receipt in file order. Run over every receipt of `origin/main` at `17519941c` (394 receipts, one `validate_receipt` call each), exactly three fail and all three are from 2026-11-07, one per merged PR that recorded a live apply:

| Receipt | Recorded by | `workflow_id` as merged | Why `workflow_id_is_known_or_historical` refuses it |
|---|---|---|---|
| `2026-11-07-log-shipping-labels-live-apply` (PR 686) | codex | `adr-0250-log-shipping-label-repair-and-main-replay` | not a catalog entry, not retired, and the historical form `adr-NNNN-<slug>-live-apply` needs the `-live-apply` suffix |
| `2026-11-07-vault-standby-ram-live-apply` (PR 688) | codex | `ws-20261107-vault-standby-ram-scratch` | the workstream id: eight digits where the `ws-NNNN-...` patterns allow four, and no `-live-apply` suffix |
| `2026-11-07-vault-standby-scratch-warning-live-apply` (PR 690) | codex | `ws-20261107-vault-standby-scratch-warning` | same |

Fixing only the first receipt would have moved the red to the second. And `workflow_id` is not the only defect: `validate_receipt` also requires `evidence_refs` (a non-empty list) and `notes` (a list), checked after `workflow_id`, and none of the three receipts has either. The JSON schema (`docs/schema/live-apply-receipt.schema.json`) requires neither, which is probably why they were written without. The other 391 receipts pass.

How the five PRs (686 to 690) reached main with this red is not established. What the repository shows: Woodpecker, the only blocking CI, runs `./scripts/validate_repo.sh json health-probes agent-standards` and a list of pytest files, not `data-models` or the receipt validator, and all five had a green Woodpecker status; the pre-push gate runs on the pusher's side only, and when its remote run fails the hook falls back to `scripts/run_gate_fallback.py`, which reruns unresolved checks or the lanes selected for the changed files, not necessarily every check. Which of these applied to each push cannot be read from the repository.

## Change

Only the three receipts, and in each only the keys `workflow_id`, `evidence_refs` and `notes` (compared key by key against `origin/main`: every other key, including `verification`, `targets`, `source_commit`, `adr` and `limitations`, is identical).

- **`workflow_id`** takes the `adr-NNNN-<slug>-live-apply` form that the validator accepts for applies that ran no catalog workflow. 229 existing receipts carry an id of this form, and in 227 of them NNNN is the receipt's own `adr`. The author's label is kept: `adr-0250-log-shipping-label-repair-and-main-replay` gains the suffix; `ws-20261107-vault-standby-ram-scratch` and `ws-20261107-vault-standby-scratch-warning` become `adr-0100-vault-standby-ram-scratch-live-apply` and `adr-0100-vault-standby-scratch-warning-live-apply` (`0100` is the receipts' own `adr`). No workflow is invented and no catalog entry is added. The tools that read receipts (`agent_tool_registry.py`, `deployment_history.py`, `ops_portal/app.py`, `declared_live_attestation.py`) only copy `workflow_id` into their output; none filters or joins on it. The workstream ids `ws-20261107-vault-standby-ram-scratch` and `ws-20261107-vault-standby-scratch-warning` themselves are not touched; only the receipts stop reusing them as a `workflow_id`.
- **`evidence_refs`** lists repository files that back the receipt, taken from the owned surfaces of the receipt's own shard (the source files its pull request changed) plus its workstream doc; the log-shipping receipt also names the runbook section that links it. Six, four and eight paths; every one was checked to exist in the tree.
- **`notes`** has one entry per receipt saying that it was corrected on 2026-11-09 by this workstream, what the old `workflow_id` was, which fields were added and that no verification result, hash, time or target changed. A corrected record that said nothing about it would be worse than the original.

## Choices the owner may want to change

- **`converge-monitoring` was not used for the log-shipping receipt.** It is a catalog id and would pass, but it asserts that the catalog's converge workflow ran; the receipt records a hash-checked file replacement and SIGHUP, so the descriptive historical id is the truer one.
- **The validator was not widened** (a pattern for `ws-YYYYMMDD-...` ids, or making `evidence_refs` and `notes` optional): 391 receipts already satisfy it, and loosening a data-integrity check to fit three records is the wrong direction.

## Found on the way, not changed here

- **Evidence paths are not really checked in a checkout with git history.** `evidence_ref_exists` ends in `git_path_exists_in_history`, which is `command_succeeds(['git', 'log', '--all', '--format=%H', '-1', '--', ref])`; `git log` exits 0 with empty output for a path it has never seen, so any ordinary path string passes. A mutation run that added a non-existent path to `evidence_refs` still passed. The paths in this change were checked by hand.
- **Woodpecker does not run the receipt or data-model validators** (above). Adding `./scripts/validate_repo.sh data-models` (about 45 s on a laptop) to the `validate-woodpecker-contract` step would make this class of defect fail the pull request instead of the next person's push. That is a CI change with its own owner and is not part of this one.

## Verification

Run in this worktree (a real checkout; a `git archive` export takes another validator path and stops on a different receipt). The per-receipt sweep and the mutation check are two small throwaway scripts outside the repository: they import `live_apply_receipts`, call `validate_receipt` for every path of `iter_receipt_paths()` (or for an in-memory copy of one receipt with one field put back or removed) and print every failure instead of stopping at the first.

- Before, on `origin/main` `17519941c`: `live_apply_receipts.py --validate` exits 2 on the log-shipping receipt; the per-receipt sweep reports 394 receipts, 3 failing.
- After: `live_apply_receipts.py --validate` prints `Live apply receipts OK`, exit 0; the sweep reports 394 receipts, 0 failing.
- Mutation check, in process, on each of the three corrected receipts (21 cases): the corrected receipt passes; putting the old `workflow_id` back, dropping the suffix, removing `evidence_refs`, emptying it, adding an empty entry and removing `notes` each fail with the expected message. The non-existent-path case is the leniency described above.
- `./scripts/validate_repo.sh data-models` exits 0 (it failed on `origin/main`); `platform_manifest.py --check`, `stage_smoke_suites.py --validate`, `generate_status_docs.py --check`, `canonical_truth.py --check` and `generate_diagrams.py --check` pass; `workstream_surface_ownership.py --validate-registry` and `--validate-branch --base-ref origin/main` pass.
- Then the repository pre-push gate on the build server, whose result is in the pull request description.

## Rollback

Revert the commit: the three receipts return to their recorded form and the gate lane is red again. Nothing outside the repository was touched.
