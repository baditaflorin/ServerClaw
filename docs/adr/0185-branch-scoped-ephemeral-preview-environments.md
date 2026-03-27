# ADR 0185: Branch-Scoped Ephemeral Preview Environments

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-27

## Context

ADR 0088 established ephemeral fixtures for role and infrastructure testing, but the platform still lacks a higher-level environment for validating multi-service changes before they touch integrated truth.

Many changes that affect availability or recovery are difficult to judge from unit tests alone:

- ingress and TLS cutover behaviour
- service-to-service dependency changes
- rollback bundle verification
- release compatibility across multiple services

Without branch-scoped previews, the repo either under-tests these changes or pushes them directly into shared environments.

## Decision

We will support **branch-scoped ephemeral preview environments** assembled from the branch's release manifest and destroyed automatically after use.

### Preview contract

Each preview environment must declare:

- owning branch or workstream
- TTL and auto-destroy policy
- service subset or stack profile
- network isolation boundary
- smoke and synthetic validation steps

### Build model

Previews should be created from committed automation only:

- immutable VM or container images where possible
- generated environment-specific inventory overlays
- isolated DNS names such as `<workstream>.preview.lv3.org`
- default deployment on preview networks or the auxiliary cloud domain

### Intended use

Previews are the default place to verify:

- ingress and certificate changes
- failover rehearsals that should not touch primaries
- branch-local API and workflow integration
- rollback and release-bundle validation before merge

## Consequences

**Positive**

- The platform gets a realistic pre-merge environment without requiring a permanent staging fleet for every branch.
- Testing availability-sensitive changes becomes faster and safer.
- Another assistant can reproduce the same preview from committed branch state instead of tribal knowledge.

**Negative / Trade-offs**

- Preview orchestration adds lifecycle and naming complexity.
- Preview sprawl becomes a real risk unless TTL enforcement is strong.
- Some services with large state footprints will still need narrower preview profiles or seeded snapshots rather than full clones.

## Boundaries

- Preview environments are for validation, not for permanent shared staging.
- This ADR does not decide which tests run in previews; later ADRs define replay, impairment, and failover drill usage.

## Related ADRs

- ADR 0073: Environment promotion gate and deployment pipeline
- ADR 0088: Ephemeral infrastructure fixtures
- ADR 0174: Integration-only canonical truth assembly
- ADR 0182: Live apply merge train and rollback bundle
