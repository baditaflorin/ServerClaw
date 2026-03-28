# Workstream ws-0232-main-merge

- ADR: [ADR 0232](../adr/0232-nomad-for-durable-batch-and-long-running-internal-jobs.md)
- Title: Integrate ADR 0232 Nomad live apply into `origin/main`
- Status: merged
- Included In Repo Version: 0.177.52
- Platform Version Observed During Merge: 0.130.43
- Release Date: 2026-03-28
- Branch: `codex/ws-0232-main-merge`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0232-main-merge`
- Owner: codex
- Depends On: `ws-0232-live-apply`

## Purpose

Carry the verified ADR 0232 Nomad live-apply branch onto the latest
`origin/main`, cut repository release `0.177.52`, advance the canonical
platform version to `0.130.43`, refresh the protected generated truth surfaces,
and rerun the repo automation plus validation bundle from the clean integration
worktree before pushing `main`.

## Shared Surfaces

- `Makefile`
- `playbooks/groups/automation.yml`
- `playbooks/nomad.yml`
- `playbooks/services/nomad.yml`
- `collections/ansible_collections/lv3/platform/roles/nomad_cluster_member/`
- `collections/ansible_collections/lv3/platform/roles/nomad_cluster_bootstrap/`
- `collections/ansible_collections/lv3/platform/roles/proxmox_network/`
- `config/nomad/jobs/`
- `config/ansible-execution-scopes.yaml`
- `config/ansible-role-idempotency.yml`
- `config/command-catalog.json`
- `config/service-capability-catalog.json`
- `config/service-completeness.json`
- `config/service-redundancy-catalog.json`
- `config/health-probe-catalog.json`
- `config/secret-catalog.json`
- `config/controller-local-secrets.json`
- `config/dependency-graph.json`
- `config/workflow-catalog.json`
- `inventory/host_vars/proxmox_florin.yml`
- `inventory/group_vars/platform.yml`
- `scripts/generate_platform_vars.py`
- `tests/test_nomad_playbook.py`
- `tests/test_nomad_cluster_roles.py`
- `tests/test_generate_platform_vars.py`
- `tests/test_proxmox_tailscale_proxy_role.py`
- `workstreams.yaml`
- `docs/workstreams/ws-0232-main-merge.md`
- `README.md`
- `RELEASE.md`
- `VERSION`
- `changelog.md`
- `docs/release-notes/README.md`
- `docs/release-notes/0.177.52.md`
- `versions/stack.yaml`
- `build/platform-manifest.json`
- `docs/site-generated/architecture/dependency-graph.md`
- `docs/diagrams/agent-coordination-map.excalidraw`
- `docs/diagrams/service-dependency-graph.excalidraw`
- `docs/adr/.index.yaml`
- `docs/adr/0232-nomad-for-durable-batch-and-long-running-internal-jobs.md`
- `docs/runbooks/configure-nomad.md`
- `docs/workstreams/ws-0232-live-apply.md`
- `receipts/live-applies/2026-03-28-adr-0232-nomad-live-apply.json`
- `receipts/live-applies/2026-03-28-adr-0232-nomad-mainline-live-apply.json`

## Plan

- register the integration branch so `workstream-surfaces` can validate the
  combined live-apply and protected-release diff against `origin/main`
- cut release `0.177.52` from the latest rebased integration worktree
- promote the integrated Nomad receipt into canonical truth and bump
  `versions/stack.yaml.platform_version` from `0.130.42` to `0.130.43`
- rerun the repo validation and live-apply automation checks before pushing
  `main`

## Verification

- `git fetch origin --prune` confirmed the integration worktree remained based
  on `origin/main` commit `6ca35b46` before the release cut
- `uv run --with pyyaml python scripts/release_manager.py --bump patch --platform-impact "release 0.177.52 records the verified latest-origin/main Nomad scheduler replay; the follow-on mainline live-apply proof advances platform version from 0.130.42 to 0.130.43" --dry-run` reported `Current version: 0.177.51`, `Next version: 0.177.52`, and one unreleased note
- `uv run --with pyyaml python scripts/release_manager.py --bump patch --platform-impact "release 0.177.52 records the verified latest-origin/main Nomad scheduler replay; the follow-on mainline live-apply proof advances platform version from 0.130.42 to 0.130.43"` prepared release `0.177.52`
- `make immutable-guest-replacement-plan service=nomad` confirmed the ADR 0191 guard for `monitoring-lv3`, and `make live-apply-service service=nomad env=production` failed closed at that guard until `ALLOW_IN_PLACE_MUTATION=true` was explicitly supplied for the documented narrow exception
- `uv run --with pytest --with pyyaml pytest tests/test_nomad_playbook.py tests/test_nomad_cluster_roles.py tests/test_generate_platform_vars.py tests/test_proxmox_tailscale_proxy_role.py -q` passed with `27 passed in 1.59s`
- `make syntax-check-nomad`, `uv run --with pyyaml --with jsonschema python scripts/live_apply_receipts.py --validate`, `uvx --from pyyaml python scripts/canonical_truth.py --check`, `uv run --with pyyaml --with jsonschema python scripts/platform_manifest.py --check`, and `git diff --check` all passed on the refreshed integration worktree
- `./scripts/validate_repo.sh agent-standards workstream-surfaces` passed after the integration branch was temporarily marked `ready` so the branch-ownership validator could treat `codex/ws-0232-main-merge` as the active workstream while validating the combined live-apply plus protected-release diff
- `uv run --with jsonschema python scripts/generate_dependency_diagram.py --write`, `uvx --from pyyaml python scripts/generate_diagrams.py --write`, and `./scripts/validate_repo.sh workstream-surfaces generated-docs` refreshed and revalidated the stale dependency-graph and diagram artifacts that the first full validation pass surfaced
- the final `make validate` run completed successfully end to end on the `ready` validation state; the bundle still emitted the same seven warning-level `ansible-lint` findings in `control_plane_recovery/defaults/main.yml`, `monitoring_vm/tasks/main.yml`, `openbao_runtime/defaults/main.yml`, and `windmill_runtime/{defaults,tasks}/main.yml`, plus MkDocs informational output about non-nav docs pages, but the overall exit code was `0`

## Outcome

- release `0.177.52` now records ADR 0232 on `main`, and `versions/stack.yaml`
  promotes `nomad_scheduler` to receipt
  `2026-03-28-adr-0232-nomad-mainline-live-apply`
- the canonical platform version advanced to `0.130.43` after the verified
  latest-`origin/main` Nomad replay, while the ADR metadata preserves
  `0.130.41` as the first platform version where ADR 0232 became true
- the branch-local receipt remains preserved as historical evidence, but the
  new mainline-equivalent receipt is now the canonical live-apply source for
  README, release notes, and stack truth
