# Workstream ADR 0254: ServerClaw Architecture Bundle

- ADR: [ADR 0254](../adr/0254-serverclaw-as-a-distinct-self-hosted-agent-product-on-lv3.md)
- Title: Ten architecture ADRs that turn the current governed LV3 platform into
  a ServerClaw product surface closer to OpenClaw's chat-first assistant model
- Status: implemented
- Implemented In Repo Version: 0.177.53
- Implemented In Platform Version: N/A
- Implemented On: 2026-03-28
- Branch: `codex/ws-0254-serverclaw-adrs`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0254-serverclaw-adrs`
- Owner: codex
- Depends On: `adr-0060-open-webui-workbench`,
  `adr-0069-agent-tool-registry`, `adr-0145-local-ollama`,
  `adr-0146-langfuse-observability`, `adr-0197-dify-canvas`,
  `adr-0198-semantic-rag`, `adr-0205-capability-contracts`,
  `adr-0206-ports-and-adapters`, `adr-0224-server-resident-ops`,
  `adr-0232-nomad-jobs`
- Conflicts With: none
- Shared Surfaces: `docs/adr/0254-0263`, `docs/adr/.index.yaml`,
  `docs/workstreams/adr-0254-serverclaw-architecture-bundle.md`,
  `workstreams.yaml`, `VERSION`, `changelog.md`, `RELEASE.md`,
  `docs/release-notes/README.md`, `docs/release-notes/0.177.53.md`,
  `build/platform-manifest.json`

## Scope

- add ten accepted ADRs that define ServerClaw as a coherent product surface on
  top of the current LV3 control plane
- choose mature open source defaults for conversation transport, channel
  bridges, skills, orchestration, connectors, personal data, browser actions,
  delegated authorization, and memory
- keep the new product direction aligned with the repo's existing
  capability-first, ports-and-adapters architecture
- record the bundle in workstream and release metadata

## Non-Goals

- deploying the new ServerClaw stack in this workstream
- claiming live product readiness
- replacing upstream OpenClaw with this repository or pretending the two
  runtimes are identical

## Expected Repo Surfaces

- `docs/adr/0254-serverclaw-as-a-distinct-self-hosted-agent-product-on-lv3.md`
- `docs/adr/0255-matrix-synapse-as-the-canonical-serverclaw-conversation-hub.md`
- `docs/adr/0256-mautrix-bridges-for-external-chat-channel-adapters.md`
- `docs/adr/0257-openclaw-compatible-skill-md-packs-and-workspace-precedence-for-serverclaw.md`
- `docs/adr/0258-temporal-as-the-durable-serverclaw-session-orchestrator.md`
- `docs/adr/0259-n8n-as-the-external-app-connector-fabric-for-serverclaw.md`
- `docs/adr/0260-nextcloud-as-the-canonical-personal-data-plane-for-serverclaw.md`
- `docs/adr/0261-playwright-browser-runners-for-serverclaw-web-action-and-extraction.md`
- `docs/adr/0262-openfga-and-keycloak-for-delegated-serverclaw-capability-authorization.md`
- `docs/adr/0263-qdrant-postgresql-and-local-search-as-the-serverclaw-memory-substrate.md`
- `docs/adr/.index.yaml`
- `docs/workstreams/adr-0254-serverclaw-architecture-bundle.md`
- `workstreams.yaml`
- `VERSION`
- `changelog.md`
- `RELEASE.md`
- `README.md`
- `versions/stack.yaml`
- `docs/release-notes/README.md`
- `docs/release-notes/0.177.53.md`
- `docs/diagrams/agent-coordination-map.excalidraw`
- `build/platform-manifest.json`

## Expected Live Surfaces

- none; this is a repo-only architecture release

## Selected ServerClaw Defaults

- Matrix Synapse for the canonical conversation hub
- mautrix bridges for external chat adapters
- OpenClaw-compatible `SKILL.md` skill packs
- Temporal for durable session orchestration
- n8n for third-party connector flows
- Nextcloud for canonical personal data
- Playwright for browser action and extraction
- OpenFGA plus Keycloak for delegated runtime authorization
- PostgreSQL, Qdrant, and local search for memory

## Ownership Notes

- this workstream owns the ServerClaw architecture bundle and release metadata
- no live receipts or `versions/stack.yaml` updates are expected
- future implementation work should start with ADR 0254, ADR 0255, ADR 0258,
  and ADR 0262 so product identity, transport, workflow runtime, and authz do
  not drift apart

## Verification

- Run `uv run --with pyyaml python scripts/generate_adr_index.py --write`
- Run `make generate-platform-manifest`
- Run `./scripts/validate_repo.sh agent-standards`

## Merge Criteria

- the bundle reads as one coherent ServerClaw product direction rather than ten
  disconnected tool picks
- the selected products are mature open source defaults that fit the current LV3
  architecture instead of fighting it
- release metadata reflects a repo-only merge to `main` with no platform
  version bump

## Outcome

- recorded in repo version `0.177.53`
- the repository now carries a ServerClaw architecture direction for
  chat-first, self-hosted assistant operation built on mature open source
  messaging, workflow, connector, browser, authz, and memory components
- no platform version bump was required because this bundle is governance-only

## Notes For The Next Assistant

- implement ADR 0254 through ADR 0256 together so the product boundary and
  messaging backbone land coherently
- implement ADR 0258, ADR 0261, and ADR 0262 together before exposing broad
  end-user action capabilities
- treat ADR 0260 and ADR 0263 as the privacy and ownership core of the product,
  not as optional polish
