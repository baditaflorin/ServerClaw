# ADR 0036: Live Apply Receipts And Verification Evidence

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
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
