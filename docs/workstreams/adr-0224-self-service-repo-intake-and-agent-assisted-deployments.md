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
  `docs/adr/.index.yaml`, `docs/runbooks/configure-coolify.md`,
  `inventory/host_vars/proxmox_florin.yml`, `inventory/group_vars/platform.yml`,
  `config/subdomain-exposure-registry.json`,
  `scripts/coolify_tool.py`, `scripts/lv3_cli.py`,
  `tests/test_coolify_tool.py`, `tests/test_lv3_cli.py`, `workstreams.yaml`
- Ownership Manifest: `workstreams.yaml` `ownership_manifest`

## Scope

- create a tracked workstream for the requested repo-intake flow
- record the architecture direction in ADR 0224
- implement the governed private-repo bootstrap path for the existing Coolify
  repo deploy wrapper
- expose the new private deploy-key and Docker Compose fields through `lv3`
- anchor the first smoke target on the Dockerized `education_wemeshup`
  repository

## Non-Goals

- mutating the live platform in this discovery turn
- changing protected integration truth such as `README.md`, `VERSION`,
  `changelog.md`, or `versions/stack.yaml`
- editing the dirty local
  `/Users/live/Documents/GITHUB_PROJECTS/education_wemeshup` checkout owned by
  another session
- redesigning the entire intake catalog before the first governed smoke path
  works end to end

## Expected Repo Surfaces

- `docs/runbooks/configure-coolify.md`
- `inventory/host_vars/proxmox_florin.yml`
- `inventory/group_vars/platform.yml`
- `config/subdomain-exposure-registry.json`
- `scripts/coolify_tool.py`
- `scripts/lv3_cli.py`
- `tests/test_coolify_tool.py`
- `tests/test_lv3_cli.py`
- `docs/adr/0224-self-service-repo-intake-and-agent-assisted-deployments.md`
- `docs/workstreams/adr-0224-self-service-repo-intake-and-agent-assisted-deployments.md`
- `docs/adr/.index.yaml`
- `workstreams.yaml`

## Expected Live Surfaces

- none yet

The first live smoke path should be a private-repo deployment of the Dockerized
`education_wemeshup` GitHub repository into `*.apps.lv3.org`.

## Ownership Notes

- The current governed deployment lane already exists through ADR 0194:
  private Coolify API, protected dashboard, and wildcard app ingress are live.
- The missing governed capability was private-repo credential bootstrap plus a
  richer intake contract on top of the existing deploy wrapper. This workstream
  implements that slice first.
- The original `/Users/live/Documents/GITHUB_PROJECTS/education_wemeshup`
  checkout is still dirty and remains reference-only.
- A clean deployment worktree at
  `/Users/live/Documents/GITHUB_PROJECTS/education_wemeshup/.worktrees/live-11-deploy-fixes`
  is pinned to committed GitHub state for verification and any app-side fixes.

## Verification

- `git ls-remote git@github.com:baditaflorin/education_wemeshup.git HEAD`
- `git -C /Users/live/Documents/GITHUB_PROJECTS/education_wemeshup/.worktrees/live-11-deploy-fixes status --short --branch`
- `git -C /Users/live/Documents/GITHUB_PROJECTS/education_wemeshup/.worktrees/live-11-deploy-fixes log -1 --oneline`
- `docker compose -f /Users/live/Documents/GITHUB_PROJECTS/education_wemeshup/.worktrees/live-11-deploy-fixes/compose.yaml config`
- `docker compose -f /Users/live/Documents/GITHUB_PROJECTS/education_wemeshup/.worktrees/live-11-deploy-fixes/compose.yaml up --build -d`
- `curl http://127.0.0.1:8081/readyz`
- `curl http://127.0.0.1:8080/healthz`
- `curl http://127.0.0.1:8080/api/v1/catalog/taxonomy`

Observed on 2026-03-28:

- GitHub SSH access works from the controller.
- The current committed app head is `0f3c228 Add compose live stack wiring`.
- The clean deployment worktree composes three healthy services:
  `postgres`, `catalog-api`, and `catalog-web`.
- Local smoke checks pass against the committed Dockerized stack:
  `/readyz`, `/healthz`, and `/api/v1/catalog/taxonomy`.
- After the app-side port fix merged, Coolify deployment finished healthy from
  `main`, but the outer wildcard edge still looped on `307` because NGINX was
  proxying wildcard app traffic to the Coolify VM over plain HTTP instead of
  HTTPS.
- After switching the wildcard edge upstream to HTTPS, the public app path still
  timed out until the managed `coolify-lv3` guest firewall allowed `nginx-lv3`
  to reach TCP `443` in addition to `80` and `8000`.
- After replaying the Proxmox guest-firewall files plus the `coolify-lv3`
  nftables policy, `education-wemeshup.apps.lv3.org` returned `HTTP/2 200` and
  `/api/v1/catalog/taxonomy` answered with API version `v1`, `2` categories,
  and `6` activities through the public edge.

## Merge Criteria

- a governed private-repo auth path is documented and implemented
- one governed deployment request can select environment, source mode, and
  domain without hand-editing Coolify API calls
- the first private GitHub smoke repo deploys from committed Git state
- the path clearly separates direct deploy, bounded agent assist, and
  production promotion

## Notes For The Next Assistant

- The app repo has moved beyond the original `index.html` baseline. Use the
  clean `live-11-deploy-fixes` worktree, not the dirty top-level checkout, if
  app-side fixes become necessary.
- The current implementation path uses per-repo GitHub deploy keys and a
  matching Coolify private key instead of a broad PAT.
- If wildcard app traffic loops on `307 https://same-host/...`, check whether
  the NGINX edge is still proxying `coolify_apps` to `http://<coolify-vm>:80`
  instead of `https://<coolify-vm>:443`.
- If the wildcard edge already proxies to `https://<coolify-vm>:443` but the
  request still times out, verify both the Proxmox VM firewall file and the
  `coolify-lv3` guest nftables policy allow `nginx-lv3` to reach TCP `443`.
- The next layer after this workstream should be a deployment-profile catalog
  and intake UI, not another bespoke deployment mechanism.
- The first normal push attempt on 2026-03-28 was blocked by stale generated
  `build/platform-manifest.json` and `docs/diagrams/agent-coordination-map.excalidraw`
  surfaces that are currently claimed by `adr-0204-architecture-governance`, so
  use the audited `SKIP_REMOTE_GATE=1 git push` path unless that older
  ownership and generation drift is resolved first.
