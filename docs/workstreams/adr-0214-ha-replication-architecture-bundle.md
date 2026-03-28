# Workstream ADR 0214: HA And Replication Architecture Bundle

- ADR: [ADR 0214](../adr/0214-production-and-staging-cells-as-the-unit-of-high-availability.md)
- Title: Ten architecture ADRs for production and staging HA, data replication,
  service criticality, and role-based separation of concerns
- Status: implemented
- Implemented In Repo Version: 0.177.31
- Implemented In Platform Version: N/A
- Implemented On: 2026-03-28
- Branch: `codex/ws-0214-ha-replication-adrs`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0214-ha-replication-adrs`
- Owner: codex
- Depends On: `adr-0072-staging-production-topology`,
  `adr-0073-promotion-pipeline`, `adr-0179-redundancy-tier-matrix`,
  `adr-0184-failure-domain-labels`
- Conflicts With: none
- Shared Surfaces: `docs/adr/0214-0223`, `docs/adr/.index.yaml`,
  `docs/workstreams/adr-0214-ha-replication-architecture-bundle.md`,
  `workstreams.yaml`, `VERSION`, `changelog.md`, `RELEASE.md`,
  `docs/release-notes/README.md`, `docs/release-notes/0.177.31.md`,
  `build/platform-manifest.json`

## Scope

- add ten accepted ADRs that define the target HA architecture for production
  and staging cells, node-role taxonomy, service criticality, data-class
  replication, bootstrap sequencing, and failover authority
- normalize the user request for "init/core/peripheral" into standard
  operations language that better supports separation of concerns
- record the bundle in the workstream registry and release metadata
- regenerate ADR discovery metadata and release-generated artifacts required by
  the repository gates

## Non-Goals

- implementing the new catalogs, placement rules, or replication automation in
  this workstream
- claiming new live platform behavior or a platform-version bump
- rewriting the current inventories or playbooks to full node-pool separation in
  one pass

## Expected Repo Surfaces

- `docs/adr/0214-production-and-staging-cells-as-the-unit-of-high-availability.md`
- `docs/adr/0215-node-role-taxonomy-for-bootstrap-control-state-edge-workload-observability-recovery-and-build.md`
- `docs/adr/0216-service-criticality-rings-for-foundation-core-supporting-and-peripheral-functions.md`
- `docs/adr/0217-one-way-environment-data-flow-and-replication-authority.md`
- `docs/adr/0218-relational-database-replication-and-single-writer-policy.md`
- `docs/adr/0219-data-class-replication-policies-for-queues-object-stores-search-cache-secrets-and-time-series.md`
- `docs/adr/0220-bootstrap-and-recovery-sequencing-for-environment-cells.md`
- `docs/adr/0221-role-based-node-pools-and-placement-boundaries.md`
- `docs/adr/0222-failover-authority-and-service-endpoint-separation.md`
- `docs/adr/0223-canonical-ha-topology-catalog-and-reusable-automation-profiles.md`
- `docs/adr/.index.yaml`
- `docs/workstreams/adr-0214-ha-replication-architecture-bundle.md`
- `workstreams.yaml`
- `VERSION`
- `changelog.md`
- `RELEASE.md`
- `docs/release-notes/README.md`
- `docs/release-notes/0.177.31.md`
- `build/platform-manifest.json`

## Expected Live Surfaces

- none; this is a repo-only architecture release

## Ownership Notes

- the workstream owns the new ADR bundle and its release metadata
- no live receipts or `versions/stack.yaml` updates are expected because no
  platform mutation is performed
- future implementation work should reference these ADRs instead of reopening
  the topology and replication vocabulary from scratch

## Verification

- Run `uv run --with pyyaml python scripts/generate_adr_index.py --write`
- Run `make generate-platform-manifest`
- Run `./scripts/validate_repo.sh agent-standards`
- Run `make validate`

## Merge Criteria

- the ten ADRs read as one coherent architecture direction rather than ten
  isolated documentation fragments
- the bundle translates the requested "init/core/peripheral" split into
  standard operations taxonomy with clear separation of concerns
- release metadata reflects a repo-only merge to `main` with no platform version
  bump claim

## Outcome

- recorded in repo version `0.177.31`
- the repository now has a structured HA and replication architecture for
  production and staging, including cells, node roles, criticality rings,
  one-way data authority, data-class replication policy, bring-up sequencing,
  placement boundaries, failover authority, and DRY automation profiles
- no platform version bump was required because the workstream is governance-only

## Notes For The Next Assistant

- use ADR 0223 as the implementation pivot when introducing the future catalog;
  it is the most direct DRY mechanism in this bundle
- apply ADR 0217 before any staging data automation so cross-environment writes
  do not become an accidental default
- when decomposing the current guest estate into clearer pools, use ADR 0215 and
  ADR 0221 together rather than only one of them
