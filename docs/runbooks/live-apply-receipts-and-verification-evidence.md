# Live Apply Receipts And Verification Evidence

## Purpose

This runbook defines the structured receipt format used to record live platform applies and their verification evidence.

## Canonical Sources

- receipt directory: [receipts/live-applies](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/receipts/live-applies)
- receipt CLI: [scripts/live_apply_receipts.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/live_apply_receipts.py)
- current evidence index in platform state: [versions/stack.yaml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/versions/stack.yaml)

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

## Receipt Rules

Each receipt must record:

1. `applied_on` and `recorded_on`
2. the operator or assistant identity
3. the exact source git commit
4. the workflow id used for the live change
5. the affected targets
6. concise verification checks and observed results

Keep receipts concise and non-secret. Record evidence, not full command transcripts or sensitive outputs.

## Operating Rule

After a live apply from the repository:

1. verify the real platform state
2. add or update the receipt under [receipts/live-applies](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/receipts/live-applies)
3. update [versions/stack.yaml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/versions/stack.yaml) if merged truth or observed state changed
4. update the relevant runbook and README summary when integrated current state changed

Backfilled receipts are allowed when older live changes were verified but not recorded in structured form at the time. Note that explicitly in the receipt.
