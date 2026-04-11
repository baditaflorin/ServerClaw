# Workstream ws-0232-main-merge

- ADR: [ADR 0232](../adr/0232-nomad-for-durable-batch-and-long-running-internal-jobs.md)
- Title: Integrate ADR 0232 Nomad live apply into `origin/main`
- Status: merged
- Included In Repo Version: 0.177.65
- Platform Version Observed During Merge: 0.130.44
- Release Date: 2026-03-29
- Branch: `codex/ws-0232-main-merge`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.worktrees/ws-0232-main-merge`
- Owner: codex
- Depends On: `ws-0232-live-apply`

## Purpose

Carry the verified ADR 0232 Nomad scheduler work onto the latest `origin/main`
after successive rebases through repository versions `0.177.58`, `0.177.59`,
`0.177.60`, `0.177.61`, `0.177.62`, `0.177.63`, and `0.177.64`, rerun the
guarded production replay from the final `0.177.64` base, record fresh
exact-main evidence, and cut repository release `0.177.65` without changing
the live platform baseline from `0.130.44`.

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
- `inventory/host_vars/proxmox-host.yml`
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
- `docs/release-notes/0.177.65.md`
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
- `receipts/live-applies/2026-03-29-adr-0232-nomad-mainline-live-apply.json`

## Verification

- `git fetch origin --prune` confirmed the final integration base was
  `origin/main` commit `a33ac1b8` with repository version `0.177.64`
- `make immutable-guest-replacement-plan service=nomad` confirmed ADR 0191
  still classifies `monitoring` as `edge_and_stateful` with validation mode
  `preview_guest` and rollback window `180m`
- `make live-apply-service service=nomad env=production` passed canonical
  truth, interface-contract, capacity, and redundancy checks, then failed
  closed at the immutable guest replacement gate until the documented narrow
  exception was supplied
- `make live-apply-service service=nomad env=production ALLOW_IN_PLACE_MUTATION=true`
  completed successfully from the rebased `0.177.64` worktree with final recap
  `docker-build ok=83 changed=5 failed=0`,
  `docker-runtime ok=95 changed=5 failed=0`,
  `localhost ok=12 changed=0 failed=0`,
  `monitoring ok=98 changed=2 failed=0`, and
  `proxmox-host ok=51 changed=4 failed=0`
- controller-side Nomad verification returned leader `"10.10.10.40:4647"` and
  nodes `docker-runtime ready runtime` plus `docker-build ready build`
- guest-side smoke verification returned `lv3-nomad-smoke-service` as
  `running` with deployment `successful`, `curl -fsS http://10.10.10.30:18180/`
  returned `lv3 nomad smoke service`, and the durable batch marker on
  `docker-runtime` recorded `2026-03-29T02:19:07+00:00`
- `LV3_SKIP_OUTLINE_SYNC=1 uv run --with pyyaml python scripts/release_manager.py --bump patch --platform-impact "release 0.177.65 records the verified ADR 0232 Nomad replay from the latest origin/main while the live platform baseline remains 0.130.44"` prepared release `0.177.65`
- `uv run --with pytest --with pyyaml pytest tests/test_nomad_playbook.py tests/test_nomad_cluster_roles.py tests/test_generate_platform_vars.py tests/test_proxmox_tailscale_proxy_role.py -q` passed with `27 passed in 1.48s`
- `make syntax-check-nomad`, `uv run --with pyyaml --with jsonschema python scripts/live_apply_receipts.py --validate`, `uvx --from pyyaml python scripts/canonical_truth.py --check`, `uv run --with pyyaml --with jsonschema python scripts/platform_manifest.py --check`, and `git diff --check` all passed on the final integration worktree
- `./scripts/validate_repo.sh generated-vars ansible-syntax yaml role-argument-specs`, `./scripts/validate_repo.sh health-probes alert-rules tofu data-models policy architecture-fitness`, and `./scripts/validate_repo.sh generated-portals` all passed; the portal build emitted the same long-running MkDocs non-nav informational output already present on current main
- `./scripts/validate_repo.sh agent-standards workstream-surfaces generated-docs` passed after the integration branch was temporarily marked `ready` so the ownership validator could treat `codex/ws-0232-main-merge` as the active workstream while validating the combined live-apply plus protected-release diff
- `python3 scripts/check_ad_hoc_retry.py` still fails on the shared current-main issue `scripts/release_bundle.py:562: retry-like loop uses raw time.sleep; migrate to platform.retry.with_retry`
- `./scripts/validate_repo.sh ansible-lint` was retried on the refreshed branch but again stayed non-terminating for several minutes and had to be interrupted, so no fresh clean pass was captured from this run

## Outcome

- release `0.177.65` records ADR 0232 on `main` and promotes canonical receipt
  `2026-03-29-adr-0232-nomad-mainline-live-apply`
- the live platform baseline remains `0.130.44`; this merge records exact-main
  proof rather than a further platform version bump
- the earlier branch-local receipt remains preserved as the first isolated
  worktree replay, while the `2026-03-29` receipt is the canonical source for
  README, release notes, and stack truth
