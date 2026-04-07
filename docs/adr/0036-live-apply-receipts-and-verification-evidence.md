# ADR 0036: Live Apply Receipts And Verification Evidence

- Status: Accepted
- Implementation Status: Partial Implemented
- Implemented In Repo Version: 0.37.0
- Implemented In Platform Version: not applicable (repo-only)
- Implemented On: 2026-03-22
- Date: 2026-03-22

## Context

The repository separates repo truth from live platform truth, which is correct.

However, evidence for live changes is still weakly structured:

- verification often lives only in chat output
- README and `versions/stack.yaml` summarize state but not the exact apply event that established it
- later assistants must reconstruct what was run, from which commit, and what was observed
- repeated re-verification becomes harder because the previous evidence is not stored in one consistent format

This is a continuity problem for agentic operation and a rigor problem for infrastructure changes.

## Decision

We will record structured live-apply receipts and verification evidence in the repository.

Each receipt should capture, at minimum:

1. Date and operator or assistant identity.
2. Git commit applied.
3. Workflow or playbook executed.
4. Target hosts or services affected.
5. Verification checks and key observed results.

## Consequences

- Future assistants can reason from recorded evidence instead of hidden chat context.
- Live-state updates in `versions/stack.yaml` become easier to audit.
- Runbooks can point at concrete past receipts when a workflow is reapplied.
- The receipt format must stay concise and non-secret; it should record evidence, not dump full command logs.

## Implementation Notes

- Structured receipts now live under [receipts/live-applies](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/receipts/live-applies).
- [scripts/live_apply_receipts.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/live_apply_receipts.py) validates receipt schema, git commit references, workflow ids, and evidence file references.
- [Makefile](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/Makefile) now exposes `make receipts` and `make receipt-info RECEIPT=<id>` for receipt discovery.
- [versions/stack.yaml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/versions/stack.yaml) now records the latest receipt ids that support the current live platform summary.
- Historical receipts were backfilled for the current known live applies so the framework starts with actual evidence rather than an empty directory.
