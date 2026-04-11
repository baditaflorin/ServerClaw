# Live Apply Receipts And Verification Evidence

## Purpose

This runbook defines the structured receipt format used to record live platform applies and their verification evidence.

## Canonical Sources

- receipt directory: [receipts/live-applies](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/receipts/live-applies)
- receipt CLI: [scripts/live_apply_receipts.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/scripts/live_apply_receipts.py)
- current evidence index in platform state: [versions/stack.yaml](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/versions/stack.yaml)

## Primary Commands

List all receipts:

```bash
make receipts
```

Show one receipt:

```bash
make receipt-info RECEIPT=2026-03-22-adr-0011-monitoring-live-apply
```

Validate the receipt set directly:

```bash
scripts/live_apply_receipts.py --validate
```

Audit the current clone for receipt source commits whose objects are still
present locally:

```bash
LV3_REQUIRE_RECEIPT_SOURCE_COMMIT_OBJECTS=1 scripts/live_apply_receipts.py --validate
```

## Receipt Rules

Each receipt must record:

1. `applied_on` and `recorded_on`
2. the operator or assistant identity
3. the exact source git commit
4. the workflow id used for the live change
5. the affected targets
6. concise verification checks and observed results

Receipts may also record:

7. `smoke_suites` entries for ADR 0251 stage-scoped smoke evidence, including `suite_id`, `status`, `summary`, and a `report_ref`
8. linked per-run evidence files under `receipts/live-applies/evidence/` when the live verification output is worth preserving in branch-local history

Keep receipts concise and non-secret. Record evidence, not full command transcripts or sensitive outputs.
Receipt validation always requires `source_commit` to be an exact git-hash string.
When the current clone still contains that commit object, the validator can also
confirm object availability; branch-local historical receipts may outlive the
reachable lifetime of their original workstream commits, so fresh hosted clones
must not depend on those objects remaining fetchable forever.

## Operating Rule

After a live apply from the repository:

1. verify the real platform state
2. add or update the receipt under [receipts/live-applies](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/receipts/live-applies)
3. update [versions/stack.yaml](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/versions/stack.yaml) if merged truth or observed state changed
4. update the relevant runbook and README summary when integrated current state changed

Backfilled receipts are allowed when older live changes were verified but not recorded in structured form at the time. Note that explicitly in the receipt.

## ADR 0251 Smoke Evidence

When a live apply is verified through `scripts/stage_smoke_suites.py`, prefer this evidence pattern:

1. write the aggregate smoke report to `receipts/live-applies/evidence/<date>-adr-0251-<service>-smoke.json`
2. keep the per-suite integration report beside it
3. copy the aggregate payload's `receipt_smoke_suites` block into the live-apply receipt's `smoke_suites`
4. list both the receipt and the smoke report in the workstream doc so the later mainline merge can replay the evidence chain quickly
