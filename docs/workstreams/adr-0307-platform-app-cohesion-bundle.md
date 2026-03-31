# Workstream ADR 0307: Platform App Cohesion, Onboarding, And User-Flow Architecture Bundle

- ADR: [ADR 0307](../adr/0307-platform-workbench-as-the-cohesive-first-party-app-frame.md)
- Title: Ten architecture ADRs that turn the platform's human-facing surfaces
  into one cohesive app with clear onboarding, navigation, interruption
  recovery, and user-flow measurement
- Status: merged
- Branch: `codex/ws-0307-app-cohesion-bundle`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0307-app-cohesion-bundle`
- Owner: codex
- Depends On: `adr-0093-interactive-ops-portal`,
  `adr-0094-developer-portal`, `adr-0108-operator-onboarding`,
  `adr-0152-homepage`, `adr-0209-use-case-services`,
  `adr-0234-human-app-shell`, `adr-0242-guided-onboarding`
- Conflicts With: none
- Shared Surfaces: `docs/adr/0307-0316`, `docs/adr/.index.yaml`,
  `docs/workstreams/adr-0307-platform-app-cohesion-bundle.md`,
  `workstreams.yaml`, `README.md`, `VERSION`, `changelog.md`, `RELEASE.md`,
  `docs/release-notes/README.md`, `docs/release-notes/0.177.122.md`,
  `versions/stack.yaml`, `build/platform-manifest.json`,
  `docs/diagrams/agent-coordination-map.excalidraw`

## Scope

- add ten accepted ADRs that define the platform as one cohesive first-party app
- define entry routing, task lanes, first-run activation, command access,
  notifications, contextual help, resumable flows, canonical state behavior,
  and journey scorecards
- land the matching workstream and release metadata on `main`

## Non-Goals

- implementing the browser runtime changes in this workstream
- changing `versions/stack.yaml` or claiming a new live platform milestone
- replacing product-native UIs that remain the best interface for their
  specialist jobs

## Expected Repo Surfaces

- `docs/adr/0307-platform-workbench-as-the-cohesive-first-party-app-frame.md`
- `docs/adr/0308-journey-aware-entry-routing-and-saved-home-selection.md`
- `docs/adr/0309-task-oriented-information-architecture-across-the-platform-workbench.md`
- `docs/adr/0310-first-run-activation-checklists-and-progressive-capability-reveal.md`
- `docs/adr/0311-global-command-palette-and-universal-open-dialog-via-cmdk.md`
- `docs/adr/0312-shared-notification-center-and-activity-timeline-across-human-surfaces.md`
- `docs/adr/0313-contextual-help-glossary-and-escalation-drawer.md`
- `docs/adr/0314-resumable-multi-step-flows-and-return-to-task-reentry.md`
- `docs/adr/0315-canonical-page-states-and-next-best-action-guidance-for-human-surfaces.md`
- `docs/adr/0316-journey-analytics-and-onboarding-success-scorecards.md`
- `docs/workstreams/adr-0307-platform-app-cohesion-bundle.md`
- `docs/adr/.index.yaml`
- `workstreams.yaml`
- `README.md`
- `VERSION`
- `changelog.md`
- `RELEASE.md`
- `docs/release-notes/README.md`
- `docs/release-notes/0.177.122.md`
- `versions/stack.yaml`
- `build/platform-manifest.json`
- `docs/diagrams/agent-coordination-map.excalidraw`

## Expected Live Surfaces

- none; this is a repo-only architecture release

## Ownership Notes

- this workstream owns the cohesive-app and onboarding architecture bundle
- the merge to `main` advances repository truth only; platform version remains
  unchanged on purpose
- canonical truth regeneration updates the repo-version fields in `README.md`
  and `versions/stack.yaml`, plus the generated workstream count in the agent
  coordination diagram
- the next implementation steps should start with ADR 0308 through ADR 0313 so
  users feel the entry, help, and attention improvements before deeper polish

## Verification

- run `uv run --with pyyaml python scripts/generate_adr_index.py --write`
- run `make generate-platform-manifest`
- run `./scripts/validate_repo.sh agent-standards`

## Merge Criteria

- the bundle must clearly answer how the platform behaves as one cohesive app
- onboarding and user-flow work must build on existing first-party surfaces
  rather than pretending the platform is still only a loose tool collection
- another assistant must be able to continue from this worktree without hidden
  context

## Notes For The Next Assistant

- implement ADR 0308, ADR 0310, and ADR 0312 together first so home routing,
  onboarding progress, and attention flows tell one coherent story
- implement ADR 0311 and ADR 0313 after the task-lane metadata exists, or the
  command palette and help drawer will feel underpowered
- treat ADR 0315 and ADR 0316 as the contracts that keep future UX changes
  honest once runtime implementation begins
