# Workstream ADR 0224: Self-Service Repo Intake And Agent-Assisted Deployments

- ADR: [ADR 0224](../adr/0224-self-service-repo-intake-and-agent-assisted-deployments.md)
- Title: Extend the current Coolify repo-deploy lane into a catalog-driven
  self-service intake flow
- Status: ready
- Branch: `codex/ws-0224-repo-intake`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0224-repo-intake`
- Owner: codex
- Depends On: `adr-0156-agent-session-workspace-isolation`,
  `adr-0185-branch-scoped-ephemeral-preview-environments`,
  `adr-0194-coolify-paas-deploy-from-repo`,
  `adr-0204-self-correcting-automation-loops`
- Conflicts With: none
- Shared Surfaces: `docs/adr/0224-self-service-repo-intake-and-agent-assisted-deployments.md`,
  `docs/workstreams/adr-0224-self-service-repo-intake-and-agent-assisted-deployments.md`,
  `docs/adr/.index.yaml`, `workstreams.yaml`
- Ownership Manifest: `workstreams.yaml` `ownership_manifest`

## Scope

- create a tracked workstream for the requested repo-intake flow
- record the architecture direction in ADR 0224
- capture the current live platform baseline and the missing pieces before
  private repo deployment can be self-served
- anchor the first smoke target on `education_wemeshup`

## Non-Goals

- mutating the live platform in this discovery turn
- changing protected integration truth such as `README.md`, `VERSION`,
  `changelog.md`, or `versions/stack.yaml`
- editing the dirty local
  `/Users/live/Documents/GITHUB_PROJECTS/education_wemeshup` checkout owned by
  another session

## Expected Repo Surfaces

- `docs/adr/0224-self-service-repo-intake-and-agent-assisted-deployments.md`
- `docs/workstreams/adr-0224-self-service-repo-intake-and-agent-assisted-deployments.md`
- `docs/adr/.index.yaml`
- `workstreams.yaml`

Future implementation on this branch will likely expand into:

- `scripts/coolify_tool.py`
- `scripts/lv3_cli.py`
- a repo-intake or deployment-profile catalog
- operator runbooks for private repo bootstrap and intake operations

## Expected Live Surfaces

- none yet

The first live smoke path should be a private-repo deployment of the committed
`education_wemeshup` GitHub repository into `*.apps.lv3.org`.

## Ownership Notes

- The current governed deployment lane already exists through ADR 0194:
  private Coolify API, protected dashboard, and wildcard app ingress are live.
- The missing governed capability is private-repo credential bootstrap plus a
  richer intake contract on top of the existing deploy wrapper.
- The local `education_wemeshup` checkout is dirty and ahead of deployable Git
  truth. Treat it as reference-only until its upstream branch commits the new
  runtime shape.

## Verification

- `git ls-remote git@github.com:baditaflorin/education_wemeshup.git HEAD`
- `git -C /Users/live/Documents/GITHUB_PROJECTS/education_wemeshup ls-tree -r --name-only HEAD`
- `git -C /Users/live/Documents/GITHUB_PROJECTS/education_wemeshup status --short --branch`
- `git -C /Users/live/Documents/GITHUB_PROJECTS/education_wemeshup npm run build`

Observed on 2026-03-28:

- GitHub SSH access works from the controller.
- The committed repo `HEAD` contains only `.gitignore` and `index.html`.
- The local working tree has uncommitted Vite-era additions.
- `npm run build` fails in the local working tree because
  `src/domain/catalog.js` is missing.

## Merge Criteria

- a governed private-repo auth path is documented and implemented
- one catalog-driven deployment request can select environment and domain
  without hand-editing commands
- the first private GitHub smoke repo deploys from committed Git state
- the path clearly separates direct deploy, bounded agent assist, and
  production promotion

## Notes For The Next Assistant

- If the user wants the absolute fastest smoke test, deploy the committed remote
  `education_wemeshup` `index.html` first and leave the uncommitted Vite refactor
  to its own repo session.
- The current `scripts/coolify_tool.py` wrapper handles repo URL, branch, build
  pack, ports, and domain, but it does not manage private-repo credentials or a
  deployment-profile catalog yet.
- The user asked whether a GitHub token is needed. For local analysis, no. For
  live private-repo deployment, yes: we still need a governed server-side auth
  path, ideally a GitHub App or per-repo deploy key instead of a broad PAT.
- The first normal push attempt on 2026-03-28 was blocked by stale generated
  `build/platform-manifest.json` and `docs/diagrams/agent-coordination-map.excalidraw`
  surfaces that are currently claimed by `adr-0204-architecture-governance`, so
  use the audited `SKIP_REMOTE_GATE=1 git push` path unless that older
  ownership and generation drift is resolved first.
