# ADR 0134: Changelog Portal Content Redaction

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.111.0
- Implemented In Platform Version: not yet
- Implemented On: 2026-03-24
- Date: 2026-03-24

## Context

The deployment changelog portal (ADR 0081) renders live-apply receipts, version history, and mutation ledger summaries into a human-readable history of what changed and when. Even behind authenticated operator access, the portal should not expose the full detail of raw receipts and audit events.

The overexposed fields include:

- actor emails and branch-like agent identifiers
- internal hostnames and private IP addresses
- workflow parameters and environment variables
- raw error messages, stack traces, and job payloads
- inline credential material echoed by a workflow or failure path

Those fields are appropriate in the underlying receipt or audit source, but they are not appropriate in the shared portal view or in the `get-deployment-history` read surface.

## Decision

We implement a config-backed **changelog redaction pipeline** between raw history collection and portal rendering.

### Sensitive field taxonomy

| Level | Fields | Portal treatment |
| --- | --- | --- |
| `STRIP` | `error_detail`, `stack_trace`, `job_payload` | Render `[details omitted]` |
| `MASK` | actor emails, branch-like identities, internal hostnames, private IPs, inline credential values | Keep the minimum useful prefix, replace the rest with redaction markers |
| `SUMMARISE` | workflow `params`, `env_vars`, receipt references in promotion metadata | Show counts or key names, not values |
| `RETAIN` | service names, workflow IDs, event type, timestamp, duration, outcome | Shown as-is |

### Repository contract

The redaction policy lives in `config/changelog-redaction.yaml` and is validated by the repository data-model gate.

The deployment history query layer applies the policy before returning entries to:

- the static changelog portal generator
- the governed `get-deployment-history` tool

### Current scope

This implementation covers the shared read path for deployment history. It does not yet add a separate role-gated raw portal view or rewrite historical receipts already committed in git.

## Consequences

**Positive**

- Operators and agents get a safer default read model for deployment history.
- Secrets and PII are filtered once at the history model boundary instead of being reimplemented in each renderer.
- The redaction rules are explicit, reviewable, and validated in version control.

**Negative / Trade-offs**

- The redacted portal view is intentionally less useful for low-level debugging than the underlying receipt or audit source.
- Maintaining the redaction rules requires judgment: too much masking makes the timeline hard to use, too little masking leaks infrastructure detail.

## Boundaries

- Raw receipts and audit sources remain authoritative and are not mutated by this ADR.
- This ADR covers text-field redaction for deployment-history read surfaces only.
- Live platform publication of any additional raw/admin view remains future work.

## Related ADRs

- ADR 0031: Repository validation pipeline
- ADR 0036: Live-apply receipts
- ADR 0081: Platform changelog and deployment history portal
- ADR 0115: Event-sourced mutation ledger
- ADR 0121: Local search and indexing fabric
