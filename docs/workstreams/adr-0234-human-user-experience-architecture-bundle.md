# Workstream ADR 0234: Human User Experience Architecture Bundle

- ADR: [ADR 0234](../adr/0234-shared-human-app-shell-and-navigation-via-patternfly.md)
- Title: Ten architecture ADRs that make the monolithic platform feel coherent,
  usable, and production-ready for human users through mature open source UX
  tools
- Status: implemented
- Implemented In Repo Version: 0.177.47
- Implemented In Platform Version: N/A
- Implemented On: 2026-03-28
- Branch: `codex/ws-0234-human-ux-adrs`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.worktrees/ws-0234-human-ux-adrs`
- Owner: codex
- Depends On: `adr-0093-interactive-ops-portal`, `adr-0094-developer-portal`,
  `adr-0133-portal-authentication-by-default`, `adr-0152-homepage`,
  `adr-0193-plane`, `adr-0199-outline`, `adr-0209-use-case-services`
- Conflicts With: none
- Shared Surfaces: `docs/adr/0234-0243`, `docs/adr/.index.yaml`,
  `docs/workstreams/adr-0234-human-user-experience-architecture-bundle.md`,
  `workstreams.yaml`, `VERSION`, `changelog.md`, `RELEASE.md`,
  `docs/release-notes/README.md`, `docs/release-notes/0.177.47.md`,
  `docs/diagrams/agent-coordination-map.excalidraw`,
  `build/platform-manifest.json`

## Scope

- add ten accepted ADRs for the human-facing UX layer of the monolithic
  platform
- prefer production-ready open source libraries over hand-built UI primitives
- define the appearance, navigation, form, table, search, chart, editing,
  onboarding, and accessibility defaults for future first-party surfaces
- record the bundle in workstream and release metadata

## Non-Goals

- deploying the selected UX stack in this workstream
- rewriting existing first-party surfaces immediately
- making agent and LLM onboarding the primary concern of this bundle

## Expected Repo Surfaces

- `docs/adr/0234-shared-human-app-shell-and-navigation-via-patternfly.md`
- `docs/adr/0235-cross-application-launcher-and-favorites-via-patternfly-application-launcher.md`
- `docs/adr/0236-server-state-and-mutation-feedback-via-tanstack-query.md`
- `docs/adr/0237-schema-first-human-forms-via-react-hook-form-and-zod.md`
- `docs/adr/0238-data-dense-operator-grids-via-ag-grid-community.md`
- `docs/adr/0239-browser-local-search-experience-via-pagefind.md`
- `docs/adr/0240-operator-visualization-panels-via-apache-echarts.md`
- `docs/adr/0241-rich-content-and-inline-knowledge-editing-via-tiptap.md`
- `docs/adr/0242-guided-human-onboarding-via-shepherd-tours.md`
- `docs/adr/0243-component-stories-accessibility-and-ui-contracts-via-storybook-playwright-and-axe-core.md`
- `docs/adr/.index.yaml`
- `docs/workstreams/adr-0234-human-user-experience-architecture-bundle.md`
- `workstreams.yaml`
- `VERSION`
- `changelog.md`
- `RELEASE.md`
- `docs/release-notes/README.md`
- `docs/release-notes/0.177.47.md`
- `docs/diagrams/agent-coordination-map.excalidraw`
- `build/platform-manifest.json`

## Expected Live Surfaces

- none; this is a repo-only architecture release

## Selected OSS UX Defaults

- PatternFly for shared app shell, navigation, and launcher
- TanStack Query for server-state behavior
- React Hook Form plus Zod for structured forms
- AG Grid Community for data-dense operator views
- Pagefind for browser-local search
- Apache ECharts for embedded visualizations
- Tiptap for rich content editing
- Shepherd.js for guided onboarding
- Storybook, Playwright, and axe-core for UI contracts and accessibility checks

## Ownership Notes

- this workstream owns the human-first UX architecture bundle and its release
  metadata
- no live receipts or `versions/stack.yaml` changes are expected
- future agent and LLM onboarding work should build on these human-facing
  contracts instead of bypassing them

## Verification

- Run `uv run --with pyyaml python scripts/generate_adr_index.py --write`
- Run `make generate-platform-manifest`
- Run `python3 scripts/generate_diagrams.py --write`
- Run `./scripts/validate_repo.sh agent-standards`

## Merge Criteria

- the bundle answers the user request by defining how human users should see and
  interact with the monolithic setup
- each ADR chooses a mature open source library or tool instead of pushing UI
  work toward hand-built primitives
- release metadata reflects a repo-only merge to `main`

## Outcome

- recorded in repo version `0.177.47`
- the repository now has a coherent human UX direction centered on PatternFly,
  Pagefind, AG Grid Community, TanStack Query, React Hook Form, Zod, Apache
  ECharts, Tiptap, Shepherd.js, Storybook, Playwright, and axe-core
- no platform version bump was required because this bundle is governance-only

## Notes For The Next Assistant

- implement ADR 0234 and ADR 0235 together first so new navigation work starts
  from one coherent shell
- implement ADR 0237 and ADR 0238 before building more admin workflows; forms
  and data grids are where hand-coded UX debt grows fastest
- treat ADR 0243 as the bridge into future agent and LLM onboarding because it
  turns UI states into explicit stories and testable contracts
