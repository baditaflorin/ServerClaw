# Workstream lifecycle reconciliation

## Goal

Make workstream status and repository ownership auditable, reduce stale
release-blocker counts, and prevent future records from losing their exact
repository and pull-request links.

## Current findings

The release manager blocks when a workstream's status is `in_progress`. It does
not infer completion from `ready_to_merge`, `live_applied`, or completed tasks.
The pre-change base had 105 active records in that status. While this new
workstream was also `in_progress`, the audit reported 106; after PR #715 merged
and this record moved to `merged`, it reports 105. All 105 remaining records
still lack explicit repository references. On the current snapshot, 27 have
`ready_to_merge: true`, 13 have `live_applied: true`, 11 have every task marked
completed, and 2 are already marked as included in a repo version while still
`in_progress`. The completion/release signals overlap; 45 records have at least
one such signal. The audit also found 34 repeated-branch entries, so
branch-to-repository or branch-to-PR matching is not safe.

The canonical-truth release manager already updates release bookkeeping,
archives completed shards, and regenerates `workstreams.yaml`. ADR 0452's older
proposal for a separate archive pass is withdrawn. The workstream registry
contract now supports exact repository/PR metadata, and the new read-only
reconciliation command reports missing links and conflicting state signals.

## Decision for this workstream

Add optional, validated `repositories` and `pull_requests` metadata for exact
ownership and PR identity while preserving legacy records. Require these fields
on new or edited active shards. Add a read-only reconciliation report that
summarizes state signals and points to evidence that must be reviewed. It must
not change a workstream's status or archive it automatically based on branch
existence, a boolean flag, or task checkboxes.

The report distinguishes recorded repository/PR references from review
recommendations, but it does not query GitHub or verify PR state. Status changes
require human review of source, merge, deployment, and release evidence.
Release bookkeeping and archival remain handled by the existing
canonical-truth release flow.

## Outcome

Implemented on this branch: metadata contract validation, changed-shard
validation in `agent-standards`, and the `workstream_tool.py reconcile` report.
PR #715 merged at `fbbe1347` on 2026-11-20. The record is marked `merged` while
its release bookkeeping remains pending. The 105 legacy records remain
untouched and require evidence-backed repository attribution.
Follow-up PR #716 carries the lifecycle closeout and generated status summaries.

The implementation branch for PR #715 was
`codex/workstream-lifecycle-reconciliation-20261120`. This closeout runs on
`codex/ws-20261120-reconciliation-closeout`; the shard records the current
closeout branch so branch ownership validation can validate this follow-up.
