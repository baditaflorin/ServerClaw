# ADR 0187: Anonymized Seed Data Snapshots for Repeatable Tests

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.177.24
- Implemented In Platform Version: 0.130.33
- Implemented On: 2026-03-28
- Date: 2026-03-27

## Context

The platform now has restore verification, integration tests, and ephemeral fixtures, but the quality of those environments still depends heavily on what data is present. Blank fixtures are useful for bootstrap checks, yet they do not exercise realistic behaviour such as:

- database migrations against non-trivial schemas
- login and session flows with representative identities
- queue and workflow behaviour under actual object counts
- restore timing with meaningful data volume

Using live production data directly would create privacy and operational risk. Using only empty test data makes HA and recovery claims too optimistic.

## Decision

We will maintain **anonymized seed data snapshots** for repeatable preview, restore, and failover tests.

### Seed classes

The initial seed classes are:

- `tiny`: fast developer and branch smoke tests
- `standard`: realistic integration and preview validation
- `recovery`: heavier restore and failover timing rehearsals

### Data handling rules

- Seeds must be produced from deterministic anonymization pipelines.
- Secrets, tokens, private keys, and operator credentials must never be copied into seeds.
- Stable synthetic identifiers should be preserved where useful so tests remain replayable across runs.

### Usage model

Previews, restore drills, and failover rehearsals should declare which seed class they require. Empty environments remain valid for pure bootstrap tests, but availability and recovery tests should default to `standard` or `recovery` seeds unless explicitly waived.

## Consequences

**Positive**

- Tests become more realistic without leaking production secrets or personal data.
- Restore and failover timings become far more credible because they are measured against representative volumes.
- Branch previews can surface migration and compatibility problems earlier.

**Negative / Trade-offs**

- Anonymization pipelines must be maintained whenever schemas change.
- Large seed snapshots consume storage and refresh time.
- Poorly designed seeds can still mislead if they stop resembling real workload patterns.

## Boundaries

- This ADR governs test data realism; it does not replace backup or archive policy.
- Seed data is for validation and rehearsal, not for long-lived shared environments.

## Related ADRs

- ADR 0088: Ephemeral infrastructure fixtures
- ADR 0099: Automated backup restore verification
- ADR 0111: End-to-end integration test suite
- ADR 0185: Branch-scoped ephemeral preview environments

## Implementation Notes

- The implemented surface adds the deterministic seed catalog, local build and publish tooling, backup-vm snapshot-store management, fixture seed staging hooks, and restore-verification seed staging hooks.
- The merged-main live apply on 2026-03-28 re-converged `backup-lv3` from the latest integrated branch state and remotely verified the published `tiny-4fc40ef2f916`, `standard-c81d5e556889`, and `recovery-7028dc9df835` snapshots under `/var/lib/lv3/seed-data-snapshots/`.
- Two adjacent live automation gaps remain outside ADR 0187's implemented core:
  - `fixture_manager.py create ops-base` is still blocked live because template `lv3-ops-base` (`9003`) is declared in repo metadata but not currently present on the Proxmox host.
  - The restore-verification path restores and boots target VMs, but restored-guest SSH readiness remains slow enough that the full workflow does not yet complete within the current live-apply session window.
