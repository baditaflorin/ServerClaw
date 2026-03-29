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
  `inventory/group_vars/platform.yml`, `playbooks/coolify.yml`,
  `scripts/generate_platform_vars.py`,
  `scripts/coolify_tool.py`, `scripts/lv3_cli.py`,
  `tests/test_generate_platform_vars.py`, `tests/test_coolify_playbook.py`,
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
- `inventory/group_vars/platform.yml`
- `playbooks/coolify.yml`
- `scripts/generate_platform_vars.py`
- `scripts/coolify_tool.py`
- `scripts/lv3_cli.py`
- `tests/test_generate_platform_vars.py`
- `tests/test_coolify_playbook.py`
- `tests/test_coolify_tool.py`
- `tests/test_lv3_cli.py`
- `docs/adr/0224-self-service-repo-intake-and-agent-assisted-deployments.md`
- `docs/workstreams/adr-0224-self-service-repo-intake-and-agent-assisted-deployments.md`
- `docs/adr/.index.yaml`
- `workstreams.yaml`

## Expected Live Surfaces

- the named application route `education-wemeshup.apps.lv3.org`
- the wildcard DNS record `*.apps.lv3.org -> 65.108.75.123`
- the live-apply receipt
  `receipts/live-applies/2026-03-28-adr-0224-coolify-wildcard-dns-live-apply.json`

## Ownership Notes

- The current governed deployment lane already exists through ADR 0194:
  private Coolify API, protected dashboard, and wildcard app ingress are live.
- The missing governed capability was private-repo credential bootstrap plus a
  richer intake contract on top of the existing deploy wrapper. This workstream
  implements that slice first.
- The original `/Users/live/Documents/GITHUB_PROJECTS/education_wemeshup`
  checkout is still dirty and remains reference-only.
- A clean deployment worktree at
  `/Users/live/Documents/GITHUB_PROJECTS/education_wemeshup/.worktrees/ws-0224-main-check`
  is pinned to committed GitHub state for verification and app-side fixes.

## Verification

- `git ls-remote git@github.com:baditaflorin/education_wemeshup.git HEAD`
- `git -C /Users/live/Documents/GITHUB_PROJECTS/education_wemeshup/.worktrees/live-11-deploy-fixes status --short --branch`
- `git -C /Users/live/Documents/GITHUB_PROJECTS/education_wemeshup/.worktrees/live-11-deploy-fixes log -1 --oneline`
- `docker compose -f /Users/live/Documents/GITHUB_PROJECTS/education_wemeshup/.worktrees/live-11-deploy-fixes/compose.yaml config`
- `docker compose -f /Users/live/Documents/GITHUB_PROJECTS/education_wemeshup/.worktrees/live-11-deploy-fixes/compose.yaml up --build -d`
- `curl http://127.0.0.1:8081/readyz`
- `curl http://127.0.0.1:8080/healthz`
- `curl http://127.0.0.1:8080/api/v1/catalog/taxonomy`

Observed across 2026-03-28 and 2026-03-29:

- GitHub SSH access works from the controller.
- The current committed app head has advanced through PR `#2` and PR `#3` to
  `d6c58dd Harden Alpine runtime package install`.
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
- Browser reachability still failed outside controller-local `--resolve` probes
  because `*.apps.lv3.org` was present only as an NGINX edge alias, not as a
  managed Hetzner DNS wildcard record.
- This follow-up extends the generated `hetzner_dns_records` surface so public
  DNS aliases are derived from repo-managed `edge.aliases`, then replays the
  Coolify service converge path to publish `*.apps.lv3.org` automatically.
- The first scoped DNS publication attempt hit an opaque Hetzner API failure on
  wildcard-record creation while the Ansible task was still redacted by
  `no_log`. Replaying the exact `*.apps` POST directly against the Hetzner DNS
  API succeeded immediately, and the same repo-managed playbook then reran
  cleanly with `changed=0`.
- Authoritative and public recursive resolvers now answer `65.108.75.123` for
  `education-wemeshup.apps.lv3.org`, although the controller's default resolver
  briefly kept the earlier NXDOMAIN cached after the wildcard record appeared.
- Pulling the newer Dockerized app revision surfaced two transient failure
  classes that needed codified handling: Docker Hub anonymous-token timeouts
  during base-image resolution and temporary Alpine package-index failures
  during runtime-image assembly.
- The app-side fixes were merged upstream as PR `#2` and PR `#3`, and the
  infra-side governed wrapper now retries these transient deployment failures in
  a bounded way instead of failing immediately on the first network wobble.
- A follow-up live probe on 2026-03-29 exposed one more platform-side drift:
  the canonical host vars already modeled `coolify_apps` over
  `https://10.10.10.70:443`, but `scripts/generate_platform_vars.py` was still
  emitting `http://10.10.10.70:80` for the generated `platform.yml` surface.
  Replaying the public edge from that stale generated contract recreated the
  historical same-host redirect loop.
