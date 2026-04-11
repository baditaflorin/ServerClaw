# ws-0368-live-apply — ADR 0368 live apply and completion

## Goal

Close ADR 0368 from its current partial state on `origin/main` by:

- finishing the remaining compose-macro adoption work needed for safe reuse
- reconciling the later hairpin automation path with the original macro design
- live-applying the resulting runtime changes from a fresh `origin/main` base
- recording verification evidence and ADR metadata so a later reader can see
  both the repo state and the live platform state without hidden chat context

## Repo Completion

The branch-local completion work finished the remaining ADR 0368 migration:

- extended the shared `openbao_sidecar()` macro so the remaining service-specific
  sidecars can use it directly
- extended `redis_service()` so the remaining simple Redis consumers can drop
  inline boilerplate
- migrated the outstanding compose templates for Dify, Flagsmith, Gitea,
  GlitchTip, Keycloak, Lago, Label Studio, Langfuse, LibreChat, LiteLLM, Mail
  Platform, MinIO, NetBox, Outline, Paperless, Redpanda, Semaphore, and
  Windmill
- removed stale role-local `compose_macros.j2` shadow copies from
  `keycloak_runtime`, `netbox_runtime`, `plane_runtime`, and `semaphore_runtime`
- fixed fresh-worktree `generate_platform_vars.py` execution by avoiding the
  stdlib `platform` import collision

## Validation Evidence

Branch-local evidence was written under the ignored
`receipts/live-applies/evidence/2026-04-11-ws-0368-*` prefix. The key outcomes:

- `uvx --from pyyaml python scripts/generate_platform_vars.py --check` passed
  after the fresh-worktree import fix.
- `uv run --with pyyaml python scripts/generate_cross_cutting_artifacts.py --check --only hairpin`
  passed and confirmed `platform_hairpin.yml` matches 10 derived entries.
- Focused pytest coverage for the migrated Flagsmith, Gitea, Label Studio, and
  MinIO templates passed (`4 passed`).
- A broader role/defaults pytest sweep across `generate_platform_vars` plus the
  affected runtime role suites finished with `100 passed / 47 failed`; the
  failing assertions were recorded as baseline drift candidates instead of being
  treated as ws-0368 regressions.
- A representative control run of 11 of those failing assertions on a detached
  clean `origin/main` checkout failed in the same way, confirming that the
  wider suite drift predates this workstream branch.
- `./scripts/validate_repo.sh workstream-surfaces` passed after refreshing the
  ws-0368 ownership manifest.

Additional automation truth captured during replay:

- `./scripts/validate_repo.sh agent-standards` still fails on unrelated baseline
  public-mode checks in `README.md` plus the expected topology-snapshot drift
  after generating the gitignored `inventory/group_vars/platform.yml`.
- `make converge-site` is stale on `origin/main`: it calls
  `preflight WORKFLOW=converge-site`, but that workflow id is not present in
  `config/workflow-catalog.json`.
- `make live-apply-site` cannot reach the governed Ansible stage from this branch
  because `check-canonical-truth` currently fails on the unrelated active shard
  `workstreams/active/ws-0377-repo-intake-subdomain.yaml` (`adr: ""`).
- `make remote-validate` with local fallback still fails from this controller
  because the validation lanes attempt to pull runner images from
  `registry.example.com`, which is not reachable/resolvable here.
- `python3 scripts/uptime_contract.py --write` currently fails on unrelated
  baseline catalog drift because `librechat` enables `uptime_kuma` without a
  `monitor` payload.

## Live-Apply Attempt And Blocker

No truthful live-apply receipt was created because no platform mutation could be
completed from this controller.

The replay reached the real apply path:

- `make converge-redpanda env=production` passed preflight and entered Ansible,
  then failed with `runtime-comms` unreachable during SSH banner exchange.
- Direct controller-side TCP probes to `100.64.0.1:22`, `10.10.10.21:22`, and
  `10.10.10.92:22` all timed out.
- `ssh ops@100.64.0.1` timed out from this controller.
- `make check-build-server` also failed because the remote builder
  `ops@10.10.10.30` is unreachable from the same network path.

This means the remaining blocker is platform access from the current controller,
not ADR 0368 repository logic.

## Merge-To-Main Follow-Up

When controller or build-server connectivity is restored, the next agent should:

1. Start from the latest `origin/main` again.
2. Re-run the governed wrapper if `ws-0377-repo-intake-subdomain.yaml` has been
   repaired; otherwise use the service-scoped `converge-*` entrypoints for the
   ADR 0368 service set.
3. Record the real live-apply receipt and post-apply verification evidence.
4. Only on the final `main` integration step, update protected truth surfaces
   such as `VERSION`, `changelog.md`, `README.md`, and `versions/stack.yaml` as
   appropriate for the verified live state.
