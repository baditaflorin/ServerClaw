# ADR 0452: Workstream Lifecycle Reconciliation and Safe Closeout

- Status: Accepted
- Implementation Status: Implemented in main; release inclusion pending
- Date: 2026-04-28
- Revised: 2026-11-20
- First repo version: 0.179.66
- First platform version: Not applicable — repository tooling only
- Implementation date: 2026-11-20
- Concern: workstream-lifecycle, observability, throughput-measurement
- Tags: workstreams, registry, archive, lifecycle, automation, reconciliation, closeout, repository-references
- Extends: [ADR 0326 — Workstream Registry Shards With Active And Archive Assembly](0326-workstream-registry-shards-with-active-and-archive-assembly.md)
- Related:
  - ADR 0019 (Parallel ADR Delivery With Workstreams)
  - ADR 0419 (PR-Based Integration Flow)
  - ADR 0420 (CI Release-Readiness Checks)

---

## Context

ADR 0326 established active and archived workstream shards. The original
2026-04-28 version of this ADR proposed a second archive automation path based
on acceptance flags and live-apply receipt matching. That proposal no longer
matches the repository: the canonical-truth release manager already updates
release metadata, archives completed shards, and regenerates `workstreams.yaml`
as part of a release. See `docs/runbooks/canonical-truth-assembly.md`.

The release gate counts the configured blocking statuses from
`config/version-semantics.json`. At the start of this reconciliation, 105
active workstreams were marked `in_progress`. Branch names and status flags do
not reliably identify their repository or prove completion. Reused branch
names make a fuzzy PR lookup unsafe.

## Decision

Keep one lifecycle authority: the existing canonical-truth release flow owns
release bookkeeping and archival. Add a read-only reconciliation report and
exact repository/PR references so operators can review the backlog with better
evidence.

Optional `repositories` and `pull_requests` fields are backward-compatible for
legacy records. When present, the registry validator checks owner/repository
format, positive PR numbers, uniqueness, and that each PR repository is listed
in `repositories`. Every newly added or edited active shard must include both
fields; use `pull_requests: []` when no PR has been opened yet. The agent
standards validation gate enforces this for changed active shards while
leaving untouched legacy shards valid.

Run the audit with:

```bash
uv run --with pyyaml python scripts/workstream_tool.py reconcile
uv run --with pyyaml python scripts/workstream_tool.py reconcile --format json
```

The report identifies status/flag mismatches, fully checked task lists, missing
repository or PR links, and repeated branch names. Those are review signals,
not automatic status transitions. The tool is read-only and never infers a
repository or PR from a branch name.

## Reconciliation Procedure

For each flagged record:

1. Confirm the repository from the workstream's source changes or an explicit
   owner handoff. Do not infer it from a reused branch name.
2. Add an exact `owner/repository` reference and, when one exists, the numeric
   PR reference to the workstream shard.
3. Confirm the PR's merge state and the relevant live-apply receipt or runtime
   evidence where deployment was part of the work.
4. Review remaining tasks, blockers, and `canonical_truth` release metadata.
5. Change status only when the evidence supports it. Let the release manager
   handle release inclusion and archival.

The report is a snapshot of repository metadata. It does not query GitHub or
verify the current PR state; the linked PR must be checked during closeout.

## Consequences

- New and changed active workstreams carry exact repository and PR references.
- Legacy records remain readable and are surfaced as unlinked instead of
  being silently attributed to a repository.
- Reconciliation becomes repeatable without creating a competing archive path.
- Status, merge, deployment, and release inclusion remain separate facts and
  require their corresponding evidence.

## Superseded Proposal

The original proposal in this ADR to add `acceptance_criteria_met`, a
`lifecycle_state` state machine, an `--archive-completed` mode, receipt-slug
requirements, and a parallel staleness/receipt CI gate is withdrawn. Those
mechanisms duplicate current release-manager behavior and can mark workstreams
complete based on incomplete evidence. Do not implement or use that proposal.
