# Workstream ADR 0264: Receipt-Driven Resilience Architecture Bundle

- ADR: [ADR 0264](../adr/0264-failure-domain-isolated-validation-lanes.md)
- Title: Ten architecture ADRs that turn repeated gate bypasses, recovery
  repairs, restore failures, security drift, and publication mismatches into
  governed prevention controls
- Status: implemented
- Implemented In Repo Version: 0.177.56
- Implemented In Platform Version: N/A
- Implemented On: 2026-03-28
- Branch: `codex/ws-0264-receipt-driven-resilience-adrs-r3`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server`
- Owner: codex
- Depends On: `adr-0036-live-apply-receipts`, `adr-0087-validation-gate`,
  `adr-0099-backup-restore-verification`,
  `adr-0102-security-posture-reporting`,
  `adr-0141-api-token-lifecycle-and-exposure-response`,
  `adr-0163-platform-wide-retry-taxonomy-and-exponential-backoff`,
  `adr-0170-platform-wide-timeout-hierarchy`,
  `adr-0188-failover-rehearsal-gate-for-redundancy-tiers`,
  `adr-0247-authenticated-browser-journey-verification-via-playwright`,
  `adr-0252-route-and-dns-publication-assertion-ledger`
- Conflicts With: none
- Shared Surfaces: `docs/adr/0264-0273`, `docs/adr/.index.yaml`,
  `docs/workstreams/adr-0264-receipt-driven-resilience-architecture-bundle.md`,
  `workstreams.yaml`, `VERSION`, `changelog.md`, `RELEASE.md`, `README.md`,
  `versions/stack.yaml`, `docs/release-notes/README.md`,
  `docs/release-notes/0.177.56.md`,
  `docs/diagrams/agent-coordination-map.excalidraw`,
  `build/platform-manifest.json`

## Scope

- add ten accepted ADRs derived from actual receipt pain, not hypothetical
  architecture gaps
- convert repeated validation, bootstrap, runtime publication, backup, restore,
  security, and DNS failures into explicit guardrails
- preserve successful targeted validation and recovery patterns as first-class
  good-path evidence
- record the bundle in workstream and release metadata

## Non-Goals

- implementing the new guardrails in this workstream
- claiming fresh live platform evidence
- replacing the current receipts, scans, or restore drills instead of tightening
  what they feed into

## Expected Repo Surfaces

- `docs/adr/0264-failure-domain-isolated-validation-lanes.md`
- `docs/adr/0265-immutable-validation-snapshots-for-remote-builders-and-schema-checks.md`
- `docs/adr/0266-validation-runner-capability-contracts-and-environment-attestation.md`
- `docs/adr/0267-expiring-gate-bypass-waivers-with-structured-reason-codes.md`
- `docs/adr/0268-fresh-worktree-bootstrap-manifests-for-generated-artifacts-and-local-inputs.md`
- `docs/adr/0269-vulnerability-budgets-and-image-host-freshness-promotion-gates.md`
- `docs/adr/0270-docker-publication-self-healing-and-port-programming-assertions.md`
- `docs/adr/0271-backup-coverage-assertion-ledger-and-backup-of-backup-policy.md`
- `docs/adr/0272-restore-readiness-ladders-and-stateful-warm-up-verification-profiles.md`
- `docs/adr/0273-public-endpoint-admission-control-for-dns-catalog-and-certificate-concordance.md`
- `docs/adr/.index.yaml`
- `docs/workstreams/adr-0264-receipt-driven-resilience-architecture-bundle.md`
- `workstreams.yaml`
- `VERSION`
- `changelog.md`
- `RELEASE.md`
- `README.md`
- `versions/stack.yaml`
- `docs/release-notes/README.md`
- `docs/release-notes/0.177.56.md`
- `docs/diagrams/agent-coordination-map.excalidraw`
- `build/platform-manifest.json`

## Expected Live Surfaces

- none; this is a repo-only architecture release

## Selected Resilience Defaults

- failure-domain-isolated blocking lanes instead of one monolithic gate
- immutable validation snapshots instead of mutable remote worktree mirrors
- capability-attested runners instead of assumed-equivalent builders
- expiring structured waivers instead of vague bypass receipts
- worktree bootstrap manifests for generated artifacts and local inputs
- vulnerability budgets with freshness-aware promotion gates
- Docker publication self-healing before user-visible health is trusted
- backup coverage ledgers and staged restore-readiness ladders
- public endpoint admission across catalog, DNS, edge, and certificate truth

## Ownership Notes

- this workstream owns the receipt-driven resilience architecture bundle and
  release metadata
- no live receipts or platform-version changes are expected
- future implementation work should start with ADR 0264 through ADR 0268 so the
  validation substrate stops creating avoidable bypass pressure before deeper
  recovery work lands

## Verification

- Run `uv run --with pyyaml python scripts/generate_adr_index.py --write`
- Run `python3 scripts/release_manager.py --bump patch --platform-impact "..."`
- Run `uv run --with pyyaml --with jsonschema python scripts/platform_manifest.py --write`
- Run `./scripts/validate_repo.sh agent-standards`

## Merge Criteria

- the new ADRs must read as one resilience bundle driven by repository receipts
  rather than ten disconnected fixes
- the bundle must extend current validation, security, backup, restore, and DNS
  ADRs instead of duplicating them
- release metadata must show a repo-only merge to `main`

## Outcome

- recorded in repo version `0.177.56`
- the repository now carries a receipt-driven resilience direction for
  validation partitioning, builder correctness, waiver governance, bootstrap
  preflight, vulnerability gating, Docker publication repair, backup coverage,
  restore ladders, and public endpoint admission
- no platform version bump was required because this bundle is governance-only

## Notes For The Next Assistant

- implement ADR 0264 through ADR 0268 together first so bypass pressure falls
  before adding more automation
- implement ADR 0271 and ADR 0272 together so backup coverage and restore
  semantics do not drift apart
- implement ADR 0273 alongside ADR 0252 and ADR 0101 so endpoint admission
  shares one DNS-and-certificate source of truth
