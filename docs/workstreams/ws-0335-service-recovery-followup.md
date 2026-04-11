# Workstream ws-0335-service-recovery-followup: Recover The Remaining Degraded Services After Runtime-Pool Stabilization

- ADR: [ADR 0319](../adr/0319-runtime-pools-as-the-service-partition-boundary.md), [ADR 0320](../adr/0320-pool-scoped-deployment-surfaces-and-agent-execution-lanes.md)
- Title: Investigate and recover the remaining services that are still down or not responding properly after ws-0332 and ws-0333
- Status: live_applied
- Included In Repo Version: 0.178.4
- Branch-Local Receipt: `receipts/live-applies/2026-04-04-ws-0335-service-recovery-followup-live-apply.json`
- Live Applied On: 2026-04-04
- Latest Verified Base: `origin/main@0cd845578` (`repo 0.178.3`, `platform 0.130.98`)
- Branch: `codex/ws-0335-service-recovery-followup`
- Worktree: `.worktrees/ws-0335-service-recovery-followup`
- Owner: codex
- Depends On: `ws-0332-homepage-triage`, `ws-0333-service-uptime-recovery`
- Conflicts With: none
- Shared Surfaces: `workstreams.yaml`, `workstreams/active/ws-0335-service-recovery-followup.yaml`, `docs/workstreams/ws-0335-service-recovery-followup.md`, `receipts/live-applies/`

## Scope

- verify the live state of the runtime, control-plane, and Coolify-managed service surfaces from latest `origin/main`
- separate intentionally stopped services from crash-looping or misrouted services
- identify the remaining concrete blockers to uptime after the ws-0332 and ws-0333 protections landed
- apply the smallest safe repo-managed or documented live recovery needed to restore healthy service behavior
- record receipts and follow-up risks so later work does not have to rediscover the same failure classes

## Initial Questions

- which services are still down right now, on which guest, and are they `exited`, `restarting`, or only failing at the edge?
- are the remaining failures now app-local problems, missing-runtime prerequisites, stale publication state, or another shared-host issue?
- can the remaining unhealthy services be recovered from exact `main`, or do they require a new bounded fix first?

## Verification Plan

- inspect the current live container and publication state on the affected guests
- replay only the smallest safe repo-managed recovery path for the confirmed failures
- capture the evidence in `receipts/live-applies/`

## Findings

- The remaining public failures on `2026-04-04` were concentrated in Directus, Harbor, Matrix, Outline, JupyterHub, Paperless, Plausible, Woodpecker, and Vaultwarden.
- On `docker-runtime`, the main recovery blocker was missing `/run/lv3-secrets/<service>/runtime.env` material for several OpenBao-backed Compose stacks after earlier churn. Narrow recoveries succeeded by starting the stack-local `openbao-agent`, waiting for the runtime env file, and then replaying `docker compose up -d`.
- JupyterHub required an additional bounded fix because its local images (`lv3/jupyterhub-hub:latest` and `lv3/jupyterhub-singleuser:latest`) had to be rebuilt from the rendered runtime directories before the service could start again.
- Vaultwarden on `runtime-control` was healthy locally, but the Proxmox Tailscale proxy still pointed at the retired upstream `10.10.10.20:8222`; replaying the governed proxy path restored `https://vault.example.com/alive`.
- Harbor exposed a second control-plane failure class: the `vaultwarden.yml` replay on `2026-04-04T00:25:30Z` restarted `docker.service` on `runtime-control` while applying the branch-local `Disable Docker socket activation` task. After that daemon restart, most Harbor containers failed to auto-start because their logging driver expected `localhost:1514` before `harbor-log` was healthy, leaving `registry.example.com` on `502` until the Harbor compose stack was replayed.

## Recovery Summary

- Recovered Directus, Matrix Synapse, Outline, JupyterHub, Paperless, Plausible, and Woodpecker on `docker-runtime` with bounded stack-local restarts and evidence captured under `receipts/live-applies/evidence/2026-04-04-ws-0335-*.txt`.
- Replayed the Vaultwarden path on `runtime-control`, which corrected the Proxmox host proxy drift and restored the `vault.example.com` liveness contract.
- Patched `collections/ansible_collections/lv3/platform/roles/docker_runtime/tasks/main.yml` so disabling `docker.socket` no longer stops a live Docker daemon; the role now disables the socket without stopping it when `docker.service` is already active, and only stops the socket when Docker is inactive.
- Recovered Harbor with a bounded `docker compose up -d --remove-orphans` replay after the control-plane Docker restart left only `harbor-log` up.

## Verification

- `uv run --with pytest --with pyyaml python -m pytest tests/test_docker_runtime_role.py tests/test_openbao_compose_env_helper.py tests/test_compose_runtime_secret_injection.py -q` passed with `31 passed`.
- `git diff --check` passed after the role and test updates.
- A final concurrent sweep of the public `example.com` SLO catalog returned `200` for every public route except the expected Woodpecker `204`, including `registry.example.com` and `vault.example.com`.

## Exact-Main Integration Status

- The ws-0335 recovery changes are now archived into repository release `0.178.4` instead of remaining only as unreleased exact-main truth.
- Repository release `0.178.4` carries the recovery metadata through `changelog.md`, `versions/stack.yaml`, `workstreams.yaml`, `README.md`, and the generated status/history surfaces.
- These recovery fixes were already verified live on platform version `0.130.98`, so the numbered repo release does not add a platform-version bump.