- The generator now emits the `coolify_apps` internal URL and edge upstream over
  TLS `443`, and a scoped edge plus guest-network replay restored public `200`
  and the taxonomy API response for `education-wemeshup.apps.lv3.org`.
- The next live replay hardened the build lane itself: `coolify-lv3` now
  renders `/etc/docker/daemon.json` with public resolvers `1.1.1.1` and
  `8.8.8.8` plus the approved Docker Hub mirror `https://mirror.gcr.io`, and
  the previously wedged BuildKit/npm worker processes disappeared immediately
  after the Docker runtime converge.
- A first rerun of `make converge-coolify` from a fresh worktree still failed
  during the NGINX edge phase because the shared static site sync inputs
  `build/changelog-portal/` and `build/docs-portal/` were absent locally; after
  generating those artifacts and replaying `make configure-edge-publication`,
  the wildcard edge rendered cleanly from repo state.
- With the edge fixed and the guest Docker daemon hardened, the governed
  `deploy-repo` wrapper redeployed `education_wemeshup` upstream `main`
  commit `dd577f374051d24710b461e9cfb796e21ad49da2` successfully on the first
  attempt.
- Public verification now returns `HTTP/2 200` for
  `https://education-wemeshup.apps.lv3.org/`, and
  `/api/v1/catalog/taxonomy` reports catalog version `2.0.0`, `95`
  categories, and `1056` activities through the production wildcard domain.

## Merge Criteria

- a governed private-repo auth path is documented and implemented
- one governed deployment request can select environment, source mode, and
  domain without hand-editing Coolify API calls
- the first private GitHub smoke repo deploys from committed Git state
- the path clearly separates direct deploy, bounded agent assist, and
  production promotion

## Notes For The Next Assistant

- The app repo has moved beyond the original `index.html` baseline. Use the
  clean `ws-0224-main-check` worktree, not the dirty top-level checkout, if
  app-side fixes become necessary.
- The current implementation path uses per-repo GitHub deploy keys and a
  matching Coolify private key instead of a broad PAT.
- The current codified non-chat operator path is `make coolify-manage` or
  `python3 scripts/lv3_cli.py deploy-repo`; the next product layer should be a
  browser intake form in the existing ops portal, not a second deployment
  mechanism.
- No new ADR is needed for that browser/operator surface specifically, because
  ADR 0090, ADR 0092, ADR 0093, ADR 0194, and ADR 0224 already cover the
  terminal contract, gateway, portal, Coolify lane, and self-service intake
  shape.
- A new ADR was still added for the separate supply-path gap surfaced here:
  ADR 0274 now codifies cache-first base-image mirrors and warm caches for
  expected repo-deploy images.
- The first implementation slice of ADR 0274 is now live on `coolify-lv3`
  through the governed Docker daemon resolver and registry-mirror settings;
  scheduled image warming and catalog-backed bundle refresh still remain
  follow-up work.
- If the public app path unexpectedly returns a same-host `302` or times out
  after an edge replay, verify that generated `inventory/group_vars/platform.yml`
  still points `coolify_apps.edge.upstream` to `https://10.10.10.70:443`, then
  replay `configure-edge-publication` and the scoped guest-network policy for
  `proxmox_florin,coolify-lv3`.
- If wildcard app traffic loops on `307 https://same-host/...`, check whether
  the NGINX edge is still proxying `coolify_apps` to `http://<coolify-vm>:80`
  instead of `https://<coolify-vm>:443`.
- If the wildcard edge already proxies to `https://<coolify-vm>:443` but the
  request still times out, verify both the Proxmox VM firewall file and the
  `coolify-lv3` guest nftables policy allow `nginx-lv3` to reach TCP `443`.
- If `configure-edge-publication` fails on missing `build/changelog-portal/`
  or `build/docs-portal/`, run `make generate-changelog-portal docs` in the
  current worktree before replaying the edge lane.
- The next layer after this workstream should be a deployment-profile catalog
  and intake UI, not another bespoke deployment mechanism.
- The companion `education_wemeshup` repository merged PR `#10` on
  2026-03-29 to harden the frontend Docker build with an isolated npm cache and
  bounded `npm ci` retries after Coolify repeatedly hit the npm
  `Exit handler never called!` flake during fresh rebuilds.
- The companion `education_wemeshup` repository merged PR `#13` on
  2026-03-29 to wrap `npm ci` in a hard timeout after a later live build
  wedged indefinitely inside the installer with no network activity, leaving
  the Coolify deployment in `in_progress` until it was manually cancelled.
- `scripts/coolify_tool.py deploy-repo` now cancels stale queued or
  in-progress deployments for the same application before it starts the next
  governed rollout so dead queue records do not block newer commits.
- The first normal push attempt on 2026-03-28 was blocked by stale generated
  `build/platform-manifest.json` and `docs/diagrams/agent-coordination-map.excalidraw`
  surfaces that are currently claimed by `adr-0204-architecture-governance`, so
  use the audited `SKIP_REMOTE_GATE=1 git push` path unless that older
  ownership and generation drift is resolved first.
