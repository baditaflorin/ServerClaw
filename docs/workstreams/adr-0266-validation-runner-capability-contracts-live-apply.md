# Workstream ADR 0266: Validation Runner Capability Contracts Live Apply

- ADR: [ADR 0266](../adr/0266-validation-runner-capability-contracts-and-environment-attestation.md)
- Title: Make validation runners declare capability contracts and emit per-run environment attestations
- Status: ready_for_merge
- Implemented In Repo Version: 0.177.88
- Live Applied In Platform Version: 0.130.60
- Implemented On: 2026-03-30
- Live Applied On: 2026-03-30
- Branch: `codex/ws-0266-main-integration-r3`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0266-main-integration-r2`
- Owner: codex
- Depends On: `adr-0082-remote-build-gateway`, `adr-0083-docker-check-runner`, `adr-0087-validation-gate`, `adr-0156-agent-session-workspace-isolation`, `adr-0227-bounded-command-execution-via-systemd-run-and-approved-wrappers`
- Conflicts With: none
- Shared Surfaces: `workstreams.yaml`, `docs/adr/0266-validation-runner-capability-contracts-and-environment-attestation.md`, `docs/workstreams/adr-0266-validation-runner-capability-contracts-live-apply.md`, `docs/adr/.index.yaml`, `README.md`, `RELEASE.md`, `VERSION`, `changelog.md`, `versions/stack.yaml`, `docs/release-notes/README.md`, `docs/release-notes/0.177.88.md`, `build/platform-manifest.json`, `.config-locations.yaml`, `config/build-server.json`, `config/check-runner-manifest.json`, `config/validation-gate.json`, `config/validation-runner-contracts.json`, `docs/schema/validation-runner-contracts.schema.json`, `scripts/gate_status.py`, `scripts/parallel_check.py`, `scripts/policy_checks.py`, `scripts/remote_exec.sh`, `scripts/run_gate.py`, `scripts/validate_repository_data_models.py`, `scripts/validation_runner_contracts.py`, `scripts/canonical_truth.py`, `scripts/release_manager.py`, `config/windmill/scripts/post-merge-gate.py`, `config/windmill/scripts/gate-status.py`, `collections/ansible_collections/lv3/platform/roles/openbao_runtime/defaults/main.yml`, `collections/ansible_collections/lv3/platform/roles/openbao_runtime/tasks/main.yml`, `collections/ansible_collections/lv3/platform/roles/windmill_runtime/tasks/main.yml`, `collections/ansible_collections/lv3/platform/roles/windmill_runtime/tasks/verify.yml`, `collections/ansible_collections/lv3/platform/roles/windmill_runtime/tasks/wait_for_workers.yml`, `policy/conftest/repository.rego`, `platform/policy/toolchain.py`, `docs/diagrams/agent-coordination-map.excalidraw`, `docs/runbooks/configure-openbao.md`, `docs/runbooks/remote-build-gateway.md`, `docs/runbooks/validation-gate.md`, `receipts/live-applies/2026-03-29-adr-0266-validation-runner-capability-contracts-live-apply.json`, `receipts/live-applies/2026-03-29-adr-0266-validation-runner-capability-contracts-mainline-live-apply.json`, `receipts/live-applies/evidence/2026-03-29-adr-0266-*`, `tests/test_canonical_truth.py`, `tests/test_parallel_check.py`, `tests/test_policy_checks.py`, `tests/test_post_merge_gate.py`, `tests/test_release_manager.py`, `tests/test_remote_exec.py`, `tests/test_validation_gate.py`, `tests/test_validation_gate_windmill.py`, `tests/test_validation_runner_contracts.py`, `tests/test_windmill_operator_admin_app.py`

## Scope

- add one canonical validation-runner contract catalog that declares runner identity, architecture, tooling, network reachability class, scratch cleanup guarantees, and supported validation lanes
- make the build-server gateway, manifest-backed validation gate, and worker post-merge replay emit a per-run environment attestation alongside runner identity
- fail closed as `runner_unavailable` when a requested validation lane cannot run on the attested runner instead of misreporting a repository-content failure
- verify the remote build-server path, controller-local fallback path, and worker post-merge path end to end and record durable evidence in-repo

## Expected Repo Surfaces

- `workstreams.yaml`
- `docs/adr/0266-validation-runner-capability-contracts-and-environment-attestation.md`
- `docs/workstreams/adr-0266-validation-runner-capability-contracts-live-apply.md`
- `docs/adr/.index.yaml`
- `README.md`
- `RELEASE.md`
- `VERSION`
- `changelog.md`
- `versions/stack.yaml`
- `docs/release-notes/README.md`
- `docs/release-notes/0.177.88.md`
- `build/platform-manifest.json`
- `.config-locations.yaml`
- `config/build-server.json`
- `config/check-runner-manifest.json`
- `config/validation-gate.json`
- `config/validation-runner-contracts.json`
- `docs/schema/validation-runner-contracts.schema.json`
- `scripts/canonical_truth.py`
- `scripts/gate_status.py`
- `scripts/parallel_check.py`
- `scripts/policy_checks.py`
- `scripts/release_manager.py`
- `scripts/remote_exec.sh`
- `scripts/run_gate.py`
- `scripts/validate_repository_data_models.py`
- `scripts/validation_runner_contracts.py`
- `config/windmill/scripts/post-merge-gate.py`
- `config/windmill/scripts/gate-status.py`
- `collections/ansible_collections/lv3/platform/roles/openbao_runtime/defaults/main.yml`
- `collections/ansible_collections/lv3/platform/roles/openbao_runtime/tasks/main.yml`
- `collections/ansible_collections/lv3/platform/roles/windmill_runtime/tasks/main.yml`
- `collections/ansible_collections/lv3/platform/roles/windmill_runtime/tasks/verify.yml`
- `collections/ansible_collections/lv3/platform/roles/windmill_runtime/tasks/wait_for_workers.yml`
- `policy/conftest/repository.rego`
- `platform/policy/toolchain.py`
- `docs/diagrams/agent-coordination-map.excalidraw`
- `docs/runbooks/configure-openbao.md`
- `docs/runbooks/remote-build-gateway.md`
- `docs/runbooks/validation-gate.md`
- `receipts/live-applies/2026-03-29-adr-0266-validation-runner-capability-contracts-live-apply.json`
- `receipts/live-applies/2026-03-29-adr-0266-validation-runner-capability-contracts-mainline-live-apply.json`
- `receipts/live-applies/evidence/2026-03-29-adr-0266-*`
- `tests/test_canonical_truth.py`
- `tests/test_parallel_check.py`
- `tests/test_policy_checks.py`
- `tests/test_post_merge_gate.py`
- `tests/test_release_manager.py`
- `tests/test_remote_exec.py`
- `tests/test_validation_gate.py`
- `tests/test_validation_gate_windmill.py`
- `tests/test_validation_runner_contracts.py`
- `tests/test_windmill_operator_admin_app.py`

## Expected Live Surfaces

- `make remote-validate` records a status payload that names the build-server runner, its declared contract, and its attested environment facts for the executed validation slice
- `make pre-push-gate` records the same runner identity and attestation data whether the gate runs on the build server or falls back locally
- the worker-side `post_merge_gate` replay records a runner identity and attestation for the live worker checkout
- an unavailable or mismatched runner fails as `runner_unavailable` before content checks are misreported as repository defects

## Verification Plan

- targeted pytest coverage for the new contract loader, remote gateway, gate orchestration, worker replay, and policy context
- `./scripts/validate_repo.sh data-models policy`
- `./scripts/validate_repo.sh workstream-surfaces agent-standards`
- build-server path verification with `make check-build-server` and `make remote-validate`
- local fallback verification by forcing the remote path unavailable and confirming the recorded runner/attestation changes
- worker post-merge verification from the live runtime checkout after the change lands on `main`

## Branch-Local Verification

- `make check-build-server` passed on 2026-03-29 from commit `d9a17397`, verified SSH access to `ops@10.10.10.30`, a session-scoped workspace under `/home/ops/builds/proxmox_florin_server/.lv3-session-workspaces/ws-0266-validation-runner-capability-contracts-8be65b3b1f/repo`, and immutable snapshot upload via `receipts/live-applies/evidence/2026-03-29-adr-0266-check-build-server.txt`
- `make remote-validate` passed on 2026-03-29 from commit `d9a17397` with runner `build-server-validation`; the recorded status payload shows `x86_64` attestation plus all six build-server validation lanes passing in `receipts/live-applies/evidence/2026-03-29-adr-0266-remote-validate-summary.txt`
- `make pre-push-gate` passed on 2026-03-29 from commit `d9a17397` with runner `build-server-validation`; the recorded gate payload shows 15/15 checks passing in `receipts/live-applies/evidence/2026-03-29-adr-0266-pre-push-summary.txt`
- `make gate-status` now reports both the remote-validate and pre-push payloads with the attested runner id; see `receipts/live-applies/evidence/2026-03-29-adr-0266-gate-status.txt`

## Mainline Verification

- `git fetch origin main` now shows the latest mainline release cut at `f965aa3101fa2cd2260a8e6fda165f366365ed80` (`2026-03-30T01:45:22+03:00`, repository version `0.177.90`); ADR 0266 itself first became true from the earlier exact-main replay source `020c5f5ad`, whose code-carrying tree was `42fcf4c04` before the evidence-only branch-head refresh
- `./scripts/validate_repo.sh generated-docs data-models policy workstream-surfaces agent-standards` passed on the synchronized mainline tree, the targeted pytest sweep returned `88 passed in 129.31s`, and `make syntax-check-openbao` passed before the final metadata closeout
- `make check-build-server` passed for the exact-main snapshot upload, `make remote-validate` passed at `2026-03-29T22:07:09.413886+00:00`, `make pre-push-gate` passed at `2026-03-29T22:10:48.423912+00:00`, and `make gate-status` recorded both build-server proofs from the same mainline tree
- the durable runtime replay for the supporting OpenBao changes completed in `receipts/live-applies/evidence/2026-03-29-adr-0266-mainline-converge-openbao-rerun-2.txt` with `docker-runtime-lv3 : ok=140 changed=9 failed=0` and `postgres-lv3 : ok=43 changed=0 failed=0`
- `/srv/proxmox_florin_server` on `docker-runtime-lv3` is a mirrored runtime checkout, not a git clone, so the final worker proof synced the exact-main `config/windmill/scripts/gate-status.py` wrapper directly, refreshed the mirrored generated artifacts, reran `python3 /srv/proxmox_florin_server/config/windmill/scripts/gate-status.py --repo-path /srv/proxmox_florin_server`, and then reran `python3 /srv/proxmox_florin_server/config/windmill/scripts/post-merge-gate.py --repo-path /srv/proxmox_florin_server`; the worker now reports `post_merge_run.executed_at=2026-03-29T22:24:37.498783+00:00` and a passing bounded local fallback in `receipts/live-applies/evidence/2026-03-29-adr-0266-mainline-post-merge-last-run.txt`
- remaining merge-to-main work: none; `origin/main` already carries the validated ADR 0266 changeset and this closeout only updates shared metadata, receipts, and platform truth to match that verified state
