# Workstream ws-0371-live-apply: ADR 0371 Parameterized Service Verification Tasks

- ADR: [ADR 0371](../adr/0371-parameterized-verify-tasks.md)
- Title: re-verify parameterized service verification tasks from latest origin/main
- Status: blocked
- Included In Repo Version: pending merge to `main`
- Branch-Local Receipt: scoped `litellm` replay failed during `proxmox_network` post-reload reachability
- Mainline Receipt: pending
- Implemented On: 2026-04-11
- Live Applied On: pending
- Live Applied In Platform Version: pending
- Latest Verified Base: `origin/main@86390fcc8` (`repo 0.178.116`, `platform 0.178.77`)
- Branch: `codex/ws-0371-live-apply`
- Worktree: `.worktrees/ws-0371-live-apply`
- Owner: codex
- Depends On: `ADR 0165`, `ADR 0289`, `ADR 0371`
- Conflicts With: none
- Shared Surfaces: `collections/ansible_collections/lv3/platform/roles/common/defaults/main.yml`, `collections/ansible_collections/lv3/platform/roles/common/tasks/verify_service_health.yml`, `collections/ansible_collections/lv3/platform/roles/common/tasks/verify_service_health_extra.yml`, `collections/ansible_collections/lv3/platform/roles/librechat_runtime/tasks/verify.yml`, `collections/ansible_collections/lv3/platform/roles/litellm_runtime/tasks/verify.yml`, `collections/ansible_collections/lv3/platform/roles/repowise_runtime/tasks/verify.yml`, `docs/adr/0371-parameterized-verify-tasks.md`, `docs/runbooks/live-apply-receipts-and-verification-evidence.md`, `workstreams/active/ws-0371-live-apply.yaml`, `workstreams.yaml`

## Scope

- confirm the latest `origin/main` state of ADR 0371, which already contains the
  shared `verify_service_health` task include and a broad role migration
- close the remaining legacy verifier wrappers that still use hand-written
  `wait_for` and `uri` health checks instead of the shared helper
- validate the repo automation and verification gates from a fresh isolated
  worktree, then replay the governed service live-apply path for the affected
  services with explicit evidence captured in-branch
- update ADR 0371 and this workstream with the verified implementation/live
  status while leaving protected mainline release files for the merge step

## Planned Verification

- `python3 scripts/workstream_registry.py --write`
- `python3 scripts/sync_plane_agent_issues.py --workstream ws-0371-live-apply`
- focused verifier tests and targeted repo-validation commands
- governed live-apply replays for the affected services from this exact-main
  worktree with end-to-end health verification and receipts
- final handoff notes describing what is complete on-branch and what still waits
  for merge-to-`main`

## Merge Notes

- Do not bump `VERSION`, `changelog.md`, `README.md`, or `versions/stack.yaml`
  on this branch.
- If the branch proves ADR 0371 live-applied successfully, update only the
  ADR-local/workstream-local state here and leave shared integration truth for
  the final mainline step.

## 2026-04-11 Progress

- Closed the remaining hand-written verifier wrappers in
  `librechat_runtime/tasks/verify.yml`,
  `litellm_runtime/tasks/verify.yml`, and
  `repowise_runtime/tasks/verify.yml` by switching them to the shared
  `lv3.platform.common` `verify_service_health` include.
- Added stable service live-apply wrappers for `librechat`, `litellm`, and
  `repowise` under `playbooks/services/` and aligned the `repowise`
  deployment surface in `config/service-capability-catalog.json`.
- Repaired repo automation on this branch so the fresh-worktree generators no
  longer crash on Python's stdlib `platform` module shadowing the repo's
  `platform/` package. The patched entrypoints are:
  `scripts/generate_platform_vars.py`,
  `scripts/generate_ops_portal.py`,
  `scripts/platform_manifest.py`,
  `scripts/generate_status_docs.py`, and
  `scripts/generate_diagrams.py`.
- Updated `config/health-probe-catalog.json` so `librechat` and `neko` use the
  current nested `uptime_kuma.monitor` contract required by
  `scripts/uptime_contract.py`.

## Validation Completed

- `ansible-playbook -i inventory/hosts.yml playbooks/librechat.yml --syntax-check`
- `ansible-playbook -i inventory/hosts.yml playbooks/litellm.yml --syntax-check`
- `ansible-playbook -i inventory/hosts.yml playbooks/repowise.yml --syntax-check`
- `ansible-playbook -i inventory/hosts.yml playbooks/services/librechat.yml --syntax-check`
- `ansible-playbook -i inventory/hosts.yml playbooks/services/litellm.yml --syntax-check`
- `ansible-playbook -i inventory/hosts.yml playbooks/services/repowise.yml --syntax-check`
- `uv run --with pytest --with pyyaml python -m pytest -q tests/test_service_live_apply_wrappers.py`
- `./scripts/validate_repo.sh workstream-surfaces`
- `./scripts/validate_repo.sh health-probes`
- `uv run --with pyyaml python3 scripts/generate_discovery_artifacts.py --check`
- `git diff --check`

## Governed Path Findings

- `make live-apply-service service=librechat env=production` originally failed
  in preflight because `config/workflow-catalog.json` referenced local receipt
  scaffolds that did not exist in a fresh worktree. Those ignored local receipt
  paths were materialized so the governed path could progress.
- The governed path still does not reach the service replay on this branch
  because of unrelated `origin/main` automation drift:
  - `make generate-ops-portal` fails with
    `subdomain 'agents.example.com' requires edge_oidc but has no repo-managed NGINX route`
  - `make check-canonical-truth` fails because the active workstream
    `ws-0377-repo-intake-subdomain` has an empty `adr` field in
    `workstreams.yaml`

## Live-Apply Attempt And Blocker

- Because the governed `make` path was blocked by unrelated repo automation
  defects, the documented scoped-runner path was used for the first affected
  service:
  `./scripts/run_with_namespace.sh uv run --with pyyaml python ./scripts/ansible_scope_runner.py run --inventory ./inventory/hosts.yml --playbook ./playbooks/services/litellm.yml --env production -- --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/bootstrap.id_ed25519 -e proxmox_guest_ssh_connection_mode=proxmox_host_jump`
- The scoped `litellm` replay did not reach the refactored verify task. It
  entered `lv3.platform.proxmox_network`, rendered host interfaces, executed
  `ifreload` on `proxmox-host`, and then failed at
  `Wait for SSH after network reload`.
- The failure was recorded at `2026-04-11T21:29:04Z` with:
  `timed out waiting for ping module test ... ssh: connect to host 100.64.0.1 port 22: Operation timed out`
- Independent recovery probes from the worktree at
  `2026-04-11T21:30:06Z`, `21:30:36Z`, `21:31:06Z`, `21:31:36Z`, and
  `21:32:06Z` also timed out against `ops@100.64.0.1`, so the host was still
  unreachable over the canonical Tailscale management path when work stopped.
- No `repowise` or `librechat` live replay was attempted after that point.

## Remaining Work After Host Recovery

- Restore `proxmox-host` reachability on `100.64.0.1` and confirm platform
  health before any further replay.
- Re-run the scoped service wrappers in this order:
  `litellm`, `repowise`, `librechat`.
- After each replay, capture direct health verification for the service-local
  endpoint and the public edge endpoint where applicable.
- Re-evaluate whether the unrelated `generate-ops-portal` and
  `check-canonical-truth` failures should be fixed on `main` before the final
  merge-to-main replay.
- Only after a clean latest-main replay should shared integration files and the
  final platform-version truth be updated.
