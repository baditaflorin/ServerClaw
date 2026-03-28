# Workstream ADR 0244: Runtime Assurance Architecture Bundle

- ADR: [ADR 0244](../adr/0244-runtime-assurance-matrix-per-service-and-environment.md)
- Title: Ten architecture ADRs that prove multi-stage services really exist,
  respond, authenticate, log, publish correctly, and stay trustworthy at scale
- Status: implemented
- Implemented In Repo Version: 0.177.49
- Implemented In Platform Version: N/A
- Implemented On: 2026-03-28
- Branch: `codex/ws-0244-runtime-assurance-adrs`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0244-runtime-assurance-adrs`
- Owner: codex
- Depends On: `adr-0064-health-probes`, `adr-0123-uptime-contracts`,
  `adr-0133-portal-auth-default`, `adr-0142-public-surface-scan`,
  `adr-0169-structured-logs`, `adr-0190-synthetic-replay`,
  `adr-0214-prod-staging-cells`
- Conflicts With: none
- Shared Surfaces: `docs/adr/0244-0253`, `docs/adr/.index.yaml`,
  `docs/workstreams/adr-0244-runtime-assurance-architecture-bundle.md`,
  `workstreams.yaml`, `VERSION`, `changelog.md`, `RELEASE.md`,
  `docs/release-notes/README.md`, `docs/release-notes/0.177.49.md`,
  `docs/diagrams/agent-coordination-map.excalidraw`,
  `build/platform-manifest.json`

## Scope

- add ten accepted ADRs that turn fragmented health, auth, TLS, logging, and
  smoke mechanisms into one runtime-assurance model
- define what it means for a service to exist, publish correctly, authenticate,
  log centrally, and pass stage-appropriate smoke checks
- select mature open source tools where they materially reduce bespoke
  verification work
- record the bundle in workstream and release metadata

## Non-Goals

- deploying the assurance stack in this workstream
- claiming new live platform evidence
- replacing existing health, security, or logging ADRs instead of extending
  them

## Expected Repo Surfaces

- `docs/adr/0244-runtime-assurance-matrix-per-service-and-environment.md`
- `docs/adr/0245-declared-to-live-service-attestation.md`
- `docs/adr/0246-startup-readiness-liveness-and-degraded-state-semantics.md`
- `docs/adr/0247-authenticated-browser-journey-verification-via-playwright.md`
- `docs/adr/0248-session-and-logout-authority-across-keycloak-oauth2-proxy-and-apps.md`
- `docs/adr/0249-https-and-tls-assurance-via-blackbox-exporter-and-testssl-sh.md`
- `docs/adr/0250-log-ingestion-and-queryability-canaries-via-loki-canary.md`
- `docs/adr/0251-stage-scoped-smoke-suites-and-promotion-gates.md`
- `docs/adr/0252-route-and-dns-publication-assertion-ledger.md`
- `docs/adr/0253-unified-runtime-assurance-scoreboard-and-rollup.md`
- `docs/adr/.index.yaml`
- `docs/workstreams/adr-0244-runtime-assurance-architecture-bundle.md`
- `workstreams.yaml`
- `VERSION`
- `changelog.md`
- `RELEASE.md`
- `docs/release-notes/README.md`
- `docs/release-notes/0.177.49.md`
- `docs/diagrams/agent-coordination-map.excalidraw`
- `build/platform-manifest.json`

## Expected Live Surfaces

- none; this is a repo-only architecture release

## Selected Assurance Defaults

- Playwright for authenticated browser-journey proof
- Blackbox Exporter and `testssl.sh` for HTTPS and TLS assurance
- Loki Canary for end-to-end log-path canaries
- existing service catalogs, world-state, and receipts for declared-to-live
  attestation and operator rollups

## Ownership Notes

- this workstream owns the runtime-assurance architecture bundle and release
  metadata
- no live receipts or `versions/stack.yaml` updates are expected
- future implementation work should start with the assurance matrix and
  scoreboard before adding more isolated probes

## Verification

- Run `uv run --with pyyaml python scripts/generate_adr_index.py --write`
- Run `make generate-platform-manifest`
- Run `python3 scripts/generate_diagrams.py --write`
- Run `./scripts/validate_repo.sh agent-standards`

## Merge Criteria

- the bundle answers the user request by proving services exist where declared,
  really work over login, logout, HTTPS, logging, and smoke paths, and scale to
  multi-stage operation
- the new ADRs extend rather than duplicate the existing health and security
  ADRs
- release metadata reflects a repo-only merge to `main`

## Outcome

- recorded in repo version `0.177.49`
- the repository now carries a coherent runtime-assurance direction for
  large-scale multi-stage operation across existence, health semantics, auth
  journeys, session correctness, TLS posture, log canaries, smoke gates, route
  truth, and an operator-facing assurance rollup
- no platform version bump was required because this bundle is governance-only

## Notes For The Next Assistant

- implement ADR 0244 and ADR 0253 together first so assurance evidence has one
  governing model and one operator surface
- implement ADR 0247 through ADR 0250 next; browser auth, TLS, and log-path
  proof are the highest-signal gaps for a large protected service estate
- treat ADR 0252 as the guard against silent cross-environment route drift once
  staging and preview usage expands
