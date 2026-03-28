# Workstream ADR 0224: Server-Resident Operations Architecture Bundle

- ADR: [ADR 0224](../adr/0224-server-resident-operations-as-the-default-control-model.md)
- Title: Ten architecture ADRs that move operational responsibility from the
  Codex chat client into server-resident, production-grade tools
- Status: implemented
- Implemented In Repo Version: 0.177.33
- Implemented In Platform Version: N/A
- Implemented On: 2026-03-28
- Branch: `codex/ws-0224-server-resident-ops-adrs-r2`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0224-server-resident-ops-adrs-r2`
- Owner: codex
- Depends On: `adr-0043-openbao`, `adr-0044-windmill`, `adr-0048-command-catalog`,
  `adr-0143-gitea`, `adr-0214-ha-replication-bundle`
- Conflicts With: none
- Shared Surfaces: `docs/adr/0224-0233`, `docs/adr/.index.yaml`,
  `docs/workstreams/adr-0224-server-resident-operations-architecture-bundle.md`,
  `workstreams.yaml`, `VERSION`, `changelog.md`, `RELEASE.md`,
  `docs/release-notes/README.md`, `docs/release-notes/0.177.33.md`,
  `docs/diagrams/agent-coordination-map.excalidraw`,
  `build/platform-manifest.json`

## Scope

- add ten accepted ADRs that move the operating model from chat-resident and
  workstation-resident execution toward server-resident reconciliation,
  workflow, policy, packaging, and secret delivery
- select concrete mature tools that can take roles currently held by the Codex
  session or a local shell
- document the bundle in the workstream registry and release metadata
- regenerate ADR discovery and release-generated artifacts required by the merge
  gates

## Non-Goals

- deploying the selected tools in this workstream
- replacing every current execution path immediately
- claiming a live platform version bump

## Expected Repo Surfaces

- `docs/adr/0224-server-resident-operations-as-the-default-control-model.md`
- `docs/adr/0225-server-resident-reconciliation-via-ansible-pull.md`
- `docs/adr/0226-systemd-units-timers-and-paths-for-host-resident-control-loops.md`
- `docs/adr/0227-bounded-command-execution-via-systemd-run-and-approved-wrappers.md`
- `docs/adr/0228-windmill-as-the-default-browser-and-api-operations-surface.md`
- `docs/adr/0229-gitea-actions-runners-for-on-platform-validation-and-release-preparation.md`
- `docs/adr/0230-policy-decisions-via-open-policy-agent-and-conftest.md`
- `docs/adr/0231-local-secret-delivery-via-openbao-agent-and-systemd-credentials.md`
- `docs/adr/0232-nomad-for-durable-batch-and-long-running-internal-jobs.md`
- `docs/adr/0233-signed-release-bundles-via-gitea-releases-and-cosign.md`
- `docs/adr/.index.yaml`
- `docs/workstreams/adr-0224-server-resident-operations-architecture-bundle.md`
- `workstreams.yaml`
- `VERSION`
- `changelog.md`
- `RELEASE.md`
- `docs/release-notes/README.md`
- `docs/release-notes/0.177.33.md`
- `docs/diagrams/agent-coordination-map.excalidraw`
- `build/platform-manifest.json`

## Expected Live Surfaces

- none; this is a repo-only architecture release

## Ownership Notes

- the workstream owns this server-resident operations ADR bundle and its release
  metadata
- no live receipts or `versions/stack.yaml` updates are expected in this bundle
- future implementation work should treat the Codex app as an authoring client,
  not the default runtime home of platform operations

## Verification

- Run `uv run --with pyyaml python scripts/generate_adr_index.py --write`
- Run `make generate-platform-manifest`
- Run `python3 scripts/generate_diagrams.py --write`
- Run `./scripts/validate_repo.sh agent-standards`
- Run `make validate`

## Merge Criteria

- the bundle clearly answers the user's gap: the server should keep operating
  through server-resident tools rather than depending on a live chat session
- the selected tools are mature enough to justify production-facing ADRs
- release metadata reflects a repo-only merge to `main`

## Outcome

- recorded in repo version `0.177.33`
- the repository now records a server-resident operations direction centered on
  Ansible Pull, systemd, systemd-run, Windmill, Gitea Actions runners, OPA,
  OpenBao Agent, Nomad, and signed release bundles via Gitea plus Cosign
- no platform version bump was required because this bundle is governance-only

## Notes For The Next Assistant

- implement ADR 0225 and ADR 0226 together first; a reconcile loop without a
  host-native supervisor will stay brittle
- implement ADR 0231 before moving more logic onto the server, otherwise secrets
  will leak back into repo workspaces or shell state
- treat ADR 0233 as the provenance bridge between git authoring and server-side
  runtime consumption
